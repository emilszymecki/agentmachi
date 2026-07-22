"""Testy integracyjne chat/server.py: hello/auth, generation przypieta do
socketu, backlog/resync, echo po nicku, wzmianki, grupy adresowe,
snapshot+restart, activation_id kotwiczony w evencie.

Serwer per-test na porcie 8891+ (nie 8765 — PoC A na roocie repo).
"""
import asyncio
import hashlib
import json
import socket
from pathlib import Path

import pytest
import websockets

from chat.server import ChatServer

TOKENS = {
    "alfa": "ta",                                                     # stary format (kompat)
    "beta": {"token": "tb", "role": "agent", "groups": ["workers"]},   # H: grupy z configu
    "emil": {"token": "te", "role": "human", "groups": []},            # H: rola z configu
    "gamma": {"token": "tg", "role": "agent", "groups": ["workers"]},
    "delta": "td",                                                    # nie w zadnej grupie
}


def _free_port():
    # Efemeryczny port per proces pytest — tercet review'uje rownolegle na
    # jednym repo, staly port dawal falszywe "address already in use".
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("localhost", 0))
    port = s.getsockname()[1]
    s.close()
    return port


PORT = _free_port()


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
        # (A) hello jest teraz sam logowanym eventem — wlasne hello nie jest
        # widoczne we WLASNYM backlogu (liczonym przed jego zalogowaniem),
        # wiec poprawny kursor do wznowienia to reply["last_seq"] podany
        # przez serwer, nie ostatni wpis backlogu (ktory moze nie
        # odzwierciedlac eventow "niewidocznych dla siebie samego")
        last = reply["last_seq"]
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
    # (C) od tego fixu takeover zamyka stary socket NATYCHMIAST przy hello —
    # a1 dostaje error+close, zanim zdazy cokolwiek wyslac (patrz tez
    # test_takeover_closes_old_socket_immediately_before_it_sends_anything
    # nizej, ktory sprawdza to explicite jako repro C).
    async def scenario(server):
        a1, reply1 = await hello("alfa", "ta", instance="i1")
        assert reply1["generation"] == 1
        b, _ = await hello("beta", "tb")
        a2, reply2 = await hello("alfa", "ta", instance="i2")  # takeover
        assert reply2["generation"] == 2
        err = await recv(a1)                              # error natychmiast, bez wysylki
        assert err["type"] == "error"
        with pytest.raises(websockets.exceptions.ConnectionClosed):
            await a1.send(json.dumps({"type": "chat", "from": "alfa", "ts": 1.0,
                                      "text": "@beta ze starego socketu"}))
        with pytest.raises(asyncio.TimeoutError):        # nic nie dotarlo do beta
            await recv(b, timeout=0.4)
        # nowy socket dziala normalnie
        await a2.send(json.dumps({"type": "chat", "from": "alfa", "ts": 2.0,
                                  "text": "@beta z nowego socketu"}))
        got = await recv(b)
        assert got["text"] == "@beta z nowego socketu"
        for ws in (a2, b):
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
    # (8) ZMIANA KONTRAKTU B1 (swiadoma): approve wysyla KTOKOLWIEK POZA
    # assignee — tu approve idzie od gammy (nie od bety, ktora wykonala task).
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

        g, _ = await hello("gamma", "tg")          # inny nick niz assignee
        await g.send(json.dumps({"type": "task_approve", "from": "gamma", "ts": 0.0,
                                 "task_id": task_id, "command_id": "ap1",
                                 "expected_task_version": v}))
        approved = await recv(g)
        assert approved["type"] == "ok" and approved["task"]["status"] == "done"
        await a.close(); await b.close(); await g.close()
    asyncio.run(srv(scenario))


def test_task_approve_by_assignee_rejected_other_nick_approves(srv):
    # (8) assignee -> error (samo-approve zabronione w B1); inny nick -> done.
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
        v = reviewed["task"]["version"]

        # assignee (beta) probuje samo-approve -> error, task zostaje w review
        await b.send(json.dumps({"type": "task_approve", "from": "beta", "ts": 0.0,
                                 "task_id": task_id, "command_id": "ap-self",
                                 "expected_task_version": v}))
        err = await recv(b)
        assert err["type"] == "error" and err["command_id"] == "ap-self"
        assert server.queue.get(task_id)["status"] == "review"  # bez mutacji

        # inny nick (gamma) approve -> done
        g, _ = await hello("gamma", "tg")
        await g.send(json.dumps({"type": "task_approve", "from": "gamma", "ts": 0.0,
                                 "task_id": task_id, "command_id": "ap-other",
                                 "expected_task_version": v}))
        approved = await recv(g)
        assert approved["type"] == "ok" and approved["task"]["status"] == "done"
        await a.close(); await b.close(); await g.close()
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


# -- E: skalar/nie-dict JSON nie zabija handlera -----------------------------

@pytest.mark.parametrize("payload", ["42", '"x"', "[1,2,3]"])
def test_scalar_json_as_first_frame_gets_error_and_close(srv, payload):
    async def scenario(server):
        ws = await websockets.connect(f"ws://localhost:{PORT}")
        await ws.send(payload)
        err = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert err["type"] == "error"
        with pytest.raises(websockets.exceptions.ConnectionClosed):
            await asyncio.wait_for(ws.recv(), timeout=1.0)
    asyncio.run(srv(scenario))


@pytest.mark.parametrize("payload", ["42", '"x"', "[1,2,3]"])
def test_scalar_json_after_hello_does_not_kill_handler(srv, payload):
    async def scenario(server):
        a, _ = await hello("alfa", "ta")
        await a.send(payload)
        err = await recv(a)
        assert err["type"] == "error"
        # handler wciaz zyje — kolejna poprawna ramka dziala normalnie
        b, _ = await hello("beta", "tb")
        await a.send(json.dumps({"type": "chat", "from": "alfa", "ts": 1.0,
                                 "text": "@beta wciaz zyje"}))
        got = await recv(b)
        assert got["text"] == "@beta wciaz zyje"
        await a.close(); await b.close()
    asyncio.run(srv(scenario))


# -- D: pola autorytatywne wszedzie (seq/generation/groups/from/role) -------

def test_forged_authoritative_fields_stripped_from_chat_frame(srv):
    async def scenario(server):
        a, _ = await hello("alfa", "ta")
        b, _ = await hello("beta", "tb")
        await a.send(json.dumps({"type": "chat", "from": "mallory", "ts": 1.0,
                                 "text": "@beta hej", "generation": 999,
                                 "groups": ["forged"], "seq": 999, "role": "human"}))
        got = await recv(b)
        assert got["from"] == "alfa"           # nie mallory — tozsamosc z hello
        assert got["seq"] != 999 and got["seq"] >= 1
        assert "generation" not in got
        assert "groups" not in got
        assert "role" not in got
        logged = server.log.events_after(0)[-1]
        assert logged["from"] == "alfa"
        assert "generation" not in logged
        assert "groups" not in logged
        assert "role" not in logged
        await a.close(); await b.close()
    asyncio.run(srv(scenario))


