#!/usr/bin/env python3
"""Klient CLI czatu agentow — RESUMOWALNY (Task 7 / t1).

Domyslnie protokol B1 (chat/server.py): hello + token + trwaly kursor.
  python3 send.py --as <nick> "@ktos tekst"  -> hello (kursor TYLKO czytany), chat, wyjscie
  python3 send.py --listen         -> hello od kursora, apply+advance, reconnect

Tryb --legacy dla starego PoC-huba (root server.py, czysty broadcast
{from,text}, bez hello/auth):
  python3 send.py --legacy <nick> "tekst"
  python3 send.py --legacy --listen

Env: CHAT_PORT (8765), CHAT_TOKEN (B1, wymagany — brak = fail-fast),
CHAT_NICK (dla --listen), CHAT_ROLE (default "agent"),
CHAT_SESSION_DIR (default ~/.chat-sessions).

Semantyka resumowalnosci (wsad b2 + review-guard):
- sesja per hub+nick (chat/client_session.py): instance_id + kursor,
- TYLKO listener przesuwa kursor, PO zastosowaniu ramki (at-least-once;
  duplikaty tlumione po seq, wybudzenia dodatkowo po activation_id),
- send_once wspoldzieli instance_id (zero takeover wlasnego listenera),
  kursor tylko czyta,
- resync_required: stan zastosowany, kursor = snapshot_seq,
- reconnect z ograniczonym backoffem (1..30 s), hello zawsze od kursora,
- uszkodzony plik sesji = fail-closed z instrukcja naprawy (SessionError),
- dokladnie jeden listener per hub+nick (listener-lock).
"""
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

import websockets

from chat.client_session import ListenerLockHeld, Session, SessionError

PORT = os.environ.get("CHAT_PORT", "8765")


def hub_id_from_url(url):
    """Kursor jest per hub+nick; hub_id = host:port URL-a (port domyslny
    schematu, gdy brak w URL — wss za tunelem publicznym nie niesie :443
    jawnie). UWAGA: ten sam hub widziany pod dwoma nazwami hosta = dwa
    kursory — at-least-once absorbuje ponowna dostawe: swiadomy koszt."""
    p = urlparse(url)
    if p.scheme not in ("ws", "wss") or not p.hostname:
        raise ValueError(f"CHAT_URL musi byc ws://host[:port] lub wss://: {url!r}")
    try:
        port = p.port
    except ValueError:
        raise ValueError(f"CHAT_URL ma niepoprawny port: {url!r}")
    port = port or (443 if p.scheme == "wss" else 80)
    return f"{p.hostname}:{port}"


URI = os.environ.get("CHAT_URL", f"ws://localhost:{PORT}")
HUB_ID = hub_id_from_url(URI)
HELLO_TIMEOUT = 10.0
# B6: kod zamkniecia, ktorym serwer sygnalizuje wyrzucenie przez moderatora
KICKED_CODE = 4003
BACKOFF_START, BACKOFF_MAX = 1.0, 30.0
LEGACY_SESSION_FILE = Path(__file__).with_name(".chat-session.json")


def _require_token():
    # B6: token jest OPCJONALNY. Hub w trybie otwartym (loopback/tailnet)
    # przyjmuje agenta bez sekretu — wymuszanie tokenu po stronie klienta
    # blokowalo dokladnie to, co serwer wlasnie dopuscil (ta sama rodzina
    # bledu co F10: jedna strona drutu pozwala, druga zabrania). Pusty
    # string = "wejdz bez tokenu"; hub zada go tylko, gdy stoi na 0.0.0.0.
    return os.environ.get("CHAT_TOKEN", "")


def _session(nick):
    return Session(HUB_ID, nick, legacy_instance_file=LEGACY_SESSION_FILE)


class _BootIdentity:
    """Tozsamosc TYMCZASOWA na pierwsze hello, gdy nick nada dopiero hub
    (B6/B7 open mode). NIE dotyka dysku: Session pod pustym nickiem nie
    istnieje (client_session.py fail-closed odrzuca ''), a kursor+lock
    zakladamy DOPIERO pod nadanym nickiem. Bez tego cala sciezka
    'wejscie bez nicka' padala na _session('') zanim hello wyszlo."""
    def __init__(self):
        self.instance_id = uuid.uuid4().hex
        self.last_applied_seq = 0


