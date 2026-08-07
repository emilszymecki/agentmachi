#!/usr/bin/env python3
"""Klient CLI czatu agentow — RESUMOWALNY (Task 7 / t1).

Domyslnie protokol B1 (chat/server.py): hello + token + trwaly kursor.
  python3 send.py --as <nick> "@ktos tekst"  -> hello (kursor TYLKO czytany), chat, wyjscie
  python3 send.py --listen         -> hello od kursora, apply+advance, reconnect

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
import re
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import websockets

from chat import protocol, store
from chat.client_session import ListenerLockHeld, Session, SessionError

PORT = os.environ.get("CHAT_PORT", "8765")


def hub_id_from_url(url):
    """Kursor jest per hub+nick; hub_id = host:port URL-a (port domyslny
    schematu, gdy brak w URL — wss za tunelem publicznym nie niesie :443
    jawnie). UWAGA: ten sam hub widziany pod dwoma nazwami hosta = dwa
    kursory — at-least-once absorbuje ponowna dostawe: swiadomy koszt."""
    p = urlparse(url)
    if p.scheme not in ("ws", "wss") or not p.hostname:
        raise ValueError(f"CHAT_URL must be ws://host[:port] or wss://: {url!r}")
    try:
        port = p.port
    except ValueError:
        raise ValueError(f"CHAT_URL has an invalid port: {url!r}")
    port = port or (443 if p.scheme == "wss" else 80)
    return f"{p.hostname}:{port}"


# Ile MAKSYMALNIE przyjmiemy w jednej ramce OD HUBA. Jawnie, bo domyslny
# 1 MiB websockets lezy PONIZEJ tego, co hub legalnie wysyla: odpowiedz na
# hello niesie caly backlog od kursora w jednej ramce. Zmierzone na zywym
# hubie: 6000 ramek rozmowy = 772 KB (tuz pod progiem), 9000 = rozlaczenie
# kodem 1006, czyli agent wraca po przerwie i wypada.
#
# Liczone Z ARYTMETYKI, nie z sufitu wzietego z powietrza: najgorsza legalna
# odpowiedz to okno rozmowy (CONVERSATION_LIMIT) razy sufit jednej ramki,
# plus snapshot stanu i howto. Mnoznik 4 to zapas na te dodatki. Warunek
# `protocol.dumps` (ensure_ascii=False) jest tu istotny — bez niego kazda
# ramka spoza ASCII puchla na wyjsciu 3x i arytmetyka sie nie domykala
# (piate review Codexa: 200 ramek emoji = 37 MB przy sufitcie 32 MB).
# Asymetria wobec huba jest celowa: hub ogranicza WEJSCIE, bo broni sie
# przed uczestnikami; klient ufa hubowi, do ktorego SAM wszedl.
MAX_HUB_FRAME = 4 * store.CONVERSATION_LIMIT * protocol.MAX_FRAME_BYTES

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


async def do_hello(ws, nick, session, token, role=None, context=None,
                   return_errors=False):
    """`return_errors=True`: odmowa WRACA ramka zamiast konczyc proces.

    Domyslne zachowanie (print + sys.exit(1)) jest dobre dla wysylki
    i nasluchu — tam odmowa jest koncem drogi i nie ma co z nia zrobic
    poza pokazaniem. Dla ODCZYTU (`read_frames`) jest zle: surowy tekst
    serwera przy kursorze spoza logu niesie NAPRAWE NIEPRAWDZIWA (kaze
    skasowac plik sesji, choc kursor przyszedl z argumentu `--seq`), wiec
    wolajacy musi ja podmienic na wlasna. Wartosc domyslna zostaje stara —
    zaden istniejacy wolajacy nie zmienia zachowania."""
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
        print(f"hello: no reply from the hub within {HELLO_TIMEOUT}s — the "
              "hub accepted the connection but stays silent (hung?)",
              file=sys.stderr)
        sys.exit(1)
    if not isinstance(reply, dict) or reply.get("type") == "error":
        if return_errors:
            return reply
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
        print(f"hello rejected: {reply.get('text', reply) if isinstance(reply, dict) else reply}",
              file=sys.stderr)
        print(f"your session file: {session.path}", file=sys.stderr)
        sys.exit(1)
    return reply


def _znacznik_seq(data):
    """`seq` do prefiksu albo `-`, gdy ramka go NIE MA.

    Brak jest tu wartoscia jawna, nie luka do wypelnienia. `seq` NIEPEWNY
    jest gorszy niz `seq` widocznie nieobecny: brak sprawia, ze agent pyta;
    zly sprawia, ze przegrywa arbitraz i nigdy sie o tym nie dowiaduje.
    Nadaje je WYLACZNIE serwer, wiec klient nie ma czego zgadywac."""
    seq = data.get("seq")
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
        return "-"
    return str(seq)


def _print_event(data):
    """Format CZYTELNY: `[seq] nadawca: linia` — znacznik na KAZDEJ linii.

    To jest STRATNA reprezentacja dla czlowieka i nie wolno jej parsowac.
    Powod: agenci wklejaja sobie logi nawzajem, wiec w tresci cudzej
    wiadomosci siedza linie wygladajace dokladnie jak ramki. Zrodlem do
    ARBITRAZU jest `--json` (`_print_json`), nie to.

    Dlaczego znacznik idzie na kazda linie, a nie tylko na pierwsza:
    agenci budza sie przez filtr po tresci, a filtr dopasowuje LINIE.
    Wiadomosci maja tu po 20+ linii, wiec prefiks tylko na pierwszej dawalby
    `seq` tam, gdzie nikt go nie szuka, i nie dawal tam, gdzie filtr trafil.
    Zmierzone 2026-08-05: z 22-linijkowej wiadomosci agent dostal JEDEN
    akapit, akurat o wymowie ODWROTNEJ do calosci. Ucicie widac —
    odwrocenie sensu wyglada jak kompletna wypowiedz.

    Ramka bez `text` (metadane sesji, snapshot) leci calym JSON-em: `seq`
    jest juz w srodku, a tresci do rozbicia na linie nie ma.
    """
    if not isinstance(data, dict):
        print(json.dumps(data, ensure_ascii=False), flush=True)
        return
    text = data.get("text")
    if text is None:
        print(json.dumps(data, ensure_ascii=False), flush=True)
        return
    prefiks = f"[{_znacznik_seq(data)}] {data.get('from', '?')}:"
    # split("\n"), nie splitlines(): granica linii ma byc TA SAMA, ktora widzi
    # `grep` po drugiej stronie potoku. splitlines() tnie takze na U+2028
    # i \x85, wiec numeracja linii rozjechalaby sie z filtrem agenta.
    for linia in str(text).split("\n"):
        print(f"{prefiks} {linia}" if linia else prefiks, flush=True)


def _print_json(data):
    """Format MASZYNOWY: pelna ramka, JEDNA NA LINIE. Zrodlo do arbitrazu.

    Wielolinijkowa tresc zostaje w polu `text` (zaescapowana przez json),
    wiec jedna linia stdout = dokladnie jedna ramka. `ensure_ascii=False`
    jak wszedzie w tym repo — inaczej kazdy nie-ASCII puchnie 3x."""
    print(json.dumps(data, ensure_ascii=False), flush=True)


def _print_message(message, emit=None):
    """Best-effort listener: zla ramka jest widoczna, ale nie zabija socketu."""
    emit = emit or _print_event
    try:
        data = json.loads(message)
    except (json.JSONDecodeError, UnicodeDecodeError):
        if isinstance(message, bytes):
            message = message.decode("utf-8", errors="replace")
        # W trybie --json stdout ma byc parsowalny CO DO LINII. Smiec z drutu
        # nie jest ramka, wiec idzie na stderr — inaczej jedna zepsuta ramka
        # wywala parser odbiorcy, ktory buduje na tym arbitraz.
        print(message, file=(sys.stderr if emit is _print_json else sys.stdout),
              flush=True)
        return
    emit(data)


def apply_frame(session, data, emit=None):
    """Zastosuj JEDNA ramke wg kontraktu kursora. Zwraca True gdy wypisana.

    Kolejnosc: dedup po seq -> dedup wybudzenia po activation_id ->
    wypisz (apply) -> advance(seq) DOPIERO PO apply. Ramka bez seq jest
    wypisywana, ale kursora nie rusza.

    `emit` wybiera FORMAT (czytelny albo `--json`) i nie dotyka niczego
    poza emisja — kontrakt kursora jest ten sam w obu trybach. Domyslne
    None rozwiazuje sie do `_print_event` DOPIERO w wywolaniu, zeby testy
    podmieniajace `send._print_event` dalej patrzyly na te sciezke.
    """
    emit = emit or _print_event
    if not isinstance(data, dict):
        emit(data)
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
    emit(data)                  # apply (dla CLI: emisja na stdout)
    if has_activation:
        session.mark_activation(activation_id)  # mark DOPIERO po apply —
        # crash miedzy apply a mark = retry ponowi apply (at-least-once),
        # odwrotna kolejnosc = suppress nigdy-nie-zastosowanej aktywacji
    if has_seq:
        session.advance(seq)    # kursor DOPIERO po apply
    return True


def _emit_session_metadata(reply, emit=None):
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
        (emit or _print_event)({"type": "session_metadata", **meta})


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
    print(f"[warning] your nick ({nick}) was taken over {len(mine)} time(s); "
          f"last one: generation {ostatni.get('previous_generation')} -> "
          f"{ostatni.get('generation')}. Check whether you have a second "
          f"client on this nick — two live clients take over from each other "
          f"forever.", file=sys.stderr)


def _apply_hello_reply(session, reply, emit=None):
    """Zastosuj hello i zwroc, czy wyemitowano stan/ramke dla odbiorcy.

    True wolno zwrocic dopiero po trwalym przesunieciu kursora. Uzywa tego
    `listen --once`: proces konczy sie po zastosowaniu backlogu, ale nigdy
    w szczelinie miedzy stdout a Session.advance().
    """
    if reply["type"] == "ok":
        _emit_session_metadata(reply, emit)
        applied = False
        for frame in reply.get("backlog", []):
            applied = apply_frame(session, frame, emit) or applied
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
                f"hello ok without a valid last_seq (got: "
                f"{wire_last_seq!r}) — cursor NOT advanced")
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
        _emit_session_metadata(reply, emit)
        snapshot_seq = reply.get("snapshot_seq")
        print(f"[resync] history compacted to seq={snapshot_seq}, "
              "applying the state snapshot", file=sys.stderr)
        state = reply.get("state")
        if not isinstance(state, dict):
            # advance bez zastosowanego stanu = deklaracja "mam" przy
            # realnej utracie — fail-closed zamiast cichego przeskoku
            raise SessionError(
                f"resync_required without a valid state (got: "
                f"{type(state).__name__}) — cursor NOT advanced; "
                "check the hub version or reconnect")
        # APPLY stanu PRZED przesunieciem kursora
        (emit or _print_event)({"type": "resync_state", "state": state})
        # F1+F10: po kompakcji rozmowa wraca w `conversation`. Bez tego
        # wracajacy agent widzi kanal, na ktorym "nic sie nie wydarzylo".
        for frame in reply.get("conversation", []):
            if isinstance(frame, dict):
                (emit or _print_event)(frame)
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
    print(f"agentmachi: the hub REJECTED hello for {nick!r} — the frame was "
          f"NOT sent.\n  reason: {powod}", file=sys.stderr)
    proponowany = reply.get("suggested_nick")
    if isinstance(proponowany, str) and proponowany:
        print(f"  nick {nick!r} is now held by someone else — often YOUR OWN "
              f"`agentmachi node`,\n"
              f"  which connects with a different identity than the session "
              f"file.\n"
              f"  free nick: {proponowany} — use it EXPLICITLY if that is "
              f"really you:\n"
              f"      agentmachi send --as {proponowany} \"...\"",
              file=sys.stderr)
    print(f"  your session file: {session.path}", file=sys.stderr)
    sys.exit(1)


class SendTooLarge(SessionError):
    """Ramka nie zmiesci sie w sufit huba. Dziedziczy po SessionError, wiec
    main() konczy sie kodem 4 (blad kontraktu klienta), a nie zerem."""


def _sprawdz_rozmiar(wire):
    """Odrzuc ramke, ktora nie zmiesci sie w sufit huba. NIE jest to
    dublowanie walidacji serwera — jest to jedyne miejsce, gdzie agent
    w ogole DOWIE SIE, ze wiadomosc nie doszla.

    `chat` nie ma ACK. Serwer zamyka polaczenie kodem 1009, a menedzer
    kontekstu websockets polyka to zamkniecie — bez tej kontroli
    `agentmachi send` konczy sie ZEREM, a wiadomosci nie ma ani w logu, ani
    u nikogo. Cicha utrata jest gorsza niz odmowa: agent idzie dalej
    przekonany, ze powiedzial (zlapane 2026-07-31, piate review Codexa)."""
    # Surogat PRZED rozmiarem: `protocol.dumps` dla takiej ramki wraca do
    # escapowania i NIE rzuca, wiec sam pomiar rozmiaru jej nie wykryje.
    # Hub odbija ja na wejsciu, ale `chat` nie ma ACK — czyli dokladnie ta
    # cicha utrata, dla ktorej ten przedlot powstal. Zrodlem bywa argv
    # zdekodowane przez `surrogateescape` (nazwa pliku spoza UTF-8), wiec
    # agent nie musi tego robic celowo (dziewiate review Codexa).
    if not protocol.utf8_safe(wire):
        raise SendTooLarge(
            "the frame contains a lone surrogate (\\udXXX) — it cannot be "
            "written as UTF-8 and the hub will reject it. Usual source: text "
            "taken from a file name or from argv that is not UTF-8. Re-encode "
            "the content or pass a path instead of pasting the contents.")
    rozmiar = protocol.frame_bytes(wire)
    if rozmiar > protocol.MAX_FRAME_BYTES:
        raise SendTooLarge(
            f"the frame is {rozmiar} B, the hub limit is "
            f"{protocol.MAX_FRAME_BYTES} B "
            f"({protocol.MAX_FRAME_BYTES // 1024} KiB). The hub drops such "
            f"frames and does NOT send back an error for chat — which is why "
            f"you hear it here. Split the message or pass a file path instead "
            f"of pasting the content onto the channel.")
    return wire


# Ile czekamy na ewentualne `error` po wyslaniu chat/fyi. ZMIERZONE na zywym
# hubie, nie zgadniete: ostrzezenie wraca w 2.4-5.6 ms (piec prob, loopback),
# bo serwer wysyla je PRZED zapisem ramki. 250 ms to ~45x zapas nad pomiarem
# i mieszczi sie w nim takze hub w tailnecie. Pierwsza wersja miala 1.0 s
# i to byl blad w rozumowaniu: napisalem, ze "sciezka szczesliwa placi tylko
# gdy serwer milczy", a CISZA JEST sciezka szczesliwa — czyli kazda zwykla
# wysylka placila pelna sekunde. Za krotkie okno gubi ostrzezenie, czyli
# wraca do stanu sprzed tej zmiany; za dlugie spowalnia KAZDA wysylke.
OKNO_OSTRZEZENIA = 0.25


async def _pokaz_ostrzezenie_serwera(ws):
    """Po wyslaniu chat/fyi poczekaj CHWILE na ewentualne `error` i wypisz je.

    `chat` nie ma ACK, wiec dotad `send` konczyl sie zerem niezaleznie od
    tego, co serwer o tej ramce sadzil. Ostrzezenia (nieznany nick, nieznana
    grupa) leca WYLACZNIE na zywo i NIE sa utrwalane — zmierzone przez
    agent1: w events.jsonl nie ma ani jednej ramki `error`. Kto wysyla
    jednorazowo, bez podniesionego nasluchu, nie mial ich wiec SKAD
    przeczytac: hub mowil do sciany.

    Dlaczego nie utrwalamy `error` w logu, choc taka byla pierwsza
    propozycja: ramka jest adresowana do JEDNEGO nadawcy, a log czyta kazdy
    przy wznowieniu. Zamiast tego pytamy o nia tam, gdzie powstala.

    Okno konczy sie na PIERWSZEJ ramce, ale cisza trwa pelne okno — a cisza
    to wlasnie sciezka szczesliwa, wiec KAZDA zwykla wysylka za nie placi.
    Dlatego jest krotkie i oparte na pomiarze (patrz OKNO_OSTRZEZENIA), a nie
    na ostroznosci: serwer wysyla ostrzezenie PRZED zapisem ramki
    (_handle_chat), wiec jesli ma cokolwiek do powiedzenia, mowi od razu.

    Kod wyjscia zostaje ZERO. Ramka doszla do logu i do ludzi — to
    ostrzezenie, nie odmowa, a skrypt traktujacy niezerowy kod jako
    "nie wyslano" dostalby falszywy sygnal.

    Cudze ramki moga tu wpasc, bo `send_once` dzieli instance_id z nasluchem
    i serwer pcha do WSZYSTKICH socketow nicka — pomijamy je i nic nie ginie:
    ta sama ramka poszla rownolegle do nasluchu i siedzi w logu.
    """
    koniec = time.monotonic() + OKNO_OSTRZEZENIA
    while True:
        zostalo = koniec - time.monotonic()
        if zostalo <= 0:
            return None                      # cisza = sukces, chat nie ma ACK
        try:
            surowe = await asyncio.wait_for(ws.recv(), zostalo)
        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
            return None
        try:
            ramka = json.loads(surowe)
        except ValueError:
            continue
        if isinstance(ramka, dict) and ramka.get("type") == "error":
            print(f"hub: {ramka.get('text', '(no text)')}", file=sys.stderr)
            return ramka
        # cokolwiek innego to cudzy ruch na wspolnym nicku — nie nasza sprawa


async def send_once(nick, text, quiet=False):
    """quiet=True: ramka trafia do logu i do ludzi, ale NIE budzi agentow.
    Publikacja zamiast zawolania — patrz chat/server.py._publish_chat."""
    token = _require_token()
    session = _session(nick)  # kursor tylko do odczytu — nie ruszamy go
    async with websockets.connect(URI, max_size=MAX_HUB_FRAME) as ws:
        _wysylka_albo_padnij(await do_hello(ws, nick, session, token),
                             nick, session)
        # quiet -> typ `fyi`, ktory istnieje od planu B1: laduje w logu
        # i dociera do ludzi, ale NIE budzi agentow. Nie dodajemy drugiego
        # mechanizmu obok istniejacego — brakowalo tylko wygodnego wejscia.
        await ws.send(protocol.dumps(_sprawdz_rozmiar({
            "type": "fyi" if quiet else "chat",
            "from": nick, "ts": 0.0, "text": text})))
        await _pokaz_ostrzezenie_serwera(ws)


async def listen(nick, context=None, once=False, as_json=False):
    token = _require_token()
    # None, a nie `_print_event`: format czytelny ma zostac wiazany PO NAZWIE
    # przy kazdej emisji (testy podmieniaja `send._print_event`), a --json
    # jest jawnym wyborem, wiec wolno go zwiazac tutaj raz.
    emit = _print_json if as_json else None
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
                async with websockets.connect(URI, max_size=MAX_HUB_FRAME) as ws:
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
                        print(f"[nick] '{nick}' is taken by someone else — "
                              f"coming up as '{proponowany}'",
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
                        # ZAMEK PRZED zapisem. Hub uznaje nick za wolny na
                        # podstawie swoich `conns`, a lokalny listener moze
                        # go trzymac, bedac chwilowo rozlaczonym — wtedy
                        # acquire rzuca ListenerLockHeld. Gdyby adopcja szla
                        # pierwsza, odrzucony proces zdazylby nadpisac CUDZY
                        # plik sesji (tozsamosc + wyzerowany kursor) i zabrac
                        # temu listenerowi trwaly kursor. Kolejnosc jest
                        # jedyna ochrona: adoptujemy dopiero to, co nasze
                        # (zlapane 2026-07-31, drugie review Codexa).
                        session.acquire_listener_lock()
                        # Tozsamosc bierzemy z _BootIdentity, bo TA jest juz
                        # zarejestrowana na hubie (poszla w hello). Swiezy
                        # instance_id z pliku sesji zamykalby agentowi usta:
                        # `send --as <nick>` odbija sie o "nick zajety przez
                        # polaczonego <nick>". Patrz adopt_boot_identity.
                        session.adopt_boot_identity(boot.instance_id)
                        print(f"[hub] assigned nick: {nick}", file=sys.stderr)
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
                        print("hello: the hub accepted entry without a nick "
                              "but did not assign one in the reply — I cannot "
                              "establish a durable identity. Update the hub "
                              "or pass CHAT_NICK.", file=sys.stderr)
                        sys.exit(1)
                    applied_from_hello = _apply_hello_reply(session, reply,
                                                            emit)
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
                            _print_message(message, emit)
                            continue
                        applied = apply_frame(session, data, emit)
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
                    print("[kick] kicked off the channel by a moderator — "
                          "ending the listen. To come back, start it again.",
                          file=sys.stderr)
                    return
                print(f"[reconnect] connection dropped ({e}); retrying in "
                      f"{backoff:.0f}s from cursor "
                      f"{session.last_applied_seq if session else 0}", file=sys.stderr)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX)
            except OSError as e:
                # session moze byc None, gdy nickless hello padlo, zanim hub
                # nadal nick (np. hub chwilowo niedostepny) — kursor jeszcze
                # nie istnieje, wiec meldujemy 0 zamiast siegac po None.
                print(f"[reconnect] connection dropped ({e}); retrying in "
                      f"{backoff:.0f}s from cursor "
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
    async with websockets.connect(URI, max_size=MAX_HUB_FRAME) as ws:
        # Ta sama dziura co w send_once, tylko lepiej zamaskowana: po odmowie
        # hello ramka szla na zamykany socket, ACK nie przychodzil, a brak
        # ACK jest tu LEGALNY (status go nie dostaje) — wiec funkcja zwracala
        # None, czyli "sukces".
        _wysylka_albo_padnij(await do_hello(ws, nick, session, token),
                             nick, session)
        await ws.send(protocol.dumps(
            _sprawdz_rozmiar({"from": nick, "ts": 0.0, **frame})))
        try:
            while True:
                reply = json.loads(await asyncio.wait_for(ws.recv(), 5))
                if isinstance(reply, dict) and reply.get("type") in (
                        "ok", "error"):
                    return reply
        except asyncio.TimeoutError:
            return None  # np. status — serwer nie odsyla ACK i to jest OK


# --- odczyt logu przez drut: jedyna droga agenta do WLASNEJ ramki ---------
#
# Zmierzone 2026-08-06: agent na ZDALNYM hubie nie ma jak przeczytac tego, co
# sam powiedzial, ani doczytac cudzej ramki w calosci. Zlozylo sie na to kilka
# poprawnych z osobna decyzji: serwer tlumi echo po nicku (server.py
# `_publish_chat`: `- {sender}`), wiec nasluch nigdy nie widzi wlasnych ramek;
# kursor nasluchu przeskakuje ZA wlasna ramke przy pierwszej cudzej o wyzszym
# seq, wiec backlog jej juz nie odda; `events.jsonl` ma WYLACZNIE operator
# huba, wiec agent na innej maszynie nie ma go wcale. Skutek: agent nie moze
# zweryfikowac wlasnego dowodu i prosi czlowieka o zajrzenie w TUI.
#
# LOG TE RAMKI MA — `events_after` nie filtruje nadawcy, a `wire_backlog`
# wycina tylko `hello`. Brakowalo wylacznie komendy, ktora o nie poprosi, nie
# psujac przy tym stanu sesji.


class ReadRefused(SessionError):
    """`read` NIE oddal tego, o co poproszono. Dziedziczy po SessionError,
    wiec kod wyjscia jest niezerowy.

    Cisza z kodem 0 byla by tu najgorszym mozliwym wynikiem: wyglada
    identycznie jak "ramka jest pusta", jak "zapytalem o zly seq" i jak
    "hub mnie nie wpuscil". To ta sama klasa bledu, ktora dala "start
    zameldowal sukces PID-em trupa"."""


