"""Serwer czatu agentow: hello/auth, backlog/resync, echo po nicku,
wzmianki, grupy adresowe. Jedyny modul z asyncio/websockets.

Kluczowe niezmienniki (review tercetu, wiazace):
  a) generation przypieta do SOCKETU przy hello — kazda kolejna ramka z
     tego samego polaczenia jest mutowana TA generacja, nigdy
     frame.get("generation"). Po takeover (nowe hello tego samego nicka
     z innym instance_id) serwer zamyka stare sockety NATYCHMIAST (przy
     samym hello, nie dopiero przy ich kolejnej ramce); per-ramkowy check
     generacji zostaje jako druga linia obrony.
  b) snapshot niesie {"registry": ..., "status": ...} — restart odtwarza je
     i DODATKOWO replay'uje kazdy event > snapshot_seq (registry z hello/
     membership, status z deklaracji). Kolejka zadaniowa wycieta (laka-nie-
     obora, A4): stary log z task_*/task_expired_batch jest pomijany.
     resync_required robi swiezy, atomowy snapshot() PRZED odpowiedzia, zeby
     zwracany snapshot_seq zawsze etykietowal dokladnie ten state.
  c) snapshot po kazdych SNAPSHOT_EVERY=100 eventach (licznik zasiany przy
     starcie liczba eventow juz w logu po snapshot_seq) ORAZ przy stop()
     (w tym Ctrl+C/SIGTERM — patrz main()/finally).
  d) grupy adresowe ($group) — patrz protocol.parse_groups; nieznana
     grupa = error do nadawcy, zero publikacji do niej (inne wzmianki w
     tej samej ramce dzialaja normalnie). role/groups faktycznie przypisane
     nickowi pochodza WYLACZNIE z configu serwera (Registry.role_of/
     groups_of) — to co klient deklaruje w hello jest tylko walidowane.
  e) wejscie klienckie walidowane zanim dotknie rejestru/logu; zaden
     pojedynczy zly frame (w tym JSON-skalar/lista zamiast obiektu) nie
     moze zabic handlera ani serwera.
  f) trwalosc przed publikacja: kazda trwala ramka klienta najpierw append
     (dostaje seq), potem dostarczenie/odpowiedz. Pola seq/generation/groups/role/
     from sa nadpisywane przez serwer na KAZDEJ ramce klienta przed
     zapisem — nigdy nie przechodza z ramki do logu/odbiorcow.
"""
import asyncio
import copy
import hashlib
import json
import logging
import os
import signal
import time
from pathlib import Path

import websockets

from . import protocol
from .identity import AuthError, Registry
from .store import EventLog, ForeignWriterError

SNAPSHOT_EVERY = 100  # polityka snapshotow: co N eventow (+ zawsze przy stop())
STORAGE_UNAVAILABLE = "storage unavailable; retry"
STOP_CLOSE_TIMEOUT = 3.0   # F9: sufit czasu na zamkniecie serwera w stop()
LOGGER = logging.getLogger(__name__)


def _is_tailnet_ip(host):
    """Czy `host` to adres w zakresie tailnetu (CGNAT 100.64/10 albo fd7a:...)."""
    if not isinstance(host, str):
        return False
    if host.startswith("100."):          # tailnet IPv4 (100.64.0.0/10)
        try:
            drugi = int(host.split(".")[1])
        except (ValueError, IndexError):
            return False
        return 64 <= drugi <= 127
    return host.lower().startswith("fd7a:115c:a1e0")   # tailnet IPv6


def _open_bind(bind):
    """Czy ten bind sam w sobie jest bramka (loopback albo tailnet)."""
    if not isinstance(bind, str):
        return False
    if bind in ("127.0.0.1", "localhost", "::1"):
        return True
    return _is_tailnet_ip(bind)


def _bind_is_tailnet(bind):
    """B7: czy hub bindowany na interfejs TAILNETU (nie loopback).

    Tylko wtedy `remote_address` peera to jego prawdziwy adres tailnetu i
    IP-binding ma sens. Przy bind-loopback wszyscy peer to 127.0.0.1
    (lokalny test albo proxy) — adres nie rozroznia podmiotow, wiec
    wiazanie sie NIE stosuje. Patrz tabela bind->zachowanie w planie B7."""
    return _is_tailnet_ip(bind)


def _reject_json_constant(value):
    """Odrzuc rozszerzenia Pythona (NaN/Infinity), ktore nie sa JSON-em."""
    raise ValueError(f"invalid JSON constant: {value}")


def _strict_json_loads(raw):
    return json.loads(raw, parse_constant=_reject_json_constant)


