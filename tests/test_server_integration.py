"""Testy integracyjne chat/server.py: hello/auth, generation przypieta do
socketu, backlog/resync, echo po nicku, wzmianki, grupy adresowe,
snapshot+restart, activation_id kotwiczony w evencie.

Serwer per-test na porcie 8891+ (nie 8765 — PoC A na roocie repo).
"""
import asyncio
import hashlib
import json

import pytest
import websockets

from chat.server import ChatServer

TOKENS = {"alfa": "ta", "beta": "tb", "emil": "te", "gamma": "tg",
          "delta": "td"}
PORT = 8891


@pytest.fixture()
def srv(tmp_path):
    async def _run(coro):
        server = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                             lease_ttl=5.0, offer_timeout=0.3)
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
    return json.loads(await asyncio.wait_for(ws.recv(), timeout))


CARD = {"goal": "x", "acceptance": "y", "verify": "true", "files": [],
        "head": "h", "brief": "b"}


# -- Step 1 (adaptowane: hello niesie teraz opcjonalnie groups) -------------

def test_hello_auth_and_generation(srv):
    async def scenario(server):
        ws, reply = await hello("alfa", "ta")
        assert reply["type"] == "ok" and reply["generation"] == 1
        bad = await websockets.connect(f"ws://localhost:{PORT}")
        await bad.send(json.dumps({"type": "hello", "from": "alfa", "ts": 0.0,
                                   "instance_id": "x", "token": "ZLY",
                                   "last_seq": 0}))
        err = json.loads(await bad.recv())
        assert err["type"] == "error"
        await ws.close()
    asyncio.run(srv(scenario))


def test_mention_routing_and_echo_suppression(srv):
    async def scenario(server):
        a1, _ = await hello("alfa", "ta")            # dwa sockety alfy —
        a2, _ = await hello("alfa", "ta")            # zaden nie dostanie echa
        b, _ = await hello("beta", "tb")
        g, _ = await hello("gamma", "tg")
        await a1.send(json.dumps({"type": "chat", "from": "alfa", "ts": 1.0,
                                  "text": "@beta patrz"}))
        got = await recv(b)
        assert got["text"] == "@beta patrz" and got["seq"] >= 1
        for ws in (a1, a2, g):                        # gamma niewspomniana
            with pytest.raises(asyncio.TimeoutError):
                await recv(ws, timeout=0.4)
        for ws in (a1, a2, b, g):
            await ws.close()
    asyncio.run(srv(scenario))


def test_human_gets_everything_live(srv):
    async def scenario(server):
        h, _ = await hello("emil", "te", role="human")
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "chat", "from": "alfa", "ts": 1.0,
                                 "text": "bez wzmianki"}))
        got = await recv(h)
        assert got["text"] == "bez wzmianki"
        await h.close(); await a.close()
    asyncio.run(srv(scenario))


def test_reconnect_resumes_from_last_seq(srv):
    async def scenario(server):
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "chat", "from": "alfa", "ts": 1.0,
                                 "text": "@beta jeden"}))
        await a.send(json.dumps({"type": "chat", "from": "alfa", "ts": 2.0,
                                 "text": "@beta dwa"}))
        await asyncio.sleep(0.2)                      # niech serwer zapisze
        b, reply = await hello("beta", "tb", last_seq=0)
        texts = [f["text"] for f in reply["backlog"] if f["type"] == "chat"]
        assert texts == ["@beta jeden", "@beta dwa"]
        last = reply["backlog"][-1]["seq"]
        b2, reply2 = await hello("beta", "tb", last_seq=last)
        assert reply2["backlog"] == []                # nic nowego
        for ws in (a, b, b2):
            await ws.close()
    asyncio.run(srv(scenario))


def test_too_old_cursor_gets_resync_required(srv):
    async def scenario(server):
        a, _ = await hello("alfa", "ta")
        for i in range(3):
            await a.send(json.dumps({"type": "chat", "from": "alfa",
                                     "ts": float(i), "text": f"@beta {i}"}))
        await asyncio.sleep(0.2)
        server.snapshot()                              # kompakcja logu
        b, reply = await hello("beta", "tb", last_seq=1)  # kursor sprzed snapshotu
        assert reply["type"] == "resync_required"
        assert reply["snapshot_seq"] >= 3
        assert "state" in reply                        # spojny snapshot stanu
        await a.close(); await b.close()
    asyncio.run(srv(scenario))


# -- Nowe: hello zwraca regulamin (rules.md), jesli istnieje ---------------

def test_hello_returns_rules_when_present(srv):
    async def scenario(server):
        text = "badz mily\n"
        (server.log.dir / "rules.md").write_text(text)
        ws, reply = await hello("alfa", "ta")
        assert reply["rules"] == text
        assert reply["rules_hash"] == hashlib.sha256(text.encode()).hexdigest()
        await ws.close()
    asyncio.run(srv(scenario))