class _ReadIdentity:
    """Tozsamosc na hello `read`: instance_id Z PLIKU SESJI, kursor Z ARGUMENTU.

    Rozdzielenie tych dwoch rzeczy jest calym sensem tej klasy:
    - instance_id MUSI byc ten sam, ktorym legitymuje sie nasluch — inaczej
      hello bumpuje generacje i wypiera zywy `listen` (dokladnie ta pulapka,
      dla ktorej `oneshot_frame` bierze tozsamosc z sesji),
    - kursor MUSI byc inny niz sesyjny, bo pytamy o miejsce w logu, ktore
      nasluch dawno minal.

    Pliku sesji NIE DOTYKAMY: kursor nasluchu jest jego wlasnoscia. `path`
    niesiemy tylko po to, zeby komunikaty bledu mialy co pokazac."""

    def __init__(self, session, last_applied_seq):
        self.instance_id = session.instance_id
        self.last_applied_seq = last_applied_seq
        self.path = session.path


def _koniec_logu_z_odmowy(reply):
    """Serwerowy `last_seq` z odmowy "kursor spoza logu" albo None.

    Ta odmowa jest dla `read` sytuacja ZWYKLA, nie awaria: agent pyta o seq,
    ktorego jeszcze nie ma, i musi dostac koniec logu, zeby wiedziec, o co
    zapytac. Trzeba ja tez odroznic od kazdej innej odmowy, bo surowy tekst
    serwera kaze SKASOWAC PLIK SESJI — a tutaj plik sesji jest niewinny
    (kursor przyszedl z argumentu `--seq`). Odeslanie agenta do kasowania
    kursora WLASNEGO nasluchu byloby szkoda wyrzadzona przez komunikat bledu.

    ZRODLEM JEST POLE `server_last_seq`, nie zdanie. Pierwsza wersja
    wylapywala liczbe regexem z tekstu pisanego dla czlowieka — czyli robila
    to, czego to repo zakazuje wprost przy formacie czytelnym `listen`.
    Przeredagowanie tamtego zdania w server.py cicho degradowaloby `read` do
    odmowy ogolnej i zaden test po stronie serwera by nie spuchl. Pole jest
    kontraktem (chat/server.py, CursorBeyondLog); zdanie nie jest.

    Regex zostaje WYLACZNIE jako most do starszego huba, ktory pola jeszcze
    nie wysyla — klient bywa nowszy od serwera, do ktorego wchodzi."""
    if not isinstance(reply, dict):
        return None
    pole = reply.get("server_last_seq")
    if isinstance(pole, int) and not isinstance(pole, bool) and pole >= 0:
        return pole
    tekst = reply.get("text")
    dopasowanie = re.search(r"> server last_seq (\d+)",
                            tekst if isinstance(tekst, str) else "")
    return int(dopasowanie.group(1)) if dopasowanie else None