class ChatServer:
    def __init__(self, data_dir, tokens, port, bind="127.0.0.1", open_mode=None):
        self.port = port
        self.bind = bind
        # B6: tryb otwarty (agent bez tokenu) wlacza sie SAM przy bindzie,
        # ktory juz jest bramka: loopback albo adres tailnetowy. Przy 0.0.0.0
        # hub stoi takze na LAN i publicznie — tam siec nie chroni niczego,
        # wiec token wraca jako wymog dla wszystkich.
        self.open_mode = _open_bind(bind) if open_mode is None else open_mode
        self.log = EventLog(Path(data_dir))
        snap = self.log.load_snapshot()
        if snap:
            state, _snapshot_seq = snap
            self.registry = Registry.restore(tokens, state.get("registry", {}))
            restored_status = state.get("status", {})
        else:
            self.registry = Registry(tokens)
        self.conns = {}        # nick -> set[ws]
        self.roles = {}        # nick -> role
        self.groups = {}       # nick -> set[group], lustro trwalego Registry
        self._server = None
        # niezmiennik A: eventy > snapshot_seq NIGDY nie byly odtwarzane do
        # stanu — trwalosc byla teatrem. Replay stosuje te same mutacje
        # (registry/status) co live, bez zadnych side-effectow sieciowych
        # (bez _send/_append — eventy juz sa na dysku).
        # self.status MUSI istniec PRZED _replay_events() — replay eventow
        # status nadpisuje stan przywrocony ze snapshotu (nowsze wygrywa)
        self.status = {}       # nick -> {state, subject?, note?} (ostatnia deklaracja)
        if snap:
            # Legacy-snapshot sanityzacja: stary snapshot (pre-B1) niesie martwe
            # task_id w status. Projektujemy KAZDY wpis tylko na dozwolone klucze,
            # zeby martwe/obce pola nie przetrwaly restartu — handler/replay juz
            # ich nie zapisuja, stare log-eventy czysci projekcja _replay_events.
            self.status = {n: {k: v[k] for k in ("state", "subject", "note")
                               if k in v}
                           for n, v in restored_status.items()
                           if isinstance(n, str) and isinstance(v, dict)}
        self._replay_events()
        self.groups = {nick: set(self.registry.groups_of(nick))
                       for nick in self.registry.tokens}
        # (A3) licznik snapshot-co-100 liczy DALEJ od tego, co juz jest w
        # logu po snapshot_seq — nie od zera (inaczej po restarcie trzeba by
        # 100 nowych eventow, zanim serwer w ogole rozwazy snapshot).
        self._events_since_snapshot = len(self.log.replay())

    def _replay_events(self):
        # Replay: eventy > snapshot_seq odtwarzaja stan (registry z hello/
        # membership, status z deklaracji) BEZ re-execution i side-effectow
        # sieciowych. Kolejka zadaniowa wycieta (A4) — stary log z task_*/
        # task_expired_batch jest pomijany.
        for event in self.log.replay():
            etype = event.get("type")
            if etype == "status":
                key = event.get("target", event["from"])
                if isinstance(key, str) and key:
                    self.status[key] = {k: event[k] for k in
                                        ("state", "subject", "note")
                                        if k in event}
            elif etype == "hello":
                self.registry.replay_hello(event["from"], event["instance_id"])
            elif etype == "membership_set":
                # Usuniety z konfiguracji nick nie odzyskuje czlonkostwa z logu.
                if event["target"] in self.registry.tokens:
                    self.registry.set_groups(event["target"], event["groups"])
            # chat/fyi/status/ok/error i stare task_*/offer/expiry-eventy: bez
            # mutacji — cala kolejka wycieta (laka-nie-obora, A4). Stary log z
            # task_new/task_claim/task_expired_batch/offer jest po prostu pomijany;
            # zostaje tylko registry (hello/membership) i status.

    # -- infrastruktura ----------------------------------------------------
    async def start(self):
        # Keepalive JAWNIE, nie z domyslnych: od niego zalezy, co znaczy
        # "nick zajety przez zywe polaczenie" (B6). Martwy socket bez pingu
        # wisi w ESTAB minutami — zdarzylo sie w dogfoodzie i agent nie mogl
        # wrocic na wlasny nick. Przy tych wartosciach trup wypada w ~40 s.
        self._server = await websockets.serve(
            self._handler, self.bind, self.port,
            ping_interval=20, ping_timeout=20)

    async def stop(self):
        self._server.close()
        # F9: zamykanie serwera pod TWARDYM limitem czasu. Zmierzone na
        # produkcji: hub dostal SIGTERM, zwolnil port, ale PROCES WISIAL —
        # operator musial go dobic kill -9, a do tego czasu zawieszony proces
        # blokowal kolejny start (fail-fast z F7 widzi go jako zywy hub).
        # Root cause zawisu nie zostal odtworzony w tescie, ale kontrakt jest
        # od niego niezalezny: `stop()` konczy sie zawsze, a snapshot (ponizej)
        # MUSI sie wykonac, bo to on domyka trwalosc. Glosny log zamiast ciszy.
        try:
            await asyncio.wait_for(self._server.wait_closed(),
                                   timeout=STOP_CLOSE_TIMEOUT)
        except asyncio.TimeoutError:
            LOGGER.warning(
                "stop(): zamykanie serwera nie skonczylo sie w %.0fs — "
                "porzucam czekanie i domykam trwalosc (snapshot). Port jest "
                "juz zwolniony; wiszace polaczenia zamknie wyjscie procesu.",
                STOP_CLOSE_TIMEOUT)
        self.snapshot()  # clean shutdown -> snapshot zawsze (polityka c)

    def snapshot(self):
        """F7: kompakcja jest jedyna operacja przepisujaca log w calosci.
        Gdy w katalogu pisze inny proces huba (split-brain), store odmawia —
        i DOBRZE: wolimy hub bez kompakcji niz skasowana rozmowe. Glosny log
        operatora, zycie huba bez zmian."""
        try:
            self._save_snapshot_unchecked({"registry": self.registry.dump(),
                                 "status": dict(self.status)})
        except ForeignWriterError:
            LOGGER.error(
                "SPLIT-BRAIN: do %s pisze inny proces huba — kompakcja "
                "przerwana, dane nietkniete. Zatrzymaj nadmiarowy hub "
                "(agentmachi list / agentmachi stop).", self.log.dir)
            return
        self._events_since_snapshot = 0

    def _save_snapshot_unchecked(self, state):
        self.log.save_snapshot(state)

    def _append(self, frame):
        seq = self._append_durable(frame)
        self._maybe_snapshot()
        return seq

    def _append_durable(self, frame):
        # (Runda 5 A) trwaly append ROZDZIELONY od auto-snapshotu: seq
        # przydzielony i event NA DYSKU, ale snapshot jeszcze NIE odpalony.
        # Mutacje wymagajace domkniecia stanu MIEDZY (trwaly event) a
        # (ewentualny snapshot) wstawiaja swoj efekt PO udanym appendzie,
        # a PRZED snapshotem. Nieudany append (wyjatek z
        # log.append) rzuca zanim cokolwiek zmutujemy — brak dziury w numeracji
        # i brak przedwczesnej mutacji stanu zaleznego od trwalosci.
        seq = self.log.append(frame)
        self._events_since_snapshot += 1
        return seq

    def _maybe_snapshot(self):
        if self._events_since_snapshot >= SNAPSHOT_EVERY:
            self.snapshot()

    async def _push_presence(self, nick, connected):
        """Efemeryczna ramka presence do WSZYSTKICH podlaczonych humanow —
        TUI aktualizuje liste online na zywo, bez czekania na kolejny hello.
        Bez seq/persystencji: prawda autorytatywna i tak wraca w snapshocie
        przy kazdym hello."""
        frame = protocol.make_frame(
            "presence", "server", time.time(), nick=nick,
            connected=bool(connected),
            status=self.status.get(nick))
        for other, role in self.roles.items():
            if role == "human" and self.conns.get(other):
                await self._send(other, frame)

    def _participants_snapshot(self):
        """Autorytatywny roster dla TUI humana: KAZDY nick z configu
        (registry) + jego serwerowe role/groups + realne connected.
        Zrodlo prawdy: registry (durable, replayowane) + conns (live) —
        nigdy statyczny plik tokenow po stronie klienta."""
        # B6: roster to NIE lista posiadaczy tokenow. W trybie otwartym agent
        # wchodzi bez wpisu w tokens.json — gdyby go tu brakowalo, moderator
        # nie zobaczylby, kogo ma wyrzucic, a inni agenci nie wiedzieliby, ze
        # ktos doszedl. Zrodlem jest suma: konfiguracja + realne polaczenia.
        znani = set(self.registry.tokens) | set(self.registry.roles)
        # last_seq: numer OSTATNIEJ ramki, ktora ten uczestnik wyslal.
        # `connected` mowi tylko tyle, ze gniazdo jest otwarte — a gniazdo
        # zyje niezaleznie od tego, czy ktokolwiek po drugiej stronie czyta.
        # W dogfoodzie kinas-machine dwa agenty mialy procesy z uptime 2h,
        # gniazda ESTAB i przesuwajacy sie kursor, a model nie zobaczyl ani
        # jednej ramki; hub raportowal je jako obecne, czlowiek trzy razy
        # pytal "czemu stoicie". Dane sa juz w logu — to tylko ich pokazanie,
        # bez nowego mechanizmu i bez zmian w protokole.
        ostatnia = {}
        for e in self.log.conversation_after(0):
            nadawca, seq = e.get("from"), e.get("seq")
            if isinstance(seq, int) and not isinstance(seq, bool):
                ostatnia[nadawca] = max(ostatnia.get(nadawca, 0), seq)
        return [{"nick": nick,
                 "role": self.registry.role_of(nick),
                 "groups": sorted(self.registry.groups_of(nick)),
                 "connected": bool(self.conns.get(nick)),
                 "status": self.status.get(nick),
                 "last_seq": ostatnia.get(nick, 0)}
                for nick in sorted(znani | set(self.conns))]

    def _wolny_nick(self, prefix="worker"):
        """Pierwszy nick, ktorego nikt nie trzyma — propozycja dla wchodzacego."""
        n = 1
        while True:
            kandydat = f"{prefix}{n}"
            if not self.conns.get(kandydat) and kandydat not in self.registry.tokens:
                return kandydat
            n += 1

    def _load_rules(self):
        path = self.log.dir / "rules.md"
        if not path.exists():
            return None, None
        text = path.read_text()
        return text, hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _load_howto(self):
        """F5 (B5): instrukcja obslugi kanalu — dla agenta, ktory ma TYLKO
        socket. Plik w repo jest bezuzyteczny dla klienta na golym ws (nie
        ma repo), wiec onboarding musi isc ta sama droga co rules: w
        odpowiedzi na hello. Rules mowia JAK sie zachowywac, howto — JAK sie
        tu poruszac (adres, nicki, uzbrojenie nasluchu, pulapki)."""
        path = self.log.dir / "howto.md"
        if not path.exists():
            return None
        return path.read_text()

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
        if event.get("quiet"):
            # PUBLIKACJA, NIE ZAWOLANIE. Ramka ląduje w logu i dociera do ludzi
            # (oni i tak dostają wszystko), ale NIE budzi żadnego agenta —
            # nawet wzmiankowanego.
            #
            # Po co: dziś jedynym sposobem opublikowania czegokolwiek jest
            # obudzenie wszystkich adresatów. Napisanie kosztuje autora raz,
            # przeczytanie kosztuje każdego wzmiankowanego — więc autorowi
            # OPŁACA SIĘ pisać długo, bo jedna gęsta ramka oszczędza mu trzy
            # rundy pytań. W dogfoodzie kinas-machine dało to ramki po 2-3 tys.
            # znaków. Ekonomia narzędzia premiowała obciążanie innych.
            #
            # To jest MOŻLIWOŚĆ, nie decyzja za agenta: nadawca sam wybiera,
            # czy jego raport ma kogoś wyrywać z pracy, czy poczekać w logu.
            targets |= {n for n, r in self.roles.items()
                        if r == "human" and n != sender and n in self.conns}
            for nick in targets:
                await self._send(nick, event)
            return
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
        seq = self._append(frame)  # trwaly zapis PRZED publikacja (niezmiennik f)
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
        # pochodzi z configu serwera — niezmiennik d/H) — ale jesli podana,
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
            try:
                frame = _strict_json_loads(raw)
            except ValueError:
                await ws.send(json.dumps(protocol.make_frame(
                    "error", "server", time.time(), text="invalid json")))
                await ws.close(code=1008, reason="invalid json")
                return
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
                # (Runda 7) PROVISIONAL-THEN-COMMIT dla Registry: hello mutuje
                # tozsamosc (bump generacji + zapis
                # instance) na KLONIE, nie na live. AuthError leci Z KLONA ZANIM
                # cokolwiek trwalego/live sie zmieni (auth-fail => error, zero
                # mutacji, zero appendu). generation to na razie PREVIEW —
                # commit dopiero po udanym durable appendzie. Registry to male
                # dicty (nick->gen, nick->instance), wiec deepcopy-per-hello to
                # swiadomy, tani trade-off — hello jest rzadki (nie hot-path).
                trial_registry = copy.deepcopy(self.registry)
                # B6: w trybie otwartym agent moze wejsc BEZ tokenu. Rola
                # human wymaga go zawsze (open_hello odmawia), a tryb otwarty
                # wlacza sie wylacznie przy bindzie loopback/tailnet — patrz
                # _open_mode(). Nick zajety przez ZYWE polaczenie nie jest
                # odbierany (nizej): martwe sockety wypadaja same dzieki
                # keepalive, wiec "zajety" znaczy "zajety naprawde".
                if self.open_mode and not frame.get("token"):
                    zadany = frame.get("from")
                    # Brak propozycji nicka = "dajcie mi jakikolwiek". Agent
                    # nie musi wiedziec, kim jest, zanim wejdzie — dowie sie
                    # z pola `nick` w odpowiedzi ok (bez tego musialby to
                    # wywnioskowac z participants, co lamie sie przy dwoch
                    # swiezych wejsciach naraz).
                    if not zadany:
                        zadany = self._wolny_nick()
                        frame["from"] = zadany
                    # B7: adres wiazania. Aktywny TYLKO przy bindzie na
                    # interfejs tailnetu — wtedy remote_address peera to jego
                    # prawdziwy adres. Przy bind-loopback adres nie rozroznia
                    # podmiotow (addr = None -> open_hello nie wiaze).
                    addr = None
                    if _bind_is_tailnet(self.bind):
                        peer = ws.remote_address
                        host = peer[0] if peer else None
                        if host is None or host in ("127.0.0.1", "::1",
                                                    "localhost"):
                            # Loopback-peer przy bindzie na tailnet to ANOMALIA:
                            # skad loopback, gdy hub stoi na tailnecie? Tylko
                            # przez lokalny serve/tunnel (proxy). remote_address
                            # to wtedy proxy, nie peer — IP-binding daloby
                            # falszywa ochrone. Nie ufamy: open bez tokenu
                            # odrzucone, tozsamosc wraca do tokenu.
                            await ws.send(json.dumps(protocol.make_frame(
                                "error", "server", time.time(),
                                text="hub za proxy/tunelem — wejscie bez tokenu "
                                     "niedostepne; podaj CHAT_TOKEN")))
                            return
                        addr = host
                    # Odmowa TYLKO gdy zywy nick nalezy do INNEGO instance_id.
                    # Ten sam instance = wlasny self-resume/self-send (send/frame
                    # wspoldziela tozsamosc listenera, zeby nie robic takeoveru)
                    # — musi przejsc jak na sciezce tokenowej. Bez tego zdalny
                    # agent bez tokenu nie mogl wyslac ramki trzymajac nasluch
                    # (finding Opuska: obietnica polowiczna, tylko dla nasluchu).
                    if (isinstance(zadany, str) and self.conns.get(zadany)
                            and trial_registry.role_of(zadany) != "human"
                            and self.registry.instance_of(zadany)
                                != frame.get("instance_id")):
                        wolny = self._wolny_nick()
                        await ws.send(json.dumps(protocol.make_frame(
                            "error", "server", time.time(),
                            text=f"nick {zadany} jest zajety przez polaczonego "
                                 f"uczestnika; wolny nick: {wolny}")))
                        return
                    # B7 host-check + zapis wiazania — w open_hello, na trial
                    # (provisional-then-commit). Inny adres na przypiety nick =
                    # AuthError (lapane nizej jak kazdy blad open_hello).
                    generation = trial_registry.open_hello(
                        zadany, frame.get("instance_id"), addr)
                else:
                    generation = trial_registry.hello(
                        frame.get("from"), frame.get("instance_id"),
                        frame.get("token"))
            except AuthError as e:
                await ws.send(json.dumps(protocol.make_frame(
                    "error", "server", time.time(), text=str(e))))
                return
            nick = frame["from"]
            # role jest stala z configu; groups to aktualny, trwaly stan
            # serwera. Deklaracja hello zadnego z nich nie nadpisuje.
            # Z KLONA, nie z live: w trybie otwartym (B6) nowy nick dostaje
            # role i grupy dopiero w open_hello, czyli na klonie — live
            # jeszcze go nie zna, bo swap nastepuje po durable appendzie.
            # Czytanie z live dawalo agentowi PUSTE grupy: technicznie na
            # kanale, praktycznie gluchy na $workers (zlapane na zywym pokoju,
            # testy jednostkowe Registry tego nie widzialy).
            role = trial_registry.role_of(nick)
            groups = trial_registry.groups_of(nick)
            # backlog liczony PRZED zalogowaniem WLASNEGO hello — inaczej
            # klient zawsze widzialby wlasna ramke hello w swoim backlogu i
            # "last_seq == biezacy cursor" po reconnnekcie nigdy by nie
            # dawalo pustego backlogu (por. test_reconnect_resumes_from_last_seq)
            # KONTRAKT (B3, zadanie 2): backlog jest NIEFILTROWANY. Filtr wzmianek
            # dotyczy wylacznie live push (_publish_chat) — spiacy agent nie placi
            # za cudza rozmowe. Replay od kursora zwraca pelny log kazdemu
            # uwierzytelnionemu: selekcje robi node/agent, nie hub. Node (wake)
            # pobiera tedy kontekst — filtr tutaj = amnezja agentow tylnymi drzwiami.
            backlog = self.log.events_after(last_seq)
            # niezmiennik A + (Runda 7) DURABLE-FIRST: mutacja tozsamosci jest
            # TRWALA PRZED live-swapem i JAKIMKOLWIEK side-effectem. Durable
            # append NAJPIERW (bez tokenu — sekret nigdy na dysk; bez auto-
            # snapshotu, patrz _maybe_snapshot na koncu). Gdy rzuci (np. OSError/
            # dysk pelny): self.registry NIETKNIETY (klon wyrzucony), ZADEN stary
            # socket nie zamkniety, conns bez zmian — klient dostaje
            # error/rozlaczenie, a retry moze legalnie powtorzyc (kolejny bump
            # idzie znow na swiezym klonie, wiec generacja podbija sie DOKLADNIE
            # raz). instance_id jest juz zwalidowany przez trial_registry.hello.
            try:
                self._append_durable(protocol.make_frame(
                    "hello", nick, time.time(),
                    instance_id=frame.get("instance_id"),
                    groups=list(groups), role=role))
            except OSError:
                # niezmiennik e: awaria storage (dysk pelny) na hello NIE moze
                # zabic handlera brutalnym 1011 — hello odpowiada czysta ramka
                # error i dopiero potem graceful close. Stan pozostaje
                # czysty (klon wyrzucony, registry nietkniety, zero side-effektow
                # bo sa PO tym appendzie), a klient odroznia storage-fail od padu
                # sieci i moze legalnie retry. Pelny wyjatek (w tym sciezka FS)
                # trafia WYLACZNIE do logu operatora; klient dostaje staly tekst.
                LOGGER.exception("storage failure during hello for nick=%r", nick)
                await ws.send(json.dumps(protocol.make_frame(
                    "error", "server", time.time(), text=STORAGE_UNAVAILABLE)))
                await ws.close(code=1011, reason="storage unavailable")
                return
            # COMMIT: dopiero po udanym durable appendzie swap live=klon, a
            # POTEM side-effects (takeover close + rejestracja socketu).
            self.registry = trial_registry
            if generation != old_gen:
                # niezmiennik C: takeover — odetnij stare sockety TERAZ (po
                # trwalym fakcie), nie dopiero przy ich kolejnej (moze nigdy nie
                # nadejsc) ramce
                await self._close_stale_sockets(nick)
            # F3 (B5): slad TYLKO dla faktycznego wyparcia. old_gen == 0 to
            # pierwsze hello tego nicka — nikogo nie wypiera, wiec nie ma o
            # czym meldowac (reconnect z tym samym instance_id nie bumpuje
            # generacji, wiec tez tu nie wpada).
            if generation != old_gen and old_gen:
                # zostaw SLAD. Bez niego wyparty agent znika po cichu:
                # dla reszty kanalu wciaz jest "connected", a jego nasluch juz
                # nic nie slyszy — agent-widmo, ktory milczy i nikt nie wie
                # dlaczego. Zdarzylo sie w dogfoodzie B5 i kosztowalo godzine
                # szukania winy w kliencie. Trwale (nie efemerycznie jak
                # presence), bo pytanie "dlaczego zamilkl" pada PO fakcie.
                takeover = protocol.make_frame(
                    "takeover", "server", time.time(), nick=nick,
                    generation=generation, previous_generation=old_gen,
                    text=(f"{nick}: nowe polaczenie wyparlo poprzednie "
                          f"(generacja {old_gen} -> {generation}); "
                          f"stare sockety zamkniete"))
                # trwalosc PRZED publikacja (inwariant projektowy)
                seq = self._append_durable(takeover)
                event = {**takeover, "seq": seq}
                # Push NA ZYWO tylko do ludzi — tak samo jak presence: to oni
                # reaguja na widmo (restart, ubicie klienta), a agentow nie
                # budzimy ramka bez wzmianki. Agenci dostana ten slad z logu
                # przy swoim najblizszym hello: takeover jest w
                # CONVERSATION_TYPES, wiec wraca w 'conversation' i przezywa
                # kompakcje.
                for other, role in self.roles.items():
                    if role == "human" and other != nick and self.conns.get(other):
                        await self._send(other, event)
            self.conns.setdefault(nick, set()).add(ws)
            self.roles[nick] = role
            self.groups[nick] = set(groups)
            rules_text, rules_hash = self._load_rules()
            extra = {}
            if rules_text is not None:
                extra["rules"] = rules_text
                extra["rules_hash"] = rules_hash
            howto_text = self._load_howto()
            if howto_text is not None:
                extra["howto"] = howto_text
            # (t2 review + B4 agent-first) roster musi byc cursor-coherent
            # i JAWNY dla kazdego uczestnika: czlowiek renderuje z niego TUI,
            # agent czyta board ("kto tu jest, kto co robi") — starsze ramki
            # status leza przed oknem kontekstu agenta, wiec snapshot w hello
            # to jedyne zrodlo pelnego stanu. Live push do agentow pozostaje
            # wylacznie wzmiankowy — to jest odpowiedz na hello, nie budzenie.
            extra["participants"] = self._participants_snapshot()
            if backlog is None:
                # niezmiennik B: resync spojny — snapshot_seq zwracany
                # klientowi musi etykietowac DOKLADNIE ten state, ktory
                # wysylamy. Bez swiezego, atomowego snapshotu tutaj,
                # self.log.snapshot_seq bylby STARA wartoscia (sprzed
                # eventy, ktore juz sa w `state`) — klient wznowilby replay
                # od stalej etykiety i zdublowal eventy, ktore `state` juz
                # zawiera.
                self.snapshot()
                # (Runda 4 #4) wire resync state = DOKLADNIE persisted snapshot
                # state ({registry, status}), nie okrojony.
                # F1 (B5): resync niesie takze PAMIEC kanalu. `state` odtwarza
                # rejestr i board (registry/status), ale rozmowy nie odtworzy
                # nic — a to ona jest jedyna pamiecia agenta. Bez tego agent
                # po kompakcji wchodzil na kanal, na ktorym "nic sie nigdy nie
                # wydarzylo" (zmierzone na produkcji: 105 ramek dogfoodu).
                reply = protocol.make_frame(
                    "resync_required", "server", time.time(),
                    nick=nick,   # KIM jestes — takze na sciezce resync, nie
                                 # tylko w ok (agent bez wlasnej propozycji
                                 # nicka, ktory po kompakcji trafia na resync,
                                 # inaczej nigdy nie pozna przydzielonego nicka)
                    snapshot_seq=self.log.snapshot_seq,
                    state={"registry": self.registry.dump(),
                           "status": dict(self.status)},
                    conversation=self.log.conversation_after(last_seq),
                    generation=generation, role=role, groups=list(groups), **extra)
            else:
                # F2 (B5): backlog NA DRUCIE pomija ramki hello (zmierzone na
                # produkcji: 54% backlogu to cudze hello). Log na dysku je
                # zachowuje (potrzebne do replayu generacji przy restarcie) —
                # filtrujemy wylacznie to, co idzie do klienta. Roster i tak
                # przychodzi autorytatywnie w participants (B4), wiec agent
                # placi kontekstem za czysty szum bez tego filtra. last_seq
                # PONIZEJ zostaje self.log.last_seq (prawdziwy koniec logu),
                # NIGDY seq ostatniej ramki po filtrowaniu — inaczej klient
                # zapetlalby sie prosząc w kolko o ramki, ktorych nigdy nie
                # dostanie (por. test_reconnect_with_wire_last_seq_gives_
                # empty_backlog_no_loop).
                wire_backlog = [e for e in backlog if e.get("type") != "hello"]
                reply = protocol.make_frame(
                    "ok", "server", time.time(),
                    nick=nick,   # KIM jestes — jawnie, nie do wywnioskowania
                                 # z participants (B6 review: agent bez
                                 # wlasnej propozycji nicka inaczej nie wie,
                                 # kim zostal, a przy dwoch swiezych
                                 # wejsciach naraz zgadywanie sie lamie)
                    generation=generation, role=role, groups=list(groups),
                    backlog=wire_backlog, last_seq=self.log.last_seq, **extra)
            await ws.send(json.dumps(reply))
            await self._push_presence(nick, True)
            # (Runda 7) hello append jest durable-only (bez auto-snapshotu) —
            # domykamy polityke snapshot-co-100 tutaj, PO swapie live=klon, zeby
            # ewentualny snapshot #100 zlapal juz NOWA generacje. resync-branch
            # zrobil pelny snapshot() wyzej (licznik=0), wiec to wtedy no-op.
            self._maybe_snapshot()
            async for raw in ws:
                try:
                    frame = _strict_json_loads(raw)
                except ValueError:
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
                except OSError:
                    # Storage detail moze zawierac errno i absolutna sciezke.
                    # Loguj go operatorowi, ale nigdy nie odbijaj klientowi.
                    LOGGER.exception(
                        "storage failure for nick=%r type=%r command_id=%r",
                        nick, frame.get("type"), frame.get("command_id"))
                    await ws.send(json.dumps(protocol.make_frame(
                        "error", "server", time.time(),
                        command_id=frame.get("command_id"),
                        text=STORAGE_UNAVAILABLE)))
                    stop = False
                except Exception:
                    # Ostatnia linia obrony (niezmiennik e): detal tylko w logu,
                    # odpowiedz publiczna nie ujawnia implementacji ani sciezek.
                    LOGGER.exception(
                        "internal frame failure for nick=%r type=%r command_id=%r",
                        nick, frame.get("type"), frame.get("command_id"))
                    await ws.send(json.dumps(protocol.make_frame(
                        "error", "server", time.time(),
                        command_id=frame.get("command_id"),
                        text="internal error")))
                    stop = False
                if stop:
                    break
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            if nick and ws in self.conns.get(nick, set()):
                self.conns[nick].discard(ws)
                if not self.conns[nick]:
                    # lista online jak na czacie: znikasz gdy pada OSTATNIE
                    # polaczenie (best-effort; sockety humanow moga juz byc
                    # w trakcie zamykania)
                    try:
                        await self._push_presence(nick, False)
                    except Exception:
                        pass

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
            # error niesie command_id z ramki, jesli byl — aktualne typy inbound
            # go nie uzywaja (-> None, nieszkodliwe); pole zostaje dla korelacji,
            # gdyby ktorys przyszly typ znow go wprowadzil.
            await ws.send(json.dumps(protocol.make_frame(
                "error", "server", time.time(),
                command_id=frame.get("command_id"), text=err)))
            return False
        # niezmiennik D: pola autorytatywne (seq/generation/groups/role) nadaje
        # WYLACZNIE serwer. membership_set.groups jest tylko zwalidowanym
        # zadaniem zmiany; handler zapisze znormalizowany wynik serwera.
        ftype = frame["type"]
        requested_groups = frame.get("groups") if ftype == "membership_set" else None
        for field in ("seq", "generation", "groups", "role"):
            frame.pop(field, None)
        frame["from"] = nick  # tozsamosc z hello, nie z ramki (pole autorytatywne)
        if ftype == "chat":
            await self._handle_chat(frame, nick)
        elif ftype == "fyi":
            self._append(frame)
        elif ftype == "status":
            target = frame.get("target") or nick
            if target != nick and not (
                    self.registry.role_of(nick) == "human"
                    or "orchestrator" in self.registry.groups_of(nick)):
                await ws.send(json.dumps(protocol.make_frame(
                    "error", "server", time.time(),
                    text="forbidden: cudzy status wymaga human albo "
                         "grupy orchestrator")))
                return False
            frame["target"] = target  # pole autorytatywne: server-side default
            seq = self._append(frame)
            frame["seq"] = seq
            self.status[target] = {k: frame[k] for k in
                                   ("state", "subject", "note")
                                   if k in frame}
            # Etap 1 (laka-nie-obora): status to CZYSTY fakt na boardzie —
            # zero side-effectu schedulera. `state=idle` nie dopisuje juz do
            # kolejki round-robin ani nie wyzwala oferty. Board jest pasywny.
            for observer, role in list(self.roles.items()):
                if role == "human" and observer != nick:
                    # live board dla TUI; agenci dostaja tylko backlog/preambule
                    await self._send(observer, frame)
        elif ftype == "kick":
            await self._on_kick(frame, nick, ws)
        elif ftype == "membership_set":
            await self._on_membership_set(frame, requested_groups, nick, ws)
        else:
            await ws.send(json.dumps(protocol.make_frame(
                "error", "server", time.time(),
                text=f"nieoczekiwany typ ramki od klienta: {ftype}")))
        return False

    async def _on_kick(self, frame, nick, ws):
        """B6: moderacja czlowieka — jedyna odpowiedz na pytanie 'kim jestes'
        w kanale bez tokenow dla agentow.

        Uprawnienie ma WYLACZNIE rola human (a human zawsze ma token, wiec
        to realne uprawnienie, nie umowa). Swiadomie WEZSZE niz przy
        membership_set, gdzie wystarczy grupa admin: zmiana grup jest
        odwracalna i wewnetrzna, a kick ODCINA uczestnika od kanalu.
        """
        now = time.time()
        target = frame["target"]
        # Moderacja: rola human ZAWSZE, plus grupa admin (orchestrator-agent,
        # gdy czlowiek jawnie mu ja nada). Lancuch zaufania zostaje: do admina
        # wprowadza wylacznie human/admin przez membership_set, wiec agent nie
        # da sobie tej mocy sam. (B6 mial kick human-only; rozszerzone na
        # rozkaz roota — rule 2 rules.md.)
        if (self.registry.role_of(nick) != "human"
                and "admin" not in self.registry.groups_of(nick)):
            await ws.send(json.dumps(protocol.make_frame(
                "error", "server", now,
                text="forbidden: kick wymaga roli human albo grupy admin")))
            return
        if not self.conns.get(target):
            await ws.send(json.dumps(protocol.make_frame(
                "error", "server", now,
                text=f"kick: {target} nie jest polaczony")))
            return
        event = protocol.make_frame("kick", "server", now,
                                    target=target, by=nick)
        seq = self._append(event)      # trwalosc PRZED publikacja
        event["seq"] = seq
        await ws.send(json.dumps(protocol.make_frame(
            "ok", "server", now, target=target)))
        # JEDYNY WYJATEK od reguly "agenta budzi tylko wzmianka" — i ma nim
        # zostac. Uzasadnienie: kick zmienia SKLAD ZESPOLU, a nie tresc
        # rozmowy. Agent, ktory wlasnie uzgodnil podzial pracy z wyrzuconym,
        # musi wiedziec, ze partner zniknal, bo inaczej czeka na robote,
        # ktorej nikt nie zrobi. Kazdy kolejny wyjatek zabija te regule
        # przez tysiac drobnych ustepstw — nie dokladaj drugiego bez
        # rownie mocnego powodu.
        for other in list(self.conns):
            if other != target:
                await self._send(other, event)
        await self._send(target, protocol.make_frame(
            "error", "server", now,
            text=f"wyrzucony z kanalu przez {nick}"))
        for sock in list(self.conns.get(target, ())):
            try:
                await sock.close(code=4003, reason="kicked")
            except websockets.exceptions.ConnectionClosed:
                pass
        # B7: rozkaz roota bije wiazanie — zwolnij przypiecie nick->adres,
        # zeby ten sam agent po re-IP (albo ktos inny) mogl wejsc na ten nick
        # z nowego adresu. Bez tego wyrzucony agent, ktory zmienil IP, byloby
        # trwale zablokowany z wlasnego nicka.
        self.registry.release_open_addr(target)

    async def _on_membership_set(self, frame, requested_groups, nick, ws):
        """Przekaz funkcje przez grupy; bez RBAC, elekcji i CAS."""
        now = time.time()
        if (self.registry.role_of(nick) != "human"
                and "admin" not in self.registry.groups_of(nick)):
            await ws.send(json.dumps(protocol.make_frame(
                "error", "server", now,
                text="forbidden: membership_set wymaga human albo grupy admin")))
            return
        trial = copy.deepcopy(self.registry)
        try:
            groups = trial.set_groups(frame["target"], requested_groups)
        except AuthError as e:
            await ws.send(json.dumps(protocol.make_frame(
                "error", "server", now, text=str(e))))
            return
        event = {**frame, "groups": groups}
        seq = self._append_durable(event)
        event["seq"] = seq
        self.registry = trial
        self.groups[frame["target"]] = set(groups)
        self._maybe_snapshot()
        await ws.send(json.dumps(protocol.make_frame(
            "ok", "server", now, target=frame["target"], groups=groups)))
        if frame["target"] != nick:
            await self._send(frame["target"], event)
        for observer, role in list(self.roles.items()):
            if role == "human" and observer not in {nick, frame["target"]}:
                await self._send(observer, event)