def test_hello_no_rules_field_when_file_absent(srv):
    async def scenario(server):
        ws, reply = await hello("alfa", "ta")
        assert "rules" not in reply
        assert "rules_hash" not in reply
        await ws.close()
    asyncio.run(srv(scenario))


# -- Nowe: grupy adresowe (aneks v2, kontrakt codexa) ------------------------

def test_group_mention_wakes_exact_members(srv):
    async def scenario(server):
        b, _ = await hello("beta", "tb", groups=["workers"])
        g, _ = await hello("gamma", "tg", groups=["workers"])
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "chat", "from": "alfa", "ts": 1.0,
                                 "text": "$workers hej"}))
        got_b = await recv(b)
        got_g = await recv(g)
        assert got_b["text"] == "$workers hej"
        assert got_g["text"] == "$workers hej"
        for ws in (a, b, g):
            await ws.close()
    asyncio.run(srv(scenario))


def test_group_mention_does_not_wake_non_members(srv):
    async def scenario(server):
        b, _ = await hello("beta", "tb", groups=["workers"])
        d, _ = await hello("delta", "td")             # nie nalezy do grupy
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "chat", "from": "alfa", "ts": 1.0,
                                 "text": "$workers tylko dla czlonkow"}))
        got_b = await recv(b)
        assert got_b["text"] == "$workers tylko dla czlonkow"
        with pytest.raises(asyncio.TimeoutError):
            await recv(d, timeout=0.4)
        for ws in (a, b, d):
            await ws.close()
    asyncio.run(srv(scenario))


def test_group_membership_survives_reconnect(srv):
    async def scenario(server):
        b1, _ = await hello("beta", "tb", instance="i1", groups=["workers"])
        await b1.close()
        await asyncio.sleep(0.1)
        b2, _ = await hello("beta", "tb", instance="i2", groups=["workers"])
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "chat", "from": "alfa", "ts": 1.0,
                                 "text": "$workers ping po reconnect"}))
        got = await recv(b2)
        assert got["text"] == "$workers ping po reconnect"
        await a.close(); await b2.close()
    asyncio.run(srv(scenario))


def test_unknown_group_yields_error_no_silent_broadcast(srv):
    async def scenario(server):
        b, _ = await hello("beta", "tb")
        g, _ = await hello("gamma", "tg")
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "chat", "from": "alfa", "ts": 1.0,
                                 "text": "@beta hej $upiory"}))
        err = await recv(a)                            # nadawca dostaje error
        assert err["type"] == "error"
        got_b = await recv(b)                           # @beta dziala normalnie
        assert got_b["text"] == "@beta hej $upiory"
        with pytest.raises(asyncio.TimeoutError):        # zero cichego broadcastu
            await recv(g, timeout=0.4)
        for ws in (a, b, g):
            await ws.close()
    asyncio.run(srv(scenario))


# -- Nowe: stary socket po takeover odrzucany --------------------------------

def test_stale_socket_rejected_after_takeover(srv):
    async def scenario(server):
        a1, reply1 = await hello("alfa", "ta", instance="i1")
        assert reply1["generation"] == 1
        b, _ = await hello("beta", "tb")
        a2, reply2 = await hello("alfa", "ta", instance="i2")  # takeover
        assert reply2["generation"] == 2
        await a1.send(json.dumps({"type": "chat", "from": "alfa", "ts": 1.0,
                                  "text": "@beta ze starego socketu"}))
        err = await recv(a1)
        assert err["type"] == "error"
        with pytest.raises(asyncio.TimeoutError):        # nic nie dotarlo do beta
            await recv(b, timeout=0.4)
        # nowy socket dziala normalnie
        await a2.send(json.dumps({"type": "chat", "from": "alfa", "ts": 2.0,
                                  "text": "@beta z nowego socketu"}))
        got = await recv(b)
        assert got["text"] == "@beta z nowego socketu"
        for ws in (a1, a2, b):
            await ws.close()
    asyncio.run(srv(scenario))


# -- Nowe: kontrakt wejscia ramek taskowych (niezmiennik f) -----------------

def test_task_flow_and_malformed_frame_does_not_crash_server(srv):
    async def scenario(server):
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                 "command_id": "n1", "card": CARD}))
        ok = await recv(a)
        assert ok["type"] == "ok" and ok["task"]["status"] == "open"
        task_id = ok["task"]["id"]

        b, _ = await hello("beta", "tb")
        await b.send(json.dumps({"type": "task_claim", "from": "beta", "ts": 0.0,
                                 "task_id": task_id, "command_id": "c1",
                                 "expected_task_version": 1}))
        claimed = await recv(b)
        assert claimed["type"] == "ok" and claimed["task"]["status"] == "claimed"

        # zle uformowana ramka taskowa (brak task_id) -> error, bez crasha
        await a.send(json.dumps({"type": "task_claim", "from": "alfa", "ts": 0.0,
                                 "command_id": "bad1"}))
        err = await recv(a)
        assert err["type"] == "error" and err["command_id"] == "bad1"

        # serwer nadal dziala normalnie po zlej ramce
        await a.send(json.dumps({"type": "chat", "from": "alfa", "ts": 1.0,
                                 "text": "@beta wciaz zyje"}))
        got = await recv(b)
        assert got["text"] == "@beta wciaz zyje"
        for ws in (a, b):
            await ws.close()
    asyncio.run(srv(scenario))


