"""Testy integracyjne chat/server.py: hello/auth, generation przypieta do
socketu, backlog/resync, echo po nicku, wzmianki, grupy adresowe,
snapshot+restart, replay result-based, pasywny board.

Serwer per-test na porcie 8891+ (nie 8765 — PoC A na roocie repo).
"""
import asyncio
import hashlib
import json
import socket
import time
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
                             )
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
    """Odbierz nastepna ramke, POMIJAJAC efemeryczne presence (serwer pcha
    je do humanow przy kazdym wejsciu/wyjsciu — to szum dla asercji)."""
    while True:
        frame = json.loads(await asyncio.wait_for(ws.recv(), timeout))
        if isinstance(frame, dict) and frame.get("type") == "presence":
            continue
        return frame


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


# -- F5 (B5): onboarding w PROTOKOLE. Agent na golym sockecie nie ma repo
# ani plikow projektu — jedyne, co ma, to odpowiedz na hello. Howto musi
# przyjsc ta sama droga co rules, inaczej kazdy nowy agent zaczyna od
# zgadywania (zmierzone w dogfoodzie B5: godzina straty na nasluchu).

def test_hello_returns_howto_when_present(srv):
    async def scenario(server):
        text = "adres: ws://host:8767\nnasluch: Monitor persistent\n"
        (server.log.dir / "howto.md").write_text(text)
        ws, reply = await hello("alfa", "ta")
        assert reply["howto"] == text
        await ws.close()
    asyncio.run(srv(scenario))


def test_hello_no_howto_field_when_file_absent(srv):
    async def scenario(server):
        ws, reply = await hello("alfa", "ta")
        assert "howto" not in reply
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

def test_takeover_leaves_trace_for_human_and_survives_compaction(srv):
    """F3 (B5): wyparcie nicka musi zostawic SLAD, nie ciche zniknięcie.

    Repro z dogfoodu: agent zostal wyparty przez wlasne drugie polaczenie,
    dla reszty kanalu nadal byl "connected", a jego nasluch juz nic nie
    slyszal. Nikt nie wiedzial, dlaczego zamilkl. Slad idzie na zywo do
    ludzi (jak presence — to oni reaguja) i ZOSTAJE w logu, bo pytanie
    "dlaczego zamilkl" pada dopiero po fakcie, czesto po kompakcji.
    """
    async def scenario(server):
        h, _ = await hello("emil", "te", role="human")
        a1, r1 = await hello("alfa", "ta", instance="i1")
        assert r1["generation"] == 1

        a2, r2 = await hello("alfa", "ta", instance="i2")   # wyparcie
        assert r2["generation"] == 2

        mark = await recv(h)
        assert mark["type"] == "takeover"
        assert mark["nick"] == "alfa"
        assert mark["previous_generation"] == 1 and mark["generation"] == 2
        assert "wyparlo" in mark["text"]

        # slad przezywa kompakcje i wraca agentowi w 'conversation'
        server.snapshot()
        _b, reply = await hello("beta", "tb", instance="swiezy", last_seq=0)
        assert reply["type"] == "resync_required"
        traces = [f for f in reply["conversation"] if f["type"] == "takeover"]
        assert [t["nick"] for t in traces] == ["alfa"]
        for ws in (h, a2, _b):
            await ws.close()
    asyncio.run(srv(scenario))


def test_first_hello_is_not_a_takeover(srv):
    """Pierwsze polaczenie nikogo nie wypiera — zaden slad nie moze powstac
    (inaczej kazde wejscie na kanal produkowaloby falszywy alarm)."""
    async def scenario(server):
        h, _ = await hello("emil", "te", role="human")
        await hello("alfa", "ta", instance="i1")
        with pytest.raises(asyncio.TimeoutError):
            await recv(h, timeout=0.4)
        await h.close()
    asyncio.run(srv(scenario))


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


# -- A2 (laka-nie-obora): inbound task_*/heartbeat WYCIETE — czyste odrzucenie

def test_inbound_task_new_rejected_cleanly_server_stays_live(srv):
    # Step 5b A2: po wycieciu wejscia task_new wpada w dispatcher `else` ->
    # czysty error (nieoczekiwany typ), serwer NIE crashuje, nic nie zapisuje,
    # a chat i status dzialaja dalej. Kodyfikuje runtime-check zamiast ustnej
    # weryfikacji ze serwer przezyl.
    async def scenario(server):
        a, _ = await hello("alfa", "ta")
        b, _ = await hello("beta", "tb")
        before = server.log.last_seq
        await a.send(json.dumps({"type": "task_new", "from": "alfa", "ts": 0.0,
                                 "command_id": "n1", "card": CARD}))
        err = await recv(a)
        assert err["type"] == "error"                  # odrzucone, nie crash
        assert server.log.last_seq == before            # task_new NIE zapisany

        # serwer zyje: chat dochodzi do drugiego uczestnika
        await a.send(json.dumps({"type": "chat", "from": "alfa", "ts": 1.0,
                                 "text": "@beta wciaz zyje"}))
        got = await recv(b)
        assert got["text"] == "@beta wciaz zyje"

        # status tez dziala (board pasywny)
        await a.send(json.dumps({"type": "status", "from": "alfa", "ts": 2.0,
                                 "state": "working"}))
        await asyncio.sleep(0.05)
        assert server.status["alfa"]["state"] == "working"
        for ws in (a, b):
            await ws.close()
    asyncio.run(srv(scenario))


# -- Nowe: restart odtwarza registry po snapshocie --------------------------

def test_restart_restores_registry_after_snapshot(tmp_path):
    async def scenario():
        s1 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT)
        await s1.start()
        ws, reply = await hello("alfa", "ta", instance="i1")
        assert reply["generation"] == 1
        s1.snapshot()
        await ws.close()
        await s1.stop()

        s2 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT)
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
        # trwaly status PO snapshotcie — etykieta snapshot_seq musi go objac
        await a.send(json.dumps({"type": "status", "from": "alfa", "ts": 0.0,
                                 "state": "working", "subject": "audyt"}))
        await asyncio.sleep(0.05)
        # kursor sprzed WSZYSTKICH powyzszych eventow -> resync_required
        b, reply = await hello("beta", "tb", last_seq=0)
        assert reply["type"] == "resync_required"
        # (B) etykieta snapshot_seq MUSI odzwierciedlac faktyczny, swiezy
        # stan (status juz w srodku), nie stara wartosc sprzed niego
        assert reply["snapshot_seq"] == server.log.last_seq
        # (A4) resync wire state = DOKLADNIE {registry, status} (queue wyciete,
        # status dodane — dzis wire pomijal status)
        state = reply["state"]
        assert set(state) == {"registry", "status"}
        assert state["status"]["alfa"]["subject"] == "audyt"
        assert "alfa" in state["registry"]["gen"]
        # replay od zwroconego snapshot_seq nie dubluje niczego juz w state
        assert server.log.events_after(reply["snapshot_seq"]) == []
        await a.close(); await b.close()
    asyncio.run(srv(scenario))


# -- A: crash-recovery — eventy po (ostatnim) snapshocie MUSZA sie odtworzyc

async def _crash_stop(server):
    """Symuluje crash: zamyka nasluch serwera BEZ wywolania snapshot()
    (w odroznieniu od server.stop(), ktory zawsze snapshotuje na koniec —
    to jest wlasnie sciezka, ktora maskowalaby brak replay w __init__)."""
    server._server.close()
    await server._server.wait_closed()