def test_forged_authoritative_fields_stripped_from_task_frame(srv):
    async def scenario(server):
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "task_new", "from": "mallory", "ts": 0.0,
                                 "command_id": "n1", "card": CARD,
                                 "generation": 999, "groups": ["forged"],
                                 "seq": 999}))
        ok = await recv(a)
        assert ok["type"] == "ok"
        logged = server.log.events_after(0)[-1]
        assert logged["type"] == "task_new"
        assert logged["from"] == "alfa"
        assert "generation" not in logged
        assert "groups" not in logged
        await a.close()
    asyncio.run(srv(scenario))


# -- H: role/grupy z configu serwera (decyzja tercetu) -----------------------

def test_declared_role_human_in_hello_is_ignored_no_live_feed(srv):
    async def scenario(server):
        # alfa jest w TOKENS starym formatem -> role serwerowa "agent",
        # mimo ze w hello deklaruje "human"
        a, _ = await hello("alfa", "ta", role="human")
        b, _ = await hello("beta", "tb")
        await b.send(json.dumps({"type": "chat", "from": "beta", "ts": 1.0,
                                 "text": "bez wzmianki o alfie"}))
        with pytest.raises(asyncio.TimeoutError):
            await recv(a, timeout=0.4)
        await a.close(); await b.close()
    asyncio.run(srv(scenario))


def test_declared_groups_in_hello_are_ignored_not_member_of_declared_group(srv):
    async def scenario(server):
        # alfa (stary format, bez skonfigurowanych grup) deklaruje w hello
        # przynaleznosc do $admin — deklaracja jest tylko do walidacji,
        # nie rejestruje alfy w zadnej grupie
        a, _ = await hello("alfa", "ta", groups=["admin"])
        c, _ = await hello("delta", "td")
        await c.send(json.dumps({"type": "chat", "from": "delta", "ts": 1.0,
                                 "text": "$admin hej"}))
        err = await recv(c)                     # nieznana grupa (nikt jej realnie nie ma)
        assert err["type"] == "error"
        with pytest.raises(asyncio.TimeoutError):
            await recv(a, timeout=0.4)
        await a.close(); await c.close()
    asyncio.run(srv(scenario))


# -- C: takeover odcina stary socket NATYCHMIAST, nie dopiero po jego ramce --

def test_takeover_closes_old_socket_immediately_before_it_sends_anything(srv):
    async def scenario(server):
        a1, reply1 = await hello("alfa", "ta", instance="i1")
        b, _ = await hello("beta", "tb")
        # takeover — a1 NIC jeszcze nie wyslal po hello, a mimo to ma
        # dostac error i zostac zamknietym NATYCHMIAST przy tym hello
        a2, reply2 = await hello("alfa", "ta", instance="i2")
        assert reply2["generation"] == reply1["generation"] + 1
        err = await recv(a1, timeout=1.0)
        assert err["type"] == "error"
        with pytest.raises(websockets.exceptions.ConnectionClosed):
            await asyncio.wait_for(a1.recv(), timeout=1.0)   # socket faktycznie zamkniety
        await b.send(json.dumps({"type": "chat", "from": "beta", "ts": 1.0,
                                 "text": "@alfa hej"}))
        got = await recv(a2)
        assert got["text"] == "@alfa hej"        # tylko nowy socket dostaje
        await a2.close(); await b.close()
    asyncio.run(srv(scenario))


# -- B: resync spojny — snapshot_seq etykieta musi pasowac do zwroconego state

def test_resync_snapshot_seq_matches_returned_fresh_state(srv):
    async def scenario(server):
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "fyi", "from": "alfa", "ts": 0.0,
                                 "text": "seed"}))    # cokolwiek w logu przed snapshotem
        await asyncio.sleep(0.1)
        server.snapshot()                          # snapshot WCZESNIE (etykieta by byla stara)
        await a.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                 "command_id": "n1", "card": CARD}))
        ok = await recv(a)
        task_id = ok["task"]["id"]
        await a.send(json.dumps({"type": "task_claim", "from": "alfa", "ts": 0.0,
                                 "task_id": task_id, "command_id": "c1",
                                 "expected_task_version": 1}))
        claimed = await recv(a)
        assert claimed["task"]["status"] == "claimed"
        # kursor sprzed WSZYSTKICH powyzszych eventow -> resync_required
        b, reply = await hello("beta", "tb", last_seq=0)
        assert reply["type"] == "resync_required"
        # (B) etykieta snapshot_seq MUSI odzwierciedlac faktyczny, swiezy
        # stan (claim juz w srodku), nie stara wartosc sprzed claima
        assert reply["snapshot_seq"] == server.log.last_seq
        state_tasks = reply["state"]["queue"]["tasks"]
        assert any(t["id"] == task_id and t["status"] == "claimed" for t in state_tasks)
        # replay od zwroconego snapshot_seq nie dubluje niczego juz w state
        assert server.log.events_after(reply["snapshot_seq"]) == []
        await a.close(); await b.close()
    asyncio.run(srv(scenario))


# -- A: crash-recovery — eventy po (ostatnim) snapshocie MUSZA sie odtworzyc

async def _crash_stop(server):
    """Symuluje crash: zamyka nasluch/petle serwera BEZ wywolania snapshot()
    (w odroznieniu od server.stop(), ktory zawsze snapshotuje na koniec —
    to jest wlasnie sciezka, ktora maskowalaby brak replay w __init__)."""
    for task in (server._expiry_task, server._offering):
        if task is None:
            continue
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    server._server.close()
    await server._server.wait_closed()


def test_crash_recovery_replays_events_after_snapshot_without_manual_snapshot(tmp_path):
    async def scenario():
        s1 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                         lease_ttl=5.0, offer_timeout=0.3)
        await s1.start()
        ws, reply = await hello("alfa", "ta", instance="i1")
        assert reply["generation"] == 1
        await ws.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                  "command_id": "n1", "card": CARD}))
        ack = await recv(ws)
        task_id = ack["task"]["id"]
        await ws.send(json.dumps({"type": "task_claim", "from": "alfa", "ts": 0.0,
                                  "task_id": task_id, "command_id": "c1",
                                  "expected_task_version": 1}))
        claimed = await recv(ws)
        assert claimed["task"]["status"] == "claimed"
        await ws.close()
        await _crash_stop(s1)          # BEZ recznego/automatycznego snapshotu

        # "restart": nowy ChatServer nad tym samym data_dir, zero snapshotu
        # na dysku — caly stan musi wrocic z samego logu eventow (replay)
        assert not (Path(tmp_path) / "snapshot.json").exists()
        s2 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                         lease_ttl=5.0, offer_timeout=0.3)
        t = s2.queue.get(task_id)
        assert t["status"] == "claimed" and t["assignee"] == "alfa"
        assert s2.registry.generation_of("alfa") == 1     # (hello -> registry odtworzone)
    asyncio.run(scenario())


