#!/usr/bin/env python3
"""Klient CLI czatu agentow (B1: hello + instance_id).

  python3 send.py <nick> "tekst"   -> hello, jedna ramka chat, wyjscie
  python3 send.py --listen         -> hello, wypisuj ruch az Ctrl+C
Env: CHAT_PORT (8765), CHAT_TOKEN (wymagany), CHAT_NICK (dla --listen).
Plik sesji .chat-session.json trzyma instance_id.
"""
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import websockets

URI = f"ws://localhost:{os.environ.get('CHAT_PORT', 8765)}"
SESSION_FILE = Path(__file__).with_name(".chat-session.json")


def instance_id():
    if SESSION_FILE.exists():
        return json.loads(SESSION_FILE.read_text())["instance_id"]
    iid = str(uuid.uuid4())
    SESSION_FILE.write_text(json.dumps({"instance_id": iid}))
    return iid


async def do_hello(ws, nick, role="agent"):
    await ws.send(json.dumps({
        "type": "hello", "from": nick, "ts": 0.0,
        "instance_id": instance_id(),
        "token": os.environ.get("CHAT_TOKEN", ""),
        "last_seq": 0, "role": role}))
    reply = json.loads(await ws.recv())
    if reply["type"] == "error":
        print(f"hello odrzucone: {reply.get('text', reply)}", file=sys.stderr)
        sys.exit(1)
    return reply


def _print_event(data):
    text = data.get("text")
    if text is not None:
        print(f"{data.get('from', '?')}: {text}", flush=True)
    else:
        print(json.dumps(data, ensure_ascii=False), flush=True)


def _print_hello_backlog(reply):
    # ok i resync_required traktowane jednakowo: przy --listen wypisz to,
    # co da sie odtworzyc z historii, zanim zaczna plynac zywe ramki.
    if reply["type"] == "ok":
        for frame in reply.get("backlog", []):
            _print_event(frame)
    elif reply["type"] == "resync_required":
        print(f"[resync] historia skompaktowana do seq="
              f"{reply.get('snapshot_seq')}, zaczynam od biezacego stanu",
              file=sys.stderr)


async def send_once(nick, text):
    async with websockets.connect(URI) as ws:
        await do_hello(ws, nick)
        await ws.send(json.dumps({"type": "chat", "from": nick,
                                  "ts": 0.0, "text": text}))


async def listen(nick):
    async with websockets.connect(URI) as ws:
        reply = await do_hello(ws, nick, role="human")
        _print_hello_backlog(reply)
        async for message in ws:
            _print_event(json.loads(message))


def main():
    args = sys.argv[1:]
    try:
        if args == ["--listen"]:
            asyncio.run(listen(os.environ.get("CHAT_NICK", "listener")))
        elif len(args) == 2:
            asyncio.run(send_once(args[0], args[1]))
        else:
            print('usage: send.py <nick> "tekst"  |  send.py --listen',
                  file=sys.stderr)
            sys.exit(1)
    except KeyboardInterrupt:
        pass
    except OSError as e:
        print(f"blad polaczenia z {URI}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