def test_crash_recovery_replays_events_after_snapshot_without_manual_snapshot(tmp_path):
    async def scenario():
        s1 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT)
        await s1.start()
        ws, reply = await hello("alfa", "ta", instance="i1")
        assert reply["generation"] == 1
        # trwaly status jako event PO (braku) snapshotu — musi wrocic z replay
        await ws.send(json.dumps({"type": "status", "from": "alfa", "ts": 0.0,
                                  "state": "working", "subject": "audyt"}))
        await asyncio.sleep(0.05)
        await ws.close()
        await _crash_stop(s1)          # BEZ recznego/automatycznego snapshotu

        # "restart": nowy ChatServer nad tym samym data_dir, zero snapshotu
        # na dysku — caly stan musi wrocic z samego logu eventow (replay)
        assert not (Path(tmp_path) / "snapshot.json").exists()
        s2 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT)
        assert s2.registry.generation_of("alfa") == 1     # hello -> registry z replay
        assert s2.status["alfa"]["subject"] == "audyt"    # status z replay
    asyncio.run(scenario())


def test_crash_recovery_snapshot_counter_seeded_from_replayed_events(tmp_path):
    async def scenario():
        s1 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT)
        await s1.start()
        ws, _ = await hello("alfa", "ta", instance="i1")
        s1._append({"type": "fyi", "from": "alfa", "ts": 0.0, "text": "x"})
        events_on_disk = s1.log.last_seq
        await ws.close()
        await _crash_stop(s1)

        s2 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT)
        # (A3) licznik snapshot-co-100 startuje od liczby eventow juz w logu,
        # nie od zera — inaczej po restarcie trzeba by 100 NOWYCH eventow
        # zanim serwer w ogole rozwazy pierwszy snapshot po starcie
        assert s2._events_since_snapshot == events_on_disk
    asyncio.run(scenario())


# -- (6) brak okna wycieku przy takeover (_close_stale_sockets) --------------

def test_close_stale_sockets_evicts_from_conns_before_first_await(tmp_path):
    async def scenario():
        server = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                            )

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
        # Odmowa MUSI niesc naprawe. Kursor jest per host:port, wiec nowy hub
        # na porcie po poprzednim zamurowuje kazdego, kto tam byl — bez tego
        # zdania czlowiek widzi tylko dwie liczby i pusty pokoj (2026-07-26).
        assert "chat-sessions" in err["text"], err["text"]
        assert "skasuj" in err["text"], err["text"]
        await a.close(); await bad.close()
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
    # (5) backlog/resync_required/ok/error to typy WYLACZNIE OUTBOUND — NIE moga
    # przyjsc od klienta. validate odrzuca je inbound-em (znane, nie unknown);
    # zero zapisu. (Kolejka wycieta w A4: task_expired/batch to juz unknown.)
    async def scenario(server):
        a, _ = await hello("alfa", "ta")
        before = server.log.last_seq
        for ftype in ("backlog", "resync_required", "ok", "error"):
            await a.send(json.dumps({"type": ftype, "from": "alfa", "ts": 0.0}))
            err = await recv(a)
            assert err["type"] == "error"
        assert server.log.last_seq == before      # zadna outbound-only nie w logu
        await a.close()
    asyncio.run(srv(scenario))


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


def test_strict_json_rejects_nested_nan_and_extra_infinity(srv):
    # Python json.loads domyslnie akceptuje NaN/Infinity. Brama strict JSON ma
    # odrzucic je niezaleznie od zagniezdzenia/pola, zanim zmienia room_seq
    # lub trafi do logu; poprawny socket po hello pozostaje przy tym uzywalny.
    async def scenario(server):
        a, _ = await hello("alfa", "ta")
        before = server.log.last_seq

        # nested NaN w ZYWEJ ramce (membership_set.groups) — strict-json odrzuca
        # niezaleznie od zagniezdzenia/pola, przed jakakolwiek mutacja registry/log
        await a.send(json.dumps({
            "type": "membership_set", "from": "alfa", "ts": 0.0,
            "target": "beta", "groups": ["workers", float("nan")],
        }))
        err = await recv(a)
        assert err["type"] == "error" and err["text"] == "invalid json"

        await a.send(
            '{"type":"chat","from":"alfa","ts":0.0,'
            '"text":"bez publikacji","extra":Infinity}')
        err = await recv(a)
        assert err["type"] == "error" and err["text"] == "invalid json"

        assert server.log.last_seq == before
        await a.close()
    asyncio.run(srv(scenario))


def test_strict_json_rejects_nan_in_first_hello_without_side_effects(srv):
    async def scenario(server):
        before = server.log.last_seq
        ws = await websockets.connect(f"ws://localhost:{PORT}")
        await ws.send(
            '{"type":"hello","from":"alfa","ts":0.0,'
            '"instance_id":"nan-hello","token":"ta","last_seq":0,'
            '"extra":NaN}')
        err = await recv(ws)
        assert err["type"] == "error" and err["text"] == "invalid json"
        assert server.log.last_seq == before
        assert server.registry.generation_of("alfa") == 0
        assert "alfa" not in server.conns
        await ws.close()
    asyncio.run(srv(scenario))


# -- Runda 7: Registry durability w hello (provisional-then-commit) ----------

def test_hello_append_failure_no_registry_bump_no_socket_close(tmp_path, caplog):
    # (Runda 7) hello mutowal Registry (bump generacji) PRZED durable appendem.
    # Injekcja: pierwszy log.append typu "hello" rzuca OSError -> registry
    # NIETKNIETY (generation_of == 0, klon wyrzucony), ZERO eventow hello na
    # dysku, polaczenie pada bez ok. Po naprawie retry tego samego hello ->
    # generation podbita DOKLADNIE raz (==1). Na starym kodzie registry.hello
    # szlo LIVE przed appendem: append-fail zostawial gen=1 NIEDURABLE (rozjazd
    # live vs replay).
    async def scenario():
        s1 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                        )
        await s1.start()

        orig = s1.log.append
        calls = {"n": 0}
        secret_path = str(s1.log.events_path.resolve())

        def flaky(frame):
            if frame.get("type") == "hello":
                calls["n"] += 1
                if calls["n"] == 1:
                    raise OSError(
                        f"dysk pelny na pierwszym hello append: {secret_path}")
            return orig(frame)

        s1.log.append = flaky
        seq_before = s1.log.last_seq

        bad = await websockets.connect(f"ws://localhost:{PORT}")
        await bad.send(json.dumps({"type": "hello", "from": "alfa", "ts": 0.0,
                                   "instance_id": "i1", "token": "ta",
                                   "last_seq": 0}))
        # niezmiennik f: storage-fail daje czysta ramke error (jednolity
        # kontrakt kazdej ramki), nie brutalne 1011 — dopiero POTEM graceful close
        err = json.loads(await asyncio.wait_for(bad.recv(), timeout=2.0))
        assert err["type"] == "error"
        assert err["text"] == "storage unavailable; retry"
        assert secret_path not in json.dumps(err)
        assert secret_path in caplog.text
        # registry NIETKNIETY, zero eventow hello na dysku
        assert s1.registry.generation_of("alfa") == 0
        assert s1.log.last_seq == seq_before
        assert [e for e in s1.log.events_after(0) if e["type"] == "hello"] == []

        # retry (append juz sprawny) -> generation podbita DOKLADNIE raz
        s1.log.append = orig
        good, reply = await hello("alfa", "ta", instance="i1")
        assert reply["type"] == "ok" and reply["generation"] == 1
        assert s1.registry.generation_of("alfa") == 1
        assert len([e for e in s1.log.events_after(0)
                    if e["type"] == "hello"]) == 1
        await good.close()
        await _crash_stop(s1)
    asyncio.run(scenario())


