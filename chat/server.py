"""Serwer czatu agentow: hello/auth, backlog/resync, echo po nicku,
wzmianki, grupy adresowe, oferty taskow. Jedyny modul z asyncio/websockets.

Kluczowe niezmienniki (review tercetu, wiazace):
  a) generation przypieta do SOCKETU przy hello — kazda kolejna ramka z
     tego samego polaczenia jest mutowana TA generacja, nigdy
     frame.get("generation"). Po takeover (nowe hello tego samego nicka
     z innym instance_id) serwer zamyka stare sockety NATYCHMIAST (przy
     samym hello, nie dopiero przy ich kolejnej ramce); per-ramkowy check
     generacji zostaje jako druga linia obrony.
  b) snapshot niesie {"queue": ..., "registry": ..., "offers": ...} —
     restart odtwarza je i DODATKOWO replay'uje kazdy event > snapshot_seq.
     Replay jest RESULT-BASED (nie re-execution): kazdy event mutacji taska
     niesie serwerowy wynik (task_state) i jest APLIKOWANY wprost przez
     queue.apply_replayed — bez ponownej walidacji WIP/lease/CAS i bez
     zaleznosci od biezacej polityki (wip_limit/lease_ttl moga sie zmienic
     miedzy restartami; lease_until odtwarzany HISTORYCZNY). Expiry to tez
     trwaly event (task_expired), nie fyi. resync_required robi swiezy,
     atomowy snapshot() PRZED odpowiedzia, zeby zwracany snapshot_seq
     zawsze etykietowal dokladnie ten state.
  c) snapshot po kazdych SNAPSHOT_EVERY=100 eventach (licznik zasiany przy
     starcie liczba eventow juz w logu po snapshot_seq) ORAZ przy stop()
     (w tym Ctrl+C/SIGTERM — patrz main()/finally).
  d) activation_id kotwiczony w TRWALYM evencie: seq jest przewidywalny
     (log.last_seq+1, event loop jednowatkowy), wiec activation_id jest
     wliczany do ramki PRZED jej zapisem — trwaly event ma i seq, i
     activation_id. Cache pending ofert (_offer_cache) trzyma PELNY event
     (z seq) i przezywa restart: snapshot ("offers") + replay (task_offer =
     pending, offer_resolved = rozstrzygnieta). Retry TEJ SAMEJ proby (ten
     sam nick+task+wersja) zwraca ten sam event bez nowego zapisu; po
     rozstrzygnieciu (timeout/claim/ewikcja) appendujemy TRWALY offer_resolved
     i ewikujemy z cache, wiec kolejna proba (po pelnym okrazeniu idle) to
     NOWY event/id. Reinsert do idle po timeoucie tylko dla nicka z ZYWYM
     socketem (brak ducha w idle).
  e) grupy adresowe ($group) — patrz protocol.parse_groups; nieznana
     grupa = error do nadawcy, zero publikacji do niej (inne wzmianki w
     tej samej ramce dzialaja normalnie). role/groups faktycznie przypisane
     nickowi pochodza WYLACZNIE z configu serwera (Registry.role_of/
     groups_of) — to co klient deklaruje w hello jest tylko walidowane.
  f) wejscie klienckie walidowane zanim dotknie kolejki/rejestru; zaden
     pojedynczy zly frame (w tym JSON-skalar/lista zamiast obiektu) nie
     moze zabic handlera ani serwera.
  g) trwalosc przed publikacja: chat/task_*/hello najpierw append (dostaje
     seq), potem dostarczenie/odpowiedz. Pola seq/generation/groups/role/
     from sa nadpisywane przez serwer na KAZDEJ ramce klienta przed
     zapisem — nigdy nie przechodza z ramki do logu/odbiorcow.
"""
import asyncio
import copy
import hashlib
import json
import os
import time
from pathlib import Path

import websockets

from . import protocol
from .identity import AuthError, Registry
from .store import EventLog
from .tasks import TaskError, TaskQueue

SNAPSHOT_EVERY = 100  # polityka snapshotow: co N eventow (+ zawsze przy stop())

_TASK_REQUIRED_FIELDS = {
    "task_new": ("card", "command_id"),
    "task_claim": ("task_id", "command_id", "expected_task_version"),
    "task_done": ("task_id", "command_id", "expected_task_version"),
    "task_blocked": ("task_id", "command_id", "expected_task_version"),
    "review_changes": ("task_id", "command_id", "expected_task_version"),
    "task_approve": ("task_id", "command_id", "expected_task_version"),
    "task_unblock": ("task_id", "command_id", "expected_task_version"),
}

# Eventy niosace SERWEROWY WYNIK mutacji (task_state) — replay stosuje ten
# stan WPROST przez queue.apply_replayed (result-based), bez re-execution.
# task_expired to trwaly, server-generowany event (nie fyi): reopen po
# wygasnieciu lease jest tak samo odtwarzalny jak kazda inna mutacja.
_TASK_STATE_EVENTS = frozenset(_TASK_REQUIRED_FIELDS) | {"task_expired"}