async def do_hello(ws, nick, session, token, role=None, context=None):
    hello = {
        "type": "hello", "ts": 0.0,
        "instance_id": session.instance_id,
        "last_seq": session.last_applied_seq,
        "role": role or os.environ.get("CHAT_ROLE", "agent")}
    if context:
        hello["context"] = context   # "fresh" = wejscie bez historii rozmowy
    if nick:
        hello["from"] = nick         # bez nicka hub nada go sam (B6)
    if token:
        hello["token"] = token       # tylko gdy jest — pusty wymusil sciezke
    await ws.send(json.dumps(hello)) # tokenowa po stronie huba (bad token)
    try:
        reply = json.loads(await asyncio.wait_for(ws.recv(), HELLO_TIMEOUT))
    except asyncio.TimeoutError:
        print(f"hello: brak odpowiedzi huba w {HELLO_TIMEOUT}s — hub "
              "przyjal polaczenie ale milczy (zawieszony?)", file=sys.stderr)
        sys.exit(1)
    if not isinstance(reply, dict) or reply.get("type") == "error":
        # C4: odmowa "nick zajety" niesie POLE `suggested_nick`. Dla NASLUCHU
        # to nie jest blad koncowy — wolajacy (listen) podnosi sie pod tym
        # nickiem. Zwracamy wiec ramke zamiast umierac; decyzje podejmuje
        # listen, bo dla WYSYLKI podmiana nadawcy byla by podszyciem.
        if (isinstance(reply, dict)
                and isinstance(reply.get("suggested_nick"), str)
                and reply["suggested_nick"]):
            return reply
        # Sciezke pliku sesji zna tylko klient — serwer podaje wzorzec.
        # Najczestsza odmowa (kursor z poprzedniego huba na tym samym
        # porcie) naprawia sie kasowaniem dokladnie tego pliku.
        print(f"hello odrzucone: {reply.get('text', reply) if isinstance(reply, dict) else reply}",
              file=sys.stderr)
        print(f"twoj plik sesji: {session.path}", file=sys.stderr)
        sys.exit(1)
    return reply


def _print_event(data):
    if not isinstance(data, dict):
        print(json.dumps(data, ensure_ascii=False), flush=True)
        return
    text = data.get("text")
    if text is not None:
        print(f"{data.get('from', '?')}: {text}", flush=True)
    else:
        print(json.dumps(data, ensure_ascii=False), flush=True)


def _print_message(message):
    """Best-effort listener: zla ramka jest widoczna, ale nie zabija socketu."""
    try:
        data = json.loads(message)
    except (json.JSONDecodeError, UnicodeDecodeError):
        if isinstance(message, bytes):
            message = message.decode("utf-8", errors="replace")
        print(message, flush=True)
        return
    _print_event(data)


def apply_frame(session, data):
    """Zastosuj JEDNA ramke wg kontraktu kursora. Zwraca True gdy wypisana.

    Kolejnosc: dedup po seq -> dedup wybudzenia po activation_id ->
    wypisz (apply) -> advance(seq) DOPIERO PO apply. Ramka bez seq jest
    wypisywana, ale kursora nie rusza.
    """
    if not isinstance(data, dict):
        _print_event(data)
        return True
    seq = data.get("seq")
    has_seq = (not isinstance(seq, bool)) and isinstance(seq, int) and seq >= 1
    if has_seq and seq <= session.last_applied_seq:
        return False  # duplikat/replay czegos juz zastosowanego
    activation_id = data.get("activation_id")
    has_activation = isinstance(activation_id, str) and bool(activation_id)
    if has_activation and session.is_activation_applied(activation_id):
        # duplikat wybudzenia (retransmisja tej samej proby) — suppress,
        # ale kursor przesuwamy, zeby nie odbierac go w kolko z backlogu
        if has_seq:
            session.advance(seq)
        return False
    _print_event(data)          # apply (dla CLI: emisja na stdout)
    if has_activation:
        session.mark_activation(activation_id)  # mark DOPIERO po apply —
        # crash miedzy apply a mark = retry ponowi apply (at-least-once),
        # odwrotna kolejnosc = suppress nigdy-nie-zastosowanej aktywacji
    if has_seq:
        session.advance(seq)    # kursor DOPIERO po apply
    return True