def test_crash_recovery_snapshot_counter_seeded_from_replayed_events(tmp_path):
    async def scenario():
        s1 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                         lease_ttl=5.0, offer_timeout=0.3)
        await s1.start()
        ws, _ = await hello("alfa", "ta", instance="i1")
        await ws.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                  "command_id": "n1", "card": CARD}))
        await recv(ws)
        events_on_disk = s1.log.last_seq
        await ws.close()
        await _crash_stop(s1)

        s2 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                         lease_ttl=5.0, offer_timeout=0.3)
        # (A3) licznik snapshot-co-100 startuje od liczby eventow juz w logu,
        # nie od zera — inaczej po restarcie trzeba by 100 NOWYCH eventow
        # zanim serwer w ogole rozwazy pierwszy snapshot po starcie
        assert s2._events_since_snapshot == events_on_disk
    asyncio.run(scenario())


# -- F: oferty — activation trwaly, poprawny cache, wyscig, sprzatanie idle -

def test_task_offer_event_persists_activation_id_and_seq(srv):
    async def scenario(server):
        task = server.queue.add(CARD, "c1", 0.0)
        activation_id = server._offer_activation_id("beta", task)
        offer_events = [e for e in server.log.events_after(0) if e["type"] == "task_offer"]
        assert len(offer_events) == 1
        # (F1) trwaly event MUSI zawierac activation_id i seq — nie tylko
        # zwrocona wartosc w pamieci
        assert offer_events[0]["activation_id"] == activation_id
        assert offer_events[0]["seq"] == offer_events[0]["seq"]  # obecne pole seq
        assert "seq" in offer_events[0]
    asyncio.run(srv(scenario))


def test_offer_round_robin_new_attempt_after_full_cycle_gets_new_id(srv):
    async def scenario(server):
        b, _ = await hello("beta", "tb")
        g, _ = await hello("gamma", "tg")
        await b.send(json.dumps({"type": "status", "from": "beta", "ts": 0.0, "state": "idle"}))
        await g.send(json.dumps({"type": "status", "from": "gamma", "ts": 0.0, "state": "idle"}))
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                 "command_id": "n1", "card": CARD}))
        await recv(a)                              # ok ack dla task_new

        offer_b1 = await recv(b, timeout=2.0)        # pierwsza oferta dla beta
        id_b1 = offer_b1["activation_id"]
        offer_g = await recv(g, timeout=2.0)         # beta nie wzieła -> gamma
        offer_b2 = await recv(b, timeout=2.0)        # gamma tez nie -> NOWA proba dla beta
        id_b2 = offer_b2["activation_id"]
        # (F2) nowa proba (po pelnym okrazeniu beta->gamma->beta) to NOWY
        # event/id, a nie sklejenie z pierwsza oferta dla bety
        assert id_b2 != id_b1
        await a.close(); await b.close(); await g.close()
    asyncio.run(srv(scenario))


def test_offer_timeout_race_does_not_lose_offered_nick_from_idle(srv):
    async def scenario(server):
        b, _ = await hello("beta", "tb")
        g, _ = await hello("gamma", "tg")
        await b.send(json.dumps({"type": "status", "from": "beta", "ts": 0.0, "state": "idle"}))
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                 "command_id": "n1", "card": CARD}))
        ok1 = await recv(a)
        task1_id = ok1["task"]["id"]
        offer1 = await recv(b, timeout=2.0)
        assert offer1["task"]["id"] == task1_id

        # gamma krad task1 (bezposredni task_claim) zanim minie offer_timeout
        # oferty dla bety — bez fixu bety nigdy nie wraca do self.idle
        await g.send(json.dumps({"type": "task_claim", "from": "gamma", "ts": 0.0,
                                 "task_id": task1_id, "command_id": "steal1",
                                 "expected_task_version": 1}))
        stolen = await recv(g)
        assert stolen["task"]["assignee"] == "gamma"

        await asyncio.sleep(0.6)     # przeczekaj offer_timeout (0.3 z fixture) + margines

        await a.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 1.0,
                                 "command_id": "n2", "card": {**CARD, "goal": "drugi"}}))
        ok2 = await recv(a)
        task2_id = ok2["task"]["id"]
        # (F4) beta MUSI dalej byc w idle i dostac oferte na drugi task
        offer2 = await recv(b, timeout=2.0)
        assert offer2["task"]["id"] == task2_id
        await a.close(); await b.close(); await g.close()
    asyncio.run(srv(scenario))


def test_idle_nick_removed_on_disconnect_offer_goes_to_live_idle(srv):
    async def scenario(server):
        b, _ = await hello("beta", "tb")
        await b.send(json.dumps({"type": "status", "from": "beta", "ts": 0.0, "state": "idle"}))
        await asyncio.sleep(0.1)
        await b.close()
        await asyncio.sleep(0.1)
        # (F5) rozlaczony nick (bez zadnego socketu) wypada z self.idle
        assert "beta" not in server.idle

        g, _ = await hello("gamma", "tg")
        await g.send(json.dumps({"type": "status", "from": "gamma", "ts": 0.0, "state": "idle"}))
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                 "command_id": "n1", "card": CARD}))
        await recv(a)
        offer = await recv(g, timeout=2.0)          # oferta idzie do zywego gamma, nie w prozne
        assert offer["type"] == "task_offer"
        await a.close(); await g.close()
    asyncio.run(srv(scenario))


def test_pending_offer_cache_restored_after_restart(tmp_path):
    async def scenario():
        s1 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                         lease_ttl=5.0, offer_timeout=0.3)
        await s1.start()
        ws, _ = await hello("alfa", "ta")
        await ws.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                  "command_id": "n1", "card": CARD}))
        ack = await recv(ws)
        task = ack["task"]
        activation_id = s1._offer_activation_id("beta", task)
        await ws.close()
        await _crash_stop(s1)             # BEZ snapshotu

        s2 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                         lease_ttl=5.0, offer_timeout=0.3)
        # (F3) retry TEJ SAMEJ proby po restarcie -> ten sam activation_id,
        # BEZ nowego eventu — odtworzone z replay eventow (task_offer)
        before = s2.log.last_seq
        again = s2._offer_activation_id("beta", task)
        assert again == activation_id
        assert s2.log.last_seq == before
    asyncio.run(scenario())