def _odczyt_albo_padnij(reply, nick, session, from_seq, naprawa=None):
    """Fail-closed dla ODCZYTU, gdy hub odmowil hello. Zwraca None albo rzuca.

    Rownowaznik `_wysylka_albo_padnij` dla drugiej strony: tam chodzilo o to,
    zeby wysylka nie udawala, ze poszla; tu o to, zeby odczyt nie udawal, ze
    czegos nie ma. Odmowy nie da sie tu przemilczec — pusty stdout i kod 0
    znacza dla wolajacego dokladnie to samo, co udany odczyt pustego zakresu.

    `naprawa` to gotowa komenda do przepisania, gdy hub proponuje inny nick.
    Jest argumentem, bo tej sciezki uzywa juz DRUGI wolajacy (`read_board`),
    a komunikat, ktory kaze uruchomic nie te komende co trzeba, jest gorszy
    niz brak komunikatu: agent robi dokladnie to, co przeczytal.
    """
    if isinstance(reply, dict) and reply.get("type") in ("ok",
                                                         "resync_required"):
        return
    if not isinstance(reply, dict):
        raise ReadRefused(
            f"the hub replied to hello with something that is not a frame "
            f"({reply!r}) — nothing was read. Check that {URI} is really an "
            f"agentmachi hub.")
    powod = reply.get("text", reply)
    koniec = _koniec_logu_z_odmowy(reply)
    if koniec is not None:
        raise ReadRefused(
            f"seq {from_seq} is BEYOND the end of the log — the hub's last "
            f"seq is {koniec}. Nothing was read.\n"
            f"  your session file is NOT involved here — the cursor came from "
            f"the argument, not from the file, so leave the file alone.\n"
            f"  the tail of the log: agentmachi read --from-seq "
            f"{max(koniec - 9, 1)}")
    proponowany = reply.get("suggested_nick")
    if isinstance(proponowany, str) and proponowany:
        raise ReadRefused(
            f"the hub REJECTED hello for {nick!r} — nothing was read.\n"
            f"  reason: {powod}\n"
            f"  the nick is held by a client with a DIFFERENT identity than "
            f"your session file — often your own `agentmachi node`.\n"
            f"  read as the nick you really are on this hub:\n"
            f"      {naprawa(proponowany) if naprawa else f'agentmachi read --nick {proponowany} --from-seq {from_seq}'}")
    raise ReadRefused(
        f"the hub REJECTED hello for {nick!r} — nothing was read.\n"
        f"  reason: {powod}\n"
        f"  your session file: {session.path}")


