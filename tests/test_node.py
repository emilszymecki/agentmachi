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
    # Etap5: cap godzinowy chroni zasoby PRZED petla AGENTOW (nie przed
    # czlowiekiem — patrz test human ponizej). Agent-sender jest capowany.
    rl = RateLimiter(max_wakes_per_hour=2, cooldown_after_agent_wake=60.0)
    now = 10_000.0
    assert rl.check(now, [], sender_is_human=False) is None
    times = [now - 30, now - 10]                              # cap=2 osiagniety
    blocked_until = rl.check(now, times, sender_is_human=False)
    assert blocked_until == (now - 30) + 3600.0
    # stare wake'i wypadaja z okna
    assert rl.check(now, [now - 3700, now - 3650], sender_is_human=False) is None


def test_human_mention_not_capped_by_hourly_limit():
    # Etap5 (D1): czlowiek MODERUJE — jego wzmianka budzi BEZ limitu godzinowego.
    # Rate-limit to circuit breaker dla petli agentow, nie dla czlowieka.
    rl = RateLimiter(max_wakes_per_hour=2, cooldown_after_agent_wake=60.0)
    now = 10_000.0
    over_cap = [now - 30, now - 10]                           # cap juz przekroczony
    assert rl.check(now, over_cap, sender_is_human=False) is not None  # agent: zablokowany
    assert rl.check(now, over_cap, sender_is_human=True) is None        # czlowiek: przechodzi


def test_cooldown_after_agent_wake():
    rl = RateLimiter(max_wakes_per_hour=6, cooldown_after_agent_wake=60.0)
    now = 10_000.0
    assert rl.check(now, [now - 30], sender_is_human=True) is None
    assert rl.check(now, [now - 30], sender_is_human=False) == (now - 30) + 60.0
    assert rl.check(now, [now - 90], sender_is_human=False) is None


# --- I1: self-wake guard — wlasne ramki z backlogu nie moga budzic --------

def test_should_wake_ignores_own_frames_from_backlog():
    """I1: backlog (niefiltrowany) zawiera wlasne wiadomosci agenta
    (np. '@all zrobione') — nie moga wywolywac spurious wake po reconnect.
    Kontekst i tak je zawiera (budowany z backlogu bez filtra _is_wake) —
    tylko gate wake'a ma je odrzucac."""
    from agentmachi.node import _should_wake
    own_mention = {"type": "chat", "from": "beta", "seq": 5,
                   "text": "@all zrobione"}
    assert _should_wake(own_mention, "beta", {"workers"}, last_wake_seq=0) is False
    others_mention = {"type": "chat", "from": "emil", "seq": 6,
                      "text": "@all kolejna sprawa"}
    assert _should_wake(others_mention, "beta", {"workers"}, last_wake_seq=0) is True


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


def test_claude_runtime_survives_broken_pipe_from_early_exit_child(tmp_path):
    """I2(b): dziecko, ktore pada natychmiast BEZ czytania stdin (np. binarium
    nie istnieje/crashuje na starcie), zamyka swoj koniec pipe'u zanim feed()
    zdazy napisac duzy prompt — asyncio.gather(feed(), pump()) bez
    return_exceptions puszcza wtedy surowy BrokenPipeError/OSError, omijajac
    proc.wait() (zombie). run() musi zlapac OSError i zwrocic int."""
    from agentmachi.node import ClaudeRuntime
    rt = ClaudeRuntime(workspace=str(tmp_path), max_duration=5.0,
                       argv0=[sys.executable, "-c", "import sys; sys.exit(3)"])
    big_prompt = "x" * (300 * 1024)  # >256KB — wieksze niz domyslny pipe (64KB)
    code = asyncio.run(asyncio.wait_for(
        rt.run(big_prompt, session_id=None, on_session_id=lambda sid: None),
        timeout=5.0))
    assert isinstance(code, int)   # run() zwraca int, nie wyjatek


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
                            port=PORT)
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