def test_takeover_hello_append_failure_keeps_old_socket_and_generation(tmp_path):
    # (Runda 7) TAKEOVER: hello innego instance_id zamykal stary socket i
    # bumpowal generacje PRZED durable appendem. Injekcja: append drugiego hello
    # rzuca -> gen NADAL 1, stary socket A NADAL zywy (takeover NIE wykonany),
    # zero eventow hello #2. Po naprawie retry -> gen=2, socket A zamkniety, nowy
    # socket aktywny. Na starym kodzie takeover zamykal A i bumpowal gen PRZED
    # appendem -> append-fail rozjezdzal tozsamosc (gen=2 niedurable, A martwy).
    async def scenario():
        s1 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                        )
        await s1.start()
        a1, reply1 = await hello("alfa", "ta", instance="i1")
        assert reply1["generation"] == 1

        orig = s1.log.append
        calls = {"n": 0}

        def flaky(frame):
            if frame.get("type") == "hello":
                calls["n"] += 1
                if calls["n"] == 1:
                    raise OSError("dysk pelny na hello takeover")
            return orig(frame)

        s1.log.append = flaky
        seq_before = s1.log.last_seq

        bad = await websockets.connect(f"ws://localhost:{PORT}")
        await bad.send(json.dumps({"type": "hello", "from": "alfa", "ts": 0.0,
                                   "instance_id": "i2", "token": "ta",
                                   "last_seq": 0}))
        # storage-fail na takeover: czysta ramka error dla nowego socketu
        err_bad = json.loads(await asyncio.wait_for(bad.recv(), timeout=2.0))
        assert err_bad["type"] == "error" and "storage" in err_bad["text"]
        # takeover NIE wykonany: gen nadal 1, zero eventow hello #2, A zywy
        assert s1.registry.generation_of("alfa") == 1
        assert s1.log.last_seq == seq_before
        # A NADAL zarejestrowany po stronie serwera (dokladnie jeden socket alfy;
        # gdyby takeover sie wykonal, _close_stale_sockets wypielby A -> 0)
        assert len(s1.conns.get("alfa", set())) == 1
        with pytest.raises(asyncio.TimeoutError):    # A nie dostal error/close
            await recv(a1, timeout=0.4)

        # retry (append sprawny) -> gen=2, A zamkniety, nowy socket aktywny
        s1.log.append = orig
        a2, reply2 = await hello("alfa", "ta", instance="i2")
        assert reply2["generation"] == 2
        err = await recv(a1, timeout=1.0)            # A dostaje error teraz
        assert err["type"] == "error"
        with pytest.raises(websockets.exceptions.ConnectionClosed):
            await asyncio.wait_for(a1.recv(), timeout=1.0)   # A faktycznie zamkniety
        assert s1.registry.generation_of("alfa") == 2
        await a2.close()
        await _crash_stop(s1)
    asyncio.run(scenario())


def test_hello_at_snapshot_boundary_restores_registry_generation(tmp_path):
    # (Runda 7) hello jako event #100: durable append hello bez auto-snapshotu,
    # potem swap live=klon, na koncu _maybe_snapshot -> snapshot #100 lapie NOWA
    # generacje registry. Restart odtwarza registry generation z tego snapshotu.
    async def scenario():
        s1 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT)
        await s1.start()
        a, _ = await hello("alfa", "ta", instance="i1")     # hello #1
        while s1._events_since_snapshot < 99:               # kolejny append = #100
            s1._append({"type": "fyi", "from": "filler", "ts": 0.0, "text": "f"})
        assert s1._events_since_snapshot == 99
        b, reply = await hello("beta", "tb", instance="ib")  # hello bety = event #100
        assert reply["generation"] == 1
        assert s1._events_since_snapshot == 0                # snapshot #100 strzelil
        snap = json.loads((Path(tmp_path) / "snapshot.json").read_text())
        assert snap["state"]["registry"]["gen"]["beta"] == 1
        await a.close(); await b.close()
        await _crash_stop(s1)

        s2 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT)
        assert s2.registry.generation_of("beta") == 1
        assert s2.registry.generation_of("alfa") == 1
    asyncio.run(scenario())


def test_auth_fail_hello_no_registry_mutation_no_event(tmp_path):
    # (Runda 7) hello ze zlym tokenem: AuthError leci z KLONA registry -> error
    # do klienta, ZERO mutacji rejestru (generation bez zmiany), ZERO eventu na
    # dysku. Guard provisional-then-commit: auth-fail nie moze nic utrwalic ani
    # zbumpowac.
    async def scenario():
        s1 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                        )
        await s1.start()
        seq_before = s1.log.last_seq
        bad = await websockets.connect(f"ws://localhost:{PORT}")
        await bad.send(json.dumps({"type": "hello", "from": "alfa", "ts": 0.0,
                                   "instance_id": "i1", "token": "ZLY",
                                   "last_seq": 0}))
        err = json.loads(await bad.recv())
        assert err["type"] == "error"
        assert s1.registry.generation_of("alfa") == 0
        assert s1.log.last_seq == seq_before
        assert [e for e in s1.log.events_after(0) if e["type"] == "hello"] == []
        await bad.close()
        await _crash_stop(s1)
    asyncio.run(scenario())


# -- Plynne funkcje operacyjne: minimalne membership_set --------------------

def test_membership_set_is_event_first_transferable_and_replayed(tmp_path):
    async def scenario():
        s1 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                        )
        await s1.start()
        human, _ = await hello("emil", "te", role="human")
        beta, _ = await hello("beta", "tb")
        gamma, _ = await hello("gamma", "tg")
        alfa, _ = await hello("alfa", "ta")

        original_append = s1.log.append
        failed = {"once": False}

        def fail_first_membership(frame):
            if frame.get("type") == "membership_set" and not failed["once"]:
                failed["once"] = True
                raise OSError("disk unavailable")
            return original_append(frame)

        s1.log.append = fail_first_membership
        seq_before = s1.log.last_seq
        await human.send(json.dumps({
            "type": "membership_set", "from": "forged", "ts": 0.0,
            "target": "beta", "groups": ["workers", "admin"],
        }))
        error = await recv(human)
        assert error["type"] == "error" and error["text"] == "storage unavailable; retry"
        assert s1.registry.groups_of("beta") == ["workers"]
        assert s1.log.last_seq == seq_before

        s1.log.append = original_append
        await human.send(json.dumps({
            "type": "membership_set", "from": "forged", "ts": 0.0,
            "target": "beta", "groups": ["workers", "admin", "admin"],
        }))
        promoted = await recv(human)
        notice_beta = await recv(beta)
        assert promoted["type"] == "ok" and promoted["groups"] == ["workers", "admin"]
        assert notice_beta["type"] == "membership_set"
        assert notice_beta["from"] == "emil"  # socket jest autorytatywny

        # Nowy admin przekazuje funkcje dalej, a potem sam schodzi do workera.
        await beta.send(json.dumps({
            "type": "membership_set", "from": "beta", "ts": 0.0,
            "target": "gamma", "groups": ["head", "admin"],
        }))
        assert (await recv(beta))["type"] == "ok"
        notice_gamma = await recv(gamma)
        assert notice_gamma["groups"] == ["head", "admin"]
        await gamma.close()
        gamma, gamma_reply = await hello(
            "gamma", "tg", instance="i2", groups=["forged"])
        assert gamma_reply["role"] == "agent"
        assert gamma_reply["groups"] == ["head", "admin"]

        await beta.send(json.dumps({
            "type": "membership_set", "from": "beta", "ts": 0.0,
            "target": "beta", "groups": ["workers"],
        }))
        assert (await recv(beta))["type"] == "ok"
        assert s1.registry.role_of("beta") == "agent"  # tozsamosc stala

        # Byly admin traci prawo natychmiast; odrzucenie nie trafia do logu.
        seq_before_forbidden = s1.log.last_seq
        await beta.send(json.dumps({
            "type": "membership_set", "from": "beta", "ts": 0.0,
            "target": "alfa", "groups": ["admin"],
        }))
        forbidden = await recv(beta)
        assert forbidden["type"] == "error" and "forbidden" in forbidden["text"]
        assert s1.log.last_seq == seq_before_forbidden

        # Routing korzysta z nowego czlonkostwa od razu.
        await alfa.send(json.dumps({
            "type": "chat", "from": "alfa", "ts": 0.0,
            "text": "$head ping",
        }))
        assert (await recv(gamma))["text"] == "$head ping"
        with pytest.raises(asyncio.TimeoutError):
            await recv(beta, timeout=0.2)

        events = [event for event in s1.log.events_after(0)
                  if event["type"] == "membership_set"]
        assert len(events) == 3
        assert events[-1]["target"] == "beta" and events[-1]["groups"] == ["workers"]
        for ws in (human, beta, gamma, alfa):
            await ws.close()
        await _crash_stop(s1)

        # Bez clean snapshotu: replay eventow zachowuje przekazanie funkcji.
        s2 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT,
                        )
        assert s2.registry.groups_of("beta") == ["workers"]
        assert s2.registry.groups_of("gamma") == ["head", "admin"]
        assert s2.groups["gamma"] == {"head", "admin"}
        assert s2.registry.role_of("beta") == "agent"

    asyncio.run(scenario())