def _zakres_seq(ramki):
    """Zakres `seq` w tym, co hub ODDAL — do komunikatu o nietrafieniu.

    Agent, ktory nie dostal swojej ramki, musi wiedziec, w czym jej nie bylo.
    Bez zakresu "nie ma" znaczy naraz "log jej nie ma", "wypadla z okna po
    kompakcji" i "zapytales o zly przedzial" — trzy rozne naprawy."""
    seqs = [f.get("seq") for f in ramki
            if isinstance(f.get("seq"), int)
            and not isinstance(f.get("seq"), bool)]
    return f"{min(seqs)}..{max(seqs)}" if seqs else "(nothing came back)"


async def read_frames(nick, from_seq, only_seq=None, emit=None):
    """Doczytaj log kanalu PRZEZ DRUT. Zwraca liczbe wypisanych ramek.

    Trzy rzeczy, ktorych ta droga NIE robi — i ktore sa jej kontraktem, nie
    optymalizacja:
    - NIE bierze listener-locka: agent ma zwykle dzialajacy `listen`, a
      `read` ma dzialac OBOK niego, nie zamiast niego,
    - NIE rusza kursora sesji (zero `advance`, zero `reset_cursor`): kursor
      nasluchu jest jego wlasnoscia i przesuniecie go tutaj zabraloby
      nasluchowi ramki, ktorych nigdy nie zobaczyl,
    - NIE bumpuje generacji: tozsamosc idzie z pliku sesji (`_ReadIdentity`),
      dokladnie jak w `oneshot_frame`.

    Kursor w hello jest PODSTAWIONY (`from_seq - 1`), nie sesyjny — to caly
    mechanizm: hub liczy backlog od tego, co dostal w hello, a plik sesji
    zostaje nietkniety.
    """
    # Kontrakt wejscia publicznej metody. `from_seq` idzie od agenta (argv),
    # a serwer odrzuca ujemne dopiero po polaczeniu — lepiej powiedziec to
    # przed otwarciem socketu i z numeracja, ktora obowiazuje.
    if (isinstance(from_seq, bool) or not isinstance(from_seq, int)
            or from_seq < 1):
        raise ReadRefused(
            f"invalid from_seq: {from_seq!r} — seq numbering starts at 1 "
            f"(the server assigns it; you see it on every `agentmachi listen` "
            f"line)")
    if only_seq is not None and (isinstance(only_seq, bool)
                                 or not isinstance(only_seq, int)
                                 or only_seq < 1):
        raise ReadRefused(
            f"invalid seq: {only_seq!r} — seq numbering starts at 1")
    emit = emit or _print_json
    token = _require_token()
    session = _session(nick)          # tylko zrodlo tozsamosci — zero zapisu
    async with websockets.connect(URI, max_size=MAX_HUB_FRAME) as ws:
        reply = await do_hello(ws, nick,
                               _ReadIdentity(session, from_seq - 1), token,
                               return_errors=True)
        _odczyt_albo_padnij(reply, nick, session, from_seq)
        if reply["type"] == "resync_required":
            # Legalna sciezka, nie awaria — ale wynik jest WEZSZY niz
            # pytanie i agent musi to uslyszec, inaczej uzna niepelna
            # odpowiedz za pelna. Po kompakcji przezywa wylacznie okno
            # rozmowy (chat/fyi/takeover/kick); ramek sluzbowych sprzed
            # snapshotu nie ma juz nigdzie poza `events.jsonl` operatora.
            print(f"[resync] the hub compacted its log at "
                  f"seq={reply.get('snapshot_seq')} — what follows is the "
                  f"CONVERSATION WINDOW, not the full range from "
                  f"{from_seq}. Frames outside that window are gone from the "
                  f"hub; only its operator still has events.jsonl.",
                  file=sys.stderr)
            ramki = [f for f in (reply.get("conversation") or [])
                     if isinstance(f, dict)]
            koniec_logu = reply.get("snapshot_seq")
        else:
            ramki = [f for f in (reply.get("backlog") or [])
                     if isinstance(f, dict)]
            koniec_logu = reply.get("last_seq")
    wybrane = ([f for f in ramki if f.get("seq") == only_seq]
               if only_seq is not None else ramki)
    for ramka in wybrane:
        emit(ramka)
    if only_seq is not None and not wybrane:
        raise ReadRefused(
            f"seq {only_seq} is NOT among the {len(ramki)} frame(s) the hub "
            f"returned (seq range: {_zakres_seq(ramki)}). NOTHING was "
            f"printed — this silence is not a confirmation that the frame is "
            f"empty.\n"
            f"  the hub never puts `hello` frames on the wire, so a seq "
            f"belonging to somebody's entry is invisible this way;\n"
            f"  after compaction only the conversation window survives;\n"
            f"  see what IS there: agentmachi read --from-seq {from_seq}")
    if not wybrane:
        # `--from-seq` na pustym zakresie to LEGALNA odpowiedz ("nic nowego"),
        # inaczej niz pytanie o jedna ramke — dlatego kod wyjscia zostaje 0.
        # Ale milczec i tak nie wolno: pusty stdout czyta sie tak samo jak
        # komenda, ktora nie doszla tam, gdzie mysli wolajacy.
        print(f"[read] no frames at or after seq {from_seq} — the hub's log "
              f"ends at seq {koniec_logu}. Nothing printed.", file=sys.stderr)
    return len(wybrane)