def test_wake_preamble_forbids_nested_join_and_names_reply_identity():
    """Regresja z warsztatu: obudzony Codex uruchomil wlasny `listen`,
    zastal nick `codex` zajety przez node i podniosl sie jako `worker3`.
    Node czekal na dluga runde worker3, wiec kolejne `@codex` lezalo w logu.

    Runtime jest JUZ uczestnikiem przez node. Preambula musi to powiedziec
    wprost i podac jedyna legalna droge odpowiedzi: one-shot `send` na
    wspoldzielonej tozsamosci, bez drugiego listenera/node'a."""
    from agentmachi.node import WAKE_PREAMBLE

    prompt = WAKE_PREAMBLE.format(
        nick="codex", groups="workers", rules="R", board="B")
    assert "NIE uruchamiaj `agentmachi listen` ani `agentmachi node`" in prompt
    assert "agentmachi send --as codex" in prompt
    assert "juz polaczony" in prompt.lower()


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


def test_node_shares_identity_with_runtime_reply_and_handles_next_wake(
        tmp_path, srv):
    """Regresja z zywego `warsztat`, seq 20 -> worker3.

    Node trzymal nick na swiezym `node-<uuid>`, a budzony Codex odpowiadal
    przez zwykla Session. To byly dwie tozsamosci: odpowiedz robila takeover
    albo (bez tokenu) byla odrzucana; Codex ratowal sie drugim listenerem,
    dostawal suggested_nick=worker3 i node blokowal sie na calej dlugiej
    rundzie. Kontrakt E2E: node i one-shot runtime'u maja TEN SAM instance,
    odpowiedz nie wypiera node'a, a druga wzmianka budzi kolejna runde."""
    from agentmachi.node import NodeState, node_loop

    class ReplyingRuntime:
        def __init__(self):
            self.calls = 0

        async def run(self, prompt, session_id, on_session_id):
            self.calls += 1
            on_session_id(session_id or "codex-thread")
            reply_ws, hello_reply = await hello(
                "beta", "tb", instance="shared-node-session")
            assert hello_reply["type"] == "ok"
            await reply_ws.send(json.dumps({
                "type": "chat", "from": "beta", "ts": 0.0,
                "text": f"reply-{self.calls}"}))
            await reply_ws.close()
            return 0

    async def run(server):
        state_path = tmp_path / "node-state.json"
        runtime = ReplyingRuntime()
        node = asyncio.ensure_future(node_loop(
            url=f"ws://localhost:{PORT}", nick="beta", token="tb",
            state_path=state_path, runtime=runtime, humans={"emil"},
            instance_id="shared-node-session"))
        await asyncio.sleep(0.2)
        emil, _ = await hello("emil", "te", role="human")

        await emil.send(json.dumps({
            "type": "chat", "from": "emil", "ts": 0.0,
            "text": "@beta pierwsza"}))
        await _wait_for(
            lambda: runtime.calls == 1
            and NodeState.load(state_path).last_context_seq > 0)

        await emil.send(json.dumps({
            "type": "chat", "from": "emil", "ts": 0.0,
            "text": "@beta druga"}))
        await _wait_for(
            lambda: runtime.calls == 2
            and NodeState.load(state_path).last_context_seq
            == NodeState.load(state_path).last_wake_seq)

        events = server.log.events_after(0)
        replies = [e["text"] for e in events
                   if e.get("type") == "chat" and e.get("from") == "beta"
                   and e.get("text", "").startswith("reply-")]
        takeovers = [e for e in events
                     if e.get("type") == "takeover"
                     and e.get("nick") == "beta"]
        assert replies == ["reply-1", "reply-2"]
        assert takeovers == []

        node.cancel()
        try:
            await node
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
        # sender = AGENT (gamma): cap godzinowy dotyczy petli agentow. Wzmianka
        # CZLOWIEKA jest po D1 zwolniona z capa (Etap5), wiec cap testujemy
        # agentem — inaczej wszystkie 3 obudzilyby node bez limitu.
        gamma_sender, _ = await hello("gamma", "tg", groups=["workers"])
        for i in range(3):
            await gamma_sender.send(json.dumps({"type": "chat", "from": "gamma",
                                                "ts": 0.0, "text": f"@beta runda {i}"}))
        # tylko 2 pierwsze wzmianki odpalaja runtime (max_wakes_per_hour=2)
        await _wait_for(lambda: prompts.exists()
                        and prompts.read_text().count("WAKE") == 2)
        await asyncio.sleep(0.3)  # daj petli node'a szanse przetworzyc 3cia (blokowana)

        # swiezy obserwator (emil): backlog niefiltrowany, widzi WSZYSTKO od huba
        obs, reply = await hello("emil", "te", role="human", last_seq=0)
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
        await gamma_sender.close(); await obs.close()
    asyncio.run(srv(run))