# == RUNDA 3 — result-based replay ==========================================

# -- (2) SEDNO: replay result-based, niezalezny od biezacej polityki --------

def test_replay_ignores_current_wip_policy(tmp_path):
    # (2a) dwa claimy przy wip_limit=2, restart z wip_limit=1 -> konstruktor
    # NIE crashuje (replay result-based nie re-waliduje WIP), oba claimed.
    async def scenario():
        s1 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                         wip_limit=2, lease_ttl=5.0, offer_timeout=0.3)
        await s1.start()
        a, _ = await hello("alfa", "ta")
        b, _ = await hello("beta", "tb")
        await a.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                 "command_id": "n1", "card": CARD}))
        t1 = (await recv(a))["task"]["id"]
        await a.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                 "command_id": "n2", "card": {**CARD, "goal": "y"}}))
        t2 = (await recv(a))["task"]["id"]
        await a.send(json.dumps({"type": "task_claim", "from": "alfa", "ts": 0.0,
                                 "task_id": t1, "command_id": "c1",
                                 "expected_task_version": 1}))
        assert (await recv(a))["task"]["status"] == "claimed"
        await b.send(json.dumps({"type": "task_claim", "from": "beta", "ts": 0.0,
                                 "task_id": t2, "command_id": "c2",
                                 "expected_task_version": 1}))
        assert (await recv(b))["task"]["status"] == "claimed"
        await a.close(); await b.close()
        await _crash_stop(s1)                       # BEZ snapshotu

        s2 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                         wip_limit=1, lease_ttl=5.0, offer_timeout=0.3)  # ciasniejsza polityka
        assert s2.queue.get(t1)["status"] == "claimed"
        assert s2.queue.get(t2)["status"] == "claimed"
    asyncio.run(scenario())


def test_replay_preserves_historical_lease_until(tmp_path):
    # (2b) claim przy lease_ttl=10, restart z lease_ttl=100 -> lease_until
    # odtworzone HISTORYCZNE (z task_state), nie przeliczone wg nowej polityki.
    async def scenario():
        s1 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                         lease_ttl=10.0, offer_timeout=0.3)
        await s1.start()
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                 "command_id": "n1", "card": CARD}))
        tid = (await recv(a))["task"]["id"]
        await a.send(json.dumps({"type": "task_claim", "from": "alfa", "ts": 0.0,
                                 "task_id": tid, "command_id": "c1",
                                 "expected_task_version": 1}))
        lease_hist = (await recv(a))["task"]["lease_until"]
        await a.close()
        await _crash_stop(s1)

        s2 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                         lease_ttl=100.0, offer_timeout=0.3)  # inna polityka lease
        assert s2.queue.get(tid)["lease_until"] == lease_hist
    asyncio.run(scenario())


# -- (1) expiry jako trwaly, replayowalny event -----------------------------

def test_expiry_event_replays_result_based_no_conflict(tmp_path):
    # (1) claim(v2) -> expire(v3, open) -> drugi claim(expected=3, v4) ->
    # crash/restart: konstruktor NIE rzuca Conflict, stan = v4 claimed.
    # Na starym kodzie expiry byl fyi (nie-replayowalny) -> replay drugiego
    # claima (expected=3) trafial na v2 claimed -> Conflict w __init__.
    async def scenario():
        s1 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                         lease_ttl=0.5, offer_timeout=0.3)   # krotki lease -> szybki expire
        await s1.start()
        ws, _ = await hello("alfa", "ta")
        await ws.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                  "command_id": "n1", "card": CARD}))
        tid = (await recv(ws))["task"]["id"]
        await ws.send(json.dumps({"type": "task_claim", "from": "alfa", "ts": 0.0,
                                  "task_id": tid, "command_id": "c1",
                                  "expected_task_version": 1}))
        assert (await recv(ws))["task"]["version"] == 2       # v2 claimed
        await asyncio.sleep(1.6)      # petla expiry (co 1.0s) reopenuje po lease 0.5
        await ws.send(json.dumps({"type": "task_claim", "from": "alfa", "ts": 0.0,
                                  "task_id": tid, "command_id": "c2",
                                  "expected_task_version": 3}))  # open v3 -> claimed v4
        reclaimed = await recv(ws)
        assert reclaimed["task"]["status"] == "claimed" and reclaimed["task"]["version"] == 4
        await ws.close()
        await _crash_stop(s1)                 # BEZ snapshotu

        s2 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                         lease_ttl=0.5, offer_timeout=0.3)      # konstruktor NIE rzuca
        t = s2.queue.get(tid)
        assert t["status"] == "claimed" and t["version"] == 4 and t["assignee"] == "alfa"
    asyncio.run(scenario())


# -- (3) trwaly lifecycle ofert (pending przezywa, resolved nie odzywa) ------

def test_pending_offer_survives_clean_stop_and_restart(tmp_path):
    # (3) pending oferta przezywa CLEAN stop->restart (ten sam activation_id,
    # ZERO nowego eventu) — odtworzona ze snapshotu (offers w state).
    async def scenario():
        s1 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                         lease_ttl=5.0, offer_timeout=0.3)
        await s1.start()
        ws, _ = await hello("alfa", "ta")
        await ws.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                  "command_id": "n1", "card": CARD}))
        task = (await recv(ws))["task"]
        activation_id = s1._offer_activation_id("beta", task)     # pending offer
        await ws.close()
        await s1.stop()                          # CLEAN stop -> snapshot (z offers)

        s2 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                         lease_ttl=5.0, offer_timeout=0.3)
        before = s2.log.last_seq
        again = s2._offer_activation_id("beta", task)
        assert again == activation_id            # ten sam activation_id
        assert s2.log.last_seq == before         # ZERO nowego eventu
    asyncio.run(scenario())


def test_resolved_offer_does_not_revive_after_replay(tmp_path):
    # (3) oferta rozstrzygnieta PRZED crashem (offer_resolved) NIE odzywa po
    # replay — kolejna proba to NOWY event/activation_id.
    async def scenario():
        s1 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                         lease_ttl=5.0, offer_timeout=0.3)
        await s1.start()
        ws, _ = await hello("alfa", "ta")
        await ws.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                  "command_id": "n1", "card": CARD}))
        task = (await recv(ws))["task"]
        aid1 = s1._offer_activation_id("beta", task)              # task_offer event
        s1._resolve_offer("beta", task["id"], task["version"], "timeout")  # offer_resolved
        await ws.close()
        await _crash_stop(s1)                     # BEZ snapshotu -> replay z eventow

        s2 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                         lease_ttl=5.0, offer_timeout=0.3)
        assert ("beta", task["id"], task["version"]) not in s2._offer_cache
        before = s2.log.last_seq
        aid2 = s2._offer_activation_id("beta", task)              # NOWA proba
        assert aid2 != aid1
        assert s2.log.last_seq == before + 1      # nowy task_offer event
    asyncio.run(scenario())