# -- t2 review + B4 agent-first: participants snapshot dla kazdego ----------

def test_human_hello_gets_authoritative_participants(srv):
    async def scenario(server):
        # human dostaje snapshot; agent (B4: agent-first) rowniez
        ws_h, rep_h = await hello("emil", "te", role="human")
        assert isinstance(rep_h.get("participants"), list)
        by_nick = {p["nick"]: p for p in rep_h["participants"]}
        assert set(by_nick) == set(TOKENS)
        assert by_nick["emil"]["connected"] is True
        assert by_nick["emil"]["role"] == "human"
        ws_a, rep_a = await hello("alfa", "ta", instance="ia")
        assert isinstance(rep_a.get("participants"), list)
        await ws_h.close()
        await ws_a.close()
    asyncio.run(srv(scenario))


def test_participants_reflect_membership_after_reconnect(srv):
    """Repro review t2: membership_set -> reconnect humana z wysokim
    kursorem (pusty backlog) -> snapshot MUSI niesc nowe grupy."""
    async def scenario(server):
        ws_h, rep1 = await hello("emil", "te", role="human")
        before = {p["nick"]: p["groups"] for p in rep1["participants"]}
        await ws_h.send(json.dumps({
            "type": "membership_set", "from": "emil", "ts": 1.0,
            "target": "alfa", "groups": ["head", "admin"]}))
        ok = await recv(ws_h)
        while ok.get("type") != "ok":
            ok = await recv(ws_h)
        await ws_h.close()
        # reconnect z kursorem = koniec loga (pusty backlog) — dokladnie
        # scenariusz, w ktorym stary TUI klamal
        ws_h2, rep2 = await hello("emil", "te", role="human",
                                  last_seq=server.log.last_seq)
        assert rep2.get("backlog") == []
        by_nick = {p["nick"]: p for p in rep2["participants"]}
        assert by_nick["alfa"]["groups"] == ["admin", "head"]  # sorted
        assert before["alfa"] != by_nick["alfa"]["groups"]
        await ws_h2.close()
    asyncio.run(srv(scenario))


def test_agent_hello_receives_participants_snapshot(srv):
    # Agent-first (B4): roster+board w hello to nie przywilej TUI.
    # Agent bez tego jest slepy na "kto tu jest i kto co robi" —
    # starsze ramki status sa PRZED jego oknem kontekstu.
    async def scenario(server):
        beta, reply = await hello("beta", "tb")
        parts = {p["nick"]: p for p in reply["participants"]}
        assert set(parts) == set(TOKENS)
        assert parts["beta"]["connected"] is True
        assert "status" in parts["beta"] and "groups" in parts["beta"]
        await beta.close()
    asyncio.run(srv(scenario))


# -- statusy agentow (kanon: sleeping/idle/working/blocked/review/done,
#    ale to WOLNY TEKST — hub nie waliduje przynaleznosci do enuma) --------

def test_status_tracked_in_snapshot(srv):
    # (A1, laka-nie-obora) status jest CZYSTYM faktem na boardzie — usuniete
    # asercje server.idle: sync status->idle->offer byl swiadomie wycinanym
    # side-effectem schedulera. Board sledzi stan, nie wyzwala pracy.
    async def scenario(server):
        ws_b, _ = await hello("beta", "tb", instance="ib")
        await ws_b.send(json.dumps({"type": "status", "from": "beta",
                                    "ts": 1.0, "state": "idle"}))
        await asyncio.sleep(0.1)
        # (A1) POZYTYWNY dowod inwariantu: state=idle laduje na boardzie jako
        # czysty fakt, ale NIE zasila kolejki round-robin. Reintrodukcja starego
        # side-effectu status->idle OBLALABY ta asercje.
        assert server.status["beta"] == {"state": "idle"}
        assert not hasattr(server, "idle")   # (A3) offer machinery wyciete — brak idle
        await ws_b.send(json.dumps({"type": "status", "from": "beta",
                                    "ts": 2.0, "state": "working",
                                    "subject": "t9"}))
        await asyncio.sleep(0.1)
        snap = server._participants_snapshot()
        by_nick = {p["nick"]: p for p in snap}
        assert by_nick["beta"]["status"] == {"state": "working",
                                             "subject": "t9"}
        # dowolny wolny tekst (spoza kanonu) jest teraz akceptowany
        await ws_b.send(json.dumps({"type": "status", "from": "beta",
                                    "ts": 2.5, "state": "spie"}))
        await asyncio.sleep(0.1)
        assert server.status["beta"]["state"] == "spie"
        # ale schemat (niepusty string, maks 32 znaki) nadal jest twardy
        before = server.log.last_seq
        await ws_b.send(json.dumps({"type": "status", "from": "beta",
                                    "ts": 3.0, "state": "x" * 33}))
        err = await recv(ws_b)
        assert err["type"] == "error" and "status" in err["text"]
        assert server.log.last_seq == before      # odrzucone, nie w logu
        await ws_b.close()
    asyncio.run(srv(scenario))


def test_status_subject_on_board(srv):
    # B1 (laka-nie-obora): board niesie subject obok state/note jako plaska
    # mapa deklaracji. subject = "nad czym pracuje"; zagniezdzony w
    # participant["status"] (jak state/note), NIE top-level. task_id
    # (scheduler-era) zretirowane — subject je zastapil, board = {state,subject,note}.
    async def scenario(server):
        ws_b, _ = await hello("beta", "tb", instance="ib")
        await ws_b.send(json.dumps({"type": "status", "from": "beta", "ts": 1.0,
                                    "state": "working", "subject": "B1 subject",
                                    "note": "czekam na kontrakt"}))
        await asyncio.sleep(0.1)
        by_nick = {p["nick"]: p for p in server._participants_snapshot()}
        assert by_nick["beta"]["status"]["subject"] == "B1 subject"
        assert by_nick["beta"]["status"]["note"] == "czekam na kontrakt"
        assert by_nick["beta"]["status"]["state"] == "working"
        await ws_b.close()
    asyncio.run(srv(scenario))