def _emit_session_metadata(reply):
    """Jedna ramka metadanych sesji PRZED backlogiem/stanem — adapter/harness
    widzi kontekst, zanim poplyna eventy. Bez cache: kazde hello emituje
    aktualny stan z serwera.

    F10 (B5): przekazujemy TAKZE `participants` (board — kto istnieje, kto
    polaczony, co robi) i `howto` (instrukcja obslugi kanalu). Hub wysyla
    oba od B4/F5, ale listener je gubil — agent wchodzacy jedyna
    udokumentowana droga nie dostawal ani boardu, ani instrukcji. Obietnica
    protokolu musi docierac do odbiorcy, nie tylko na drut."""
    meta = {k: reply[k] for k in ("rules", "rules_hash", "role", "groups",
                                  "generation", "participants", "howto")
            if k in reply}
    if meta:
        _print_event({"type": "session_metadata", **meta})


def _warn_if_taken_over(reply, nick):
    """Powiedz agentowi, ze ktos siedzial na jego nicku.

    F3 dal slad po takeoverze LUDZIOM (push do TUI) — ale ofiara nie
    dostaje nic: w chwili wyparcia jej socket jest wlasnie zamykany,
    a po powrocie ramka jest juz historia, ktorej nikt jej nie pokazuje.
    Zmierzone na produkcji: 40 wyparc worker1 w osiem sekund i ani jedno
    nie dotarlo do wypartego — dowiedzial sie od czlowieka.

    `takeover` jest w CONVERSATION_TYPES, wiec wraca w `conversation`
    przy hello. Wystarczy je przefiltrowac po wlasnym nicku — zero zmian
    w protokole i zero pracy po stronie serwera.
    """
    # Dwa zrodla, bo hub uzywa ich zaleznie od kursora: `backlog` przy
    # zwyklym powrocie (odpowiedz ok), `conversation` po kompakcji
    # (resync_required). Patrzenie tylko na jedno dawalo ostrzezenie
    # wylacznie po snapshocie — czyli prawie nigdy.
    ramki = list(reply.get("backlog") or []) + list(reply.get("conversation") or [])
    mine = [f for f in ramki
            if isinstance(f, dict) and f.get("type") == "takeover"
            and f.get("nick") == nick]
    if not mine:
        return
    ostatni = mine[-1]
    print(f"[uwaga] na twoim nicku ({nick}) doszlo do {len(mine)} wyparc; "
          f"ostatnie: generacja {ostatni.get('previous_generation')} -> "
          f"{ostatni.get('generation')}. Sprawdz, czy nie masz drugiego "
          f"klienta na tym nicku — dwa zywe klienty wypieraja sie w kolko.",
          file=sys.stderr)


