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

import websockets

from chat.client_session import ListenerLockHeld, Session, SessionError

PORT = os.environ.get("CHAT_PORT", "8765")
URI = f"ws://localhost:{PORT}"
HUB_ID = f"localhost:{PORT}"
HELLO_TIMEOUT = 10.0
BACKOFF_START, BACKOFF_MAX = 1.0, 30.0
LEGACY_SESSION_FILE = Path(__file__).with_name(".chat-session.json")


def _require_token():
    token = os.environ.get("CHAT_TOKEN", "")
    if not token:
        print("brak CHAT_TOKEN — ustaw token agenta zanim polaczysz sie "
              "z hubem B1 (fail-fast po stronie klienta, zeby nie slac "
              "pustego sekretu)", file=sys.stderr)
        sys.exit(2)
    return token


def _session(nick):
    return Session(HUB_ID, nick, legacy_instance_file=LEGACY_SESSION_FILE)


async def do_hello(ws, nick, session, token, role=None):
    await ws.send(json.dumps({
        "type": "hello", "from": nick, "ts": 0.0,
        "instance_id": session.instance_id,
        "token": token,
        "last_seq": session.last_applied_seq,
        "role": role or os.environ.get("CHAT_ROLE", "agent")}))
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
    if (isinstance(activation_id, str) and activation_id
            and session.seen_activation(activation_id)):
        # duplikat wybudzenia (retransmisja tej samej proby) — suppress,
        # ale kursor przesuwamy, zeby nie odbierac go w kolko z backlogu
        if has_seq:
            session.advance(seq)
        return False
    _print_event(data)          # apply (dla CLI: emisja na stdout)
    if has_seq:
        session.advance(seq)    # kursor DOPIERO po apply
    return True


def _apply_hello_reply(session, reply):
    if reply["type"] == "ok":
        for frame in reply.get("backlog", []):
            apply_frame(session, frame)
    elif reply["type"] == "resync_required":
        snapshot_seq = reply.get("snapshot_seq")
        print(f"[resync] historia skompaktowana do seq={snapshot_seq}, "
              "stosuje biezacy stan", file=sys.stderr)
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
    session = _session(nick)
    session.acquire_listener_lock()
    backoff = BACKOFF_START
    try:
        while True:
            try:
                async with websockets.connect(URI) as ws:
                    reply = await do_hello(ws, nick, session, token)
                    _apply_hello_reply(session, reply)
                    backoff = BACKOFF_START
                    async for message in ws:
                        try:
                            data = json.loads(message)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            _print_message(message)
                            continue
                        apply_frame(session, data)
            except (websockets.exceptions.ConnectionClosed, OSError) as e:
                print(f"[reconnect] polaczenie padlo ({e}); ponawiam za "
                      f"{backoff:.0f}s od kursora "
                      f"{session.last_applied_seq}", file=sys.stderr)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX)
    finally:
        session.release_listener_lock()


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
        elif len(args) == 2:
            asyncio.run(send_once(args[0], args[1]))
        else:
            print('usage: send.py <nick> "tekst"  |  send.py --listen  |  '
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