def main():
    tokens_path = os.environ.get("CHAT_TOKENS", "tokens.json")
    tokens = json.loads(Path(tokens_path).read_text())
    server = ChatServer(
        data_dir=os.environ.get("CHAT_DATA", "./chat-data"),
        tokens=tokens,
        port=int(os.environ.get("CHAT_PORT", 8765)),
        bind=os.environ.get("CHAT_BIND", "127.0.0.1"))

    async def run():
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        sigterm_installed = False
        try:
            loop.add_signal_handler(signal.SIGTERM, stop_event.set)
            sigterm_installed = True
        except (NotImplementedError, RuntimeError):
            # add_signal_handler nie jest dostepny na kazdym loopie/platformie;
            # na wspieranym produkcyjnym Unixie SIGTERM idzie ta sciezka.
            pass
        await server.start()
        print(f"chat server on ws://{server.bind}:{server.port}", flush=True)
        try:
            await stop_event.wait()
        finally:
            try:
                # SIGTERM ustawia event i schodzi kontrolowanie tutaj; SIGINT
                # nadal anuluje run() przez asyncio.Runner. Obie sciezki musza
                # poczekac na stop(), a wiec i atomowy snapshot.
                await server.stop()
            finally:
                if sigterm_installed:
                    loop.remove_signal_handler(signal.SIGTERM)

    asyncio.run(run())


if __name__ == "__main__":
    main()