def test_status_with_task_id_rejected_not_logged_not_on_board(srv):
    # B1 retire: task_id wycofane -> validate ODRZUCA, wiec ramka NIE trafia
    # ani na dysk (handler _append) ani na board ani do live broadcastu. Sam
    # board-drop nie wystarczyl: handler utrwala cala ramke PRZED projekcja,
    # wiec legacy task_id wyciekalby do logu i do ludzi (P1 codex).
    async def scenario(server):
        ws_b, _ = await hello("beta", "tb", instance="ib")
        before = server.log.last_seq
        await ws_b.send(json.dumps({"type": "status", "from": "beta", "ts": 1.0,
                                    "state": "working", "task_id": "legacy"}))
        err = await recv(ws_b)
        assert err["type"] == "error"
        assert server.log.last_seq == before          # nie utrwalone (durable gate)
        assert "beta" not in server.status             # zero mutacji boardu
        await ws_b.close()
    asyncio.run(srv(scenario))


def test_status_state_is_free_text(srv):
    # hub nie waliduje przynaleznosci do slownika stanow — "sleeping" (spoza
    # dotychczasowego idle/working/blocked/review) jest przyjmowane wprost.
    async def scenario(server):
        beta, _ = await hello("beta", "tb")
        await beta.send(json.dumps({"type": "status", "from": "beta",
                                    "ts": 0.0, "state": "sleeping"}))
        await asyncio.sleep(0.1)
        assert server.status["beta"]["state"] == "sleeping"
        await beta.close()
    asyncio.run(srv(scenario))


def test_orchestrator_sets_others_status_humans_see_live(srv):
    async def scenario(server):
        emil, _ = await hello("emil", "te", role="human")
        # human nadaje grupe orchestrator becie (jedyna autoryzacja: human)
        await emil.send(json.dumps({
            "type": "membership_set", "from": "emil", "ts": 0.0,
            "target": "beta", "groups": ["orchestrator"]}))
        ack = await recv(emil)
        assert ack["type"] == "ok"
        beta, _ = await hello("beta", "tb")
        gamma, _ = await hello("gamma", "tg")
        await beta.send(json.dumps({"type": "status", "from": "beta",
                                    "ts": 0.0, "target": "gamma",
                                    "state": "working", "subject": "C"}))
        await asyncio.sleep(0.1)
        assert server.status["gamma"] == {"state": "working", "subject": "C"}
        ev = await recv(emil)                       # human widzi na zywo
        assert ev["type"] == "status"
        assert ev["target"] == "gamma" and ev["from"] == "beta"
        # zwykly agent (bez grupy orchestrator) NIE ustawi cudzego statusu
        await gamma.send(json.dumps({"type": "status", "from": "gamma",
                                     "ts": 0.0, "target": "beta",
                                     "state": "idle"}))
        err = await recv(gamma)
        assert err["type"] == "error" and "forbidden" in err["text"]
        assert "beta" not in server.status  # odrzucone przed append/mutacja
        for ws in (emil, beta, gamma):
            await ws.close()
    asyncio.run(srv(scenario))


def test_status_survives_restart_via_replay(srv, tmp_path):
    async def scenario(server):
        ws_b, _ = await hello("beta", "tb", instance="ib")
        await ws_b.send(json.dumps({"type": "status", "from": "beta",
                                    "ts": 1.0, "state": "blocked",
                                    "subject": "audyt logu",
                                    "note": "czekam na decyzje"}))
        await asyncio.sleep(0.1)
        await ws_b.close()
        return server.log.dir

    data_dir = asyncio.run(srv(scenario))
    reborn = ChatServer(data_dir=data_dir, tokens=TOKENS, port=PORT + 1)
    snap = {p["nick"]: p for p in reborn._participants_snapshot()}
    # subject przechodzi przez branch _replay_events (B1 retire: bez task_id)
    assert snap["beta"]["status"] == {"state": "blocked",
                                       "subject": "audyt logu",
                                       "note": "czekam na decyzje"}
    assert snap["beta"]["connected"] is False


# -- presence: lista online jak na czacie -----------------------------------

def test_presence_pushed_to_human_on_connect_and_disconnect(srv):
    async def scenario(server):
        h, _ = await hello("emil", "te", role="human")

        async def next_presence():
            while True:
                frame = json.loads(
                    await asyncio.wait_for(h.recv(), 2))
                if frame.get("type") == "presence":
                    return frame

        a, _ = await hello("alfa", "ta")
        p_on = await next_presence()
        while p_on.get("nick") != "alfa":  # pomin wlasne presence emila
            p_on = await next_presence()
        assert p_on["connected"] is True
        await a.close()
        p_off = await next_presence()
        assert p_off["nick"] == "alfa" and p_off["connected"] is False
        await h.close()
    asyncio.run(srv(scenario))


def test_status_survives_crash_restart_without_snapshot(srv):
    """Regresja: replay eventow status PRZED init self.status crashowal
    ChatServer przy restarcie bez snapshotu (AttributeError)."""
    async def scenario(server):
        ws_b, _ = await hello("beta", "tb", instance="ib")
        await ws_b.send(json.dumps({"type": "status", "from": "beta",
                                    "ts": 1.0, "state": "working",
                                    "subject": "t7"}))
        await asyncio.sleep(0.1)
        await ws_b.close()
        # symulacja crasha: BEZ server.stop() (zero snapshotu) — kopiujemy
        # data_dir zanim fixture zrobi clean stop
        import shutil
        crash_dir = server.log.dir.parent / "crash-copy"
        shutil.copytree(server.log.dir, crash_dir)
        return crash_dir

    crash_dir = asyncio.run(srv(scenario))
    reborn = ChatServer(data_dir=crash_dir, tokens=TOKENS, port=PORT + 2)
    snap = {p["nick"]: p for p in reborn._participants_snapshot()}
    assert snap["beta"]["status"] == {"state": "working", "subject": "t7"}


def test_legacy_snapshot_task_id_sanitized_on_restore(tmp_path):
    # B1 retire: stary snapshot (pre-B1) niesie martwe task_id w status.
    # Restore MUSI je odsiac (projekcja na state/subject/note), inaczej pole
    # przetrwaloby restart mimo usuniecia handler/replay. dict(v) by je
    # przepuscil — dlatego __init__ projektuje kazdy wpis przy restore.
    async def scenario():
        s1 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT)
        await s1.start()
        try:
            # symulacja pre-B1 stanu: task_id wprost w self.status (dzisiejszy
            # handler by go odrzucil), utrwalone snapshotem na dysk
            s1.status["beta"] = {"state": "working", "task_id": "legacy",
                                 "subject": "audyt", "note": "x"}
            s1.snapshot()
        finally:
            await s1.stop()
    asyncio.run(scenario())
    s2 = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=PORT + 3)
    restored = s2.status["beta"]
    assert "task_id" not in restored                       # odsiane przy restore
    assert restored == {"state": "working", "subject": "audyt", "note": "x"}


# -- Task 1: bind jest parametrem serwera -----------------------------------

def test_bind_all_interfaces(tmp_path):
    async def run():
        port = _free_port()
        server = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=port,
                            bind="0.0.0.0")
        await server.start()
        try:
            ws = await websockets.connect(f"ws://127.0.0.1:{port}")
            await ws.close()
        finally:
            await server.stop()
    asyncio.run(run())