def _apply_hello_reply(session, reply):
    """Zastosuj hello i zwroc, czy wyemitowano stan/ramke dla odbiorcy.

    True wolno zwrocic dopiero po trwalym przesunieciu kursora. Uzywa tego
    `listen --once`: proces konczy sie po zastosowaniu backlogu, ale nigdy
    w szczelinie miedzy stdout a Session.advance().
    """
    if reply["type"] == "ok":
        _emit_session_metadata(reply)
        applied = False
        for frame in reply.get("backlog", []):
            applied = apply_frame(session, frame) or applied
        # C2: kursor konczy na AUTORYTATYWNYM koncu logu, nie na ostatniej
        # ramce backlogu. Roznica to (a) ramki celowo niewyslane na drucie —
        # serwer filtruje cudze hello, ale w `last_seq` podaje prawdziwy
        # koniec (por. test_reconnect_with_wire_last_seq_gives_empty_backlog_
        # no_loop), oraz (b) caly przypadek `context=fresh`, gdzie backlog
        # jest pusty z definicji. Bez tego agent wchodzacy fresh pominalby
        # historie raz, a przy pierwszym reconnekcie dostal ja w calosci.
        wire_last_seq = reply.get("last_seq")
        if (isinstance(wire_last_seq, bool)
                or not isinstance(wire_last_seq, int)
                or wire_last_seq < 0):
            raise SessionError(
                f"hello ok bez poprawnego last_seq (dostalem: "
                f"{wire_last_seq!r}) — kursor NIE przesuniety")
        # 0 = pusty log: legalne, tylko nie ma czego przesuwac. advance()
        # wymaga seq >= 1 i rzucilby SessionError na swiezym kanale.
        if wire_last_seq > 0:
            session.advance(wire_last_seq)
        durable = (
            wire_last_seq == 0
            or session.last_applied_seq >= wire_last_seq
        )
        return applied and durable
    elif reply["type"] == "resync_required":
        _emit_session_metadata(reply)
        snapshot_seq = reply.get("snapshot_seq")
        print(f"[resync] historia skompaktowana do seq={snapshot_seq}, "
              "stosuje snapshot stanu", file=sys.stderr)
        state = reply.get("state")
        if not isinstance(state, dict):
            # advance bez zastosowanego stanu = deklaracja "mam" przy
            # realnej utracie — fail-closed zamiast cichego przeskoku
            raise SessionError(
                f"resync_required bez poprawnego state (dostalem: "
                f"{type(state).__name__}) — kursor NIE przesuniety; "
                "sprawdz wersje huba albo ponow polaczenie")
        # APPLY stanu PRZED przesunieciem kursora
        _print_event({"type": "resync_state", "state": state})
        # F1+F10: po kompakcji rozmowa wraca w `conversation`. Bez tego
        # wracajacy agent widzi kanal, na ktorym "nic sie nie wydarzylo".
        for frame in reply.get("conversation", []):
            if isinstance(frame, dict):
                _print_event(frame)
        if (not isinstance(snapshot_seq, bool)
                and isinstance(snapshot_seq, int) and snapshot_seq >= 1):
            session.advance(snapshot_seq)
            # Snapshot i conversation zostaly wypisane, a ich autorytatywny
            # kursor jest juz trwaly. `--once` ma je oddac modelowi od razu.
            return session.last_applied_seq >= snapshot_seq
        return False


def _wysylka_albo_padnij(reply, nick, session):
    """Fail-closed dla WYSYLKI, gdy hub odmowil hello.

    `do_hello` celowo NIE umiera przy odmowie niosacej `suggested_nick` —
    zwraca ramke, bo dla NASLUCHU to nie jest blad koncowy (listen podnosi
    sie pod proponowanym nickiem, 7ea4130). Ale wolajacy z drugiej strony,
    `send_once`/`oneshot_frame`, tej zwrotki nie sprawdzal i lecial dalej:
    wysylal ramke na sockecie, ktory hub wlasnie zamykal, po czym konczyl
    sie ZEREM. Komenda meldowala sukces, ramki nie bylo nigdzie.

    Zmierzone na zywym kanale przez drugiego agenta (Codex): dwa
    `send --as codex` skonczyly sie 0, zadnego nie ma w logu huba. Powod
    byl systemowy, nie przypadkowy — `agentmachi node` nadaje instance_id
    per polaczenie (node.py:317), a `send` bierze tozsamosc z pliku sesji,
    wiec pod dzialajacym nodem KAZDA wysylka trafiala w te sciezke.

    To najgorsza klasa bledu, jaka ten produkt ma: cichy false-success.
    Ta sama, ktora dala "start zameldowal sukces PID-em trupa" i "list
    pokazywal dwa huby jako dzialajace". Wysylka nie ma prawa udawac, ze
    poszla.

    Nadawcy NIE podstawiamy, nawet gdy hub podal wolny nick: przy nasluchu
    zmiana nazwy jest ratunkiem, przy wysylce byloby podpisaniem sie cudza
    tozsamoscia."""
    if not (isinstance(reply, dict) and reply.get("type") == "error"):
        return
    powod = reply.get("text", reply)
    print(f"agentmachi: hub ODRZUCIL hello dla {nick!r} — ramka NIE zostala "
          f"wyslana.\n  powod: {powod}", file=sys.stderr)
    proponowany = reply.get("suggested_nick")
    if isinstance(proponowany, str) and proponowany:
        print(f"  nick {nick!r} trzyma teraz ktos inny — czesto TWOJ WLASNY "
              f"`agentmachi node`,\n"
              f"  ktory laczy sie z osobna tozsamoscia niz plik sesji.\n"
              f"  wolny nick: {proponowany} — uzyj go JAWNIE, jesli to "
              f"naprawde ty:\n"
              f"      agentmachi send --as {proponowany} \"...\"",
              file=sys.stderr)
    print(f"  twoj plik sesji: {session.path}", file=sys.stderr)
    sys.exit(1)