class ChatServer:
    def __init__(self, data_dir, tokens, port, wip_limit=3,
                 lease_ttl=120.0, offer_timeout=5.0):
        self.port = port
        self.offer_timeout = offer_timeout
        self.log = EventLog(Path(data_dir))
        snap = self.log.load_snapshot()
        if snap:
            state, _snapshot_seq = snap
            self.queue = TaskQueue.restore(
                state.get("queue", {"next_id": 0, "tasks": []}),
                wip_limit=wip_limit, lease_ttl=lease_ttl)
            self.registry = Registry.restore(tokens, state.get("registry", {}))
            offers = state.get("offers", [])
        else:
            self.queue = TaskQueue(wip_limit=wip_limit, lease_ttl=lease_ttl)
            self.registry = Registry(tokens)
            offers = []
        self.conns = {}        # nick -> set[ws]
        self.roles = {}        # nick -> role
        self.groups = {}       # nick -> set[group] (przezywa reconnect, nie restart)
        self.idle = []         # nicki wyrobnic zglaszajacych idle (round-robin)
        # (3) trwaly lifecycle ofert: _offer_cache trzyma PELNY event task_offer
        # (z seq+activation_id) per (nick, task_id, version). Pending oferty sa
        # w snapshocie (odtwarzane z niego) i dodatkowo rekonstruowane z replay
        # (task_offer dodaje, offer_resolved usuwa).
        self._offer_cache = self._restore_offers(offers)  # (nick,task_id,ver) -> event
        self._offering = None
        self._server = None
        self._expiry_task = None
        # niezmiennik A: eventy > snapshot_seq NIGDY nie byly odtwarzane do
        # stanu — trwalosc byla teatrem. Replay stosuje te same mutacje
        # (queue/registry) co live, bez zadnych side-effectow sieciowych
        # (bez _send/_append — eventy juz sa na dysku).
        self._replay_events()
        # (A3) licznik snapshot-co-100 liczy DALEJ od tego, co juz jest w
        # logu po snapshot_seq — nie od zera (inaczej po restarcie trzeba by
        # 100 nowych eventow, zanim serwer w ogole rozwazy snapshot).
        self._events_since_snapshot = len(self.log.replay())

    def _replay_events(self):
        # Replay result-based: eventy > snapshot_seq odtwarzaja stan BEZ
        # re-execution i BEZ zaleznosci od biezacej polityki (wip_limit/
        # lease_ttl mogly sie zmienic miedzy restartami). Kazdy event mutacji
        # niesie serwerowy wynik (task_state) — apply_replayed wstawia go
        # wprost. Rejestr (hello) i lifecycle ofert (task_offer/offer_resolved)
        # odtwarzane osobno.
        for event in self.log.replay():
            etype = event.get("type")
            if etype == "hello":
                self.registry.replay_hello(event["from"], event["instance_id"])
            elif etype == "task_offer":
                key = (event["target"], event["task"]["id"], event["task"]["version"])
                self._offer_cache[key] = event  # pending: pelny event (z seq)
            elif etype == "offer_resolved":
                key = (event["nick"], event["task_id"], event["task_version"])
                self._offer_cache.pop(key, None)  # rozstrzygnieta = nie pending
            elif etype in _TASK_STATE_EVENTS:
                self.queue.apply_replayed(event["task_state"],
                                          event.get("command_id"),
                                          event.get("fingerprint"))
                if etype == "task_claim":
                    # (Runda 5 B / Runda 6) claim SAM JEST faktem resolution:
                    # usun pending offers dla (task_id, wersja-open) z
                    # odtwarzanego cache. Sciezka claim NIE appenduje juz
                    # offer_resolved (Runda 6) — replay MUSI wywiesc resolution z
                    # samego task_claim (dziala tez dla steal-claim, ktorego
                    # klucz cudzej oferty claimer nigdy by sam nie trafil).
                    # offer_resolved w logu pochodzi WYLACZNIE z timeoutu/ewikcji.
                    for key in self._pending_offer_keys_for(
                            event.get("task_id"), event.get("expected_task_version")):
                        self._offer_cache.pop(key, None)
            # chat/fyi/status/ok/error: bez mutacji stanu queue/registry

    # -- pending oferty (trwaly lifecycle) ---------------------------------
    @staticmethod
    def _restore_offers(offer_events):
        cache = {}
        for e in offer_events:
            key = (e["target"], e["task"]["id"], e["task"]["version"])
            cache[key] = e
        return cache

    def _dump_offers(self):
        return list(self._offer_cache.values())  # pelne eventy task_offer (z seq)

    # -- infrastruktura ----------------------------------------------------
    async def start(self):
        self._server = await websockets.serve(self._handler, "localhost", self.port)
        self._expiry_task = asyncio.ensure_future(self._expiry_loop())

    async def stop(self):
        for task in (self._expiry_task, self._offering):
            if task is None:
                continue
            if not task.done():
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._server.close()
        await self._server.wait_closed()
        self.snapshot()  # clean shutdown -> snapshot zawsze (polityka c)

    def snapshot(self):
        self.log.save_snapshot({"queue": self.queue.dump(),
                                 "registry": self.registry.dump(),
                                 "offers": self._dump_offers()})
        self._events_since_snapshot = 0

    def _append(self, frame):
        seq = self._append_durable(frame)
        self._maybe_snapshot()
        return seq

    def _append_durable(self, frame):
        # (Runda 5 A) trwaly append ROZDZIELONY od auto-snapshotu: seq
        # przydzielony i event NA DYSKU, ale snapshot jeszcze NIE odpalony.
        # Mutacje wymagajace domkniecia stanu MIEDZY (trwaly event) a
        # (ewentualny snapshot) — patrz _offer_event — wstawiaja swoj efekt PO
        # udanym appendzie, a PRZED snapshotem. Nieudany append (wyjatek z
        # log.append) rzuca zanim cokolwiek zmutujemy — brak dziury w numeracji
        # i brak przedwczesnej mutacji stanu zaleznego od trwalosci.
        seq = self.log.append(frame)
        self._events_since_snapshot += 1
        return seq

    def _maybe_snapshot(self):
        if self._events_since_snapshot >= SNAPSHOT_EVERY:
            self.snapshot()

    async def _expiry_loop(self):
        while True:
            await asyncio.sleep(1.0)
            self._reap_expired(time.time())

    def _reap_expired(self, now):
        # (1) expiry jest TRWALYM, replayowalnym eventem — nie fyi. Kazdy
        # reopen appenduje {type:"task_expired", task_id, task_state} niosacy
        # pelny stan taska po powrocie do open, zeby replay odtworzyl reopen
        # wprost (bez tego drugi claim po expire dawalby Conflict przy
        # restarcie — patrz apply_replayed).
        expired = self.queue.expire(now)
        for task in expired:
            self._append(protocol.make_frame(
                "task_expired", "server", time.time(),
                task_id=task["id"], task_state=task))
        if expired:
            self._trigger_offer()

    def _load_rules(self):
        path = self.log.dir / "rules.md"
        if not path.exists():
            return None, None
        text = path.read_text()
        return text, hashlib.sha256(text.encode("utf-8")).hexdigest()

    # -- dostarczanie ------------------------------------------------------
    async def _send(self, nick, payload):
        data = json.dumps(payload)
        for ws in list(self.conns.get(nick, ())):
            try:
                await ws.send(data)
            except websockets.exceptions.ConnectionClosed:
                pass

    async def _close_stale_sockets(self, nick):
        # niezmiennik C: wywolywane w momencie takeover (bump generacji przy
        # nowym hello) — zamyka KAZDY dotychczasowy socket tego nicka zanim
        # dolaczy nowy, zeby nic wiecej do nich nie trafilo (routing/_send).
        # (6) usuniecie z conns MUSI byc SYNCHRONICZNE — przed pierwszym await.
        # Inaczej rownolegly _send (np. broadcast humanowi) w oknie miedzy
        # await send a discard dostarczylby jeszcze staremu socketowi. Najpierw
        # wypinamy z routingu (synchronicznie), dopiero potem best-effort
        # error+close (na wypietych juz socketach — _send ich nie widzi).
        stale = list(self.conns.get(nick, ()))
        bucket = self.conns.get(nick)
        if bucket is not None:
            for old_ws in stale:
                bucket.discard(old_ws)
        for old_ws in stale:
            try:
                await old_ws.send(json.dumps(protocol.make_frame(
                    "error", "server", time.time(),
                    text="stale generation: ten socket zostal wyparty przez nowsze hello")))
            except websockets.exceptions.ConnectionClosed:
                pass
            try:
                await old_ws.close(code=4001, reason="takeover")
            except websockets.exceptions.ConnectionClosed:
                pass

    async def _publish_chat(self, event, mentions, groups_mentioned, unknown_groups):
        sender = event["from"]
        targets = set()
        if "all" in mentions:
            targets |= set(self.conns) - {sender}
        else:
            targets |= {n for n in mentions if n in self.conns} - {sender}
        for g in groups_mentioned:
            if g in unknown_groups:
                continue
            members = {n for n, gs in self.groups.items() if g in gs}
            targets |= (members & set(self.conns)) - {sender}
        targets |= {n for n, r in self.roles.items()
                    if r == "human" and n != sender and n in self.conns}
        for nick in targets:
            await self._send(nick, event)

    async def _handle_chat(self, frame, nick):
        text = frame.get("text", "")
        mentions = protocol.parse_mentions(text)
        groups_mentioned = protocol.parse_groups(text)
        known_groups = {g for gs in self.groups.values() for g in gs}
        unknown_groups = sorted(g for g in groups_mentioned if g not in known_groups)
        if unknown_groups:
            await self._send(nick, protocol.make_frame(
                "error", "server", time.time(),
                text=f"nieznana grupa: {', '.join(unknown_groups)}"))
        seq = self._append(frame)  # trwaly zapis PRZED publikacja (niezmiennik g)
        frame["seq"] = seq
        await self._publish_chat(frame, mentions, groups_mentioned, set(unknown_groups))

    # -- hello / auth --------------------------------------------------------
    @staticmethod
    def _validate_last_seq(value):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise AuthError(f"invalid last_seq: {value!r}")
        return value

    @staticmethod
    def _validate_groups(value):
        if value is None:
            return []
        if not isinstance(value, list) or not all(
                isinstance(g, str) and g for g in value):
            raise AuthError(f"invalid groups: {value!r}")
        return value

    @staticmethod
    def _validate_role(value):
        # (7) role deklarowana w hello jest tylko WALIDOWANA (przypisanie
        # pochodzi z configu serwera — niezmiennik e/H) — ale jesli podana,
        # musi byc NIEPUSTYM stringiem (AGENTS.md: typ + niepustosc). role=[]
        # oraz role="" to blad wejscia do nadawcy. (Runda 6 #4: "" przechodzil,
        # bo "" jest str — teraz jawnie odrzucony.)
        if value is not None and (not isinstance(value, str) or not value):
            raise AuthError(f"invalid role: {value!r}")
        return value

    # -- handler -----------------------------------------------------------
    async def _handler(self, ws):
        nick = None
        try:
            raw = await ws.recv()
            frame = json.loads(raw)
            if not isinstance(frame, dict):
                # niezmiennik E: skalar/lista jako JSON nie moze zabic
                # handlera przez .get() na nie-dict — error + jawne zamkniecie
                await ws.send(json.dumps(protocol.make_frame(
                    "error", "server", time.time(),
                    text="ramka musi byc obiektem JSON")))
                await ws.close(code=1008, reason="ramka musi byc obiektem JSON")
                return
            if frame.get("type") != "hello":
                await ws.send(json.dumps(protocol.make_frame(
                    "error", "server", time.time(), text="pierwsza ramka musi byc hello")))
                return
            # (Runda 5 C3) pierwsze hello przez WSPOLNY schemat (type/from/ts)
            # PRZED auth — dotad hello NIGDY nie przechodzilo przez
            # protocol.validate, wiec hello bez ts / z from=[] dostawalo ok i
            # bylo logowane (niestandardowy/niekompletny event). Gleboka
            # walidacja hello (instance_id/token/last_seq/groups/role) zostaje w
            # identity/serwerze ponizej.
            hello_err = protocol.validate(frame)
            if hello_err:
                await ws.send(json.dumps(protocol.make_frame(
                    "error", "server", time.time(), text=hello_err)))
                return
            nick_candidate = frame.get("from")
            # niezmiennik C: generacja SPRZED tego hello — potrzebna zeby
            # odroznic zwykly reconnect (ten sam instance_id, bez bumpa) od
            # faktycznego takeover (bump), zeby wiedziec czy stare sockety
            # trzeba zamknac natychmiast
            old_gen = (self.registry.generation_of(nick_candidate)
                       if isinstance(nick_candidate, str) else 0)
            try:
                last_seq = self._validate_last_seq(frame.get("last_seq"))
                # (7) kursor spoza logu (last_seq > serwerowy last_seq) to
                # jawny blad — klient nie mogl widziec eventow, ktorych serwer
                # nie ma; bez tego dostawalby ciche ok+pusty backlog.
                if last_seq > self.log.last_seq:
                    raise AuthError(
                        f"last_seq {last_seq} > serwerowy last_seq "
                        f"{self.log.last_seq}")
                # niezmiennik H: groups/role w hello sa TYLKO walidowane —
                # przypisanie faktyczne pochodzi WYLACZNIE z configu serwera
                # (registry.role_of/groups_of), nigdy z deklaracji klienta.
                self._validate_groups(frame.get("groups"))
                self._validate_role(frame.get("role"))
                generation = self.registry.hello(
                    frame.get("from"), frame.get("instance_id"), frame.get("token"))
            except AuthError as e:
                await ws.send(json.dumps(protocol.make_frame(
                    "error", "server", time.time(), text=str(e))))
                return
            nick = frame["from"]
            role = self.registry.role_of(nick)
            groups = self.registry.groups_of(nick)
            if generation != old_gen:
                # niezmiennik C: takeover — odetnij stare sockety TERAZ, nie
                # dopiero przy ich kolejnej (moze nigdy nie nadejsc) ramce
                await self._close_stale_sockets(nick)
            self.conns.setdefault(nick, set()).add(ws)
            self.roles[nick] = role
            self.groups[nick] = set(groups)
            # backlog liczony PRZED zalogowaniem WLASNEGO hello — inaczej
            # klient zawsze widzialby wlasna ramke hello w swoim backlogu i
            # "last_seq == biezacy cursor" po reconnnekcie nigdy by nie
            # dawalo pustego backlogu (por. test_reconnect_resumes_from_last_seq)
            backlog = self.log.events_after(last_seq)
            # niezmiennik A: KAZDA mutacja stanu (hello -> registry) jest
            # logowana PRZED odpowiedzia klientowi — bez tokenu (nie ma czego
            # ukrywac przy replay, ale sekret nie powinien nigdy trafic na
            # dysk); instance_id jest juz zwalidowany przez registry.hello.
            self._append(protocol.make_frame(
                "hello", nick, time.time(),
                instance_id=frame.get("instance_id"),
                groups=list(groups), role=role))
            rules_text, rules_hash = self._load_rules()
            extra = {}
            if rules_text is not None:
                extra["rules"] = rules_text
                extra["rules_hash"] = rules_hash
            if backlog is None:
                # niezmiennik B: resync spojny — snapshot_seq zwracany
                # klientowi musi etykietowac DOKLADNIE ten state, ktory
                # wysylamy. Bez swiezego, atomowego snapshotu tutaj,
                # self.log.snapshot_seq bylby STARA wartoscia (sprzed
                # mutacji, ktore juz sa w queue.dump()) — klient wznowilby
                # replay od stalej etykiety i zdublowal mutacje, ktore
                # `state` juz zawiera.
                self.snapshot()
                # (Runda 4 #4) wire resync state = DOKLADNIE persisted snapshot
                # state (queue + registry + offers), nie okrojony do queue.
                # Snapshot niesie offers (pending activations); gdyby resync
                # wysylal sam queue, klient z za starym kursorem nie odzyskalby
                # pending ofert po kompakcji.
                reply = protocol.make_frame(
                    "resync_required", "server", time.time(),
                    snapshot_seq=self.log.snapshot_seq,
                    state={"queue": self.queue.dump(),
                           "registry": self.registry.dump(),
                           "offers": self._dump_offers()},
                    generation=generation, **extra)
            else:
                reply = protocol.make_frame(
                    "ok", "server", time.time(),
                    generation=generation, backlog=backlog,
                    last_seq=self.log.last_seq, **extra)
            await ws.send(json.dumps(reply))
            async for raw in ws:
                try:
                    frame = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send(json.dumps(protocol.make_frame(
                        "error", "server", time.time(), text="invalid json")))
                    continue
                if not isinstance(frame, dict):
                    # niezmiennik E: w petli — error bez rozlaczania
                    await ws.send(json.dumps(protocol.make_frame(
                        "error", "server", time.time(),
                        text="ramka musi byc obiektem JSON")))
                    continue
                try:
                    stop = await self._on_frame(frame, nick, generation, ws)
                except Exception as e:  # ostatnia linia obrony (niezmiennik f):
                    # zaden pojedynczy blad ramki nie moze zabic serwera
                    await ws.send(json.dumps(protocol.make_frame(
                        "error", "server", time.time(),
                        command_id=frame.get("command_id"),
                        text=f"internal error: {type(e).__name__}: {e}")))
                    stop = False
                if stop:
                    break
        except (websockets.exceptions.ConnectionClosed, json.JSONDecodeError):
            pass
        finally:
            if nick and ws in self.conns.get(nick, set()):
                self.conns[nick].discard(ws)
                # (F5) nick bez zadnego zostalego socketu wypada z self.idle —
                # inaczej oferta poszlaby w prozne (nikt jej nigdy nie odbierze)
                if not self.conns[nick] and nick in self.idle:
                    self.idle.remove(nick)

    async def _on_frame(self, frame, nick, sock_gen, ws):
        # niezmiennik a): generation przypieta do SOCKETU, nie frame.get(...)
        if self.registry.generation_of(nick) != sock_gen:
            await ws.send(json.dumps(protocol.make_frame(
                "error", "server", time.time(),
                command_id=frame.get("command_id"),
                text="stale generation: ten socket zostal wyparty przez nowsze hello")))
            return True  # zamknij petle tego (juz nieaktualnego) polaczenia
        err = protocol.validate(frame)
        if err:
            # (Runda 4 #5) walidacja schematu per typ wyprzedza _on_task_frame,
            # wiec error MUSI niesc command_id (dla task_*), by klient mogl
            # skorelowac odrzucenie (None dla typow bez command_id — nieszkodliwe).
            await ws.send(json.dumps(protocol.make_frame(
                "error", "server", time.time(),
                command_id=frame.get("command_id"), text=err)))
            return False
        # niezmiennik D: pola autorytatywne (seq/generation/groups/role) nadaje
        # WYLACZNIE serwer — kazda ramka klienta jest tu oczyszczana zanim
        # dotknie logu/kolejki/odbiorcow, niezaleznie od typu ramki
        for field in ("seq", "generation", "groups", "role"):
            frame.pop(field, None)
        frame["from"] = nick  # tozsamosc z hello, nie z ramki (pole autorytatywne)
        ftype = frame["type"]
        if ftype == "chat":
            await self._handle_chat(frame, nick)
        elif ftype == "fyi":
            self._append(frame)
        elif ftype == "status":
            self._append(frame)
            if frame.get("state") == "idle" and nick not in self.idle:
                self.idle.append(nick)
                self._trigger_offer()
        elif ftype in _TASK_REQUIRED_FIELDS:
            await self._on_task_frame(frame, nick, sock_gen, ws)
        else:
            await ws.send(json.dumps(protocol.make_frame(
                "error", "server", time.time(),
                text=f"nieoczekiwany typ ramki od klienta: {ftype}")))
        return False

    _TASK_OP = {
        "task_claim": "claim", "task_done": "to_review",
        "task_blocked": "block", "task_unblock": "unblock",
    }

    def _apply_task_op(self, queue, ftype, frame, nick, sock_gen, now):
        # Wykonuje mutacje na PODANEJ kolejce (klon transakcji) — zwraca
        # serwerowy result (task_state) i ustawia queue.last_dedup_hit.
        # Walidacja (Conflict/StaleGeneration/WIP/TaskError) rzuca STAD, zanim
        # cokolwiek trwalego dotknie live queue/dedup.
        if ftype == "task_new":
            return queue.add(frame["card"], frame["command_id"], now)
        if ftype == "task_claim":
            return queue.claim(frame["task_id"], nick, sock_gen,
                               frame["command_id"], frame["expected_task_version"], now)
        if ftype == "task_done":
            return queue.to_review(frame["task_id"], nick, sock_gen,
                                  frame["command_id"], frame["expected_task_version"], now)
        if ftype == "task_blocked":
            return queue.block(frame["task_id"], nick, sock_gen,
                              frame["command_id"], frame["expected_task_version"], now)
        if ftype == "review_changes":  # od matki, bez ownera
            return queue.request_changes(frame["task_id"], frame["command_id"],
                                        frame["expected_task_version"], now)
        if ftype == "task_approve":  # (8) B1: approve = KTOKOLWIEK POZA assignee
            return queue.approve(frame["task_id"], nick, frame["command_id"],
                                frame["expected_task_version"], now)
        return queue.unblock(frame["task_id"], nick, sock_gen,  # task_unblock
                            frame["command_id"], frame["expected_task_version"], now)

    def _peek_cached(self, ftype, frame, nick, sock_gen):
        # (Runda 6 #1) podglad dedup na ZYWEJ kolejce PRZED deepcopy — retry to
        # najczestsza sciezka i nie placi kosztu kopii calej kolejki. Fingerprint
        # budowany TYM SAMYM helperem co mutacja (dedup_fingerprint), wiec
        # trafienie tu == trafienie w klonie. Zle wejscie (np. nieserializowalna
        # karta) -> None: pelna sciezka klon-mutacja zwaliduje i zglosi blad.
        try:
            if ftype == "task_new":
                fp = self.queue.dedup_fingerprint("add", card=frame["card"])
            elif ftype == "review_changes":
                fp = self.queue.dedup_fingerprint(
                    "request_changes", task_id=frame["task_id"],
                    expected_version=frame["expected_task_version"])
            elif ftype == "task_approve":
                fp = self.queue.dedup_fingerprint(
                    "approve", task_id=frame["task_id"], nick=nick,
                    expected_version=frame["expected_task_version"])
            else:
                fp = self.queue.dedup_fingerprint(
                    self._TASK_OP[ftype], task_id=frame["task_id"], nick=nick,
                    generation=sock_gen, expected_version=frame["expected_task_version"])
        except TaskError:
            return None
        return self.queue.peek_dedup(frame["command_id"], fp)

    async def _on_task_frame(self, frame, nick, sock_gen, ws):
        """Transakcyjne, event-first przetwarzanie ramek task_*.

        (Runda 6 #1) PROVISIONAL-THEN-COMMIT: cache-hit (retry) jest
        short-circuitowany peek_dedup-em na ZYWEJ kolejce PRZED deepcopy; realna
        mutacja idzie na KLONIE (walidacja Conflict/StaleGeneration/WIP + serwerowy
        result), potem durable append, i DOPIERO po udanym appendzie klon staje
        sie live (swap). Nieudany append (OSError) => live queue i dedup
        NIETKNIETE, retry dziala normalnie (komenda nie zostaje 'zjedzona' przez
        dedup cache-hit bez trwalego faktu). Crash miedzy append a swap odtworzy
        fakt z eventu przy replay (jednowatkowy event loop = crash-safe).
        Deepcopy-per-mutacja to SWIADOMY trade-off dla skali B1 (dziesiatki
        taskow) — do rewizji przy setkach taskow (clone()/undo-log); YAGNI teraz.
        """
        now = time.time()
        ftype = frame["type"]
        command_id = frame.get("command_id")
        missing = [f for f in _TASK_REQUIRED_FIELDS[ftype] if frame.get(f) is None]
        if missing:
            await ws.send(json.dumps(protocol.make_frame(
                "error", "server", now, command_id=command_id,
                text=f"{ftype}: brakujace pola {missing}")))
            return
        # (Runda 4 #1) cache-hit = ODPOWIEDZ, nie fakt: bez deepcopy, appendu,
        # swapu ani side-effectow (offer/idle/notify).
        cached = self._peek_cached(ftype, frame, nick, sock_gen)
        if cached is not None:
            await ws.send(json.dumps(protocol.make_frame(
                "ok", "server", now, command_id=command_id, task=cached)))
            return
        trial = copy.deepcopy(self.queue)
        try:
            result = self._apply_task_op(trial, ftype, frame, nick, sock_gen, now)
        except TaskError as e:  # Conflict/StaleGeneration sa jego podklasami
            await ws.send(json.dumps(protocol.make_frame(
                "error", "server", now, command_id=command_id,
                text=f"{type(e).__name__}: {e}")))
            return
        if trial.last_dedup_hit:
            # fallback: peek nie zlapal (teoretyczny rozjazd fingerprintu) — klon
            # jest autorytatywny: cache-hit => bez appendu i bez swapu.
            await ws.send(json.dumps(protocol.make_frame(
                "ok", "server", now, command_id=command_id, task=result)))
            return
        # (2) trwaly event result-based: PELNY stan taska po mutacji (task_state)
        # + fingerprint dedup — replay stosuje stan WPROST przez apply_replayed.
        # durable NAJPIERW (bez snapshotu); rzuca ZANIM swap -> live+dedup nietkniete.
        self._append_durable({**frame, "task_state": result,
                              "fingerprint": trial.fingerprint_for(frame["command_id"])})
        self.queue = trial  # commit: klon (z mutacja + wpisem dedup) staje sie live
        if ftype == "task_new":
            self._trigger_offer()
        elif ftype == "task_claim":
            if nick in self.idle:
                self.idle.remove(nick)
            # (Runda 6 #2) ATOMOWA sekcja claim: task_claim JUZ durable (bez
            # snapshotu), teraz USUN wszystkie matching pending offers z cache —
            # BEZ osobnego offer_resolved (udany claim SAM jest trwalym faktem
            # resolution; replay pop-uje je z task_claim — Runda 5 B; offer_resolved
            # zostaje WYLACZNIE dla timeoutow/ewikcji). Jeden _maybe_snapshot
            # ponizej: bez tego auto-snapshot na granicy #100 kompaktowalby
            # task_claim ZANIM resolution zajdzie -> snapshot task=claimed z
            # offers=[pending] -> restart niespojny.
            self._drop_offers_for_task(
                frame["task_id"], frame["expected_task_version"])
        self._maybe_snapshot()
        await ws.send(json.dumps(protocol.make_frame(
            "ok", "server", now, command_id=command_id, task=result)))
        if ftype == "review_changes":
            await self._send(result["assignee"], protocol.make_frame(
                "review_changes", "server", now, task=result))

    # -- oferty (round-robin + timeout) -------------------------------------
    def _offer_activation_id(self, nick, task):
        return self._offer_event(nick, task)["activation_id"]

    def _offer_event(self, nick, task):
        # niezmiennik d)/F1: activation_id kotwiczony w TRWALYM evencie —
        # event NA DYSKU musi sam zawierac activation_id (i seq). Seq
        # przydzielany przez log.append() jest deterministyczny (petla
        # asyncio jednowatkowa, wiec kolejny append dostanie DOKLADNIE
        # przewidywany numer) — liczymy go z gory, zeby moc wlozyc
        # activation_id do ramki PRZED jej zapisem, zamiast dopisywac
        # cos do juz zapisanej linii (store.py nie pozwala na to).
        # Retry TEJ SAMEJ proby (ten sam nick+task_id+wersja taska) zwraca
        # ten sam event BEZ nowego zapisu; zmiana ktoregokolwiek pola to
        # nowa proba -> nowy event. (4) cache trzyma PELNY event (z seq),
        # zeby _offer_loop wyslal klientowi dokladnie ten trwaly event.
        key = (nick, task["id"], task["version"])
        cached = self._offer_cache.get(key)
        if cached is not None:
            return cached
        predicted_seq = self.log.last_seq + 1
        activation_id = f"{nick}:{predicted_seq}"
        frame = protocol.make_frame(
            "task_offer", "server", time.time(), task=task, target=nick,
            activation_id=activation_id)
        # (Runda 5 A) DURABILITY-BEFORE-PUBLICATION: trwaly append NAJPIERW.
        # Gdy append rzuci (np. OSError/dysk pelny), _offer_cache pozostaje
        # NIETKNIETY — a to cache steruje publikacja w _offer_loop, wiec zaden
        # niedurable offer nie moze pojsc do klienta ani zwrocic sie jako cached
        # przy kolejnej probie. Dopiero PO udanym, trwalym appendzie domykamy
        # stan (offer -> cache), a snapshot (dumpuje _dump_offers) odpalamy na
        # KONCU: oferta jest juz w cache, wiec auto-snapshot #100 ja obejmuje
        # (utrzymuje fix Rundy 4 #2 — pending offer przezywa kompakcje). Seq
        # przewidywalny (jednowatkowy event loop), append tylko potwierdza numer.
        seq = self._append_durable(frame)
        assert seq == predicted_seq  # jednowatkowy event loop — brak wyscigu
        stored = {**frame, "seq": seq}  # dokladnie ten trwaly event (z seq)
        self._offer_cache[key] = stored
        self._maybe_snapshot()
        return stored

    def _pending_offer_keys_for(self, task_id, task_version):
        # (Runda 5 B) wszystkie klucze pending ofert dla danego (task_id,
        # wersja) niezaleznie od targetu. Zwraca LISTE (kopie) — wolajacy
        # mutuje _offer_cache w petli.
        return [k for k in self._offer_cache
                if k[1] == task_id and k[2] == task_version]

    def _drop_offers_for_task(self, task_id, task_version):
        # (Runda 6) udany claim SAM jest trwalym faktem resolution (task_claim
        # event; replay pop-uje WSZYSTKIE matching offers dla (task_id, wersja-
        # open) niezaleznie od targetu — Runda 5 B, wiec steal-claim gammy tez
        # czysci oferte bety). Sciezka claim wiec tylko USUWA pending offers z
        # cache live, BEZ osobnego offer_resolved (bylby redundantny audyt, a
        # jego durable append w petli przy wielu ofertach wymuszalby snapshoty w
        # srodku transakcji). offer_resolved zostaje WYLACZNIE dla timeoutow/
        # ewikcji (_offer_loop), gdzie NIE ma task_claim jako durable faktu.
        for key in self._pending_offer_keys_for(task_id, task_version):
            self._offer_cache.pop(key, None)

    def _resolve_offer(self, nick, task_id, task_version, outcome):
        # (3) rozstrzygniecie pending oferty przez TIMEOUT/EWIKCJE (_offer_loop)
        # appenduje TRWALY event offer_resolved — dla tych sciezek to JEDYNY
        # durable fakt resolution (nie ma task_claim). Sukces claim NIE idzie
        # tedy (patrz _drop_offers_for_task). Idempotentne: tylko jesli pending.
        key = (nick, task_id, task_version)
        if key not in self._offer_cache:
            return
        self._offer_cache.pop(key, None)
        self._append(protocol.make_frame(
            "offer_resolved", "server", time.time(),
            nick=nick, task_id=task_id, task_version=task_version,
            outcome=outcome))

    def _trigger_offer(self):
        if self._offering is None or self._offering.done():
            self._offering = asyncio.ensure_future(self._offer_loop())

    async def _offer_loop(self):
        while True:
            task = self.queue.offerable()
            if task is None or not self.idle:
                return
            nick = self.idle.pop(0)
            # (4) wysylamy klientowi DOKLADNIE trwaly event (z seq), nie
            # okrojona ramke — odbiorca widzi seq == seq zapisanego eventu.
            offer_event = self._offer_event(nick, task)
            await self._send(nick, offer_event)
            await asyncio.sleep(self.offer_timeout)
            fresh = self.queue.get(task["id"])
            # (F4) sprawdzamy KTO faktycznie dostal taska, nie tylko czy
            # przestal byc "open" — inny klient mogl go ukrasc bezposrednim
            # task_claim (poza mechanizmem ofert) w trakcie sleep().
            # (3) proba jest ROZSTRZYGNIETA — trwaly offer_resolved (i ewikcja
            # z cache), zeby PONOWNA oferta tego samego taska/wersji temu
            # samemu nickowi (po pelnym okrazeniu idle) byla NOWA proba/event.
            outcome = "claimed" if fresh["assignee"] == nick else "timeout"
            self._resolve_offer(nick, task["id"], task["version"], outcome)
            if fresh["assignee"] != nick:
                # (5) reinsert do idle TYLKO gdy nick ma zywy socket — inaczej
                # rozlaczony w oknie oferty zostawialby "ducha" w idle i kolejna
                # oferta szlaby w prozne (nikt jej nie odbierze).
                if self.conns.get(nick):
                    self.idle.append(nick)      # na koniec kolejki
                    if len(self.idle) == 1:
                        return                  # nikt inny nie czeka


def main():
    tokens_path = os.environ.get("CHAT_TOKENS", "tokens.json")
    tokens = json.loads(Path(tokens_path).read_text())
    server = ChatServer(
        data_dir=os.environ.get("CHAT_DATA", "./chat-data"),
        tokens=tokens,
        port=int(os.environ.get("CHAT_PORT", 8765)))

    async def run():
        await server.start()
        print(f"chat server on ws://localhost:{server.port}", flush=True)
        try:
            await asyncio.Future()
        finally:
            # (I) Ctrl+C / SIGTERM -> asyncio.run() anuluje to zadanie
            # (CancelledError) — finally gwarantuje clean snapshot zawsze,
            # nie tylko przy programowym wywolaniu stop()
            await server.stop()

    asyncio.run(run())


if __name__ == "__main__":
    main()