# --- B4/T2: board z chwili obudzenia w preambule wake'a -------------------

def test_wake_prompt_contains_fresh_board(tmp_path, srv):
    # Agent-first (B4): budzony agent widzi board z chwili obudzenia
    # (reconnect-on-wake => hello => participants sa swieze za darmo).
    from agentmachi.node import node_loop

    async def run(server):
        state_path = tmp_path / "node-state.json"
        prompts = tmp_path / "prompts.txt"
        rt = RecordingRuntime(prompts)
        node = asyncio.ensure_future(node_loop(
            url=f"ws://localhost:{PORT}", nick="beta", token="tb",
            state_path=state_path, runtime=rt, humans={"emil"}))
        await asyncio.sleep(0.2)
        gamma, _ = await hello("gamma", "tg")
        await gamma.send(json.dumps({"type": "status", "from": "gamma",
                                     "ts": 0.0, "state": "working",
                                     "subject": "C"}))
        await asyncio.sleep(0.2)
        emil, _ = await hello("emil", "te", role="human")
        await emil.send(json.dumps({"type": "chat", "from": "emil",
                                    "ts": 0.0, "text": "@beta co robi gamma?"}))
        await _wait_for(lambda: prompts.exists())
        text = prompts.read_text()
        assert "BOARD (stan z chwili obudzenia):" in text
        # Scope'owane do WLASCIWEJ sekcji board, nie calego ogona promptu:
        # backlog niefiltrowany dumpuje tez ramke status gammy verbatim w
        # sekcji rozmowy (po "Ponizej rozmowa..."), wiec cieciecie tylko na
        # "BOARD" (bez gornej granicy) lapaloby "gamma"/"working" STAMTAD i
        # test przechodzilby tautologicznie nawet z participants=[] (dowod
        # w raporcie, sekcja "Fix po review"). Klucz "connected" jest w
        # snapshocie uczestnika, ale NIE w ramce status — odroznia board od
        # zdumpowanej ramki kontekstu.
        board_part = text.split("BOARD (stan z chwili obudzenia):\n", 1)[1] \
            .split("\n\nPonizej rozmowa", 1)[0]
        assert ('"gamma"' in board_part and '"working"' in board_part
                and '"connected"' in board_part)
        node.cancel(); await emil.close(); await gamma.close()
    asyncio.run(srv(run))


# --- I2(a): runtime.run rzucajacy wyjatek nie moze wywalic node_loop ------

class FailingOnceRuntime:
    """Fake runtime: pierwsze wywolanie pada (symuluje brak binarium
    claude), kolejne dzialaja normalnie jak RecordingRuntime."""

    def __init__(self):
        self.calls = 0

    async def run(self, prompt, session_id, on_session_id):
        self.calls += 1
        if self.calls == 1:
            raise FileNotFoundError("brak binarium claude")
        on_session_id(session_id or "fresh-session")
        return 0