async def send_once(nick, text, quiet=False):
    """quiet=True: ramka trafia do logu i do ludzi, ale NIE budzi agentow.
    Publikacja zamiast zawolania — patrz chat/server.py._publish_chat."""
    token = _require_token()
    session = _session(nick)  # kursor tylko do odczytu — nie ruszamy go
    async with websockets.connect(URI) as ws:
        _wysylka_albo_padnij(await do_hello(ws, nick, session, token),
                             nick, session)
        # quiet -> typ `fyi`, ktory istnieje od planu B1: laduje w logu
        # i dociera do ludzi, ale NIE budzi agentow. Nie dodajemy drugiego
        # mechanizmu obok istniejacego — brakowalo tylko wygodnego wejscia.
        await ws.send(json.dumps({"type": "fyi" if quiet else "chat",
                                  "from": nick, "ts": 0.0, "text": text}))


async def listen(nick, context=None, once=False):
    token = _require_token()
    # C2: `fresh` to JEDNORAZOWA decyzja przy starcie procesu, nie tryb
    # polaczenia. Gdyby leciala przy kazdym obiegu petli reconnectu, kursor
    # przeskakiwalby na koniec logu po kazdym zerwaniu — a wiadomosci z okna
    # rozlaczenia gineliby bezpowrotnie. Gasimy flage dopiero PO zastosowaniu
    # poprawnej odpowiedzi (nizej), zeby pad przed nia nie zjadl intencji.
    fresh_pending = context == "fresh"
    # B6: nick moze byc pusty — wtedy hub nada go sam i odesle w hello.
    # Sesje (kursor + lock) tworzymy DOPIERO gdy znamy tozsamosc, zeby
    # kursor byl trwaly per przydzielony nick, a nie per "" przy kazdym
    # reconnekcie. Do pierwszego hello uzywamy sesji tymczasowej.
    session = _session(nick) if nick else None
    if session:
        session.acquire_listener_lock()
    backoff = BACKOFF_START
    try:
        while True:
            try:
                async with websockets.connect(URI) as ws:
                    boot = session or _BootIdentity()   # tozsamosc na pierwsze hello
                    reply = await do_hello(
                        ws, nick, boot, token,
                        context="fresh" if fresh_pending else None)
                    # C4: nick zajal KTOS INNY — podnosimy sie pod nickiem,
                    # ktory hub podal w `suggested_nick`, zamiast umierac.
                    # Agent bez nicka jest gluchy i niemy, wiec wejscie pod
                    # inna nazwa jest zawsze lepsze niz brak wejscia. Hub
                    # decyduje, ktory nick jest wolny; klient tylko przestaje
                    # sie o to rozbijac. Zmierzone na kanale rube: agent
                    # stracil nick, dostal propozycje w TRESCI bledu i utknal
                    # na kilkanascie minut, bo nie mial jej z czego odczytac.
                    if (isinstance(reply, dict)
                            and reply.get("type") == "error"
                            and reply.get("suggested_nick")):
                        proponowany = reply["suggested_nick"]
                        print(f"[nick] '{nick}' zajety przez kogos innego — "
                              f"podnosze sie jako '{proponowany}'",
                              file=sys.stderr)
                        if session is not None:
                            session.release_listener_lock()
                        nick = proponowany
                        session = _session(nick)
                        session.acquire_listener_lock()
                        backoff = BACKOFF_START
                        continue
                    nadany = reply.get("nick") if isinstance(reply, dict) else None
                    if session is None and nadany:
                        # przyjmij nick nadany przez huba i od teraz trzymaj
                        # trwaly kursor+lock pod nim
                        nick = nadany
                        session = _session(nick)
                        session.acquire_listener_lock()
                        print(f"[hub] nadany nick: {nick}", file=sys.stderr)
                    elif session is None:
                        # Weszlismy bez nicka, ale hub przyjal hello i NIE
                        # odeslal nadanego nicka. _BootIdentity zyje tylko
                        # na pierwsze hello — nie ma listener-locka ani
                        # kursora, wiec nie da sie na nim trzymac sesji.
                        # Fail-closed z czytelnym komunikatem zamiast
                        # AttributeError przy version-skew z hubem, ktory
                        # przyjmuje nickless hello, ale nicka nie nadaje
                        # (review worker2). Tozsamosci nie zgadujemy —
                        # nick jest autorytatywnie od huba.
                        print("hello: hub przyjal wejscie bez nicka, ale nie "
                              "nadal nicka w odpowiedzi — nie moge ustalic "
                              "trwalej tozsamosci. Zaktualizuj hub albo podaj "
                              "CHAT_NICK.", file=sys.stderr)
                        sys.exit(1)
                    applied_from_hello = _apply_hello_reply(session, reply)
                    # Gasimy PO zastosowaniu odpowiedzi: gdyby polaczenie
                    # padlo wczesniej, nastepna proba nadal ma byc fresh.
                    fresh_pending = False
                    _warn_if_taken_over(reply, nick)
                    backoff = BACKOFF_START
                    if once and applied_from_hello:
                        return
                    async for message in ws:
                        try:
                            data = json.loads(message)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            _print_message(message)
                            continue
                        applied = apply_frame(session, data)
                        seq = data.get("seq") if isinstance(data, dict) else None
                        durable = (
                            not isinstance(seq, bool)
                            and isinstance(seq, int)
                            and seq >= 1
                            and session.last_applied_seq >= seq
                        )
                        if once and applied and durable:
                            return
            except websockets.exceptions.ConnectionClosed as e:
                # B6: 4003 = wyrzucony przez czlowieka. Reconnect jest tu
                # ODWROTNOSCIA intencji: serwer mowi "wyjdz", a klient
                # wracalby po sekundzie — moderator klikalby kick w kolko
                # i nic by nie wskoral (zmierzone na zywym pokoju).
                # Pozostale kody (1006 zerwana siec itd.) reconnectuja jak
                # dotad; wyrzucenie to DECYZJA, a nie awaria transportu.
                if getattr(e, "rcvd", None) is not None and e.rcvd.code == KICKED_CODE:
                    print("[kick] wyrzucony z kanalu przez moderatora — "
                          "koncze nasluch. Zeby wrocic, uruchom go ponownie.",
                          file=sys.stderr)
                    return
                print(f"[reconnect] polaczenie padlo ({e}); ponawiam za "
                      f"{backoff:.0f}s od kursora "
                      f"{session.last_applied_seq if session else 0}", file=sys.stderr)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX)
            except OSError as e:
                # session moze byc None, gdy nickless hello padlo, zanim hub
                # nadal nick (np. hub chwilowo niedostepny) — kursor jeszcze
                # nie istnieje, wiec meldujemy 0 zamiast siegac po None.
                print(f"[reconnect] polaczenie padlo ({e}); ponawiam za "
                      f"{backoff:.0f}s od kursora "
                      f"{session.last_applied_seq if session else 0}", file=sys.stderr)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX)
    finally:
        # session bywa None, gdy weszlismy bez nicka i hub nicka nie nadal
        # (fail-closed wyzej) albo pierwsze hello padlo przed nadaniem —
        # lock wtedy nigdy nie powstal, wiec nie ma czego zwalniac.
        if session is not None:
            session.release_listener_lock()