def _wiek_deklaracji(status_seq, biezacy_seq):
    """Ile RAMEK temu powstala deklaracja statusu. None = nigdy nie zadeklarowal.

    Jednostka jest tu czescia wyniku, nie ozdoba: to ramki, nie sekundy.
    Board klamie najgorzej wtedy, gdy wyglada na swiezy — snapshot huba po
    dogfoodzie kinas-machine pokazywal `worker1: idle` przez cala jego prace
    (patrz chat/server.py:401). Wiek nie mowi, czy ktos utknal; mowi, ile
    kanal przezyl od czasu, gdy to zdanie bylo prawda. Wniosek nalezy do
    czytajacego — hub go nie wyciaga."""
    if (isinstance(status_seq, bool) or not isinstance(status_seq, int)
            or isinstance(biezacy_seq, bool)
            or not isinstance(biezacy_seq, int)):
        return None
    return max(biezacy_seq - status_seq, 0)


def _opis_statusu(status, wiek):
    """Jedna linia o deklaracji uczestnika — SUROWA, bez klasyfikacji.

    `idle`/`stuck`/`coding` swiadomie nie powstaja tutaj: to wnioski, a
    wniosek na boardzie zamienilby hub w ukrytego orchestratora
    (CONTRIBUTING.md, "Board classification, scoring, activity ranking")."""
    if not isinstance(status, dict) or not status:
        return "status: (never declared)"
    czesci = [str(status.get("state") or "?")]
    for pole in ("subject", "note"):
        wartosc = status.get(pole)
        if isinstance(wartosc, str) and wartosc.strip():
            czesci.append(wartosc.strip())
    ogon = ("(declared right now)" if wiek == 0
            else f"(declared {wiek} frame(s) ago)" if wiek is not None
            else "(age unknown — the hub sent no status_seq)")
    return f"status: {' — '.join(czesci)}  {ogon}"


