"""Test akceptacyjny konstytucji (laka-nie-obora): DOWOD samoorganizacji bez
schedulera i bez routingu przez czlowieka. Hub UMOZLIWIA przebieg (routing
wzmianki, pasywny board, trwaly log), nie prowadzi go — po Fazie A (scheduler
task/offer/expiry/queue wyciety) i Fazie B (board = {state, subject, note}).

Wzorzec repo: helper hello/recv/_free_port/srv POWIELONE lokalnie (nie
importowane z test_server_integration.py), jak w test_node.py.
"""
import asyncio
import json
import socket

import pytest
import websockets

from chat.server import ChatServer

TOKENS = {
    "alfa": "ta",
    "beta": {"token": "tb", "role": "agent", "groups": ["workers"]},
    "emil": {"token": "te", "role": "human", "groups": []},
    "gamma": {"token": "tg", "role": "agent", "groups": ["workers"]},
}


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("localhost", 0))
    port = s.getsockname()[1]
    s.close()
    return port


PORT = _free_port()


@pytest.fixture()
def srv(tmp_path):
    async def _run(coro):
        server = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT)
        await server.start()
        try:
            return await asyncio.wait_for(coro(server), timeout=10)
        finally:
            await server.stop()
    return _run


async def hello(nick, token, instance="i1", last_seq=0, role="agent", groups=None):
    ws = await websockets.connect(f"ws://localhost:{PORT}")
    await ws.send(json.dumps({"type": "hello", "from": nick, "ts": 0.0,
                              "instance_id": instance, "token": token,
                              "last_seq": last_seq, "role": role,
                              "groups": groups or []}))
    reply = json.loads(await ws.recv())
    return ws, reply


async def recv(ws, timeout=2.0):
    """Odbierz nastepna ramke, POMIJAJAC efemeryczne presence (szum dla asercji)."""
    while True:
        frame = json.loads(await asyncio.wait_for(ws.recv(), timeout))
        if isinstance(frame, dict) and frame.get("type") == "presence":
            continue
        return frame


# Wszystkie typy ramek dawnego schedulera — log przebiegu NIE moze ich zawierac.
_SCHEDULER_FRAMES = {"task_new", "task_claim", "task_done", "task_blocked",
                     "review_changes", "task_approve", "task_unblock",
                     "heartbeat", "task_offer", "offer_resolved",
                     "task_expired", "task_expired_batch"}


def test_self_organization_flow_without_scheduler(srv):
    """A deleguje do B wzmianka; B przyjmuje i raportuje status — czysty
    chat+status, ZERO ramek schedulera. Hub tylko routuje i utrwala.
    Kontrakt: wzmianka budzi live TYLKO adresata-agenta; status to fakt boardu
    pchany live TYLKO do ludzi (agent go NIE dostaje)."""
    async def scenario(server):
        a, _ = await hello("alfa", "ta", groups=["workers"])
        b, _ = await hello("beta", "tb", groups=["workers"])
        g, _ = await hello("gamma", "tg", groups=["workers"])   # obecny, NIE wzmiankowany
        h, _ = await hello("emil", "te", role="human")           # obserwator-czlowiek
        # A deleguje do B PRZEZ ROZMOWE (wzmianka @beta) — zero mechanizmu huba
        await a.send(json.dumps({"type": "chat", "from": "alfa", "ts": 1.0,
                                 "text": "@beta wez czesc C"}))
        # DOWOD routingu: B dostaje; czlowiek dostaje (chat leci do ludzi);
        # gamma (agent nie-wzmiankowany) NIE.
        got_b = await recv(b)
        assert got_b["type"] == "chat" and got_b["from"] == "alfa" and "@beta" in got_b["text"]
        assert (await recv(h))["text"] == "@beta wez czesc C"    # chat -> ludzie
        with pytest.raises(asyncio.TimeoutError):
            await recv(g, timeout=0.4)              # wzmianka budzi tylko adresata
        # B przyjmuje i raportuje status working+subject (pole boardu po Fazie B)
        await b.send(json.dumps({"type": "status", "from": "beta", "ts": 2.0,
                                 "state": "working", "subject": "C"}))
        # DOWOD: status to fakt boardu pchany live TYLKO do ludzi.
        st = await recv(h)                           # czlowiek dostaje status...
        assert st["type"] == "status" and st["from"] == "beta" and st.get("subject") == "C"
        with pytest.raises(asyncio.TimeoutError):
            await recv(a, timeout=0.4)              # ...agent alfa NIE (status nie budzi agentow)
        # recv(h) statusu jest tez BARIERA sync: serwer przetworzyl status.
        board = {p["nick"]: p for p in server._participants_snapshot()}
        assert board["beta"]["status"]["state"] == "working"
        assert board["beta"]["status"]["subject"] == "C"
        # DOWOD braku schedulera: realny skan logu, nie komentarz
        types = {e.get("type") for e in server.log.replay()}
        assert not (types & _SCHEDULER_FRAMES)
        assert not hasattr(server, "queue")          # kolejka wycieta (A4)
        for ws in (a, b, g, h):
            await ws.close()
    asyncio.run(srv(scenario))


def test_selforg_state_survives_restart(srv):
    """Trwalosc: przebieg (a@beta + status B working/C), stop (snapshot), nowy
    ChatServer nad tym samym data_dir odtwarza BOARD (subject!) i ROZMOWE z
    logu/snapshotu. Sam brak queue nie dowodzi samoorganizacji — dowodem jest
    routing + trwalosc + zero ramek schedulera."""
    async def scenario(server):
        a, _ = await hello("alfa", "ta", groups=["workers"])
        b, _ = await hello("beta", "tb", groups=["workers"])
        await a.send(json.dumps({"type": "chat", "from": "alfa", "ts": 1.0,
                                 "text": "@beta wez czesc C"}))
        await recv(b)                                # sync: B dostal wzmianke
        await b.send(json.dumps({"type": "status", "from": "beta", "ts": 2.0,
                                 "state": "working", "subject": "C"}))
        await asyncio.sleep(0.1)                     # bariera: status przetworzony
        await a.close()
        await b.close()
        return server.log.dir

    data_dir = asyncio.run(srv(scenario))
    # nowy serwer nad tym samym data_dir — odtwarza ze snapshotu+logu (bez start)
    reborn = ChatServer(data_dir=data_dir, tokens=TOKENS, port=PORT + 1)
    board = {p["nick"]: p for p in reborn._participants_snapshot()}
    assert board["beta"]["status"]["state"] == "working"
    assert board["beta"]["status"]["subject"] == "C"      # subject przetrwal restart
    conv = reborn.log.conversation_after(0)               # rozmowa przetrwala
    assert any(e.get("type") == "chat" and "@beta" in e.get("text", "") for e in conv)
    # zero ramek schedulera takze po odtworzeniu z dysku
    types = {e.get("type") for e in reborn.log.replay()}
    assert not (types & _SCHEDULER_FRAMES)