async def oneshot_frame(nick, frame):
    """Jednorazowa ramka NIE-chat (status/membership_set/kick) na TOZSAMOSCI
    SESJI — ten sam instance_id co listener, wiec ZERO takeoveru i
    zero ping-ponga generacji (bug znaleziony testem skilla: one-shot
    z innym instance wypieral listener i gubil lease). Kursora nie rusza.
    Zwraca odpowiedz serwera (ok/error) albo None (np. status bez ACK)."""
    token = _require_token()
    session = _session(nick)
    async with websockets.connect(URI) as ws:
        # Ta sama dziura co w send_once, tylko lepiej zamaskowana: po odmowie
        # hello ramka szla na zamykany socket, ACK nie przychodzil, a brak
        # ACK jest tu LEGALNY (status go nie dostaje) — wiec funkcja zwracala
        # None, czyli "sukces".
        _wysylka_albo_padnij(await do_hello(ws, nick, session, token),
                             nick, session)
        await ws.send(json.dumps({"from": nick, "ts": 0.0, **frame}))
        try:
            while True:
                reply = json.loads(await asyncio.wait_for(ws.recv(), 5))
                if isinstance(reply, dict) and reply.get("type") in (
                        "ok", "error"):
                    return reply
        except asyncio.TimeoutError:
            return None  # np. status — serwer nie odsyla ACK i to jest OK