# -- Task 2 (B3): kontrakt replayu — backlog bez filtra wzmianek ------------

def test_replay_backlog_unfiltered_for_agents(srv):
    async def scenario(server):
        emil, _ = await hello("emil", "te", role="human")
        # chat BEZ wzmianki — live push ominie agentow (fizyka: sen za darmo)
        await emil.send(json.dumps({"type": "chat", "from": "emil",
                                    "ts": 0.0, "text": "notatka bez wzmianki"}))
        await asyncio.sleep(0.2)                      # niech serwer zapisze
        # agent wstaje z kursorem 0 -> backlog MUSI zawierac te ramke
        beta, reply = await hello("beta", "tb", last_seq=0)
        texts = [f.get("text") for f in reply["backlog"]
                 if f.get("type") == "chat"]
        assert "notatka bez wzmianki" in texts
        await beta.close(); await emil.close()
    asyncio.run(srv(scenario))


# -- F1 (B5): resync niesie PAMIEC, nie tylko stan maszyny ----------------
# Zmierzone na produkcji: snapshot skasowal 105 ramek dogfoodu. Agent
# wchodzacy po kompakcji dostawal {queue, registry, offers} i zero historii
# — czyli stan maszyny przezywal, a pamiec agentow nie.

def test_resync_carries_conversation(srv):
    async def scenario(server):
        ws, _ = await hello("alfa", "ta")
        for i in range(3):
            await ws.send(json.dumps({"type": "chat", "from": "alfa",
                                      "ts": 0.0, "text": f"ustalenie {i}"}))
        await asyncio.sleep(0.2)
        server.snapshot()                      # kompakcja jak w produkcji
        await ws.close()

        ws2, reply = await hello("beta", "tb", instance="swiezy", last_seq=0)
        assert reply["type"] == "resync_required"
        conv = reply["conversation"]
        assert [f["text"] for f in conv] == ["ustalenie 0", "ustalenie 1",
                                             "ustalenie 2"]
        assert [f["seq"] for f in conv] == sorted(f["seq"] for f in conv)
        assert all(f["type"] == "chat" for f in conv)
        await ws2.close()
    asyncio.run(srv(scenario))


def test_ok_reply_has_no_conversation_field(srv):
    # kursor w zasiegu logu: backlog i tak niesie rozmowe, drugi raz
    # wysylac jej nie ma po co
    async def scenario(server):
        ws, reply = await hello("alfa", "ta")
        assert reply["type"] == "ok"
        assert "conversation" not in reply
        await ws.close()
    asyncio.run(srv(scenario))


# -- F2 (B5): backlog na drucie bez ramek hello — agent placi kontekstem --
# Zmierzone na produkcji: hello(last_seq=0) = 66 ramek/15159 B, z czego 36
# (54%) to cudze ramki hello. Agent dostaje autorytatywny roster w
# participants (B4) i tych ramek wcale nie potrzebuje — placi za czysty
# szum. Log NADAL je trzyma (replay generacji przy restarcie), filtr
# dotyczy wylacznie tego, co idzie na drut w gałęzi "ok".

def test_backlog_wire_has_no_hello_frames(srv):
    async def scenario(server):
        alfa, _ = await hello("alfa", "ta")            # loguje hello#1
        beta, _ = await hello("beta", "tb")             # loguje hello#2
        await alfa.send(json.dumps({"type": "chat", "from": "alfa",
                                    "ts": 1.0, "text": "ustalenie"}))
        await beta.send(json.dumps({"type": "status", "from": "beta",
                                    "ts": 0.0, "state": "idle"}))
        await asyncio.sleep(0.2)                       # niech serwer zapisze

        # w logu na dysku hello sa (potrzebne do replayu generacji)
        assert any(e["type"] == "hello" for e in server.log.replay())

        gamma, reply = await hello("gamma", "tg", last_seq=0)
        types = {f["type"] for f in reply["backlog"]}
        assert "hello" not in types
        assert "chat" in types and "status" in types
        await alfa.close(); await beta.close(); await gamma.close()
    asyncio.run(srv(scenario))


def test_backlog_last_seq_is_true_log_end_not_last_filtered_frame(srv):
    async def scenario(server):
        alfa, _ = await hello("alfa", "ta")
        beta, reply = await hello("beta", "tb", last_seq=0)
        # ostatnia ramka w logu jest hello bety (odfiltrowana z backlogu na
        # drucie) — last_seq zwracany klientowi MUSI byc mimo to prawdziwym
        # koncem logu, inaczej klient zapetli sie prosząc o ramki, ktorych
        # nigdy nie dostanie (bo sa hello i zawsze beda odfiltrowane)
        assert reply["last_seq"] == server.log.last_seq
        assert server.log.replay()[-1]["type"] == "hello"
        await alfa.close(); await beta.close()
    asyncio.run(srv(scenario))


def test_reconnect_with_wire_last_seq_gives_empty_backlog_no_loop(srv):
    async def scenario(server):
        alfa, _ = await hello("alfa", "ta")
        beta, reply = await hello("beta", "tb", last_seq=0)
        last = reply["last_seq"]
        # miedzy odpowiedzia a reconnectem dochodzi kolejny uczestnik — jego
        # hello lezy w logu powyzej `last`, ale MUSI zostac odfiltrowane z
        # backlogu tak samo jak przy pierwszym hello (inaczej klient
        # zapetlalby sie prosząc o ramki, ktorych nigdy nie dostanie)
        gamma, _ = await hello("gamma", "tg")
        beta2, reply2 = await hello("beta", "tb", instance="i1", last_seq=last)
        assert reply2["backlog"] == []
        await alfa.close(); await beta.close(); await gamma.close()
        await beta2.close()
    asyncio.run(srv(scenario))


# -- F9 (B5): stop() konczy sie w skonczonym czasie -----------------------
# Zmierzone na produkcji: `agentmachi stop` wyslal SIGTERM, hub zamknal
# nasluch (port wolny), ale PROCES WISIAL — bo wait_closed() czeka, az
# rozlacza sie wszyscy klienci, a nasze listenery trzymaly polaczenia
# w nieskonczonosc. Operator musial dobic kill -9, a zawieszony proces
# blokowal kolejny start (fail-fast z F7 widzial go jako zywy hub).

def test_stop_finishes_even_with_connected_clients(tmp_path):
    async def scenario():
        port = _free_port()
        server = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=port)
        await server.start()
        ws = await websockets.connect(f"ws://localhost:{port}")
        await ws.send(json.dumps({"type": "hello", "from": "alfa", "ts": 0.0,
                                  "instance_id": "i1", "token": "ta",
                                  "last_seq": 0, "role": "agent"}))
        await ws.recv()
        # klient NIE rozlacza sie — stop i tak musi zejsc
        await asyncio.wait_for(server.stop(), timeout=5.0)
        try:
            await ws.close()
        except Exception:
            pass
    asyncio.run(scenario())


def test_stop_gives_up_on_hanging_close_instead_of_hanging_forever(tmp_path):
    """F9: nie odtworzylismy root cause zawieszenia z produkcji, ale kontrakt
    jest niezalezny od przyczyny — `stop()` MUSI zejsc w skonczonym czasie.
    Zawieszony proces blokuje kolejny start (fail-fast z F7 widzi go jako
    zywy hub), wiec cichy zawis jest gorszy niz gwaltowne domkniecie."""
    async def scenario():
        port = _free_port()
        server = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=port)
        await server.start()

        async def never_returns():
            await asyncio.Event().wait()          # symuluje zawis zamykania

        server._server.wait_closed = never_returns
        await asyncio.wait_for(server.stop(), timeout=5.0)
    asyncio.run(scenario())