def _wypisz_board(uczestnicy, biezacy_seq):
    """Format DLA OCZU. Nie parsuj go — do tego jest `--json`.

    Ta sama granica co przy `listen`: czytelny format gubi informacje i
    agenci wklejaja sobie nawzajem jego fragmenty na kanal, wiec cytat
    wyglada w nim dokladnie jak prawda."""
    print(f"board of {URI} — {len(uczestnicy)} participant(s), "
          f"hub at seq {biezacy_seq}")
    # Raz w naglowku, nie przy kazdym wierszu: `last_seq` liczy ramki
    # ROZMOWY, wiec ktos, kto wlasnie zadeklarowal status, wyglada tu
    # ciszej, niz jest. Bez tego zdania pole czyta sie jako "ostatni
    # znak zycia" i wniosek wychodzi odwrotny do prawdy.
    print("last_seq = that participant's last CONVERSATION frame "
          "(chat/fyi/kick/takeover); a status declaration does not move it")
    for u in uczestnicy:
        wiek = _wiek_deklaracji(u.get("status_seq"), biezacy_seq)
        grupy = ",".join(u.get("groups") or []) or "-"
        print(f"\n{u.get('nick')}"
              f"  role={u.get('role')}"
              f"  groups={grupy}"
              f"  connected={'yes' if u.get('connected') else 'no'}"
              f"  addr={u.get('addr') or '-'}"
              f"  last_seq={u.get('last_seq')}")
        print(f"  {_opis_statusu(u.get('status'), wiek)}")
    # Puste `addr` u WSZYSTKICH czyta sie jak zepsuta kolumna, a jest
    # odmowa: hub oddaje host peera tylko przy bindzie na tailnet, bo na
    # loopbacku nie rozroznia podmiotow i wolal milczec niz zmyslic
    # (chat/server.py:415). Bez tego zdania czytajacy zglosilby buga.
    if uczestnicy and not any(u.get("addr") for u in uczestnicy):
        print("\n(addr is blank for everyone: the hub reports a peer host "
              "only on a tailnet bind — on loopback it would not tell "
              "anybody apart, so it says nothing instead)")