async def legacy_send_once(nick, text):
    async with websockets.connect(URI) as ws:
        await ws.send(json.dumps({"from": nick, "text": text}))


async def legacy_listen():
    async with websockets.connect(URI) as ws:
        async for message in ws:
            _print_message(message)


def main():
    args = sys.argv[1:]
    try:
        if args and args[0] == "--legacy":
            rest = args[1:]
            if rest == ["--listen"]:
                asyncio.run(legacy_listen())
            elif len(rest) == 2:
                asyncio.run(legacy_send_once(rest[0], rest[1]))
            else:
                print('usage: send.py --legacy <nick> "tekst"  |  '
                      'send.py --legacy --listen', file=sys.stderr)
                sys.exit(1)
        elif args == ["--listen"]:
            asyncio.run(listen(os.environ.get("CHAT_NICK", "listener")))
        elif len(args) == 2 and args[0] == "--as":
            print('send.py --as <nick>: brakuje tresci', file=sys.stderr)
            sys.exit(1)
        elif len(args) == 3 and args[0] == "--as":
            asyncio.run(send_once(args[1], args[2]))
        elif len(args) == 1:
            nick = os.environ.get("CHAT_NICK", "")
            if not nick:
                print('send.py: nie wiem, KIM jestes — podaj --as <nick> '
                      'albo ustaw CHAT_NICK', file=sys.stderr)
                sys.exit(1)
            asyncio.run(send_once(nick, args[0]))
        else:
            # C3: dawne `send.py <nick> "tekst"` USUNIETE. <nick> byl
            # NADAWCA, a czytal sie jak adresat — na zywym kanale kosztowalo
            # to ramke wyslana w cudzym imieniu. Wariant nie zostaje
            # "dla kompatybilnosci": dopoki dziala, pulapka dziala z nim.
            print('usage: send.py --as <nick> "@ktos tekst"  |  '
                  'CHAT_NICK=<nick> send.py "@ktos tekst"  |  '
                  'send.py --listen  |  send.py --legacy ...\n'
                  '  --as = KIM jestes; adresata wskazujesz @wzmianka '
                  'w tresci', file=sys.stderr)
            sys.exit(1)
    except KeyboardInterrupt:
        pass
    except ListenerLockHeld as e:
        print(str(e), file=sys.stderr)
        sys.exit(3)
    except SessionError as e:
        print(str(e), file=sys.stderr)
        sys.exit(4)
    except OSError as e:
        print(f"blad polaczenia z {URI}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