# -- B6: moderacja czlowieka (kick) --------------------------------------
# W kanale bez tokenow dla agentow to jedyna odpowiedz na pytanie "kim
# jestes": wpuszczamy wszystkich, czlowiek wyrzuca.

def test_human_kicks_agent_and_channel_learns_about_it(srv):
    async def scenario(server):
        emil, _ = await hello("emil", "te", role="human")
        beta, _ = await hello("beta", "tb")
        gamma, _ = await hello("gamma", "tg")

        await emil.send(json.dumps({"type": "kick", "from": "emil",
                                    "ts": 0.0, "target": "beta"}))
        ack = await recv(emil)
        assert ack["type"] == "ok" and ack["target"] == "beta"

        # trzeci uczestnik dowiaduje sie o zmianie skladu zespolu
        ev = await recv(gamma)
        assert ev["type"] == "kick" and ev["target"] == "beta"
        assert ev["by"] == "emil" and isinstance(ev["seq"], int)

        # wyrzucony dostaje powod i rozlaczenie
        powod = await recv(beta)
        assert powod["type"] == "error" and "wyrzucony" in powod["text"]
        with pytest.raises(websockets.exceptions.ConnectionClosed):
            await asyncio.wait_for(beta.recv(), 2.0)

        for w in (emil, gamma):
            await w.close()
    asyncio.run(srv(scenario))


def test_agent_cannot_kick_anyone(srv):
    """Swiadomie wezsze niz membership_set: agent nie odcina uczestnika."""
    async def scenario(server):
        beta, _ = await hello("beta", "tb")
        gamma, _ = await hello("gamma", "tg")
        await beta.send(json.dumps({"type": "kick", "from": "beta",
                                    "ts": 0.0, "target": "gamma"}))
        err = await recv(beta)
        assert err["type"] == "error" and "forbidden" in err["text"]
        # gamma nietkniety
        await gamma.send(json.dumps({"type": "chat", "from": "gamma",
                                     "ts": 0.0, "text": "dalej tu jestem"}))
        await asyncio.sleep(0.2)
        for w in (beta, gamma):
            await w.close()
    asyncio.run(srv(scenario))


def test_kick_survives_compaction_like_takeover(srv):
    """Pytanie 'czemu on zniknal' pada PO fakcie — slad musi przezyc."""
    async def scenario(server):
        emil, _ = await hello("emil", "te", role="human")
        beta, _ = await hello("beta", "tb")
        await emil.send(json.dumps({"type": "kick", "from": "emil",
                                    "ts": 0.0, "target": "beta"}))
        await recv(emil)
        await asyncio.sleep(0.2)
        server.snapshot()
        zachowane = [e["type"] for e in server.log.conversation_after(0)]
        assert "kick" in zachowane
        await emil.close()
    asyncio.run(srv(scenario))


def test_open_mode_agent_gets_groups_and_appears_on_board(tmp_path):
    """B6, dwa bledy zlapane dopiero na zywym pokoju:
    (1) rola/grupy czytane z LIVE registry byly puste, bo nowy nick istnieje
        na razie tylko w klonie — agent byl gluchy na $workers;
    (2) roster iterowal po posiadaczach TOKENOW, wiec wchodzacy bez tokenu
        nie pojawial sie na boardzie — moderator nie mial kogo wyrzucic."""
    async def scenario():
        port = _free_port()
        server = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=port,
                            bind="127.0.0.1")
        await server.start()
        try:
            ws = await websockets.connect(f"ws://localhost:{port}")
            await ws.send(json.dumps({"type": "hello", "from": "gosc",
                                      "ts": 0.0, "instance_id": "i1",
                                      "last_seq": 0, "role": "agent"}))
            reply = json.loads(await ws.recv())
            assert reply["type"] == "ok"
            assert reply["groups"] == ["workers"], "bez grupy agent jest gluchy"

            emil = await websockets.connect(f"ws://localhost:{port}")
            await emil.send(json.dumps({"type": "hello", "from": "emil",
                                        "ts": 0.0, "instance_id": "h1",
                                        "token": "te", "last_seq": 0,
                                        "role": "human"}))
            r = json.loads(await emil.recv())
            board = {p["nick"]: p for p in r["participants"]}
            assert "gosc" in board and board["gosc"]["connected"] is True
            await ws.close()
            await emil.close()
        finally:
            await server.stop()
    asyncio.run(scenario())


def test_open_hello_without_nick_gets_one_and_learns_it(tmp_path):
    """B6 review worker1: agent, ktory nie podal nicka, musi sie dowiedziec,
    kim jest — wprost z odpowiedzi, nie przez porownywanie participants."""
    async def scenario():
        port = _free_port()
        server = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=port,
                            bind="127.0.0.1")
        await server.start()
        try:
            ws = await websockets.connect(f"ws://localhost:{port}")
            await ws.send(json.dumps({"type": "hello", "ts": 0.0,
                                      "instance_id": "i1", "last_seq": 0,
                                      "role": "agent"}))
            reply = json.loads(await ws.recv())
            assert reply["type"] == "ok"
            assert reply["nick"].startswith("worker"), reply
            assert reply["groups"] == ["workers"]
            await ws.close()
        finally:
            await server.stop()
    asyncio.run(scenario())


def test_open_mode_same_instance_self_send_allowed(tmp_path):
    """Finding Opuska: bez tokenu, send/frame na tozsamosci LISTENERA (ten sam
    instance_id) musi przejsc jako self-resume — inaczej zdalny agent nie
    moze wyslac ramki trzymajac nasluch. Inny instance na zywy nick = odmowa."""
    async def scenario():
        port = _free_port()
        server = ChatServer(data_dir=tmp_path, tokens=TOKENS, port=port,
                            bind="127.0.0.1")
        await server.start()
        try:
            # listener trzyma nick "gosc" instance i1
            lis = await websockets.connect(f"ws://localhost:{port}")
            await lis.send(json.dumps({"type": "hello", "from": "gosc",
                                       "ts": 0.0, "instance_id": "i1",
                                       "last_seq": 0, "role": "agent"}))
            assert json.loads(await lis.recv())["type"] == "ok"
            # self-send: TEN SAM instance i1 -> przechodzi (oneshot na tozsamosci)
            me = await websockets.connect(f"ws://localhost:{port}")
            await me.send(json.dumps({"type": "hello", "from": "gosc",
                                      "ts": 0.0, "instance_id": "i1",
                                      "last_seq": 0, "role": "agent"}))
            assert json.loads(await me.recv())["type"] == "ok", "self-resume musi przejsc"
            await me.close()
            # inny instance na zywy nick -> odmowa z propozycja
            other = await websockets.connect(f"ws://localhost:{port}")
            await other.send(json.dumps({"type": "hello", "from": "gosc",
                                         "ts": 0.0, "instance_id": "INNY",
                                         "last_seq": 0, "role": "agent"}))
            r = json.loads(await other.recv())
            assert r["type"] == "error" and "zajety" in r["text"]
            await other.close()
            await lis.close()
        finally:
            await server.stop()
    asyncio.run(scenario())


