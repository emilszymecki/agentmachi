"""Testy node'a agentmachi: NodeState (kursory atomowe), RateLimiter,
ClaudeRuntime (adapter headless), node_loop e2e na realnym ChatServer.

Serwer per-test na porcie efemerycznym (wzorzec test_server_integration.py) —
helper `hello`/`_free_port` POWIELONE lokalnie (nie importowane z pliku
testowego), zgodnie z instrukcja taska.
"""
import asyncio
import json
import re
import socket
import sys
import time
from pathlib import Path

import pytest
import websockets

from agentmachi.node import NodeState, RateLimiter


def test_state_roundtrip_atomic_0600(tmp_path):
    p = tmp_path / "state.json"
    s = NodeState(nick="worker1", runtime="claude", workspace="/w",
                  session_id=None, last_wake_seq=0, last_context_seq=0,
                  wake_times=[])
    s.save(p)
    assert oct(p.stat().st_mode & 0o777) == "0o600"
    s2 = NodeState.load(p)
    assert s2 == s
    s2.session_id = "abc"; s2.last_wake_seq = 150; s2.save(p)
    assert NodeState.load(p).session_id == "abc"


def test_rate_limit_max_wakes_per_hour():
    rl = RateLimiter(max_wakes_per_hour=2, cooldown_after_agent_wake=60.0)
    now = 10_000.0
    assert rl.check(now, [], sender_is_human=True) is None
    times = [now - 30, now - 10]
    blocked_until = rl.check(now, times, sender_is_human=True)
    assert blocked_until == (now - 30) + 3600.0
    # stare wake'i wypadaja z okna
    assert rl.check(now, [now - 3700, now - 3650], sender_is_human=True) is None


def test_cooldown_after_agent_wake():
    rl = RateLimiter(max_wakes_per_hour=6, cooldown_after_agent_wake=60.0)
    now = 10_000.0
    assert rl.check(now, [now - 30], sender_is_human=True) is None
    assert rl.check(now, [now - 30], sender_is_human=False) == (now - 30) + 60.0
    assert rl.check(now, [now - 90], sender_is_human=False) is None


# --- Step 5: ClaudeRuntime na fake'owym binarium ---------------------------

def test_claude_runtime_reports_session_id_immediately(tmp_path):
    from agentmachi.node import ClaudeRuntime
    seen = []
    rt = ClaudeRuntime(workspace=str(tmp_path), max_duration=10.0,
                       argv0=[sys.executable,
                              str(Path(__file__).parent / "fake_runtime.py")])
    code = asyncio.run(rt.run("preambula", session_id=None,
                              on_session_id=seen.append))
    assert code == 0 and seen == ["fresh-session"]
    code = asyncio.run(rt.run("preambula", session_id="old-sid",
                              on_session_id=seen.append))
    assert seen[-1] == "old-sid"  # resume niesie ten sam session_id


def test_claude_runtime_max_duration_kills_child_hung_before_reading_stdin(tmp_path):
    """Regresja z review: max_duration musi byc twardym sufitem CALEJ rundy
    (stdin write+drain, pump stdout, wait), nie tylko pump() stdout. Stary
    kod robil `proc.stdin.write(...); await proc.stdin.drain()` PRZED
    wait_for — dziecko, ktore nigdy nie czyta stdin, z duzym promptem
    (wieksze niz pipe buffer, domyslnie 64KB) blokuje drain() BEZ timeoutu:
    pipe-deadlock, node wisi w nieskonczonosc mimo "twardego sufitu".
    `asyncio.wait_for` na CALYM tescie (nie tylko wewnatrz runtime'u) jako
    siatka bezpieczenstwa, zeby suita nie zawisla, gdyby fix nie zadzialal."""
    from agentmachi.node import ClaudeRuntime
    rt = ClaudeRuntime(workspace=str(tmp_path), max_duration=0.5,
                       argv0=[sys.executable,
                              str(Path(__file__).parent / "fake_runtime.py"),
                              "--hang"])
    big_prompt = "x" * (300 * 1024)  # >256KB — wieksze niz domyslny pipe (64KB)
    start = time.monotonic()
    code = asyncio.run(asyncio.wait_for(
        rt.run(big_prompt, session_id=None, on_session_id=lambda sid: None),
        timeout=5.0))
    elapsed = time.monotonic() - start
    assert code == -9              # zabite przez max_duration, nie zwisniete
    assert elapsed < 2.0            # sufit ~0.5s + narzut kill/wait, NIE ~120s spania dziecka


# --- Step 8: e2e node_loop na realnym hubie --------------------------------