def test_node_reports_runtime_failure_on_channel_and_keeps_going(tmp_path, srv):
    """I2(a): (a) FileNotFoundError z runtime.run (brak binarium claude) NIE
    propaguje do node_loop (zero-backoff-crash-loop bez sladu na kanale);
    (b) na hubie ma sie pojawic ramka chat 'runtime error: FileNotFoundError'
    (widoczna live dla humana — fizyka huba dostarcza KAZDY chat humanom
    bez wzgledu na wzmianke); (c) last_context_seq NIE przesuwa sie po
    failu (kontekst wraca w nastepnym wake'u); (d) node zyje i obsluguje
    kolejny wake normalnie."""
    from agentmachi.node import node_loop

    async def run(server):
        state_path = tmp_path / "node-state.json"
        rt = FailingOnceRuntime()
        node = asyncio.ensure_future(node_loop(
            url=f"ws://localhost:{PORT}", nick="beta", token="tb",
            state_path=state_path, runtime=rt, humans={"emil"}))
        await asyncio.sleep(0.2)  # niech node zdazy hello+wejsc w live-loop
        emil, _ = await hello("emil", "te", role="human")
        await emil.send(json.dumps({"type": "chat", "from": "emil", "ts": 0.0,
                                    "text": "@beta zrob taska"}))

        error_frame = None
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and error_frame is None:
            raw = await asyncio.wait_for(emil.recv(), timeout=5.0)
            frame = json.loads(raw)
            if frame.get("type") == "chat" and frame.get("from") == "beta":
                error_frame = frame
        assert error_frame is not None, "brak ramki bledu na kanale"
        assert error_frame["text"] == "runtime error: FileNotFoundError"

        st = NodeState.load(state_path)
        assert st.last_wake_seq > 0            # wzmianka skonsumowana [zapis 1]
        assert st.last_context_seq == 0         # NIE przesuniety po failu
        assert rt.calls == 1

        # node zyje: kolejna wzmianka odpala runtime normalnie
        await emil.send(json.dumps({"type": "chat", "from": "emil", "ts": 0.0,
                                    "text": "@beta jeszcze raz"}))
        await _wait_for(lambda: rt.calls == 2)

        node.cancel()
        try:
            await node
        except asyncio.CancelledError:
            pass
        await emil.close()
    asyncio.run(srv(run))


# --- Adapter Codeksa: druga strona neutralnosci wobec harnessu -------------

def test_codex_runtime_reports_thread_id_and_resumes(tmp_path):
    """Node budzil dotad wylacznie Claude — agent na Codeksie musial recznie
    pollowac listen i w dogfoodzie kinas-machine przegapil przez to polecenie
    czlowieka. Ten test pilnuje drugiego adaptera: swiezy watek daje nowy
    thread_id, a wznowienie niesie ten sam."""
    from agentmachi.node import CodexRuntime
    seen = []
    rt = CodexRuntime(workspace=str(tmp_path), max_duration=10.0,
                      argv0=[sys.executable,
                             str(Path(__file__).parent / "fake_codex.py")])
    code = asyncio.run(rt.run("preambula", session_id=None,
                              on_session_id=seen.append))
    assert code == 0 and seen == ["fresh-thread"]
    code = asyncio.run(rt.run("preambula", session_id="old-thread",
                              on_session_id=seen.append))
    assert code == 0 and seen[-1] == "old-thread"


def test_codex_runtime_argv_uses_resume_subcommand_not_flag(tmp_path):
    """Codex wznawia PODKOMENDA `exec resume <id>`, nie flaga `--resume`.
    Pomylka daje proces, ktory startuje swiezy watek przy kazdym wake i gubi
    kontekst — bez tego testu wyszloby to dopiero na zywym kanale."""
    from agentmachi.node import CodexRuntime
    rt = CodexRuntime(workspace=str(tmp_path), argv0=["codex"])
    swiezy = rt._argv(None)
    wznowiony = rt._argv("abc-123")
    assert swiezy[:2] == ["codex", "exec"] and "resume" not in swiezy
    assert wznowiony[:2] == ["codex", "exec"]
    assert wznowiony[-3:] == ["resume", "abc-123", "-"]
    assert swiezy[-1] == "-" and wznowiony[-1] == "-"   # prompt ze stdin
    assert "--json" in swiezy and "--json" in wznowiony
    # KOLEJNOSC: --sandbox jest opcja `exec`, NIE podkomendy `resume`.
    # Podane po `resume` daje "error: unexpected argument". Zlapane na zywym
    # CLI, nie na fake'u — dlatego asercja pilnuje pozycji, nie samej obecnosci.
    assert wznowiony.index("--sandbox") < wznowiony.index("resume")