async def read_board(nick, as_json=False, emit=None):
    """Kto jest na kanale — board PRZEZ DRUT, bez historii. Zwraca liczbe wpisow.

    Istnieje, bo nasza WLASNA wymagana praktyka wyrzuca board do kosza:
    filtr nasluchu musi ciac `session_metadata` po typie ramki
    (skills/.../claude-code.md), a board jedzie wlasnie w srodku tej ramki.
    Agent moze wiec zobaczyc, kto jest na kanale, wylacznie wchodzac od nowa
    — okolo 5k tokenow za rzecz, o ktora nie da sie zapytac.

    Zero zmian w serwerze i zero w protokole: `chat/server.py`
    `_participants_snapshot` liczy te pola od B5, a hello je odsyla. To jest
    komenda, ktora POKAZUJE dane juz wysylane.

    Trzy rzeczy, ktorych ta droga nie robi — kontrakt wspolny z `read_frames`:
    - NIE bierze listener-locka (ma dzialac OBOK zywego `listen`),
    - NIE rusza kursora sesji (zero `advance`),
    - NIE bumpuje generacji (instance_id z pliku sesji).

    Kursor w hello to STALE 0, a nie kursor sesji, i to nie jest skrot:
    `context="fresh"` kaze serwerowi policzyc backlog od konca logu, wiec
    backlog wychodzi pusty niezaleznie od tego, co przyslemy — a 0 jest
    zawsze legalne. Kursor sesji potrafi wyprzedzic hub po jego restarcie
    i wtedy board padalby na `CursorBeyondLog`, czyli na rzecz zupelnie
    niezwiazana z pytaniem "kto tu jest"."""
    token = _require_token()
    session = _session(nick)          # tylko zrodlo tozsamosci — zero zapisu
    async with websockets.connect(URI, max_size=MAX_HUB_FRAME) as ws:
        reply = await do_hello(ws, nick, _ReadIdentity(session, 0), token,
                               context="fresh", return_errors=True)
        _odczyt_albo_padnij(reply, nick, session, 1,
                            naprawa=lambda n: f"agentmachi board --nick {n}")
        uczestnicy = reply.get("participants")
        biezacy_seq = (reply.get("last_seq") if reply.get("type") == "ok"
                       else reply.get("snapshot_seq"))
    if not isinstance(uczestnicy, list):
        # Fail-closed: pusty board i board, ktorego hub nie przyslal, znacza
        # co innego. Starszy hub nie ma `participants` w hello i cisza z
        # kodem 0 kazalaby czytajacemu uwierzyc, ze kanal jest pusty.
        raise ReadRefused(
            f"the hub replied to hello without a `participants` board "
            f"(got: {type(uczestnicy).__name__}). NOTHING was printed — this "
            f"is not a confirmation that the channel is empty.\n"
            f"  a hub older than B5 does not send the board at all;\n"
            f"  check what it is: agentmachi card --name <hub>")
    uczestnicy = [u for u in uczestnicy if isinstance(u, dict)]
    if as_json:
        # JEDNA linia z calym boardem, nie linia na uczestnika: `current_seq`
        # jest potrzebny do policzenia wieku KAZDEGO wpisu, wiec rozbicie go
        # od nich oddzielaloby dane od ich jedynego punktu odniesienia.
        (emit or _print_json)({"type": "board",
                               "current_seq": biezacy_seq,
                               "participants": uczestnicy})
    else:
        _wypisz_board(uczestnicy, biezacy_seq)
    return len(uczestnicy)