def test_admin_agent_can_kick_after_human_grants_admin(srv):
    """Orchestrator-agent w grupie admin moze wyrzucac (rozkaz roota, B6+).
    Zwykly agent bez admina dalej NIE moze — lancuch zaufania trzyma, bo
    admina nadaje wylacznie human przez membership_set."""
    async def scenario(server):
        emil, _ = await hello("emil", "te", role="human")
        beta, _ = await hello("beta", "tb")
        gamma, _ = await hello("gamma", "tg")
        # zanim beta dostanie admina — kick odrzucony
        await beta.send(json.dumps({"type": "kick", "from": "beta",
                                    "ts": 0.0, "target": "gamma"}))
        assert (await recv(beta))["type"] == "error"
        # human nadaje becie grupe admin
        await emil.send(json.dumps({"type": "membership_set", "from": "emil",
                                    "ts": 0.0, "target": "beta",
                                    "groups": ["workers", "admin"]}))
        assert (await recv(emil))["type"] == "ok"
        # teraz beta (admin-agent) wyrzuca gamme
        await beta.send(json.dumps({"type": "kick", "from": "beta",
                                    "ts": 0.0, "target": "gamma"}))
        # beta dostaje ok (moze przyjsc po membership_set echo/kick event)
        # beta moze najpierw dostac membership_set (o sobie) i kick-event —
        # czekamy na wlasne ok; realnym dowodem jest rozlaczenie gammy nizej
        for _ in range(6):
            r = await recv(beta)
            if r["type"] == "ok" and r.get("target") == "gamma":
                break
        else:
            raise AssertionError("beta nie dostala ok na kick")
        # gamma dostaje najpierw ramke 'wyrzucony', potem zamkniecie socketu
        with pytest.raises(websockets.exceptions.ConnectionClosed):
            for _ in range(4):
                await asyncio.wait_for(gamma.recv(), 2.0)
        # delta bez admina dalej nie moze
        delta, _ = await hello("delta", "td")
        await delta.send(json.dumps({"type": "kick", "from": "delta",
                                     "ts": 0.0, "target": "beta"}))
        assert "forbidden" in (await recv(delta))["text"]
        for w in (emil, beta, delta):
            await w.close()
    asyncio.run(srv(scenario))


def test_b7_loopback_peer_at_tailnet_bind_is_proxy_signal(srv):
    """B7 [KRYTYCZNY, Opusek]: przy bindzie na tailnet loopback-peer to
    ANOMALIA (proxy/tunnel), nie lokalnosc — open bez tokenu odrzucone,
    zeby IP-binding nie dawal falszywej ochrony. Test laczy sie z loopbacku
    (peer=127.0.0.1), a bind jest zamockowany na tailnet."""
    async def scenario(server):
        server.bind = "100.64.0.1"     # udajemy bind na interfejs tailnetu
        ws = await websockets.connect(f"ws://localhost:{PORT}")
        await ws.send(json.dumps({"type": "hello", "from": "ghost", "ts": 0.0,
                                  "instance_id": "i1", "last_seq": 0,
                                  "role": "agent"}))
        r = json.loads(await ws.recv())
        assert r["type"] == "error"
        assert "proxy" in r["text"].lower()
        await ws.close()
    asyncio.run(srv(scenario))


def test_b7_loopback_bind_does_not_bind_addr(srv):
    """B7: przy bindzie loopback (domyslny test) IP-binding sie NIE stosuje —
    dwa wejscia tego samego nicku z loopbacku (rozne instance, ten sam peer)
    zachowuja sie jak w B6, bez odmowy z tytulu adresu. Chroni przed regresja
    'B7 wlaczylo sie tam, gdzie nie powinno'."""
    async def open_hello_ws(nick, instance):
        ws = await websockets.connect(f"ws://localhost:{PORT}")
        await ws.send(json.dumps({"type": "hello", "from": nick, "ts": 0.0,
                                  "instance_id": instance, "last_seq": 0,
                                  "role": "agent"}))
        return ws, json.loads(await ws.recv())

    async def scenario(server):
        # server.bind zostaje 127.0.0.1 (fixture) -> _bind_is_tailnet False
        ws1, r1 = await open_hello_ws("luzny", "i1")
        assert r1["type"] in ("ok", "resync_required")
        await ws1.close()
        await asyncio.sleep(0.1)
        # ten sam nick, inny instance, znow z loopbacku -> wchodzi (nick wolny
        # po rozlaczeniu, adres sie nie stosuje)
        ws2, r2 = await open_hello_ws("luzny", "i2")
        assert r2["type"] in ("ok", "resync_required")
        await ws2.close()
    asyncio.run(srv(scenario))


def test_fyi_nie_budzi_agenta_ale_zapisuje_i_dociera_do_czlowieka(srv):
    """`--quiet` to PUBLIKACJA, nie zawolanie: ramka ma wyladowac w logu
    i dojsc do ludzi, ale NIE wyrwac agenta z pracy — nawet wzmiankowanego.

    Po co: dzis jedynym sposobem opublikowania czegokolwiek jest obudzenie
    wszystkich adresatow, wiec autorowi OPLACA SIE pisac dlugo (jedna gesta
    ramka oszczedza mu trzy rundy pytan). W dogfoodzie kinas-machine dalo to
    ramki po 2-3 tys. znakow — ekonomia narzedzia premiowala obciazanie
    innych. To MOZLIWOSC, nie decyzja za agenta: nadawca sam wybiera, czy
    jego raport ma kogos wyrywac z pracy."""

    async def scenariusz(server):
        emil, _ = await hello("emil", "te", role="human")
        alfa, _ = await hello("alfa", "ta", instance="i2")
        beta, _ = await hello("beta", "tb", instance="i3")

        await beta.send(json.dumps({
            "type": "fyi", "from": "beta", "ts": 0.0,
            "text": "@alfa raport z pomiarow"}))

        # czlowiek DOSTAJE (moderuje, wiec widzi wszystko)
        u_emila = await recv(emil)
        assert u_emila["text"] == "@alfa raport z pomiarow"

        # wzmiankowany agent NIE dostaje pusha
        with pytest.raises(asyncio.TimeoutError):
            await recv(alfa, timeout=0.4)

        # ale ramka JEST w logu — alfa znajdzie ja, gdy sama zajrzy
        assert any(e.get("text") == "@alfa raport z pomiarow"
                   for e in server.log.conversation_after(0))
        for ws in (emil, alfa, beta):
            await ws.close()

    srv(scenariusz)


def test_board_pokazuje_ostatnia_ramke_uczestnika(srv):
    """`connected` mowi tylko, ze gniazdo jest otwarte — a gniazdo zyje
    niezaleznie od tego, czy ktos po drugiej stronie czyta. W dogfoodzie
    kinas-machine dwa agenty mialy procesy z uptime 2h, gniazda ESTAB
    i przesuwajacy sie kursor, a model nie zobaczyl ani jednej ramki; hub
    raportowal je jako obecne. `last_seq` odroznia 'siedzi cicho' od
    'oglochl 76 ramek temu' — bez nowego mechanizmu, z danych ktore juz sa
    w logu."""

    async def scenariusz(server):
        emil, _ = await hello("emil", "te", role="human")
        beta, r_beta = await hello("beta", "tb", instance="i2")

        # nikt jeszcze nic nie powiedzial
        board = {p["nick"]: p for p in server._participants_snapshot()}
        assert board["beta"]["last_seq"] == 0

        await beta.send(json.dumps({"type": "chat", "from": "beta",
                                    "ts": 0.0, "text": "@emil jestem"}))
        await recv(emil)

        board = {p["nick"]: p for p in server._participants_snapshot()}
        assert board["beta"]["last_seq"] > 0        # beta sie odezwala
        assert board["beta"]["connected"] is True
        assert board["gamma"]["last_seq"] == 0      # gamma milczy od poczatku
        for ws in (emil, beta):
            await ws.close()

    srv(scenariusz)