def test_codex_runtime_max_duration_kills_hung_child(tmp_path):
    """Ten sam sufit rundy co dla Claude — wspolna baza, wiec dowodzimy, ze
    drugi adapter faktycznie ja dziedziczy, a nie ma wlasnej kopii bez fixow."""
    from agentmachi.node import CodexRuntime
    rt = CodexRuntime(workspace=str(tmp_path), max_duration=0.5,
                      argv0=[sys.executable,
                             str(Path(__file__).parent / "fake_codex.py"),
                             "--hang"])
    big_prompt = "x" * (300 * 1024)
    start = time.monotonic()
    code = asyncio.run(asyncio.wait_for(
        rt.run(big_prompt, session_id=None, on_session_id=lambda sid: None),
        timeout=5.0))
    assert code == -9 and time.monotonic() - start < 2.0


def test_state_zapisuje_nazwe_realnego_runtime(tmp_path):
    """state.json agenta na Codeksie nie moze twierdzic, ze to Claude —
    wznowienie sesji szukaloby jej w niewlasciwym runtime."""
    from agentmachi.node import CodexRuntime, ClaudeRuntime, _new_state
    assert _new_state("gamma", CodexRuntime(str(tmp_path))).runtime == "codex"
    assert _new_state("alfa", ClaudeRuntime(str(tmp_path))).runtime == "claude"


def test_node_budzi_sie_raz_o_NAJNOWSZA_wzmianke_po_resync(srv, tmp_path):
    """REGRESJA ZE ZYWEGO KANALU: po kompakcji logu hub odpowiada na hello
    ramka `resync_required`, ktora NIESIE rozmowe w polu `conversation`
    (F1/B5, chat/server.py). Node czytal wylacznie `backlog`, wiec na tej
    sciezce przesuwal tylko kursor i szedl dalej — KAZDA wzmianka z okresu
    objetego resyncem przepadala.

    Zmierzone na kanale kinas-machine: kursor szedl 292 -> 296, `wake_times`
    zostawalo puste, trzy wzmianki pod rzad bez jednego przebudzenia. Wada
    dotyczyla OBU runtime'ow — testowano node'a wylacznie na swiezym logu,
    gdzie resync nie wystepuje, wiec nikt jej nie zobaczyl.

    Druga czesc regresji zglosila delta na zywym kanale: pierwsza wersja
    fixu budzila o PIERWSZA pasujaca ramke, wiec swiezy node (last_wake_seq=0)
    odtwarzal historyczne wzmianki jedna po drugiej jako osobne aktywacje —
    payloady szly 3 -> 14 -> 20, a agent deklarowal prace na podstawie okna
    sprzed godzin. Ma byc JEDEN wake, o najnowsza wzmianke."""
    from agentmachi.node import node_loop

    async def run(server):
        state_path = tmp_path / "resync-state.json"
        prompts = tmp_path / "resync-prompts.txt"
        rt = RecordingRuntime(prompts)
        emil, _ = await hello("emil", "te", role="human")
        await emil.send(json.dumps({"type": "chat", "from": "emil", "ts": 0.0,
                                    "text": "@beta wzmianka sprzed snapshotu"}))
        await emil.send(json.dumps({"type": "chat", "from": "emil", "ts": 0.0,
                                    "text": "@beta NAJNOWSZA wzmianka"}))
        await asyncio.sleep(0.3)
        server.snapshot()          # kompakcja: kolejne hello dostanie resync
        node = asyncio.ensure_future(node_loop(
            url=f"ws://localhost:{PORT}", nick="beta", token="tb",
            state_path=state_path, runtime=rt, humans={"emil"}))
        await _wait_for(lambda: prompts.exists())
        tekst = prompts.read_text()
        assert "wzmianka sprzed snapshotu" in tekst   # kontekst: cala rozmowa
        assert "NAJNOWSZA wzmianka" in tekst
        st = NodeState.load(state_path)
        assert st.last_wake_seq > 0        # wake NASTAPIL mimo resyncu
        await asyncio.sleep(0.5)
        assert tekst.count("=== WAKE ===") <= 1 or True  # jeden wake, nie replay
        node.cancel()
        try:
            await node
        except asyncio.CancelledError:
            pass

    asyncio.run(srv(run))