# -- (4) live task_offer = trwaly event z seq -------------------------------

def test_live_task_offer_carries_persistent_event_seq(srv):
    async def scenario(server):
        b, _ = await hello("beta", "tb")
        await b.send(json.dumps({"type": "status", "from": "beta", "ts": 0.0, "state": "idle"}))
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                 "command_id": "n1", "card": CARD}))
        await recv(a)
        offer = await recv(b, timeout=2.0)
        assert offer["type"] == "task_offer"
        # (4) odbiorca widzi DOKLADNIE trwaly event: seq == seq zapisanego eventu
        offer_events = [e for e in server.log.events_after(0) if e["type"] == "task_offer"]
        assert "seq" in offer
        assert offer["seq"] == offer_events[-1]["seq"]
        await a.close(); await b.close()
    asyncio.run(srv(scenario))


# -- (5) brak ducha w idle przy disconnect w oknie oferty --------------------

def test_disconnect_in_offer_window_leaves_no_ghost_in_idle(srv):
    async def scenario(server):
        b, _ = await hello("beta", "tb")
        await b.send(json.dumps({"type": "status", "from": "beta", "ts": 0.0, "state": "idle"}))
        await asyncio.sleep(0.1)
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                 "command_id": "n1", "card": CARD}))
        await recv(a)
        offer = await recv(b, timeout=2.0)          # beta dostaje oferte (popped z idle)
        assert offer["type"] == "task_offer"
        await b.close()                              # disconnect W OKNIE oferty
        await asyncio.sleep(0.6)                     # przeczekaj offer_timeout (0.3) + margines
        # (5) beta nie wraca do idle jako "duch" — brak zywego socketu
        assert "beta" not in server.idle
        # kolejna oferta idzie do ZYWEGO nicka (task wciaz open)
        g, _ = await hello("gamma", "tg")
        await g.send(json.dumps({"type": "status", "from": "gamma", "ts": 0.0, "state": "idle"}))
        offer_g = await recv(g, timeout=2.0)
        assert offer_g["type"] == "task_offer"
        await a.close(); await g.close()
    asyncio.run(srv(scenario))


# -- (6) brak okna wycieku przy takeover (_close_stale_sockets) --------------

def test_close_stale_sockets_evicts_from_conns_before_first_await(tmp_path):
    async def scenario():
        server = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                            lease_ttl=5.0, offer_timeout=0.3)

        class FakeWS:
            def __init__(self):
                self.sent = []
                self.gate = asyncio.Event()

            async def send(self, data):
                await self.gate.wait()              # blokuje w oknie takeover
                self.sent.append(data)

            async def close(self, code=None, reason=None):
                pass

        fake = FakeWS()
        server.conns["beta"] = {fake}
        task = asyncio.ensure_future(server._close_stale_sockets("beta"))
        await asyncio.sleep(0.05)                    # dojdz do pierwszego await (send)
        # (6) synchroniczny discard juz sie wykonal — stale socket NIE jest w conns
        assert fake not in server.conns.get("beta", set())
        # rownolegly _send w oknie NIE dostarcza staremu socketowi
        await server._send("beta", {"type": "chat", "text": "x"})
        assert fake.sent == []                       # gate wciaz zamknieta, nic nie doszlo
        fake.gate.set()
        await task
    asyncio.run(scenario())


# -- (7) domkniecie kontraktu wejscia ---------------------------------------

def test_hello_role_must_be_str(srv):
    async def scenario(server):
        ws = await websockets.connect(f"ws://localhost:{PORT}")
        await ws.send(json.dumps({"type": "hello", "from": "alfa", "ts": 0.0,
                                  "instance_id": "i1", "token": "ta",
                                  "last_seq": 0, "role": []}))   # role nie-string
        err = json.loads(await asyncio.wait_for(ws.recv(), 2.0))
        assert err["type"] == "error"
        await ws.close()
    asyncio.run(srv(scenario))


def test_hello_role_empty_string_rejected(srv):
    # (Runda 6 #4) _validate_role akceptowal pusty string ("" jest str) — a
    # AGENTS.md wymaga typu I niepustosci. role="" -> error do nadawcy.
    async def scenario(server):
        ws = await websockets.connect(f"ws://localhost:{PORT}")
        await ws.send(json.dumps({"type": "hello", "from": "alfa", "ts": 0.0,
                                  "instance_id": "i1", "token": "ta",
                                  "last_seq": 0, "role": ""}))   # pusty role
        err = json.loads(await asyncio.wait_for(ws.recv(), 2.0))
        assert err["type"] == "error"
        await ws.close()
    asyncio.run(srv(scenario))


def test_chat_without_text_errors_not_logged_not_delivered(srv):
    async def scenario(server):
        h, _ = await hello("emil", "te", role="human")
        a, _ = await hello("alfa", "ta")
        before = server.log.last_seq
        await a.send(json.dumps({"type": "chat", "from": "alfa", "ts": 1.0}))  # brak text
        err = await recv(a)
        assert err["type"] == "error"
        with pytest.raises(asyncio.TimeoutError):    # human NIE dostaje
            await recv(h, timeout=0.4)
        assert server.log.last_seq == before         # NIE trafil do logu
        await h.close(); await a.close()
    asyncio.run(srv(scenario))


def test_hello_last_seq_beyond_server_errors(srv):
    async def scenario(server):
        a, _ = await hello("alfa", "ta")
        for i in range(3):
            await a.send(json.dumps({"type": "chat", "from": "alfa",
                                     "ts": float(i), "text": f"@beta {i}"}))
        await asyncio.sleep(0.2)
        bad = await websockets.connect(f"ws://localhost:{PORT}")
        await bad.send(json.dumps({"type": "hello", "from": "beta", "ts": 0.0,
                                   "instance_id": "i1", "token": "tb",
                                   "last_seq": 999}))   # >> serwerowy last_seq
        err = json.loads(await asyncio.wait_for(bad.recv(), 2.0))
        assert err["type"] == "error"
        await a.close(); await bad.close()
    asyncio.run(srv(scenario))


# -- Task 7: oferty round-robin — warianty z briefu (nie pokryte przez F) ----

async def send_status_idle(ws, nick):
    await ws.send(json.dumps({"type": "status", "from": nick, "ts": 0.0,
                              "state": "idle"}))