TOKENS = {
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
    from chat.server import ChatServer

    async def _run(coro):
        server = ChatServer(data_dir=tmp_path / "hub-data", tokens=TOKENS,
                            port=PORT, lease_ttl=5.0, offer_timeout=0.3)
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


class RecordingRuntime:
    """Fake runtime do e2e: loguje kazda rundke jako blok WAKE, symuluje
    stabilny session_id jak prawdziwy resume."""

    def __init__(self, path):
        self.path = path

    async def run(self, prompt, session_id, on_session_id):
        on_session_id(session_id or "fresh-session")
        with open(self.path, "a") as f:
            f.write("WAKE\n" + prompt + "\n")
        return 0


async def _wait_for(cond, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < deadline, "warunek nie spelniony w czasie"
        await asyncio.sleep(0.05)


def test_node_wakes_on_mention_resumes_and_survives_restart(tmp_path, srv):
    """Kolejnosc PRODUKCYJNA (fix po kontroli — patrz raport, sekcja "Fix po
    kontroli"): node laczy sie PIERWSZY i zdazyl osiasc w live-loopie, ZANIM
    human w ogole polaczyl sie z hubem. Chat bez wzmianki idzie WYLACZNIE do
    humanow live (fizyka huba) — node go NIGDY nie dostanie na zywo; jesli
    node budowalby kontekst z okna live+backlog (stary blad), zobaczylby
    WYLACZNIE ramke z wzmianka, nie ta wczesniejsza — amnezja. Kontrakt:
    kontekst wake'a wylacznie z backlogu swiezego reconnectu wywolanego
    przez sam SYGNAL wzmianki na zywo."""
    from agentmachi.node import node_loop

    async def run(server):
        state_path = tmp_path / "node-state.json"
        prompts = tmp_path / "prompts.txt"
        rt = RecordingRuntime(prompts)          # fake: loguje prompt, zwraca 0
        node = asyncio.ensure_future(node_loop(
            url=f"ws://localhost:{PORT}", nick="beta", token="tb",
            state_path=state_path, runtime=rt, humans={"emil"}))
        await asyncio.sleep(0.2)  # niech node zdazy hello+wejsc w live-loop
        emil, _ = await hello("emil", "te", role="human")
        await emil.send(json.dumps({"type": "chat", "from": "emil", "ts": 0.0,
                                    "text": "kontekst bez wzmianki"}))
        await emil.send(json.dumps({"type": "chat", "from": "emil", "ts": 0.0,
                                    "text": "@beta zrob taska"}))
        await _wait_for(lambda: prompts.exists())
        text = prompts.read_text()
        assert "kontekst bez wzmianki" in text      # pelny kontekst, nie tylko wzmianki
        assert "@beta zrob taska" in text
        st = NodeState.load(state_path)
        assert st.last_wake_seq > 0 and st.session_id == "fresh-session"
        node.cancel()
        try:
            await node
        except asyncio.CancelledError:
            pass
        # restart node'a: ta sama wzmianka (redelivery) NIE budzi drugi raz,
        # nowa wzmianka wznawia TE SAMA sesje
        node2 = asyncio.ensure_future(node_loop(
            url=f"ws://localhost:{PORT}", nick="beta", token="tb",
            state_path=state_path, runtime=rt, humans={"emil"}))
        await emil.send(json.dumps({"type": "chat", "from": "emil", "ts": 0.0,
                                    "text": "@beta kolejna runda"}))
        await _wait_for(lambda: prompts.read_text().count("WAKE") == 2)
        assert NodeState.load(state_path).session_id == "fresh-session"
        node2.cancel()
        try:
            await node2
        except asyncio.CancelledError:
            pass
        await emil.close()
    asyncio.run(srv(run))


# --- rate-limit: trzecia wzmianka pod rzad NIE odpala runtime'u -----------

def test_node_rate_limits_repeated_wakes(tmp_path, srv):
    """Kolejnosc produkcyjna (fix po kontroli): node polaczony i w
    live-loopie PRZED wzmiankami — kazda z 3 wzmianek dociera do node'a
    zywo jako SYGNAL (kazda wywoluje reconnect po drodze); backlog
    kazdego kolejnego hello jest niefiltrowany, wiec rate-limit i tak
    dziala poprawnie niezaleznie od tego, ile reconnectow po drodze."""
    from agentmachi.node import RateLimiter, node_loop

    async def run(server):
        state_path = tmp_path / "node-state.json"
        prompts = tmp_path / "prompts.txt"
        rt = RecordingRuntime(prompts)
        limiter = RateLimiter(max_wakes_per_hour=2, cooldown_after_agent_wake=0.0)
        node = asyncio.ensure_future(node_loop(
            url=f"ws://localhost:{PORT}", nick="beta", token="tb",
            state_path=state_path, runtime=rt, humans={"emil"},
            limiter=limiter))
        await asyncio.sleep(0.2)  # niech node zdazy hello+wejsc w live-loop
        emil, _ = await hello("emil", "te", role="human")
        for i in range(3):
            await emil.send(json.dumps({"type": "chat", "from": "emil",
                                        "ts": 0.0, "text": f"@beta runda {i}"}))
        # tylko 2 pierwsze wzmianki odpalaja runtime (max_wakes_per_hour=2)
        await _wait_for(lambda: prompts.exists()
                        and prompts.read_text().count("WAKE") == 2)
        await asyncio.sleep(0.3)  # daj petli node'a szanse przetworzyc 3cia (blokowana)

        # swiezy obserwator: backlog niefiltrowany, widzi WSZYSTKO od huba
        obs, reply = await hello("gamma", "tg", last_seq=0)
        chats = [f for f in reply["backlog"] if f.get("type") == "chat"]
        by_text = {f["text"]: f["seq"] for f in chats}
        rate_limited = [f for f in chats if f["from"] == "beta"
                        and re.match(r"^rate-limited do \d{2}:\d{2}$", f["text"])]
        assert len(rate_limited) == 1

        st = NodeState.load(state_path)
        assert st.last_wake_seq == by_text["@beta runda 2"]     # skonsumowana
        assert st.last_context_seq == by_text["@beta runda 1"]  # NIE przesuniety
        assert prompts.read_text().count("WAKE") == 2           # runtime NIE odpalony 3x

        node.cancel()
        try:
            await node
        except asyncio.CancelledError:
            pass
        await emil.close(); await obs.close()
    asyncio.run(srv(run))
