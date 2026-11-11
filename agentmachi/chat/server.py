"""Serwer czatu agentow: hello/auth, backlog/resync, echo po nicku,
wzmianki, grupy adresowe. Jedyny modul z asyncio/websockets.

Kluczowe niezmienniki:
  a) generation przypieta do SOCKETU przy hello — kazda kolejna ramka z
     tego samego polaczenia jest mutowana TA generacja, nigdy
     frame.get("generation"). Po takeover (nowe hello tego samego nicka
     z innym instance_id) serwer zamyka stare sockety NATYCHMIAST (przy
     samym hello, nie dopiero przy ich kolejnej ramce); per-ramkowy check
     generacji zostaje jako druga linia obrony.
  b) snapshot niesie {"registry", "status", "status_seq"} — restart odtwarza je
     i DODATKOWO replay'uje kazdy event > snapshot_seq (registry z hello/
     membership, status z deklaracji). Stary log z task_*/task_expired_batch
     jest pomijany.
     resync_required zwraca snapshot_seq etykietujacy dokladnie wyslany
     state. Gdy stan zmienil sie od snapshotu na dysku, robi swiezy,
     atomowy snapshot(); gdy jest identyczny, etykietuje go biezacym koncem
     logu bez przesuwania globalnej granicy kompakcji.
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
from .identity import AuthError, Registry, UNRESOLVED_ADDR
from .store import EventLog, ForeignWriterError

SNAPSHOT_EVERY = 100  # polityka snapshotow: co N eventow (+ zawsze przy stop())
STORAGE_UNAVAILABLE = "storage unavailable; retry"
# Ten sam komunikat wysylaja DWIE sciezki: natychmiastowe odciecie starego
# socketu przy takeoverze (_close_stale_sockets) i per-ramkowy check generacji
# w _on_frame. Musza mowic klientowi doslownie to samo, wiec jest stala.
STALE_GENERATION = ("stale generation: this socket was taken over by a "
                    "newer hello")
STOP_CLOSE_TIMEOUT = 3.0   # sufit czasu na zamkniecie serwera w stop()
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
    """Czy hub bindowany na interfejs TAILNETU (nie loopback).

    Tylko wtedy `remote_address` peera to jego prawdziwy adres tailnetu i
    IP-binding ma sens. Przy bind-loopback wszyscy peer to 127.0.0.1
    (lokalny test albo proxy) — adres nie rozroznia podmiotow, wiec
    wiazanie sie NIE stosuje."""
    return _is_tailnet_ip(bind)


def _reject_json_constant(value):
    """Odrzuc rozszerzenia Pythona (NaN/Infinity), ktore nie sa JSON-em."""
    raise ValueError(f"invalid JSON constant: {value}")


def _strict_json_loads(raw):
    frame = json.loads(raw, parse_constant=_reject_json_constant)
    # Osamotniony surogat (`\ud800`) jest POPRAWNYM JSON-em, ale nie ma go
    # w UTF-8. Odbijamy go TUTAJ, na jedynych drzwiach wejsciowych — nie
    # w validate() — bo hello omija walidacje typow, a jego pola (instance_id,
    # groups) tez ida do logu. `chat` jest trwaly PRZED publikacja, wiec
    # ramka wpuszczona raz zostaje na zawsze i wywala handler przy KAZDYM
    # nastepnym hello, ktorego backlog ja obejmuje: pokoj oddaje 1011 kazdemu
    # wznawiajacemu sie, a zabic go moze dowolny uczestnik jednym stringiem.
    if not protocol.utf8_safe(frame):
        raise ValueError("frame contains a lone surrogate — it is not UTF-8")
    return frame


class CursorBeyondLog(AuthError):
    """Kursor klienta wskazuje ZA koniec logu — i odmowa niesie tu LICZBE.

    Ta odmowa jest dla `read` (send.read_frames) sytuacja ZWYKLA, nie
    awaria: agent pyta o `seq`, ktorego jeszcze nie ma, i musi dostac koniec
    logu, zeby wiedziec, o co zapytac. Liczba WYLACZNIE w tekscie dla
    czlowieka zmusza klienta do parsowania prozy regexem — przeredagowanie
    zdania w tej klasie cicho psuje klienta, bez zadnego czerwonego testu
    po stronie serwera.

    Tekst zostaje bez zmian (czyta go czlowiek), a `server_last_seq` idzie
    POLEM ramki `error` — pole jest kontraktem, zdanie nie jest."""

    def __init__(self, server_last_seq, text):
        super().__init__(text)
        self.server_last_seq = server_last_seq


class ChatServer:
    def __init__(self, data_dir, tokens, port, bind="127.0.0.1", open_mode=None):
        self.port = port
        self.bind = bind
        # Tryb otwarty (agent bez tokenu) wlacza sie SAM przy bindzie,
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
        # Eventy > snapshot_seq odtwarzamy do stanu — bez tego trwalosc jest
        # teatrem. Replay stosuje te same mutacje (registry/status) co live,
        # bez zadnych side-effectow sieciowych (bez _send/_append — eventy juz
        # sa na dysku).
        # self.status MUSI istniec PRZED _replay_events() — replay eventow
        # status nadpisuje stan przywrocony ze snapshotu (nowsze wygrywa)
        self.status = {}       # nick -> {state, subject?, note?} (ostatnia deklaracja)
        # Wiek deklaracji trzymany OSOBNO, zeby self.status zostal czysta
        # projekcja tego, co powiedzial agent — seq nadaje serwer i nie ma
        # go z czym mieszac.
        #
        # Wiek PRZEZYWA restart (snapshot). `seq` nadaje serwer przy
        # appendzie, jest monotoniczny i nigdy nie wraca, wiec "zadeklarowane
        # na 253" zostaje prawda na zawsze i liczy sie wzgledem dowolnego
        # pozniejszego konca logu — zapisany wiek jest ZNANY, nie wymyslony.
        # Snapshot z twierdzeniem bez daty to board, ktory KLAMIE zamiast
        # milczec (patrz `_participants_snapshot`): zapisujemy oba albo
        # zadne, a wyrzucenie twierdzenia niszczyloby realna informacje.
        self.status_seq = {}   # nick -> seq ramki status (metadana serwera)
        # nick -> {worktree, head, branch?}: gdzie pracuje klient. EFEMERYCZNE
        # jak `connected`: bez logu i snapshotu, bo klient wysyla je przy
        # kazdym hello, wiec po restarcie huba wraca samo.
        self.workspace = {}
        if snap:
            # Legacy-snapshot sanityzacja: stary snapshot niesie martwe
            # task_id w status. Projektujemy KAZDY wpis tylko na dozwolone klucze,
            # zeby martwe/obce pola nie przetrwaly restartu — handler/replay juz
            # ich nie zapisuja, stare log-eventy czysci projekcja _replay_events.
            self.status = {n: {k: v[k] for k in ("state", "subject", "note")
                               if k in v}
                           for n, v in restored_status.items()
                           if isinstance(n, str) and isinstance(v, dict)}
            # Sanityzacja jak wyzej, i z tego samego powodu: snapshot lezy na
            # dysku, wiec jego zawartosc jest WEJSCIEM, nie prawda. Wpis, co
            # do ktorego nie mamy pewnosci, ODPADA — a odpadniety `status_seq`
            # daje wiek "nieznany", czyli stan opisany uczciwie. Podstawienie
            # czegokolwiek w to miejsce byloby zmyslona liczba.
            #
            # BRAK pola i pole USZKODZONE to dwie rozne rzeczy i musza sie
            # roznie konczyc. Pole NIEOBECNE to legacy, czyli snapshot sprzed
            # tego pola i normalny stan; pole OBECNE, ale nie bedace mapa,
            # znaczy, ze ktos zapisal tam bzdure — naruszenie spojnosci, ktore
            # ma byc slyszalne. Zwiniecie obu do "caly wiek nieznany" cicho
            # traci wszystkie daty, a AttributeError zatrzymuje hub BEZ
            # POWODU podanego czlowiekowi.
            # Rozstrzyga OBECNOSC KLUCZA, nie wartosc `.get()`: `.get()` zwija
            # z powrotem brak klucza (legacy) i klucz z `null` (obecny, wiec
            # zapisany przez cos, co nie jest naszym kodem — nowy snapshot
            # nigdy legalnie nie pisze tam null).
            if "status_seq" not in state:
                surowe = {}                      # prawdziwe legacy
            elif not isinstance(state["status_seq"], dict):
                raise ValueError(
                    f"snapshot.json: `state.status_seq` is "
                    f"{type(state['status_seq']).__name__}, expected an object "
                    f"mapping nick -> seq. The hub is NOT starting, because "
                    f"this field is not legacy — a snapshot written before "
                    f"2026-08-07 has no such key AT ALL and starts fine. The "
                    f"key being present means something wrote it, and what it "
                    f"wrote is not a board.\n"
                    f"  the conversation log is untouched: {self.log.dir}\n"
                    f"  to start anyway and lose only the AGE of every "
                    f"declaration, delete that one key from "
                    f"{self.log.dir / 'snapshot.json'}")
            else:
                surowe = state["status_seq"]
            self.status_seq = {
                n: s for n, s in surowe.items()
                # `bool` odsiane jawnie: True jest instancja int w Pythonie.
                if isinstance(n, str) and isinstance(s, int)
                and not isinstance(s, bool)
                # Z PRZYSZLOSCI = niespojne. Seq spoza tego, co snapshot
                # obejmuje, dalby wiek ujemny — czyli liczbe wygladajaca na
                # fakt, ktorej nie da sie umiejscowic w tym logu.
                and 1 <= s <= _snapshot_seq
                # Data bez deklaracji nie jest faktem o niczyim statusie.
                # `self.status` jest juz przefiltrowany wyzej, wiec to takze
                # odsiewa wiek przypiety do wpisu, ktory sam nie przeszedl.
                and n in self.status}
        self._replay_events()
        # Zrodlem sa GRUPY rejestru, nie mapa tokenow: agent z trybu otwartego
        # ma wpis w `groups`/`roles`, ale nigdy w `tokens`. Iteracja po tokenach
        # gubilaby jego czlonkostwo przy starcie.
        self.groups = {nick: set(self.registry.groups_of(nick))
                       for nick in self.registry.roles}
        # Licznik snapshot-co-100 liczy DALEJ od tego, co juz jest w
        # logu po snapshot_seq — nie od zera (inaczej po restarcie trzeba by
        # 100 nowych eventow, zanim serwer w ogole rozwazy snapshot).
        self._events_since_snapshot = len(self.log.replay())

    def _replay_events(self):
        # Replay: eventy > snapshot_seq odtwarzaja stan (registry z hello/
        # membership, status z deklaracji) BEZ re-execution i side-effectow
        # sieciowych. Stary log z task_*/task_expired_batch jest pomijany.
        #
        # `osierocone_kickiem`: nicki, ktorym replayowany kick zabral wiazanie
        # adresu. Zyje TYLKO na czas tego przebiegu — sluzy do rozpoznania
        # sekwencji "kick -> ponowne wejscie" w logu STAREGO formatu, gdzie
        # hello nie niesie adresu (patrz galaz hello nizej).
        osierocone_kickiem = set()
        for event in self.log.replay():
            etype = event.get("type")
            if etype == "status":
                key = event.get("target", event["from"])
                if isinstance(key, str) and key:
                    self.status[key] = {k: event[k] for k in
                                        ("state", "subject", "note")
                                        if k in event}
                    if isinstance(event.get("seq"), int):
                        self.status_seq[key] = event["seq"]
            elif etype == "hello":
                # `open_addr` bywa go brak: stary log sprzed tego pola oraz
                # kazde hello tokenowe / przy bindzie loopback. None = "to
                # hello nie wiazalo adresu", nie "zwolnij wiazanie".
                kto = event["from"]
                # KLUCZ obecny = nowy format: wierzymy wartosci, takze gdy
                # jest None ("to hello swiadomie nic nie wiazalo" — sciezka
                # tokenowa albo bind loopback). Zaslepka nalezy sie WYLACZNIE
                # rekordom, w ktorych klucza NIE MA, czyli naprawde starym.
                nowy_format = "open_addr" in event
                adres = event.get("open_addr")
                if adres is None and not nowy_format and kto in osierocone_kickiem:
                    # STARY LOG, sekwencja kick -> ponowne wejscie. Kick
                    # skasowal wiazanie, a to hello nie niesie adresu, wiec
                    # rejestr nie ma jak odtworzyc, do czego nick byl
                    # przypiety. Zostawiony niezwiazany = do wziecia przez
                    # pierwszego chetnego z tailnetu, czyli upgrade huba
                    # otwieralby okno na przejecie tozsamosci.
                    adres = UNRESOLVED_ADDR
                self.registry.replay_hello(kto, event["instance_id"], adres)
                osierocone_kickiem.discard(kto)
            elif etype == "kick":
                # Rozkaz moderatora tez musi przezyc crash. `kick` zwalnia
                # wiazanie nick->adres, zeby wyrzucony wrocil po re-IP; bez
                # replayu snapshot wskrzeszalby STARE wiazanie i blokowal mu
                # powrot z nowego adresu. `kick` jest
                # w CONVERSATION_TYPES, wiec przezywa tez kompakcje.
                cel = event.get("target")
                if isinstance(cel, str) and cel:
                    # Tylko kick, ktory NAPRAWDE cos zwolnil, zostawia dziure.
                    # Kick bez wiazania niczego nie psuje i nie moze wciagac
                    # nicka w zaslepke — inaczej upgrade kazdego istniejacego
                    # pokoju blokowalby wszystkich wyrzuconych kiedykolwiek.
                    if self.registry.release_open_addr(cel):
                        osierocone_kickiem.add(cel)
            elif etype == "membership_set":
                # Usuniety z konfiguracji nick nie odzyskuje czlonkostwa z logu.
                # Znana tozsamosc = `roles` (nadzbior `tokens`) — inaczej
                # replay gubilby czlonkostwo agenta z trybu otwartego.
                if event["target"] in self.registry.roles:
                    self.registry.set_groups(event["target"], event["groups"])
            # chat/fyi/ok/error i stare task_*/offer/expiry-eventy: bez
            # mutacji — stan to wylacznie registry (hello/membership/kick)
            # i status.

    # -- infrastruktura ----------------------------------------------------
    async def start(self):
        # Keepalive JAWNIE, nie z domyslnych: od niego zalezy, co znaczy
        # "nick zajety przez zywe polaczenie". Martwy socket bez pingu wisi
        # w ESTAB minutami, a agent nie moze w tym czasie wrocic na wlasny
        # nick. Przy tych wartosciach trup wypada w ~40 s.
        # max_size JAWNIE, nie z domyslnych — dotyczy WEJSCIA, wiec to jedyna
        # rzecz stojaca miedzy jednym agentem a pamiecia huba (konstytucja:
        # "ochrona zasobow, gdy nikt nie patrzy" jest fizyka huba). Domyslny
        # 1 MiB websockets pozwala wkleic w chat prawie megabajt; taka ramka
        # zostaje w oknie rozmowy (CONVERSATION_LIMIT) i wraca w backlogu
        # KAZDEMU, kto sie wznawia. 64 KiB to wciaz ~30 stron tekstu na jedna
        # wiadomosc — plik wysyla sie sciezka, nie wklejeniem do kanalu.
        self._server = await websockets.serve(
            self._handler, self.bind, self.port,
            ping_interval=20, ping_timeout=20,
            max_size=protocol.MAX_FRAME_BYTES)

    async def stop(self):
        self._server.close()
        # Zamykanie serwera pod TWARDYM limitem czasu. Hub po SIGTERM potrafi
        # zwolnic port, a PROCES WISI — do kill -9 blokuje kolejny start
        # (fail-fast split-brain widzi go jako zywy hub). Przyczyna zawisu
        # nie jest odtworzona w tescie, ale kontrakt jest od niej niezalezny:
        # `stop()` konczy sie zawsze, a snapshot (ponizej) MUSI sie wykonac,
        # bo to on domyka trwalosc. Glosny log zamiast ciszy.
        try:
            await asyncio.wait_for(self._server.wait_closed(),
                                   timeout=STOP_CLOSE_TIMEOUT)
        except asyncio.TimeoutError:
            LOGGER.warning(
                "stop(): closing the server did not finish within %.0fs — "
                "giving up on waiting and closing durability (snapshot). The "
                "port is already free; process exit will close the hanging "
                "connections.",
                STOP_CLOSE_TIMEOUT)
        self.snapshot()  # clean shutdown -> snapshot zawsze (polityka c)

    def snapshot(self):
        """Kompakcja jest jedyna operacja przepisujaca log w calosci.
        Gdy w katalogu pisze inny proces huba (split-brain), store odmawia —
        i DOBRZE: wolimy hub bez kompakcji niz skasowana rozmowe. Glosny log
        operatora, zycie huba bez zmian."""
        try:
            self._save_snapshot_unchecked(self._stan_trwaly())
        except ForeignWriterError:
            LOGGER.error(
                "SPLIT-BRAIN: another hub process writes to %s — compaction "
                "aborted, data untouched. Stop the extra hub "
                "(agentmachi list / agentmachi stop).", self.log.dir)
            return
        self._events_since_snapshot = 0

    def _stan_trwaly(self):
        """Stan, ktory PRZEZYWA kompakcje — jedno zrodlo dla dysku i drutu.

        Snapshot i `state` w resync_required musza byc DOKLADNIE tym samym.
        Pisane w dwoch miejscach rozjezdzaja sie po cichu przy dopisaniu pola
        do jednego z nich — np. `status` przezylby restart, a jego
        `status_seq` nie."""
        return {"registry": self.registry.dump(),
                "status": dict(self.status),
                # Data deklaracji jedzie razem z deklaracja. Rozdzielenie ich
                # zostawia board z twierdzeniem bez daty — patrz komentarz
                # przy self.status_seq w __init__.
                "status_seq": dict(self.status_seq)}

    def _save_snapshot_unchecked(self, state):
        self.log.save_snapshot(state)

    def _append(self, frame):
        seq = self._append_durable(frame)
        self._maybe_snapshot()
        return seq

    def _append_durable(self, frame):
        # Trwaly append ROZDZIELONY od auto-snapshotu: seq
        # przydzielony i event NA DYSKU, ale snapshot jeszcze NIE odpalony.
        # Mutacje wymagajace domkniecia stanu MIEDZY (trwaly event) a
        # (ewentualny snapshot) wstawiaja swoj efekt PO udanym appendzie,
        # a PRZED snapshotem. Nieudany append (wyjatek z
        # log.append) rzuca zanim cokolwiek zmutujemy — brak dziury w numeracji
        # i brak przedwczesnej mutacji stanu zaleznego od trwalosci.
        #
        # `ts` NADAJE SERWER, tak samo jak `seq` — to jedyne miejsce, przez
        # ktore przechodzi KAZDY trwaly event, wiec tu jest jedyna kontrola,
        # ktorej nie da sie zapomniec przy nowym typie ramki. Klienci wysylaja
        # `ts: 0.0` (send.py, tui.py); bez nadpisania cala rozmowa — czyli to,
        # co czlowiek czyta, gdy chce zrozumiec, co sie stalo — jest bez
        # GODZINY, a ramki serwerowe (hello, kick, takeover) czas maja.
        # Mieszanka gorsza niz brak: wyglada na dzialajaca.
        #
        # Wartosc klienta jest WEJSCIEM DO WALIDACJI, nigdy prawda (niezmiennik
        # z AGENTS.md). Zegar stoi tutaj, a nie w logice decyzyjnej — zadna
        # decyzja huba nie zalezy od `ts`.
        frame["ts"] = time.time()
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
        # `list(...)` nie jest ostroznoscia — jest warunkiem poprawnosci.
        # `_send` oddaje sterowanie petli, wiec MIEDZY iteracjami moze
        # dokonczyc sie cudze hello i dopisac nick do `self.roles`; iteracja
        # po zywym dicie leci wtedy RuntimeError, ktory wywala handler
        # w polowie rozgloszenia.
        for other, role in list(self.roles.items()):
            if role == "human" and self.conns.get(other):
                await self._send(other, frame)

    def _participants_snapshot(self):
        """Autorytatywny roster dla TUI humana: KAZDY nick z configu
        (registry) + jego serwerowe role/groups + realne connected.
        Zrodlo prawdy: registry (durable, replayowane) + conns (live) —
        nigdy statyczny plik tokenow po stronie klienta."""
        # Roster to NIE lista posiadaczy tokenow. W trybie otwartym agent
        # wchodzi bez wpisu w tokens.json — gdyby go tu brakowalo, moderator
        # nie zobaczylby, kogo ma wyrzucic, a inni agenci nie wiedzieliby, ze
        # ktos doszedl. Zrodlem jest suma: konfiguracja + realne polaczenia.
        znani = set(self.registry.tokens) | set(self.registry.roles)
        # last_seq: numer ostatniej ramki ROZMOWY tego uczestnika — zrodlem
        # jest `conversation_after`, wiec licza sie CONVERSATION_TYPES
        # (chat/fyi/takeover/kick), a `status` i `hello` NIE. Agent, ktory
        # wlasnie zadeklarowal status, ma wiec stary last_seq — i slusznie:
        # "kiedy sie ostatnio odezwal" to wlasciwe pytanie, a status widac
        # osobno w status_seq.
        # `connected` mowi tylko tyle, ze gniazdo jest otwarte — a gniazdo
        # zyje niezaleznie od tego, czy ktokolwiek po drugiej stronie czyta:
        # proces z gniazdem ESTAB i przesuwajacym sie kursorem moze miec
        # model, ktory nie zobaczyl ani jednej ramki. Dane sa juz w logu —
        # to tylko ich pokazanie, bez nowego mechanizmu i bez zmian
        # w protokole.
        ostatnia = {}
        for e in self.log.conversation_after(0):
            nadawca, seq = e.get("from"), e.get("seq")
            if isinstance(seq, int) and not isinstance(seq, bool):
                ostatnia[nadawca] = max(ostatnia.get(nadawca, 0), seq)
        # status_seq OBOK status, nie w srodku: `status` zostaje czysta
        # projekcja deklaracji agenta (state/subject/note), a wiek tej
        # deklaracji jest metadana serwera — tak samo jak last_seq wyzej.
        # Agent nie deklaruje wlasnego seq, wiec nie ma prawa go tam zobaczyc.
        return [{"nick": nick,
                 "role": self.registry.role_of(nick),
                 "groups": sorted(self.registry.groups_of(nick)),
                 "connected": bool(self.conns.get(nick)),
                 "status": self.status.get(nick),
                 # Ile ramek temu ta deklaracja powstala. Bez tego board
                 # KLAMIE zamiast milczec: `idle` u kogos, kto pracuje caly
                 # czas, `working` u kogos, kto skonczyl godziny temu.
                 # Agenci nie maja powodu odswiezac statusu, gdy kazda
                 # wiadomosc i tak idzie wprost do drugiego.
                 # Wieku cudzej deklaracji nie da sie wyliczyc po stronie
                 # klienta — to jedyny powod, dla ktorego jest tutaj.
                 "status_seq": self.status_seq.get(nick),
                 # Klucz obecny ZAWSZE (takze None): po nim klient poznaje,
                 # ze hub przyjmuje ramke `workspace` — stary hub odbilby ja
                 # bledem, a `error` budzi agenta.
                 "workspace": self.workspace.get(nick),
                 "last_seq": ostatnia.get(nick, 0),
                 "addr": self._peer_host(nick)}
                for nick in sorted(znani | set(self.conns))]

    def _peer_host(self, nick):
        """Adres peera dla boardu (machine-id): host socketu, ktory hub WIDZI
        — klient go nie podaje, wiec nie da sie go podrobic (inwariant: pola
        autorytatywne nadaje serwer, nie ramka klienta). Odpowiada na pytanie
        'kto jest na ktorej maszynie', ktorego z samego kanalu nie da sie
        wyczytac (dwie lokalne instancje wygladaja jak dwie zdalne). Zrodlo
        to ws.remote_address, dokladnie to, ktorego uzywa wiazanie
        nick->adres — zero nowego kola. Ma sens TYLKO przy bindzie na
        tailnet; przy loopback/proxy remote_address nie rozroznia podmiotow,
        wiec zwracamy None zamiast falszywej informacji."""
        if not _bind_is_tailnet(self.bind):
            return None
        for ws in self.conns.get(nick, ()):
            peer = getattr(ws, "remote_address", None)
            host = peer[0] if peer else None
            if host and host not in ("127.0.0.1", "::1", "localhost"):
                return host
        return None

    def _wolny_nick(self, prefix="agent"):
        """Pierwszy nick, ktorego nikt nie trzyma — propozycja dla wchodzacego.

        Prefiks `agent`, nie `worker`. Hub nadaje te nazwe wchodzacemu bez
        nicka i temu, komu nick zajeto, wiec to pierwsza rzecz, jaka
        uczestnik o sobie slyszy. "worker" mowi, ze jest wykonawca czyjegos
        polecenia; to ustroj, a nie mechanika.

        WOLNY znaczy NIEZNANY REJESTROWI, nie "chwilowo nieobecny". Przy
        warunku `not self.conns.get(...)` nick rozlaczonego uczestnika wraca
        do puli RAZEM Z JEGO GRUPAMI, bo `roles`/`groups` rozlaczenia nie
        kasuja: agent1 dostaje `admin`, rozlacza sie, a nastepny przybysz
        BEZ NICKA dostaje `agent1` i `admin` w odpowiedzi na hello. Hub sam
        wreczylby obcemu cudza tozsamosc wraz z uprawnieniem do kicka.

        Cena: licznik rosnie przez cale zycie pokoju i agent, ktory nie
        zachowal swojego nicka, wraca pod nowym. To jest wlasciwe zachowanie,
        nie strata: hub NIE MA jak odroznic wracajacego od obcego, dopoki ten
        nie poda nicka sam (CHAT_NICK). Nick recyklingowany miedzy roznymi
        agentami klamie w logu o tym, kto co powiedzial.

        `kick` swiadomie NIE zwalnia nicka — zwalnia tylko wiazanie adresu
        (release_open_addr), zeby ten sam agent wrocil po re-IP. Oddanie
        nazwy komus innemu byloby dokladnie ta luka, ktora tu zamykamy."""
        n = 1
        while True:
            kandydat = f"{prefix}{n}"
            if (kandydat not in self.registry.roles
                    and kandydat not in self.registry.tokens
                    and not self.conns.get(kandydat)):
                return kandydat
            n += 1

    def _load_rules(self):
        path = self.log.dir / "rules.md"
        if not path.exists():
            return None, None
        text = path.read_text(encoding="utf-8")
        return text, hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _load_howto(self):
        """Instrukcja obslugi kanalu — dla agenta, ktory ma TYLKO
        socket. Plik w repo jest bezuzyteczny dla klienta na golym ws (nie
        ma repo), wiec onboarding musi isc ta sama droga co rules: w
        odpowiedzi na hello. Howto opisuje MECHANIKE protokolu (nicki,
        wzmianki, kursor, board, diagnostyka) — nie zasady wspolpracy:
        tych hub nie ma i nie narzuca. `rules` sa opcjonalne i naleza do
        konkretnego pokoju, gdy czlowiek je wpisze."""
        path = self.log.dir / "howto.md"
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    # -- dostarczanie ------------------------------------------------------
    async def _error(self, ws, text, **fields):
        """Jedno gardlo dla ramek `error` do KONKRETNEGO socketu.

        Wzorzec wystepuje kilkanascie razy; jedno gardlo domyka dwie rzeczy,
        ktorych sama dyscyplina nie utrzyma:
        - regula "detal implementacji NIGDY do klienta" (errno, sciezki
          absolutne) — teraz jest jedno miejsce, ktore da sie obwarowac,
        - `command_id` przenosilo sie tylko w czesci wywolan, mimo ze
          komentarz przy _on_frame deklaruje, ze pole zostaje "dla korelacji,
          gdyby ktorys przyszly typ znow je wprowadzil".

        NIE zamyka socketu. Trzy miejsca robia po bledzie jawne `ws.close()`
        z ROZNYMI kodami (1008 dla zlego wejscia, 1011 dla awarii storage) —
        to musi zostac ich decyzja, nie ukrytym efektem helpera."""
        await ws.send(protocol.dumps(protocol.make_frame(
            "error", "server", time.time(), text=text, **fields)))

    async def _send(self, nick, payload):
        data = protocol.dumps(payload)
        for ws in list(self.conns.get(nick, ())):
            try:
                await ws.send(data)
            except websockets.exceptions.ConnectionClosed:
                pass

    async def _close_stale_sockets(self, nick):
        # Niezmiennik a): wywolywane w momencie takeover (bump generacji przy
        # nowym hello) — zamyka KAZDY dotychczasowy socket tego nicka zanim
        # dolaczy nowy, zeby nic wiecej do nich nie trafilo (routing/_send).
        # Usuniecie z conns MUSI byc SYNCHRONICZNE — przed pierwszym await.
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
                await old_ws.send(protocol.dumps(protocol.make_frame(
                    "error", "server", time.time(), text=STALE_GENERATION)))
            except websockets.exceptions.ConnectionClosed:
                pass
            try:
                await old_ws.close(code=4001, reason="takeover")
            except websockets.exceptions.ConnectionClosed:
                pass

    def _bylby_adresatem(self, event, nick, role, groups):
        """Czy ta ramka POSZLABY na zywo do tego nicka, gdyby byl podlaczony?

        Istnieje po to, zeby dogonienie okna takeoveru dostarczalo DOKLADNIE
        to, co dostarczylby routing na zywo — ani mniej, ani wiecej. Replay
        wszystkiego po kolei wysylalby agentom `takeover`, ktory z zasady
        idzie tylko do ludzi, i lamal niezmiennik "live push do agentow jest
        WYLACZNIE wzmiankowy" — kazda ramka wyslana agentowi kosztuje go
        tokeny, wiec nie ma "przy okazji dosle jeszcze to"."""
        if event.get("from") == nick:
            return False
        typ = event.get("type")
        if typ == "kick":
            return True              # jedyny udokumentowany wyjatek od reguly
        if typ == "takeover":
            return role == "human"   # patrz _announce_takeover
        if typ not in ("chat", "fyi"):
            return False
        if role == "human":
            return True              # ludzie slysza kanal bez wzmianek
        if typ == "fyi":
            return False             # `fyi` z definicji nie budzi agentow
        tekst = event.get("text", "")
        wzmianki = protocol.parse_mentions(tekst)
        if "all" in wzmianki or nick in wzmianki:
            return True
        return bool(protocol.parse_groups(tekst) & set(groups))

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

    async def _handle_chat(self, frame, nick, ws):
        text = frame.get("text", "")
        mentions = protocol.parse_mentions(text)
        groups_mentioned = protocol.parse_groups(text)
        known_groups = {g for gs in self.groups.values() for g in gs}
        unknown_groups = sorted(g for g in groups_mentioned if g not in known_groups)
        # To samo dla NICKA: wzmianka do nieistniejacego nicka nie budzi
        # nikogo, a bez ostrzezenia nadawca uznaje, ze sie odezwal, i czeka
        # na odpowiedz, ktora nie przyjdzie. Kto istnieje, wie
        # WYLACZNIE hub — wiec to fizyka, nie uprzejmosc; zaden skill ani
        # konwencja tego nie zastapi. Ramka i tak idzie do logu: ostrzezenie
        # nie jest odmowa, tylko informacja, ze wolanie poszlo w prozne.
        znani = set(self.registry.roles) | set(self.conns)
        nieznane_nicki = sorted(
            m for m in mentions if m != "all" and m not in znani)

        # TRWALOSC PRZED PUBLIKACJA DOTYCZY TAKZE OSTRZEZEN, nie tylko ramki,
        # o ktorej one mowia. Ostrzezenie wyslane przed zapisem publikuje fakt
        # o trwalosci, zanim trwalosc zaistnieje: gdy zapis rzuci `OSError`,
        # nadawca dostaje obietnice logu, a chwile pozniej `storage
        # unavailable; retry`, i musi zgadywac, ktore zdanie jest prawdziwe.
        # Dlatego ostrzezenia wychodza ponizej, po zapisie — gdy zapis padnie,
        # nie wychodzi zadne z nich.
        # `target` jest polem AUTORYTATYWNYM (AGENTS.md, lista inwariantow) —
        # a chat go nie ma: adresatow wyznacza wylacznie wzmianka w TRESCI
        # (`_publish_chat`), wiec dla ramki chat wartosc autorytatywna to BRAK.
        # Routing jej nie czyta (pilnuje tego
        # `test_target_z_ramki_chat_nie_wplywa_na_routing`), ale ramka w logu
        # KLAMALABY o tym, kto jest adresatem, a `read`/`listen --json` oddaja
        # ja wiernie kazdemu, kto po nia siegnie. Zdjecie MUSI byc przed
        # `_append`: log jest tym artefaktem, ktory przezyje pokoj.
        frame.pop("target", None)
        seq = self._append(frame)  # trwaly zapis PRZED publikacja (niezmiennik f)
        frame["seq"] = seq
        if unknown_groups:
            # Ostrzezenie musi powiedziec, co sie stalo z RAMKA, nie tylko co
            # jest nie tak ze wzmianka. Samo "unknown group: X" agenci biora
            # za "`$nieznana` zjada cala wiadomosc" i zapisuja to sobie jako
            # fakt — choc ramka idzie do logu i budzi wzmianki `@nick`.
            # Howto mowi prawde, ale nie tam, gdzie patrzy sie z komunikatem
            # bledu przed oczami.
            #
            # "no participant has that group" jest doslowne, nie retoryczne:
            # `known_groups` liczy sie z CALEGO rejestru, wiec grupa, ktorej
            # czlonkowie tylko spia, jest znana i nie trafia tutaj (ta sama
            # regula co dla wzmianki do rozlaczonego nicka). Grupa pusta nie
            # istnieje — czlonkostwo JEST jej istnieniem.
            #
            # Do GNIAZDA nadawcy (`_error(ws, ...)` jak kazdy inny blad),
            # nie do wszystkich gniazd nicka: `send` dzieli tozsamosc
            # z nasluchem, ktory pod --wake budzilby agenta drugi raz o tym
            # samym.
            await self._error(
                ws,
                f"unknown group: {', '.join(unknown_groups)} — no "
                     f"participant has that group, so NO AGENT wakes up "
                     f"through it. This is a warning, NOT a rejection: the "
                     f"frame is routed like any other chat — into the log, to "
                     f"connected humans, and to mentions of participants who "
                     f"do exist. A group exists only where a human or $admin "
                     f"made one (membership_set); a new room has none.")
        if nieznane_nicki:
            # "zaden AGENT", nie "nikt". Ludzie dostaja kazdy chat niezaleznie
            # od wzmianek (_publish_chat dokłada wszystkie podlaczone role
            # human), wiec "nikogo nie obudzila" byloby NIEPRAWDA przy
            # podlaczonym czlowieku. I "przez TE wzmianke", nie "ta ramka":
            # ta sama ramka moze budzic poprawna wzmianke
            # (`@beta css: @font-face`). Tekst wzorowany 1:1 na galezi
            # grupowej wyzej.
            await self._error(
                ws,
                f"unknown nick: {', '.join(nieznane_nicki)} — there is no "
                     f"such participant, so NO AGENT wakes up through it. This "
                     f"is a warning, NOT a rejection: the frame is routed "
                     f"like any other chat — into the log, to connected "
                     f"humans, and to mentions of participants who do exist. "
                     f"Who is on the channel: agentmachi board.")
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
        # Role deklarowana w hello jest tylko WALIDOWANA (przypisanie
        # pochodzi z configu serwera — niezmiennik d) — ale jesli podana,
        # musi byc NIEPUSTYM stringiem (AGENTS.md: typ + niepustosc). role=[]
        # oraz role="" to blad wejscia do nadawcy.
        if value is not None and (not isinstance(value, str) or not value):
            raise AuthError(f"invalid role: {value!r}")
        return value

    # -- handler -----------------------------------------------------------
    def _orientacja(self):
        """rules/howto/participants — czesc odpowiedzi na hello, ktora nie
        zalezy od kursora. Wspolna dla wejscia i podgladu (`peek`)."""
        extra = {}
        rules_text, rules_hash = self._load_rules()
        if rules_text is not None:
            extra["rules"] = rules_text
            extra["rules_hash"] = rules_hash
        howto_text = self._load_howto()
        if howto_text is not None:
            extra["howto"] = howto_text
        # Roster musi byc cursor-coherent
        # i JAWNY dla kazdego uczestnika: czlowiek renderuje z niego TUI,
        # agent czyta board ("kto tu jest, kto co robi") — starsze ramki
        # status leza przed oknem kontekstu agenta, wiec snapshot w hello
        # to jedyne zrodlo pelnego stanu. Live push do agentow pozostaje
        # wylacznie wzmiankowy — to jest odpowiedz na hello, nie budzenie.
        extra["participants"] = self._participants_snapshot()
        return extra

    async def _odpowiedz_podgladem(self, ws, nick, role, groups, last_seq,
                                   generation):
        """Hello `peek`: ta sama odpowiedz, ZERO sladu w pokoju.

        `board` i `read` pytaja "kto tu jest" / "co jest w logu". Pelne
        hello dopisaloby patrzacego do rejestru na stale (literowka w
        `--nick` tworzylaby nick-ducha, ktory gasi ostrzezenie "unknown
        nick"), wpieloby go do `conns` (board pokazywalby pytajacego jako
        connected) i dopisalo event do logu (patrzenie postarzaloby kazdy
        status). Tu: auth przeszedl na klonie, klon idzie do kosza, nic
        nie trafia na dysk, socket nie wchodzi do `conns`, odpowiedz i koniec.

        Stan wysylany przy resync to stan ZYWY, etykietowany `last_seq` logu —
        durable-first gwarantuje, ze zywy stan to dokladnie stan po ostatnim
        evencie, wiec etykieta jest prawdziwa bez pisania snapshotu."""
        backlog = self.log.events_after(last_seq)
        koniec = self.log.last_seq
        # `peek=True` w odpowiedzi to POTWIERDZENIE: hub sprzed tej zmiany
        # ignoruje pole i robi pelne wejscie, a klient bez echa nie odrozni
        # podgladu od wejscia — patrz send._ostrzez_gdy_hub_wpisal.
        wspolne = dict(nick=nick, generation=generation, role=role,
                       groups=list(groups), peek=True, **self._orientacja())
        if backlog is None:
            reply = protocol.make_frame(
                "resync_required", "server", time.time(),
                snapshot_seq=koniec, state=self._stan_trwaly(),
                conversation=[protocol.clamp_frame(e)
                              for e in self.log.conversation_after(last_seq)],
                **wspolne)
        else:
            reply = protocol.make_frame(
                "ok", "server", time.time(),
                backlog=[protocol.clamp_frame(e) for e in backlog
                         if e.get("type") != "hello"],
                last_seq=koniec, **wspolne)
        await ws.send(protocol.dumps(reply))

    async def _handler(self, ws):
        nick = None
        try:
            raw = await ws.recv()
            try:
                frame = _strict_json_loads(raw)
            except ValueError:
                await self._error(ws, "invalid json")
                await ws.close(code=1008, reason="invalid json")
                return
            if not isinstance(frame, dict):
                # niezmiennik e): skalar/lista jako JSON nie moze zabic
                # handlera przez .get() na nie-dict — error + jawne zamkniecie
                await self._error(ws, "frame must be a JSON object")
                await ws.close(code=1008, reason="frame must be a JSON object")
                return
            if frame.get("type") != "hello":
                await self._error(ws, "the first frame must be hello")
                return
            # Pierwsze hello przez WSPOLNY schemat (type/from/ts) PRZED auth —
            # inaczej hello bez ts / z from=[] dostaje ok i trafia do logu
            # (niestandardowy/niekompletny event). Gleboka
            # walidacja hello (instance_id/token/last_seq/groups/role) zostaje w
            # identity/serwerze ponizej.
            hello_err = protocol.validate(frame)
            if hello_err:
                await self._error(ws, hello_err)
                return
            nick_candidate = frame.get("from")
            # niezmiennik a): generacja SPRZED tego hello — potrzebna zeby
            # odroznic zwykly reconnect (ten sam instance_id, bez bumpa) od
            # faktycznego takeover (bump), zeby wiedziec czy stare sockety
            # trzeba zamknac natychmiast
            old_gen = (self.registry.generation_of(nick_candidate)
                       if isinstance(nick_candidate, str) else 0)
            try:
                last_seq = self._validate_last_seq(frame.get("last_seq"))
                # Kursor spoza logu (last_seq > serwerowy last_seq) to
                # jawny blad — klient nie mogl widziec eventow, ktorych serwer
                # nie ma; bez tego dostawalby ciche ok+pusty backlog.
                #
                # Komunikat NIESIE NAPRAWE, bo bez niej odmowa jest slepym
                # zaulkiem: kursor klienta jest per host:port (patrz
                # send.hub_id_from_url), wiec KAZDY nowy hub postawiony na
                # porcie po poprzednim dziedziczy jego kursory i zamurowuje
                # wszystkich, ktorzy tam wczesniej byli. Reset kursora robi
                # CZLOWIEK — kontrakt
                # client_session jest fail-closed i nie resetuje po cichu.
                if last_seq > self.log.last_seq:
                    raise CursorBeyondLog(
                        self.log.last_seq,
                        f"last_seq {last_seq} > server last_seq "
                        f"{self.log.last_seq}: your cursor comes from a "
                        f"DIFFERENT log — usually from a previous hub on the "
                        f"same port. Fix: delete your session file "
                        f"(~/.chat-sessions/<nick>-<hash>.json) = a "
                        f"deliberate full resync from zero")
                # niezmiennik d): groups/role w hello sa TYLKO walidowane —
                # przypisanie faktyczne pochodzi WYLACZNIE z configu serwera
                # (registry.role_of/groups_of), nigdy z deklaracji klienta.
                self._validate_groups(frame.get("groups"))
                self._validate_role(frame.get("role"))
                # PROVISIONAL-THEN-COMMIT dla Registry: hello mutuje
                # tozsamosc (bump generacji + zapis
                # instance) na KLONIE, nie na live. AuthError leci Z KLONA ZANIM
                # cokolwiek trwalego/live sie zmieni (auth-fail => error, zero
                # mutacji, zero appendu). generation to na razie PREVIEW —
                # commit dopiero po udanym durable appendzie. Registry to male
                # dicty (nick->gen, nick->instance), wiec deepcopy-per-hello to
                # swiadomy, tani trade-off — hello jest rzadki (nie hot-path).
                trial_registry = copy.deepcopy(self.registry)
                # W trybie otwartym agent moze wejsc BEZ tokenu. Rola
                # human wymaga go zawsze (open_hello odmawia), a tryb otwarty
                # wlacza sie wylacznie przy bindzie loopback/tailnet — patrz
                # _open_bind(). Nick zajety przez ZYWE polaczenie nie jest
                # odbierany (nizej): martwe sockety wypadaja same dzieki
                # keepalive, wiec "zajety" znaczy "zajety naprawde".
                # Adres, do ktorego to hello przypina tozsamosc. Musi byc
                # zwiazany PRZED galezia, bo sciezka tokenowa go nie ustawia,
                # a event budujemy wspolnie dla obu.
                open_addr = None
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
                    # Adres wiazania. Aktywny TYLKO przy bindzie na
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
                            await self._error(
                                ws, "hub behind a proxy/tunnel — entry "
                                    "without a token is unavailable; pass "
                                    "CHAT_TOKEN")
                            return
                        addr = host
                    # Odmowa TYLKO gdy zywy nick nalezy do INNEGO instance_id.
                    # Ten sam instance = wlasny self-resume/self-send (send/frame
                    # wspoldziela tozsamosc listenera, zeby nie robic takeoveru)
                    # — musi przejsc jak na sciezce tokenowej. Bez tego
                    # zdalny agent bez tokenu nie moze wyslac ramki,
                    # trzymajac nasluch.
                    if (isinstance(zadany, str) and self.conns.get(zadany)
                            and trial_registry.role_of(zadany) != "human"
                            and self.registry.instance_of(zadany)
                                != frame.get("instance_id")):
                        wolny = self._wolny_nick()
                        # Propozycja idzie POLEM, nie tylko w tresci.
                        # Tekst czyta czlowiek; klient potrzebuje wartosci,
                        # ktorej nie musi wydlubywac ze stringa. Bez tego
                        # agent, ktoremu nick zajal ktos inny, utyka, majac
                        # propozycje przed oczami.
                        await self._error(
                            ws,
                            f"nick {zadany} is taken by a connected "
                            f"participant; free nick: {wolny}",
                            suggested_nick=wolny)
                        return
                    # Host-check + zapis wiazania — w open_hello, na trial
                    # (provisional-then-commit). Inny adres na przypiety nick =
                    # AuthError (lapane nizej jak kazdy blad open_hello).
                    generation = trial_registry.open_hello(
                        zadany, frame.get("instance_id"), addr)
                    open_addr = addr   # do EVENTU — snapshot sam nie wystarcza
                else:
                    generation = trial_registry.hello(
                        frame.get("from"), frame.get("instance_id"),
                        frame.get("token"))
            except AuthError as e:
                # Pole doklada WYLACZNIE ta jedna odmowa (patrz
                # CursorBeyondLog). Nie dopisujemy go do kazdego bledu auth:
                # zly token nie ma prawa dowiedziec sie, jak dlugi jest log
                # pokoju, do ktorego wlasnie nie wszedl.
                pola = ({"server_last_seq": e.server_last_seq}
                        if isinstance(e, CursorBeyondLog) else {})
                await self._error(ws, str(e), **pola)
                return
            nick = frame["from"]
            # role jest stala z configu; groups to aktualny, trwaly stan
            # serwera. Deklaracja hello zadnego z nich nie nadpisuje.
            # Z KLONA, nie z live: w trybie otwartym nowy nick dostaje role
            # i grupy dopiero w open_hello, czyli na klonie — live jeszcze go
            # nie zna, bo swap nastepuje po durable appendzie. Czytanie z live
            # daloby agentowi PUSTE grupy: technicznie na kanale, praktycznie
            # gluchy na wzmianki grupowe.
            role = trial_registry.role_of(nick)
            groups = trial_registry.groups_of(nick)
            # backlog liczony PRZED zalogowaniem WLASNEGO hello — inaczej
            # klient zawsze widzialby wlasna ramke hello w swoim backlogu i
            # "last_seq == biezacy cursor" po reconnnekcie nigdy by nie
            # dawalo pustego backlogu (por. test_reconnect_resumes_from_last_seq)
            # KONTRAKT: backlog jest NIEFILTROWANY. Filtr wzmianek
            # dotyczy wylacznie live push (_publish_chat) — spiacy agent nie placi
            # za cudza rozmowe. Replay od kursora zwraca pelny log kazdemu
            # uwierzytelnionemu: selekcje robi node/agent, nie hub. Node (wake)
            # pobiera tedy kontekst — filtr tutaj = amnezja agentow tylnymi drzwiami.
            #
            # Wejscie fresh: agent wpuszczony po NIEZALEZNA perspektywe
            # nie moze dostac cudzego rozumowania — po dostarczeniu nie da
            # sie go "nie przeczytac", kotwica siedzi juz w oknie kontekstu.
            # Zadna instrukcja w howto tego nie cofnie, wiec to fizyka, nie
            # zachowanie: co dociera przy wejsciu, decyduje wylacznie hub.
            # Realizacja: kursor na biezacy koniec logu PRZED policzeniem
            # backlogu — obie galezie odpowiedzi (resync i ok) wychodza wtedy
            # puste same z siebie, zero rozgalezien w konstrukcji reply.
            # rules/howto/participants ida normalnie: odbieramy KOTWICE, nie
            # ORIENTACJE. Walidacja `last_seq` wyzej zostaje nietknieta —
            # ocenia to, co klient PRZYSLAL, a nie to, co mu podstawiamy.
            if frame.get("context") == "fresh":
                last_seq = self.log.last_seq
            if frame.get("peek") is True:
                # Podglad: auth przeszedl na klonie, ktory tu porzucamy.
                # Generacja ZYWA (old_gen), nie podbita na klonie.
                await self._odpowiedz_podgladem(ws, nick, role, groups,
                                                last_seq, old_gen)
                nick = None   # finally nie ma czego wypinac z conns
                return
            backlog = self.log.events_after(last_seq)
            # DURABLE-FIRST (niezmiennik f): mutacja tozsamosci jest
            # TRWALA PRZED live-swapem i JAKIMKOLWIEK side-effectem. Durable
            # append NAJPIERW (bez tokenu — sekret nigdy na dysk; bez auto-
            # snapshotu, patrz _maybe_snapshot na koncu). Gdy rzuci (np. OSError/
            # dysk pelny): self.registry NIETKNIETY (klon wyrzucony), ZADEN stary
            # socket nie zamkniety, conns bez zmian — klient dostaje
            # error/rozlaczenie, a retry moze legalnie powtorzyc (kolejny bump
            # idzie znow na swiezym klonie, wiec generacja podbija sie DOKLADNIE
            # raz). instance_id jest juz zwalidowany przez trial_registry.hello.
            try:
                # `open_addr` w EVENCIE, nie tylko w snapshocie: w trybie
                # otwartym wiazanie nick->adres jest JEDYNYM dowodem
                # tozsamosci (nie ma tokenu), a snapshot zapisuje sie co
                # SNAPSHOT_EVERY eventow. Bez tego hello po ostatnim
                # snapshocie ginie przy crashu — i podszywacz odbijany przed
                # padem przechodzi po nim. Pole nie kosztuje
                # agentow kontekstu: `wire_backlog` wycina hello z drutu,
                # a hello nie jest w CONVERSATION_TYPES. Na DYSKU jest jawne —
                # kto czyta events.jsonl, widzi adresy peerow. To ten sam
                # tailnet, na ktorym wszyscy sie i tak widza, ale warto o tym
                # wiedziec, zanim ktos wystawi log poza maszyne operatora.
                self._append_durable(protocol.make_frame(
                    "hello", nick, time.time(),
                    instance_id=frame.get("instance_id"),
                    groups=list(groups), role=role,
                    # ZAWSZE, takze gdy None. Obecnosc KLUCZA (nie wartosci)
                    # odroznia nowy format od starego — a to jedyny sposob,
                    # zeby replay wiedzial, czy brak adresu znaczy "to hello
                    # swiadomie nic nie wiazalo" (token / bind loopback), czy
                    # "log sprzed tego pola, nie wiadomo". Bez klucza replay
                    # bierze legalne hello TOKENOWE za stary format i naklada
                    # na nie zaslepke.
                    open_addr=open_addr))
                # KONIEC BACKLOGU zamrozony TUTAJ, nie przy budowaniu
                # odpowiedzi. Miedzy tym punktem a wyslaniem reply sa awaity
                # (zamkniecie starych socketow — do close_timeout, gdy stary
                # klient jest trupem — plus announce takeover), a nick nie
                # jest w tym czasie w `conns`. Ramka wyslana w tym oknie
                # laduje w logu, NIE idzie live i wliczalaby sie do
                # `self.log.last_seq` czytanego pozno — czyli klient
                # przesuwalby kursor ZA nia i nie zobaczylby jej nigdy.
                # Takeover zdarza sie przy kazdym restarcie procesu agenta,
                # wiec to nie jest rzadki wyscig.
                koniec_backlogu = self.log.last_seq
            except OSError:
                # niezmiennik e: awaria storage (dysk pelny) na hello NIE moze
                # zabic handlera brutalnym 1011 — hello odpowiada czysta ramka
                # error i dopiero potem graceful close. Stan pozostaje
                # czysty (klon wyrzucony, registry nietkniety, zero side-effektow
                # bo sa PO tym appendzie), a klient odroznia storage-fail od padu
                # sieci i moze legalnie retry. Pelny wyjatek (w tym sciezka FS)
                # trafia WYLACZNIE do logu operatora; klient dostaje staly tekst.
                LOGGER.exception("storage failure during hello for nick=%r", nick)
                await self._error(ws, STORAGE_UNAVAILABLE)
                await ws.close(code=1011, reason="storage unavailable")
                return
            # COMMIT: dopiero po udanym durable appendzie swap live=klon, a
            # POTEM side-effects (takeover close + rejestracja socketu).
            self.registry = trial_registry
            if generation != old_gen:
                # niezmiennik a): takeover — odetnij stare sockety TERAZ (po
                # trwalym fakcie), nie dopiero przy ich kolejnej (moze nigdy nie
                # nadejsc) ramce
                await self._close_stale_sockets(nick)
            # Slad TYLKO dla faktycznego wyparcia. old_gen == 0 to
            # pierwsze hello tego nicka — nikogo nie wypiera, wiec nie ma o
            # czym meldowac (reconnect z tym samym instance_id nie bumpuje
            # generacji, wiec tez tu nie wpada).
            if generation != old_gen and old_gen:
                await self._announce_takeover(nick, generation, old_gen)
            self.conns.setdefault(nick, set()).add(ws)
            self.roles[nick] = role
            self.groups[nick] = set(groups)
            extra = self._orientacja()
            if backlog is None:
                # niezmiennik b): resync spojny — snapshot_seq zwracany
                # klientowi musi etykietowac DOKLADNIE ten state, ktory
                # wysylamy. Gdy stan rozni sie od tego na dysku, swiezy
                # atomowy snapshot jest obowiazkowy. Gdy jest IDENTYCZNY,
                # kolejna kompakcja bylaby nie tylko zbedna, ale szkodliwa:
                # dwa klienty listen --once przeskakiwalyby sobie snapshotem
                # po kazdym bezmutacyjnym hello i zaden nigdy by nie blokowal.
                #
                # W tym drugim przypadku biezacy last_seq jest legalna,
                # swieza etykieta TEGO SAMEGO stanu. Nie zmieniamy globalnego
                # snapshot_seq Store, wiec drugi klient moze dogonic zwyklym
                # backlogiem; klient tego resyncu stawia kursor za eventami,
                # ktore stan juz obejmuje, i nie odtwarza ich drugi raz.
                wire_state = self._stan_trwaly()
                persisted = self.log.load_snapshot()
                if persisted is None or persisted[0] != wire_state:
                    self.snapshot()
                    wire_snapshot_seq = self.log.snapshot_seq
                else:
                    wire_snapshot_seq = self.log.last_seq
                # Wire resync state = DOKLADNIE persisted snapshot state
                # (_stan_trwaly), nie okrojony.
                # Resync niesie takze PAMIEC kanalu. `state` odtwarza rejestr
                # i board (registry/status), ale rozmowy nie odtworzy nic —
                # a to ona jest jedyna pamiecia agenta. Bez tego agent po
                # kompakcji wchodzi na kanal, na ktorym "nic sie nigdy nie
                # wydarzylo".
                reply = protocol.make_frame(
                    "resync_required", "server", time.time(),
                    nick=nick,   # KIM jestes — takze na sciezce resync, nie
                                 # tylko w ok (agent bez wlasnej propozycji
                                 # nicka, ktory po kompakcji trafia na resync,
                                 # inaczej nigdy nie pozna przydzielonego nicka)
                    snapshot_seq=wire_snapshot_seq,
                    state=wire_state,
                    # clamp: log sprzed sufitu wejscia moze trzymac ramki
                    # blisko 1 MiB — patrz protocol.clamp_frame.
                    conversation=[protocol.clamp_frame(e)
                                  for e in self.log.conversation_after(last_seq)],
                    generation=generation, role=role, groups=list(groups), **extra)
            else:
                # Backlog NA DRUCIE pomija ramki hello (bywaja ponad polowa
                # backlogu). Log na dysku je zachowuje (potrzebne do replayu
                # generacji przy restarcie) — filtrujemy wylacznie to, co
                # idzie do klienta. Roster i tak przychodzi autorytatywnie
                # w participants, wiec agent
                # placi kontekstem za czysty szum bez tego filtra. last_seq
                # PONIZEJ zostaje self.log.last_seq (prawdziwy koniec logu),
                # NIGDY seq ostatniej ramki po filtrowaniu — inaczej klient
                # zapetlalby sie prosząc w kolko o ramki, ktorych nigdy nie
                # dostanie (por. test_reconnect_with_wire_last_seq_gives_
                # empty_backlog_no_loop).
                wire_backlog = [protocol.clamp_frame(e) for e in backlog
                                if e.get("type") != "hello"]
                reply = protocol.make_frame(
                    "ok", "server", time.time(),
                    nick=nick,   # KIM jestes — jawnie, nie do wywnioskowania
                                 # z participants (agent bez
                                 # wlasnej propozycji nicka inaczej nie wie,
                                 # kim zostal, a przy dwoch swiezych
                                 # wejsciach naraz zgadywanie sie lamie)
                    generation=generation, role=role, groups=list(groups),
                    backlog=wire_backlog, last_seq=koniec_backlogu, **extra)
            await ws.send(protocol.dumps(reply))
            # DOGONIENIE OKNA: co przyszlo, gdy nick byl juz wypiety z conns,
            # a nowy socket jeszcze nie wpiety. Kursor klienta stoi na
            # `koniec_backlogu`, wiec tych ramek nie przeskoczy — ale sam
            # z siebie dostalby je dopiero przy NASTEPNYM reconnekcie, czyli
            # wzmianka obudzilaby go z opoznieniem albo wcale. Duplikaty sa
            # bezpieczne: klient tnie po `seq <= last_applied_seq`, wiec
            # ramka doreczona juz na zywo zostanie tu odrzucona.
            # `events_after` zwraca None jako SYGNAL "resync_required", nie
            # jako pusta liste. Gdy galaz resync zrobila wyzej pelny
            # `snapshot()`, granica lezy ZA `koniec_backlogu` i dostajemy
            # None. Gdy stan byl identyczny z persisted snapshotem, globalna
            # granica sie nie rusza i dogonienie normalnie zwraca eventy.
            # `or ()` obsluguje obie legalne sciezki; iteracja po None wprost
            # wywala handler kodem 1011.
            #
            for zdarzenie in (self.log.events_after(koniec_backlogu) or ()):
                if self._bylby_adresatem(zdarzenie, nick, role, groups):
                    await ws.send(protocol.dumps(
                        protocol.clamp_frame(zdarzenie)))
            await self._push_presence(nick, True)
            # Hello append jest durable-only (bez auto-snapshotu) —
            # domykamy polityke snapshot-co-100 tutaj, PO swapie live=klon, zeby
            # ewentualny snapshot #100 zlapal juz NOWA generacje. Resync,
            # ktory zmienil stan, zrobil pelny snapshot() wyzej (licznik=0);
            # resync stanu identycznego swiadomie go nie robil, wiec polityka
            # co-100 nadal ma tu prawo zadzialac.
            self._maybe_snapshot()
            await self._frame_loop(ws, nick, generation)
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

    async def _announce_takeover(self, nick, generation, old_gen):
        """Trwaly slad wyparcia nicka + rozgloszenie go ludziom NA ZYWO.

        Bez tego wyparty agent znika po cichu: dla reszty kanalu wciaz jest
        "connected", a jego nasluch juz nic nie slyszy — agent-widmo, ktory
        milczy i nikt nie wie dlaczego. Slad jest TRWALY
        (nie efemeryczny jak presence), bo pytanie "dlaczego zamilkl" pada
        PO fakcie.

        Wolane WYLACZNIE po `self.registry = trial_registry` i po
        `_close_stale_sockets` — opisuje fakt JUZ utrwalony. Wewnatrz
        kolejnosc jest czescia kontraktu: durable append PRZED publikacja.

        Osobna funkcja, bo petla rozgloszenia w _handler REBINDOWALABY
        zmienna `role` — autorytatywna role wchodzacego z tego samego scope.
        Wlasny scope funkcji czyni te klase bledu niemozliwa — patrz
        test_takeover_nie_podmienia_roli_gdy_human_wszedl_ostatni."""
        takeover = protocol.make_frame(
            "takeover", "server", time.time(), nick=nick,
            generation=generation, previous_generation=old_gen,
            text=(f"{nick}: a new connection took over the previous one "
                  f"(generation {old_gen} -> {generation}); "
                  f"old sockets closed"))
        seq = self._append_durable(takeover)   # trwalosc PRZED publikacja
        event = {**takeover, "seq": seq}
        # Push NA ZYWO tylko do ludzi — tak samo jak presence: to oni reaguja
        # na widmo (restart, ubicie klienta), a agentow nie budzimy ramka bez
        # wzmianki. Agenci dostana ten slad z logu przy swoim najblizszym
        # hello: takeover jest w CONVERSATION_TYPES, wiec wraca
        # w 'conversation' i przezywa kompakcje.
        # kopia PRZED await — patrz _push_presence. Tu boli najbardziej:
        # RuntimeError leci PO zamknieciu starego socketu, a PRZED
        # zarejestrowaniem nowego, wiec nick zostaje bez zadnego polaczenia.
        for other, rola in list(self.roles.items()):
            if rola == "human" and other != nick and self.conns.get(other):
                await self._send(other, event)

    async def _frame_loop(self, ws, nick, generation):
        """Petla ramek po udanym hello. `generation` PRZYCHODZI ARGUMENTEM —
        niezmiennik a) mowi, ze jest przypieta do SOCKETU, wiec nie wolno jej
        tu odczytywac z self.registry.

        Drabina wyjatkow jest per-RAMKA i musi taka zostac: niezmiennik e)
        brzmi "zaden pojedynczy zly frame nie moze zabic handlera". Gdyby
        `except Exception` opasywal cala petle zamiast pojedynczy obieg,
        pierwsza zla ramka konczylaby polaczenie."""
        async for raw in ws:
            try:
                frame = _strict_json_loads(raw)
            except ValueError:
                await self._error(ws, "invalid json")
                continue
            if not isinstance(frame, dict):
                # niezmiennik e): w petli — error bez rozlaczania
                await self._error(ws, "frame must be a JSON object")
                continue
            try:
                stop = await self._on_frame(frame, nick, generation, ws)
            except websockets.exceptions.ConnectionClosed:
                # ROZLACZENIE, NIE AWARIA. ConnectionClosed nie jest podklasa
                # OSError (MRO: ConnectionClosed -> WebSocketException ->
                # Exception), wiec bez tej galezi wpada nizej i loguje pelny
                # traceback jako "internal frame failure" — rutynowe
                # rozlaczenia rozcienczaja jedyny sygnal, ktory ma cos
                # znaczyc dla operatora. Wychodzimy z petli — obsluge
                # przejmuje `except ConnectionClosed` w _handler.
                raise
            except OSError:
                # Storage detail moze zawierac errno i absolutna sciezke.
                # Loguj go operatorowi, ale nigdy nie odbijaj klientowi.
                LOGGER.exception(
                    "storage failure for nick=%r type=%r command_id=%r",
                    nick, frame.get("type"), frame.get("command_id"))
                await self._error(ws, STORAGE_UNAVAILABLE,
                                  command_id=frame.get("command_id"))
                stop = False
            except Exception:
                # Ostatnia linia obrony (niezmiennik e): detal tylko w logu,
                # odpowiedz publiczna nie ujawnia implementacji ani sciezek.
                LOGGER.exception(
                    "internal frame failure for nick=%r type=%r command_id=%r",
                    nick, frame.get("type"), frame.get("command_id"))
                await self._error(ws, "internal error",
                                  command_id=frame.get("command_id"))
                stop = False
            if stop:
                break

    async def _on_frame(self, frame, nick, sock_gen, ws):
        # niezmiennik a): generation przypieta do SOCKETU, nie frame.get(...)
        if self.registry.generation_of(nick) != sock_gen:
            await self._error(ws, STALE_GENERATION,
                              command_id=frame.get("command_id"))
            return True  # zamknij petle tego (juz nieaktualnego) polaczenia
        err = protocol.validate(frame)
        if err:
            # error niesie command_id z ramki, jesli byl — aktualne typy inbound
            # go nie uzywaja (-> None, nieszkodliwe); pole zostaje dla korelacji,
            # gdyby ktorys przyszly typ znow go wprowadzil.
            await self._error(ws, err, command_id=frame.get("command_id"))
            return False
        # niezmiennik f): pola autorytatywne (seq/generation/groups/role)
        # nadaje WYLACZNIE serwer. membership_set.groups jest tylko
        # zwalidowanym zadaniem zmiany; handler zapisze znormalizowany wynik
        # serwera.
        ftype = frame["type"]
        requested_groups = frame.get("groups") if ftype == "membership_set" else None
        for field in ("seq", "generation", "groups", "role"):
            frame.pop(field, None)
        frame["from"] = nick  # tozsamosc z hello, nie z ramki (pole autorytatywne)
        if ftype == "chat":
            await self._handle_chat(frame, nick, ws)
        elif ftype == "fyi":
            # PUBLIKACJA, NIE ZAWOLANIE: do logu i do ludzi, ale nie budzi
            # zadnego agenta. Bez niego jedyna droga publikacji jest
            # obudzenie wszystkich.
            seq = self._append(frame)
            frame["seq"] = seq
            for odbiorca, rola in list(self.roles.items()):
                if rola == "human" and odbiorca != nick and odbiorca in self.conns:
                    await self._send(odbiorca, frame)
        elif ftype == "status":
            target = frame.get("target") or nick
            # Prawo do CUDZEGO statusu nalezy do klasy uprawnien (`admin`),
            # nie do roli organizacyjnej: grupa dajaca tylko to jedno prawo
            # bylaby stanowiskiem wpisanym w silnik, a konstytucja mowi, ze
            # strukture zespolu wybieraja agenci, nie hub. `admin` ma juz
            # lancuch zaufania (wprowadza human/admin przez membership_set).
            if target != nick and not (
                    self.registry.role_of(nick) == "human"
                    or "admin" in self.registry.groups_of(nick)):
                await self._error(
                    ws, "forbidden: setting someone else's status requires "
                        "human or the admin group")
                return False
            frame["target"] = target  # pole autorytatywne: server-side default
            # DURABLE -> MUTACJA -> dopiero potem ewentualny snapshot (regula
            # z _append_durable). Przy `self._append(frame)` (durable
            # + snapshot naraz) z mutacja PO nim ramka status wypadajaca jako
            # event #100 trafia do snapshotu ze STARYM stanem, etykietowanego
            # jej wlasnym seq — a kompakcja usuwa ja z logu, bo `status` nie
            # jest w CONVERSATION_TYPES. Deklaracja przepada bezpowrotnie,
            # a widac to dopiero po PADZIE huba (czysty stop() robi wlasny
            # snapshot).
            seq = self._append_durable(frame)
            frame["seq"] = seq
            # `seq` przy statusie: board bez niego KLAMIE, a nie milczy
            # (patrz _participants_snapshot).
            # Wiek deklaracji zna WYLACZNIE serwer (agent nie widzi cudzego
            # zegara ani cudzego seq w chwili zapisu). Nie wygaszamy statusu
            # i nie wymuszamy aktualizacji — to byloby kodowanie zachowania.
            # Podajemy fakt i pozwalamy czytajacemu zdecydowac, czy ufa.
            self.status[target] = {k: frame[k] for k in
                                   ("state", "subject", "note")
                                   if k in frame}
            self.status_seq[target] = seq
            self._maybe_snapshot()   # dopiero TERAZ — stan jest juz domkniety
            # Status to CZYSTY fakt na boardzie — zero side-effectu
            # schedulera: `state=idle` nie dopisuje do zadnej kolejki ani nie
            # wyzwala oferty. Board jest pasywny.
            for observer, role in list(self.roles.items()):
                if role == "human" and observer != nick:
                    # live board dla TUI; agenci dostaja tylko backlog/preambule
                    await self._send(observer, frame)
        elif ftype == "workspace":
            # Bez _append: fakt o zywym kliencie, nie zdarzenie rozmowy.
            # Agentom nie wysylamy nic (zero wybudzen) — widza to na boardzie.
            stan = {k: frame[k] for k in ("worktree", "branch", "head")
                    if k in frame}
            if stan:
                self.workspace[nick] = stan
            else:
                # pusta ramka: listener z opt-outem albo spoza repo odwoluje
                # to, co zostalo po poprzednim wejsciu
                self.workspace.pop(nick, None)
            for observer, role in list(self.roles.items()):
                if role == "human" and observer != nick:
                    await self._send(observer, frame)
        elif ftype == "kick":
            await self._on_kick(frame, nick, ws)
        elif ftype == "membership_set":
            await self._on_membership_set(frame, requested_groups, nick, ws)
        else:
            await self._error(
                ws, f"unexpected frame type from a client: {ftype}")
        return False

    async def _on_kick(self, frame, nick, ws):
        """Moderacja — jedyna odpowiedz na pytanie 'kim jestes' w kanale bez
        tokenow dla agentow.

        Uprawnienie ma rola human (a human zawsze ma token, wiec to realne
        uprawnienie, nie umowa) albo grupa admin — patrz nizej.
        """
        now = time.time()
        target = frame["target"]
        # Moderacja: rola human ZAWSZE, plus grupa admin (agent, ktoremu
        # czlowiek jawnie ja nadal). Lancuch zaufania zostaje: do admina
        # wprowadza wylacznie human/admin przez membership_set, wiec agent nie
        # da sobie tej mocy sam.
        if (self.registry.role_of(nick) != "human"
                and "admin" not in self.registry.groups_of(nick)):
            await self._error(
                ws, "forbidden: kick requires the human role or the admin "
                    "group")
            return
        # Kick dziala na TOZSAMOSCI, nie na sockecie. To jedyna droga wyjscia
        # z zaslepki UNRESOLVED_ADDR (reklamuje ja komunikat open_hello),
        # a nick, ktorego wiazania nie dalo sie odtworzyc z logu, jest
        # z definicji ROZLACZONY — kick wymagajacy zywego polaczenia nie
        # mialby go jak zwolnic.
        #
        # Nieznany nick nadal odbija sie z bledem: moderacja ma dzialac na
        # uczestnikach tego pokoju, nie na dowolnym stringu.
        if not self.conns.get(target) and target not in self.registry.roles:
            await self._error(
                ws, f"kick: {target} is neither connected nor known to this "
                    f"room")
            return
        event = protocol.make_frame("kick", "server", now,
                                    target=target, by=nick)
        # DURABLE APPEND -> MUTACJA -> dopiero potem auto-snapshot. Ten sam
        # uklad co przy status i membership_set, i z tego samego powodu: gdy
        # ten event wypada na SNAPSHOT_EVERY-tym, `_append` robi snapshot
        # ZANIM zwolnimy wiazanie — snapshot utrwala stare (albo
        # UNRESOLVED_ADDR), a kick laduje NA snapshot_seq, wiec replay go nie
        # powtorzy. Moderator dostaje `ok`, a po restarcie tozsamosc jest
        # znowu zablokowana.
        seq = self._append_durable(event)
        # Rozkaz moderatora bije wiazanie — zwolnij przypiecie nick->adres,
        # zeby ten sam agent po re-IP (albo ktos inny) mogl wejsc na ten nick
        # z nowego adresu, a nick z zaslepka UNRESOLVED_ADDR mial jak wrocic.
        self.registry.release_open_addr(target)
        self._maybe_snapshot()
        event["seq"] = seq
        # ACK dla moderatora jest BEST-EFFORT — kolejnosc zostaje, znika
        # tylko mozliwosc wywrocenia nia calego rozkazu. Gdy socket
        # moderatora jest juz martwy (padlo TUI, zerwana siec, zamkniete
        # okno), niezabezpieczony `send` rzuca ConnectionClosed, handler
        # przerywa — i NIE wykonuje ani broadcastu kicka, ani close(4003).
        # Kick zostaje TRWALE w logu, a wyrzucony siedzi dalej na kanale: log
        # mowi "wyrzucony", kanal mowi "jest". Skutek rozkazu nie moze zalezec
        # od tego, czy rozkazodawca jeszcze zyje.
        #
        # ACK zostaje PRZED broadcastem: rozkazodawca poznaje wynik WLASNEJ
        # komendy przed cudzym ruchem (pilnuje tego test).
        try:
            await ws.send(protocol.dumps(protocol.make_frame(
                "ok", "server", now, target=target)))
        except websockets.exceptions.ConnectionClosed:
            pass
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
            text=f"kicked off the channel by {nick}"))
        for sock in list(self.conns.get(target, ())):
            try:
                await sock.close(code=4003, reason="kicked")
            except websockets.exceptions.ConnectionClosed:
                pass

    async def _on_membership_set(self, frame, requested_groups, nick, ws):
        """Przekaz funkcje przez grupy; bez RBAC, elekcji i CAS."""
        now = time.time()
        if (self.registry.role_of(nick) != "human"
                and "admin" not in self.registry.groups_of(nick)):
            await self._error(
                ws, "forbidden: membership_set requires human or the admin "
                    "group")
            return
        trial = copy.deepcopy(self.registry)
        try:
            groups = trial.set_groups(frame["target"], requested_groups)
        except AuthError as e:
            await self._error(ws, str(e))
            return
        event = {**frame, "groups": groups}
        seq = self._append_durable(event)
        event["seq"] = seq
        self.registry = trial
        self.groups[frame["target"]] = set(groups)
        self._maybe_snapshot()
        await ws.send(protocol.dumps(protocol.make_frame(
            "ok", "server", now, target=frame["target"], groups=groups)))
        if frame["target"] != nick:
            await self._send(frame["target"], event)
        for observer, role in list(self.roles.items()):
            if role == "human" and observer not in {nick, frame["target"]}:
                await self._send(observer, event)


def main():
    tokens_path = os.environ.get("CHAT_TOKENS", "tokens.json")
    tokens = json.loads(Path(tokens_path).read_text(encoding="utf-8"))
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