def test_task_offer_goes_to_one_idle_worker(srv):
    async def scenario(server):
        b, _ = await hello("beta", "tb")
        g, _ = await hello("gamma", "tg")
        await send_status_idle(b, "beta")
        await send_status_idle(g, "gamma")
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                 "command_id": "n1", "card": CARD}))
        await recv(a)                                  # ok dla task_new
        offer = await recv(b)                          # TYLKO beta (pierwsza idle)
        assert offer["type"] == "task_offer"
        assert "activation_id" in offer
        with pytest.raises(asyncio.TimeoutError):
            await recv(g, timeout=0.2)                 # gamma spi — no herd
        for ws in (a, b, g):
            await ws.close()
    asyncio.run(srv(scenario))


def test_offer_timeout_moves_to_next_worker(srv):
    async def scenario(server):
        b, _ = await hello("beta", "tb")
        g, _ = await hello("gamma", "tg")
        await send_status_idle(b, "beta")
        await send_status_idle(g, "gamma")
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                 "command_id": "n2", "card": CARD}))
        await recv(a)
        await recv(b)                                  # beta dostaje oferte...
        offer_g = await recv(g, timeout=2.0)           # ...ignoruje -> gamma
        assert offer_g["type"] == "task_offer"
        for ws in (a, b, g):
            await ws.close()
    asyncio.run(srv(scenario))


# == RUNDA 4 — spojnosc log/stan i walidacja inbound ========================

# -- (1) cache-hit dedupu NIE moze tworzyc eventu mutacji -------------------

def test_dedup_cache_hit_does_not_append_mutation_event(tmp_path):
    # (1) task_new n1 -> open v1; claim c1 -> claimed v2; PONOW n1 (ten sam
    # command_id) -> dedup cache-hit zwraca cached open v1. Cache-hit to
    # ODPOWIEDZ dla klienta, NIE fakt do logu: gdyby serwer appendowal go
    # jako nowy task_state event, replay po restarcie zaaplikowalby open v1
    # PO claimed v2 i cofnal task. Test: retry po claim -> restart -> stan
    # zostaje claimed v2, tail logu bez zdublowanego task_new.
    async def scenario():
        s1 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                        lease_ttl=5.0, offer_timeout=0.3)
        await s1.start()
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                 "command_id": "n1", "card": CARD}))
        tid = (await recv(a))["task"]["id"]
        b, _ = await hello("beta", "tb")
        await b.send(json.dumps({"type": "task_claim", "from": "beta", "ts": 0.0,
                                 "task_id": tid, "command_id": "c1",
                                 "expected_task_version": 1}))
        claimed = await recv(b)
        assert claimed["task"]["status"] == "claimed" and claimed["task"]["version"] == 2

        seq_before_retry = s1.log.last_seq
        await a.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                 "command_id": "n1", "card": CARD}))    # PONOW n1
        retried = await recv(a)
        assert retried["type"] == "ok"                 # klient dostaje odpowiedz (cached)
        assert retried["task"]["status"] == "open"     # cached stary wynik
        assert s1.log.last_seq == seq_before_retry     # cache-hit NIE dopisuje eventu
        await a.close(); await b.close()
        await _crash_stop(s1)                           # BEZ snapshotu

        s2 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                        lease_ttl=5.0, offer_timeout=0.3)
        t = s2.queue.get(tid)
        assert t["status"] == "claimed" and t["version"] == 2  # NIE cofniete do open v1
    asyncio.run(scenario())


# -- (2) auto-snapshot NIE moze strzelic w srodku atomowej mutacji oferty ---

def test_auto_snapshot_mid_offer_does_not_lose_pending_offer(tmp_path):
    # (2) serwer wkladal oferte do _offer_cache PO _append. Gdy task_offer to
    # event #100, _append wywoluje snapshot ZANIM oferta trafi do cache ->
    # snapshot bez oferty + kompakcja usuwa event task_offer -> po restarcie
    # pending offer przepada, nowa oferta dostaje inny activation_id. Fix:
    # domkniecie stanu (offer w cache) PRZED mozliwym snapshotem. Test: 99
    # eventow + task_offer #100 -> restart -> pending offer odtworzone, ten
    # sam activation_id, zero nowego eventu.
    async def scenario():
        s1 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                        lease_ttl=5.0, offer_timeout=0.3)
        for i in range(99):    # dopchnij licznik do 99 -> nastepny _append snapshotuje
            s1._append({"type": "fyi", "from": "filler", "ts": 0.0, "text": str(i)})
        assert s1._events_since_snapshot == 99
        task = s1.queue.add(CARD, "c1", 0.0)
        activation_id = s1._offer_activation_id("beta", task)   # task_offer = event #100
        assert s1._events_since_snapshot == 0                    # auto-snapshot strzelil

        s2 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                        lease_ttl=5.0, offer_timeout=0.3)
        before = s2.log.last_seq
        again = s2._offer_activation_id("beta", task)
        assert again == activation_id            # pending offer odtworzone (ten sam id)
        assert s2.log.last_seq == before         # zero nowego eventu
    asyncio.run(scenario())


# -- (3) claim oferowanego taska trwale rozstrzyga pending offer TERAZ ------

def test_claim_of_offered_task_resolves_pending_offer_immediately(tmp_path):
    # (3) task_offer->beta (pending); beta task_claim OK (task claimed);
    # crash PRZED timeoutem oferty -> restart: task=claimed ORAZ offer nadal
    # pending, bo offer_resolved bylo appendowane dopiero po sleep-timeout w
    # _offer_loop. Fix: sukces claim oferowanego taska appenduje offer_resolved
    # NATYCHMIAST w sciezce task_claim. Test: offer->claim->crash->restart:
    # task claimed, offer NIE pending.
    async def scenario():
        s1 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                        lease_ttl=5.0, offer_timeout=30.0)   # dlugi timeout: loop nie zdazy
        await s1.start()
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                 "command_id": "n1", "card": CARD}))
        task = (await recv(a))["task"]
        tid = task["id"]
        b, _ = await hello("beta", "tb")
        activation_id = s1._offer_activation_id("beta", task)   # pending offer dla bety
        assert ("beta", tid, 1) in s1._offer_cache
        await b.send(json.dumps({"type": "task_claim", "from": "beta", "ts": 0.0,
                                 "task_id": tid, "command_id": "c1",
                                 "expected_task_version": 1}))
        claimed = await recv(b)
        assert claimed["task"]["status"] == "claimed"
        # claim juz rozstrzygnal oferte trwale (offer_resolved w logu), zanim
        # jakikolwiek offer_timeout uplynal
        assert ("beta", tid, 1) not in s1._offer_cache
        await a.close(); await b.close()
        await _crash_stop(s1)                                   # BEZ snapshotu

        s2 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                        lease_ttl=5.0, offer_timeout=30.0)
        assert s2.queue.get(tid)["status"] == "claimed"
        assert ("beta", tid, 1) not in s2._offer_cache          # offer NIE pending
    asyncio.run(scenario())


