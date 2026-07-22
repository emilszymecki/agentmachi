"""Serwer czatu agentow: hello/auth, backlog/resync, echo po nicku,
wzmianki, grupy adresowe, oferty taskow. Jedyny modul z asyncio/websockets.

Kluczowe niezmienniki (review tercetu, wiazace):
  a) generation przypieta do SOCKETU przy hello — kazda kolejna ramka z
     tego samego polaczenia jest mutowana TA generacja, nigdy
     frame.get("generation"). Po takeover (nowe hello tego samego nicka
     z innym instance_id) stary socket dostaje error na kazdej ramce.
  b) snapshot niesie {"queue": ..., "registry": ...} — restart odtwarza
     oba (Registry.restore).
  c) snapshot po kazdych SNAPSHOT_EVERY=100 eventach ORAZ przy stop().
  d) activation_id kotwiczony w TRWALYM evencie: task_offer najpierw
     append (dostaje seq), potem activation_id = f"{nick}:{seq}"; retry
     tej samej oferty (ten sam nick+task+wersja) zwraca ten sam id bez
     nowego eventu.
  e) grupy adresowe ($group) — patrz protocol.parse_groups; nieznana
     grupa = error do nadawcy, zero publikacji do niej (inne wzmianki w
     tej samej ramce dzialaja normalnie).
  f) wejscie klienckie walidowane zanim dotknie kolejki/rejestru; zaden
     pojedynczy zly frame nie moze zabic handlera ani serwera.
  g) trwalosc przed publikacja: chat najpierw append (dostaje seq),
     potem dostarczenie.
"""
import asyncio
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
        else:
            self.queue = TaskQueue(wip_limit=wip_limit, lease_ttl=lease_ttl)
            self.registry = Registry(tokens)
        self.conns = {}        # nick -> set[ws]
        self.roles = {}        # nick -> role
        self.groups = {}       # nick -> set[group] (przezywa reconnect, nie restart)
        self.idle = []         # nicki wyrobnic zglaszajacych idle (round-robin)
        self._offer_cache = {}  # (nick, task_id, version) -> activation_id
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
        for event in self.log.replay():
            etype = event.get("type")
            if etype == "hello":
                self.registry.replay_hello(event["from"], event["instance_id"])
            elif etype == "task_offer":
                key = (event["target"], event["task"]["id"], event["task"]["version"])
                self._offer_cache[key] = event["activation_id"]
            elif etype in _TASK_REQUIRED_FIELDS:
                self._replay_task_event(event)
            # chat/fyi/status/ok/error: bez mutacji stanu queue/registry

    def _replay_task_event(self, event):
        ftype = event["type"]
        nick = event["from"]
        command_id = event.get("command_id")
        now = event.get("_now", 0.0)
        gen = event.get("_generation")
        if ftype == "task_new":
            self.queue.add(event["card"], command_id, now)
        elif ftype == "task_claim":
            self.queue.claim(event["task_id"], nick, gen, command_id,
                              event["expected_task_version"], now)
        elif ftype == "task_done":
            self.queue.to_review(event["task_id"], nick, gen, command_id,
                                  event["expected_task_version"], now)
        elif ftype == "task_blocked":
            self.queue.block(event["task_id"], nick, gen, command_id,
                              event["expected_task_version"], now)
        elif ftype == "review_changes":
            self.queue.request_changes(event["task_id"], command_id,
                                        event["expected_task_version"], now)
        elif ftype == "task_approve":
            self.queue.done(event["task_id"], nick, gen, command_id,
                             event["expected_task_version"], now)
        elif ftype == "task_unblock":
            self.queue.unblock(event["task_id"], nick, gen, command_id,
                                event["expected_task_version"], now)

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
                                 "registry": self.registry.dump()})
        self._events_since_snapshot = 0

    def _append(self, frame):
        seq = self.log.append(frame)
        self._events_since_snapshot += 1
        if self._events_since_snapshot >= SNAPSHOT_EVERY:
            self.snapshot()
        return seq

    async def _expiry_loop(self):
        while True:
            await asyncio.sleep(1.0)
            for task in self.queue.expire(time.time()):
                self._append(protocol.make_frame(
                    "fyi", "server", time.time(),
                    text=f"lease wygasl, task {task['id']} wraca do open"))
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
        # dolaczy nowy, zeby nic wiecej do nich nie trafilo (routing/_send)
        stale = list(self.conns.get(nick, ()))
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
            self.conns[nick].discard(old_ws)

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
            nick_candidate = frame.get("from")
            # niezmiennik C: generacja SPRZED tego hello — potrzebna zeby
            # odroznic zwykly reconnect (ten sam instance_id, bez bumpa) od
            # faktycznego takeover (bump), zeby wiedziec czy stare sockety
            # trzeba zamknac natychmiast
            old_gen = (self.registry.generation_of(nick_candidate)
                       if isinstance(nick_candidate, str) else 0)
            try:
                last_seq = self._validate_last_seq(frame.get("last_seq"))
                # niezmiennik H: groups/role w hello sa TYLKO walidowane —
                # przypisanie faktyczne pochodzi WYLACZNIE z configu serwera
                # (registry.role_of/groups_of), nigdy z deklaracji klienta.
                self._validate_groups(frame.get("groups"))
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
                reply = protocol.make_frame(
                    "resync_required", "server", time.time(),
                    snapshot_seq=self.log.snapshot_seq,
                    state={"queue": self.queue.dump()}, generation=generation,
                    **extra)
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
            await ws.send(json.dumps(protocol.make_frame(
                "error", "server", time.time(), text=err)))
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

    async def _on_task_frame(self, frame, nick, sock_gen, ws):
        now = time.time()
        ftype = frame["type"]
        command_id = frame.get("command_id")
        missing = [f for f in _TASK_REQUIRED_FIELDS[ftype] if frame.get(f) is None]
        if missing:
            await ws.send(json.dumps(protocol.make_frame(
                "error", "server", now, command_id=command_id,
                text=f"{ftype}: brakujace pola {missing}")))
            return
        try:
            if ftype == "task_new":
                result = self.queue.add(frame["card"], frame["command_id"], now)
                self._append({**frame, "result_version": result["version"],
                              "_generation": sock_gen, "_now": now})
                self._trigger_offer()
            elif ftype == "task_claim":
                result = self.queue.claim(frame["task_id"], nick, sock_gen,
                                          frame["command_id"],
                                          frame["expected_task_version"], now)
                self._append({**frame, "result_version": result["version"],
                              "_generation": sock_gen, "_now": now})
                if nick in self.idle:
                    self.idle.remove(nick)
            elif ftype == "task_done":
                result = self.queue.to_review(frame["task_id"], nick, sock_gen,
                                              frame["command_id"],
                                              frame["expected_task_version"], now)
                self._append({**frame, "result_version": result["version"],
                              "_generation": sock_gen, "_now": now})
            elif ftype == "task_blocked":
                result = self.queue.block(frame["task_id"], nick, sock_gen,
                                          frame["command_id"],
                                          frame["expected_task_version"], now)
                self._append({**frame, "result_version": result["version"],
                              "_generation": sock_gen, "_now": now})
            elif ftype == "review_changes":  # od matki, bez ownera
                result = self.queue.request_changes(frame["task_id"],
                                                    frame["command_id"],
                                                    frame["expected_task_version"], now)
                self._append({**frame, "result_version": result["version"],
                              "_generation": sock_gen, "_now": now})
            elif ftype == "task_approve":  # happy-end review: review -> done
                result = self.queue.done(frame["task_id"], nick, sock_gen,
                                         frame["command_id"],
                                         frame["expected_task_version"], now)
                self._append({**frame, "result_version": result["version"],
                              "_generation": sock_gen, "_now": now})
            else:  # task_unblock: blocked -> claimed
                result = self.queue.unblock(frame["task_id"], nick, sock_gen,
                                            frame["command_id"],
                                            frame["expected_task_version"], now)
                self._append({**frame, "result_version": result["version"],
                              "_generation": sock_gen, "_now": now})
        except TaskError as e:  # Conflict/StaleGeneration sa jego podklasami
            await ws.send(json.dumps(protocol.make_frame(
                "error", "server", now, command_id=command_id,
                text=f"{type(e).__name__}: {e}")))
            return
        await ws.send(json.dumps(protocol.make_frame(
            "ok", "server", now, command_id=command_id, task=result)))
        if ftype == "review_changes":
            await self._send(result["assignee"], protocol.make_frame(
                "review_changes", "server", now, task=result))

    # -- oferty (round-robin + timeout) -------------------------------------
    def _offer_activation_id(self, nick, task):
        # niezmiennik d)/F1: activation_id kotwiczony w TRWALYM evencie —
        # event NA DYSKU musi sam zawierac activation_id (i seq). Seq
        # przydzielany przez log.append() jest deterministyczny (petla
        # asyncio jednowatkowa, wiec kolejny append dostanie DOKLADNIE
        # przewidywany numer) — liczymy go z gory, zeby moc wlozyc
        # activation_id do ramki PRZED jej zapisem, zamiast dopisywac
        # cos do juz zapisanej linii (store.py nie pozwala na to).
        # Retry TEJ SAMEJ proby (ten sam nick+task_id+wersja taska) zwraca
        # ten sam id BEZ nowego eventu; zmiana ktoregokolwiek pola to
        # nowa proba -> nowy event.
        key = (nick, task["id"], task["version"])
        cached = self._offer_cache.get(key)
        if cached is not None:
            return cached
        predicted_seq = self.log.last_seq + 1
        activation_id = f"{nick}:{predicted_seq}"
        seq = self._append(protocol.make_frame(
            "task_offer", "server", time.time(), task=task, target=nick,
            activation_id=activation_id))
        assert seq == predicted_seq  # jednowatkowy event loop — brak wyscigu
        self._offer_cache[key] = activation_id
        return activation_id

    def _trigger_offer(self):
        if self._offering is None or self._offering.done():
            self._offering = asyncio.ensure_future(self._offer_loop())

    async def _offer_loop(self):
        while True:
            task = self.queue.offerable()
            if task is None or not self.idle:
                return
            nick = self.idle.pop(0)
            key = (nick, task["id"], task["version"])
            activation_id = self._offer_activation_id(nick, task)
            await self._send(nick, protocol.make_frame(
                "task_offer", "server", time.time(), task=task,
                activation_id=activation_id))
            await asyncio.sleep(self.offer_timeout)
            # (F2) proba dla (nick, task_id, wersja) jest teraz ROZSTRZYGNIETA
            # — ewikcja z cache, zeby ewentualna PONOWNA oferta tego samego
            # taska/wersji temu samemu nickowi (po pelnym okrazeniu idle) byla
            # NOWA proba/event, a nie sklejona z ta, ktora wlasnie minela
            self._offer_cache.pop(key, None)
            fresh = self.queue.get(task["id"])
            # (F4) sprawdzamy KTO faktycznie dostal taska, nie tylko czy
            # przestal byc "open" — inny klient mogl go ukrasc bezposrednim
            # task_claim (poza mechanizmem ofert) w trakcie sleep(); w takim
            # wypadku oferowany nick TEZ nie wzial i musi wrocic do idle,
            # zamiast zostac na zawsze utracony z puli
            if fresh["assignee"] != nick:
                self.idle.append(nick)          # na koniec kolejki
                if len(self.idle) == 1:
                    return                      # nikt inny nie czeka


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