# -- Nowe: activation_id kotwiczony w evencie --------------------------------

def test_activation_id_retry_identical_new_offer_different(srv):
    async def scenario(server):
        task_a = server.queue.add(CARD, "c1", 0.0)
        before = server.log.last_seq
        id1 = server._offer_activation_id("beta", task_a)
        after_first = server.log.last_seq
        id2 = server._offer_activation_id("beta", task_a)   # retry tej samej oferty
        after_second = server.log.last_seq
        assert id1 == id2
        assert after_first == before + 1          # dokladnie jeden nowy event
        assert after_second == after_first          # retry NIE dopisuje eventu

        task_b = server.queue.add({**CARD, "goal": "y"}, "c2", 0.0)
        id3 = server._offer_activation_id("beta", task_b)    # inny task -> nowa oferta
        assert id3 != id1
        id4 = server._offer_activation_id("gamma", task_a)   # inny nick -> nowa oferta
        assert id4 != id1
    asyncio.run(srv(scenario))


# -- Nowe: restart odtwarza queue+registry po snapshocie ---------------------

def test_restart_restores_queue_and_registry_after_snapshot(tmp_path):
    async def scenario():
        s1 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                         lease_ttl=5.0, offer_timeout=0.3)
        await s1.start()
        ws, reply = await hello("alfa", "ta", instance="i1")
        assert reply["generation"] == 1
        await ws.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                  "command_id": "n1", "card": CARD}))
        ack = await recv(ws)
        assert ack["type"] == "ok"
        s1.snapshot()
        await ws.close()
        await s1.stop()

        s2 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                         lease_ttl=5.0, offer_timeout=0.3)
        dumped = s2.queue.dump()
        assert any(t["status"] == "open" and t["card"]["goal"] == "x"
                   for t in dumped["tasks"])
        assert s2.registry.generation_of("alfa") == 1

        await s2.start()
        try:
            ws2, reply2 = await hello("alfa", "ta", instance="i1")  # ten sam instance
            assert reply2["generation"] == 1          # nie bumpowane po restarcie
            ws3, reply3 = await hello("alfa", "ta", instance="i2")  # nowy instance
            assert reply3["generation"] == 2
            await ws2.close(); await ws3.close()
        finally:
            await s2.stop()
    asyncio.run(scenario())


# -- G: brakujace przejscia w protokole — task_approve, task_unblock --------

def test_task_approve_completes_review_cycle_via_frames(srv):
    async def scenario(server):
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                 "command_id": "n1", "card": CARD}))
        ok = await recv(a)
        task_id = ok["task"]["id"]

        b, _ = await hello("beta", "tb")
        await b.send(json.dumps({"type": "task_claim", "from": "beta", "ts": 0.0,
                                 "task_id": task_id, "command_id": "c1",
                                 "expected_task_version": 1}))
        claimed = await recv(b)
        v = claimed["task"]["version"]

        await b.send(json.dumps({"type": "task_done", "from": "beta", "ts": 0.0,
                                 "task_id": task_id, "command_id": "d1",
                                 "expected_task_version": v}))
        reviewed = await recv(b)
        assert reviewed["task"]["status"] == "review"
        v = reviewed["task"]["version"]

        await b.send(json.dumps({"type": "task_approve", "from": "beta", "ts": 0.0,
                                 "task_id": task_id, "command_id": "ap1",
                                 "expected_task_version": v}))
        approved = await recv(b)
        assert approved["type"] == "ok" and approved["task"]["status"] == "done"
        await a.close(); await b.close()
    asyncio.run(srv(scenario))


def test_task_unblock_frame_transitions_blocked_to_claimed(srv):
    async def scenario(server):
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                 "command_id": "n1", "card": CARD}))
        ok = await recv(a)
        task_id = ok["task"]["id"]

        b, _ = await hello("beta", "tb")
        await b.send(json.dumps({"type": "task_claim", "from": "beta", "ts": 0.0,
                                 "task_id": task_id, "command_id": "c1",
                                 "expected_task_version": 1}))
        claimed = await recv(b)
        v = claimed["task"]["version"]

        await b.send(json.dumps({"type": "task_blocked", "from": "beta", "ts": 0.0,
                                 "task_id": task_id, "command_id": "bl1",
                                 "expected_task_version": v}))
        blocked = await recv(b)
        assert blocked["task"]["status"] == "blocked"
        v = blocked["task"]["version"]

        await b.send(json.dumps({"type": "task_unblock", "from": "beta", "ts": 0.0,
                                 "task_id": task_id, "command_id": "ub1",
                                 "expected_task_version": v}))
        unblocked = await recv(b)
        assert unblocked["type"] == "ok" and unblocked["task"]["status"] == "claimed"
        await a.close(); await b.close()
    asyncio.run(srv(scenario))