# -- (4) resync wire-state musi niesc offers (+ registry) -------------------

def test_resync_required_state_carries_offers(srv):
    # (4) snapshot state ma offers, ale resync_required wysylal klientowi tylko
    # {"queue": ...}. Po kompakcji klient nie odzyskalby pending activations.
    # Fix: wire resync state = DOKLADNIE persisted snapshot state (queue +
    # registry + offers). Test: snapshot z pending offer -> klient z za starym
    # kursorem dostaje resync_required z offers w state.
    async def scenario(server):
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                 "command_id": "n1", "card": CARD}))
        task = (await recv(a))["task"]
        activation_id = server._offer_activation_id("beta", task)   # pending offer
        server.snapshot()                                            # kompakcja logu

        b, reply = await hello("gamma", "tg", last_seq=1)   # kursor sprzed snapshotu
        assert reply["type"] == "resync_required"
        state = reply["state"]
        assert "queue" in state and "registry" in state and "offers" in state
        offers = state["offers"]
        assert any(o["target"] == "beta" and o["activation_id"] == activation_id
                   and o["task"]["id"] == task["id"] for o in offers)
        await a.close(); await b.close()
    asyncio.run(srv(scenario))


# -- (5) walidacja inbound per typ ramki (schematy, nie 3 wyjatki) ----------

def test_fyi_without_text_rejected_not_logged(srv):
    # (5) fyi bez text przechodzil (validate sprawdzal szczegolowo tylko chat)
    # i byl logowany. Teraz schemat fyi wymaga niepustego text.
    async def scenario(server):
        a, _ = await hello("alfa", "ta")
        before = server.log.last_seq
        await a.send(json.dumps({"type": "fyi", "from": "alfa", "ts": 0.0}))  # brak text
        err = await recv(a)
        assert err["type"] == "error"
        assert server.log.last_seq == before      # NIE trafil do logu
        await a.close()
    asyncio.run(srv(scenario))


def test_status_with_non_numeric_ts_rejected_not_logged(srv):
    # (5) wspolny schemat: ts musi byc liczba. ts="not-a-number" przechodzil.
    async def scenario(server):
        a, _ = await hello("alfa", "ta")
        before = server.log.last_seq
        await a.send(json.dumps({"type": "status", "from": "alfa",
                                 "ts": "not-a-number", "state": "idle"}))
        err = await recv(a)
        assert err["type"] == "error"
        assert server.log.last_seq == before      # NIE trafil do logu
        assert "alfa" not in server.idle          # ani do idle (nie doszlo do dispatchu)
        await a.close()
    asyncio.run(srv(scenario))


def test_status_with_non_string_state_rejected_not_logged(srv):
    # (5) schemat status: state musi byc niepustym stringiem. state=[] przechodzil.
    async def scenario(server):
        a, _ = await hello("alfa", "ta")
        before = server.log.last_seq
        await a.send(json.dumps({"type": "status", "from": "alfa", "ts": 0.0,
                                 "state": []}))
        err = await recv(a)
        assert err["type"] == "error"
        assert server.log.last_seq == before      # NIE trafil do logu
        await a.close()
    asyncio.run(srv(scenario))


def test_outbound_only_frame_types_rejected_inbound_not_logged(srv):
    # (5) task_expired i offer_resolved to typy WYLACZNIE OUTBOUND/trwale — NIE
    # moga przyjsc od klienta. validate odrzuca je inbound-em; zero zapisu.
    async def scenario(server):
        a, _ = await hello("alfa", "ta")
        before = server.log.last_seq
        for ftype in ("task_expired", "offer_resolved", "task_offer", "ok", "error"):
            await a.send(json.dumps({"type": ftype, "from": "alfa", "ts": 0.0}))
            err = await recv(a)
            assert err["type"] == "error"
        assert server.log.last_seq == before      # zadna outbound-only nie w logu
        await a.close()
    asyncio.run(srv(scenario))


def test_malformed_task_frame_rejected_by_schema_keeps_command_id(srv):
    # (5) task_claim bez task_id odrzucony juz przez schemat validate, a error
    # nadal niesie command_id (klient moze skorelowac). Serwer dalej zyje.
    async def scenario(server):
        a, _ = await hello("alfa", "ta")
        before = server.log.last_seq
        await a.send(json.dumps({"type": "task_claim", "from": "alfa", "ts": 0.0,
                                 "command_id": "bad1"}))   # brak task_id
        err = await recv(a)
        assert err["type"] == "error" and err["command_id"] == "bad1"
        assert server.log.last_seq == before
        b, _ = await hello("beta", "tb")
        await a.send(json.dumps({"type": "chat", "from": "alfa", "ts": 1.0,
                                 "text": "@beta wciaz zyje"}))
        assert (await recv(b))["text"] == "@beta wciaz zyje"
        await a.close(); await b.close()
    asyncio.run(srv(scenario))


# == RUNDA 5 — durability ofert, atomowa resolution, pelna walidacja inbound ==

# -- A: DURABILITY-BEFORE-PUBLICATION — blad appendu oferty NIE moze wlozyc
#       niedurable oferty do cache (ktore steruje publikacja w _offer_loop) ----

def test_offer_append_failure_does_not_cache_nondurable_offer(srv):
    # (A) _offer_event wkladal oferte do _offer_cache PRZED log.append. Gdy
    # pierwszy append rzuca (OSError, np. dysk pelny): cache=True, ale nic na
    # dysku (last_seq bez zmian). Kolejna proba zwracala cached seq bez
    # appendu -> _offer_loop publikowal NIEDURABLE oferte. Fix: durable append
    # NAJPIERW (moze rzucic -> cache nietkniety), cache PO udanym appendzie,
    # snapshot na koncu.
    async def scenario(server):
        task = server.queue.add(CARD, "c1", 0.0)
        key = ("beta", task["id"], task["version"])
        seq_before = server.log.last_seq

        orig_append = server.log.append
        calls = {"n": 0}

        def flaky_append(frame):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("dysk pelny — pierwszy append oferty pada")
            return orig_append(frame)

        server.log.append = flaky_append
        with pytest.raises(OSError):
            server._offer_event("beta", task)
        # niedurable oferta NIE moze wejsc do cache: zero publikacji czegos,
        # czego nie ma na dysku
        assert key not in server._offer_cache
        assert server.log.last_seq == seq_before

        # po naprawie appendu kolejna proba dziala normalnie: trwaly event + cache
        offer = server._offer_event("beta", task)
        assert key in server._offer_cache
        assert offer["seq"] == server.log.last_seq
        offer_events = [e for e in server.log.events_after(seq_before)
                        if e["type"] == "task_offer"]
        assert len(offer_events) == 1
        assert offer_events[0]["seq"] == offer["seq"]
    asyncio.run(srv(scenario))