def main():
    args = sys.argv[1:]
    try:
        if args == ["--listen"]:
            asyncio.run(listen(os.environ.get("CHAT_NICK", "listener")))
        elif len(args) == 2 and args[0] == "--as":
            print('send.py --as <nick>: missing text', file=sys.stderr)
            sys.exit(1)
        elif len(args) == 3 and args[0] == "--as":
            asyncio.run(send_once(args[1], args[2]))
        elif len(args) == 1:
            nick = os.environ.get("CHAT_NICK", "")
            if not nick:
                print('send.py: I do not know WHO you are — pass --as <nick> '
                      'or set CHAT_NICK', file=sys.stderr)
                sys.exit(1)
            asyncio.run(send_once(nick, args[0]))
        else:
            # C3: dawne `send.py <nick> "tekst"` USUNIETE. <nick> byl
            # NADAWCA, a czytal sie jak adresat — na zywym kanale kosztowalo
            # to ramke wyslana w cudzym imieniu. Wariant nie zostaje
            # "dla kompatybilnosci": dopoki dziala, pulapka dziala z nim.
            print('usage: send.py --as <nick> "@someone text"  |  '
                  'CHAT_NICK=<nick> send.py "@someone text"  |  '
                  'send.py --listen\n'
                  '  --as = WHO you are; you point at the addressee with an '
                  '@mention in the text', file=sys.stderr)
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
        print(f"connection error to {URI}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
