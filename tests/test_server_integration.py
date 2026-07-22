"""Testy integracyjne chat/server.py: hello/auth, generation przypieta do
socketu, backlog/resync, echo po nicku, wzmianki, grupy adresowe,
snapshot+restart, activation_id kotwiczony w evencie.

Serwer per-test na porcie 8891+ (nie 8765 — PoC A na roocie repo).
"""
import asyncio
import hashlib
import json
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