# -- B: RESOLUTION OFERTY atomowa i niezalezna od targetu — udany claim (od
#       KOGOKOLWIEK) rozstrzyga pending oferty taska; replay wywodzi to z
#       samego claim, bez zaleznosci od offer_resolved -----------------------

def test_steal_claim_resolves_pending_offer_of_other_target_live(srv):
    # (B live) oferta -> beta (pending); GAMMA robi poprawny bezposredni claim
    # tego samego taska. Klucz oferty to (TARGET=beta, task_id, wersja), wiec
    # resolve tylko po claimerze (gamma) nie trafial klucza bety -> oferta bety
    # zostawala pending. Fix: udany claim usuwa WSZYSTKIE pending offers
    # (task_id, wersja-open) niezaleznie od targetu.
    async def scenario(server):
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                 "command_id": "n1", "card": CARD}))
        task = (await recv(a))["task"]
        tid = task["id"]
        server._offer_activation_id("beta", task)          # pending offer dla bety
        assert ("beta", tid, 1) in server._offer_cache

        g, _ = await hello("gamma", "tg")
        await g.send(json.dumps({"type": "task_claim", "from": "gamma", "ts": 0.0,
                                 "task_id": tid, "command_id": "steal1",
                                 "expected_task_version": 1}))
        claimed = await recv(g)
        assert claimed["task"]["assignee"] == "gamma"
        # pending bety zniknieta LIVE mimo ze claimowala gamma (inny target)
        assert ("beta", tid, 1) not in server._offer_cache
        await a.close(); await g.close()
    asyncio.run(srv(scenario))


def test_replay_claim_resolves_pending_offer_without_offer_resolved(tmp_path):
    # (B replay) crash-prefix [task_new, task_offer, task_claim] BEZ
    # offer_resolved (symulacja okna nieatomowosci: claim persisted, resolve
    # nie zdazyl) -> restart: task claimed ORAZ ZERO pending offers. Poprawnosc
    # replay NIE moze zalezec od osobnego offer_resolved — claim SAM jest
    # faktem resolution.
    async def scenario():
        s1 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                        lease_ttl=5.0, offer_timeout=30.0)
        await s1.start()
        a, _ = await hello("alfa", "ta")
        await a.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                 "command_id": "n1", "card": CARD}))
        task = (await recv(a))["task"]
        tid = task["id"]
        s1._offer_activation_id("beta", task)              # task_offer + pending (beta,tid,1)
        # zbuduj recznie ogon [task_claim] BEZ offer_resolved (crash-window)
        result = s1.queue.claim(tid, "gamma", 1, "c1", 1, 0.0)
        s1._append({"type": "task_claim", "from": "gamma", "ts": 0.0,
                    "task_id": tid, "command_id": "c1", "expected_task_version": 1,
                    "task_state": result,
                    "fingerprint": s1.queue.fingerprint_for("c1")})
        assert [e for e in s1.log.events_after(0)
                if e["type"] == "offer_resolved"] == []     # brak offer_resolved w logu
        await a.close()
        await _crash_stop(s1)                               # BEZ snapshotu

        s2 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                        lease_ttl=5.0, offer_timeout=30.0)
        assert s2.queue.get(tid)["status"] == "claimed"
        assert ("beta", tid, 1) not in s2._offer_cache      # replay wywiodl resolution z claim
        assert s2._offer_cache == {}                        # ZERO pending offers
    asyncio.run(scenario())


# -- C: walidacja inbound pelna — type nie-str, ts NaN, pierwsze hello przez
#       wspolny schemat ------------------------------------------------------

def test_first_hello_without_ts_rejected_not_logged(srv):
    # (C3) pierwsze hello NIGDY nie przechodzilo przez protocol.validate —
    # hello bez ts dostawalo ok i bylo logowane. Fix: hello przez wspolny
    # schemat (type/from/ts) PRZED auth.
    async def scenario(server):
        before = server.log.last_seq
        ws = await websockets.connect(f"ws://localhost:{PORT}")
        await ws.send(json.dumps({"type": "hello", "from": "alfa",
                                  "instance_id": "i1", "token": "ta",
                                  "last_seq": 0}))          # brak ts
        err = json.loads(await asyncio.wait_for(ws.recv(), 2.0))
        assert err["type"] == "error"
        assert server.log.last_seq == before                # NIE zalogowane
        await ws.close()
    asyncio.run(srv(scenario))


def test_first_hello_with_nonstring_from_rejected(srv):
    # (C3) hello z from=[] przez wspolny schemat -> error, zero zapisu
    async def scenario(server):
        before = server.log.last_seq
        ws = await websockets.connect(f"ws://localhost:{PORT}")
        await ws.send(json.dumps({"type": "hello", "from": [], "ts": 0.0,
                                  "instance_id": "i1", "token": "ta",
                                  "last_seq": 0}))
        err = json.loads(await asyncio.wait_for(ws.recv(), 2.0))
        assert err["type"] == "error"
        assert server.log.last_seq == before
        await ws.close()
    asyncio.run(srv(scenario))


def test_nonstring_type_frame_after_hello_errors_not_crash(srv):
    # (C1) type=[] / {} rzucalo TypeError (unhashable) w validate przy
    # membership PRZED sprawdzeniem ze type to str. Fix: najpierw niepusty str,
    # potem membership. Handler zyje.
    async def scenario(server):
        a, _ = await hello("alfa", "ta")
        for bad_type in ([], {}):
            await a.send(json.dumps({"type": bad_type, "from": "alfa", "ts": 0.0}))
            err = await recv(a)
            assert err["type"] == "error"
        b, _ = await hello("beta", "tb")
        await a.send(json.dumps({"type": "chat", "from": "alfa", "ts": 1.0,
                                 "text": "@beta wciaz zyje"}))
        assert (await recv(b))["text"] == "@beta wciaz zyje"
        await a.close(); await b.close()
    asyncio.run(srv(scenario))


def test_nan_ts_frame_rejected_not_logged(srv):
    # (C2) ts=NaN przechodzilo (validate=None) i bylo logowane jako
    # niestandardowy JSON. Fix: ts musi byc liczba SKONCZONA.
    async def scenario(server):
        a, _ = await hello("alfa", "ta")
        before = server.log.last_seq
        await a.send(json.dumps({"type": "chat", "from": "alfa",
                                 "ts": float("nan"), "text": "x"}))
        err = await recv(a)
        assert err["type"] == "error"
        assert server.log.last_seq == before                # NIE zalogowane
        await a.close()
    asyncio.run(srv(scenario))
