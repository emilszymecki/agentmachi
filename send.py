#!/usr/bin/env python3
"""Klient CLI czatu agentow — RESUMOWALNY (Task 7 / t1).

Domyslnie protokol B1 (chat/server.py): hello + token + trwaly kursor.
  python3 send.py <nick> "tekst"   -> hello (kursor TYLKO czytany), chat, wyjscie
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


async def do_hello(ws, nick, session, token, role=None):
    hello = {
        "type": "hello", "ts": 0.0,
        "instance_id": session.instance_id,
        "last_seq": session.last_applied_seq,
        "role": role or os.environ.get("CHAT_ROLE", "agent")}
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
        print(f"hello odrzucone: {reply.get('text', reply) if isinstance(reply, dict) else reply}",
              file=sys.stderr)
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
    if reply["type"] == "ok":
        _emit_session_metadata(reply)
        for frame in reply.get("backlog", []):
            apply_frame(session, frame)
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


async def send_once(nick, text):
    token = _require_token()
    session = _session(nick)  # kursor tylko do odczytu — nie ruszamy go
    async with websockets.connect(URI) as ws:
        await do_hello(ws, nick, session, token)
        await ws.send(json.dumps({"type": "chat", "from": nick,
                                  "ts": 0.0, "text": text}))


async def listen(nick):
    token = _require_token()
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
                    boot = session or _session("")   # tozsamosc na pierwsze hello
                    reply = await do_hello(ws, nick, boot, token)
                    nadany = reply.get("nick") if isinstance(reply, dict) else None
                    if session is None and nadany:
                        # przyjmij nick nadany przez huba i od teraz trzymaj
                        # trwaly kursor+lock pod nim
                        nick = nadany
                        session = _session(nick)
                        session.acquire_listener_lock()
                        print(f"[hub] nadany nick: {nick}", file=sys.stderr)
                    elif session is None:
                        session = boot
                        session.acquire_listener_lock()
                    _apply_hello_reply(session, reply)
                    _warn_if_taken_over(reply, nick)
                    backoff = BACKOFF_START
                    async for message in ws:
                        try:
                            data = json.loads(message)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            _print_message(message)
                            continue
                        apply_frame(session, data)
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
                      f"{session.last_applied_seq}", file=sys.stderr)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX)
            except OSError as e:
                print(f"[reconnect] polaczenie padlo ({e}); ponawiam za "
                      f"{backoff:.0f}s od kursora "
                      f"{session.last_applied_seq}", file=sys.stderr)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX)
    finally:
        session.release_listener_lock()


def _check_heartbeat_interval(interval):
    import math
    if (isinstance(interval, bool) or not isinstance(interval, (int, float))
            or not math.isfinite(interval) or interval <= 0):
        raise SessionError(f"invalid heartbeat interval: {interval!r} "
                           "(wymagane skonczone > 0)")
    return float(interval)


async def _await_heartbeat_ok(ws, task_id):
    """Czekaj na WLASCIWE ok (kontrakt serwera: ok z task.id) — inne ramki
    (chat/backlog itd.) pomijamy. Timeout/blad = sygnal dla petli."""
    while True:
        reply = json.loads(await asyncio.wait_for(ws.recv(), HELLO_TIMEOUT))
        if not isinstance(reply, dict):
            continue
        if reply.get("type") == "error":
            return reply
        if (reply.get("type") == "ok"
                and reply.get("task", {}).get("id") == task_id):
            return reply


async def oneshot_frame(nick, frame):
    """Jednorazowa ramka NIE-chat (status/task_*) na TOZSAMOSCI SESJI —
    ten sam instance_id co listener/heartbeat, wiec ZERO takeoveru i
    zero ping-ponga generacji (bug znaleziony testem skilla: one-shot
    z innym instance wypieral listener i gubil lease). Kursora nie rusza.
    Zwraca odpowiedz serwera (ok/error) albo None (np. status bez ACK)."""
    token = _require_token()
    session = _session(nick)
    async with websockets.connect(URI) as ws:
        await do_hello(ws, nick, session, token)
        await ws.send(json.dumps({"from": nick, "ts": 0.0, **frame}))
        try:
            while True:
                reply = json.loads(await asyncio.wait_for(ws.recv(), 5))
                if isinstance(reply, dict) and reply.get("type") in (
                        "ok", "error"):
                    return reply
        except asyncio.TimeoutError:
            return None  # np. status — serwer nie odsyla ACK i to jest OK


async def heartbeat_loop(nick, task_id, interval):
    """Procesik lease (mechanika ze specu): odnawiaj heartbeat co interval,
    az do kill (worker ubija przy done). Blad serwera = koniec (nie odnawiaj
    lease taska, ktorego juz nie posiadasz); timeout na ok ORAZ pad sieci =
    reconnect z backoffem."""
    interval = _check_heartbeat_interval(interval)
    token = _require_token()
    session = _session(nick)  # kursora NIE ruszamy (to nie listener)
    backoff = BACKOFF_START
    while True:
        try:
            async with websockets.connect(URI) as ws:
                await do_hello(ws, nick, session, token)
                backoff = BACKOFF_START
                while True:
                    await ws.send(json.dumps({
                        "type": "heartbeat", "from": nick, "ts": 0.0,
                        "task_id": task_id}))
                    reply = await _await_heartbeat_ok(ws, task_id)
                    if reply.get("type") == "error":
                        print(f"heartbeat odrzucony: {reply.get('text')}",
                              file=sys.stderr)
                        return 1
                    await asyncio.sleep(interval)
        except asyncio.TimeoutError:
            print("[heartbeat-reconnect] brak ok w terminie — ponawiam "
                  f"polaczenie za {backoff:.0f}s", file=sys.stderr)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX)
        except (websockets.exceptions.ConnectionClosed, OSError) as e:
            print(f"[heartbeat-reconnect] {e}; ponawiam za {backoff:.0f}s",
                  file=sys.stderr)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX)


# --- tryb legacy: stary PoC-hub (czysty broadcast {from,text}, bez hello) ---

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
        elif args and args[0] == "--heartbeat" and len(args) in (2, 3):
            try:
                interval = float(args[2]) if len(args) == 3 else 45.0
            except ValueError:
                print(f"zly interval: {args[2]!r} (liczba sekund > 0)",
                      file=sys.stderr)
                sys.exit(1)
            code = asyncio.run(heartbeat_loop(
                os.environ.get("CHAT_NICK", "listener"), args[1], interval))
            sys.exit(code or 0)
        elif len(args) == 2:
            asyncio.run(send_once(args[0], args[1]))
        else:
            print('usage: send.py <nick> "tekst"  |  send.py --listen  |  '
                  'send.py --heartbeat <task_id> [interval]  |  '
                  'send.py --legacy ...', file=sys.stderr)
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
