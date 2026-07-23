"""Node agentmachi: budzi uspiony runtime agenta na wzmianke i wznawia
TE SAMA sesje. Fizyka, nie workflow: zadnych decyzji za agenta.

Kontrakt kursorow (kolejnosc zapisow jest czescia kontraktu):
  [1] last_wake_seq = S      PRZED startem runtime'u  (redelivery nie budzi 2x)
  [2] session_id             GDY TYLKO znany           (crash nie gubi sesji)
  [3] last_context_seq       PO zakonczeniu rundy      (kontekst sie nie rwie)

Petla (node_loop -> _one_connection): polacz (hello z last_seq=
last_context_seq) -> backlog + live w jednym strumieniu (window) -> kazda
ramka chat z seq > last_wake_seq spelniajaca wzmianke @nick/$grupa/@all
budzi runtime; kontekst przekazany runtime'owi to ramki (last_context_seq, S]
z okna tego polaczenia, verbatim (jedna linia JSON na ramke). Rate limiter
moze zablokowac start runtime'u — wtedy last_wake_seq i tak sie przesuwa
(wzmianka skonsumowana odpowiedzia rate-limit), ale last_context_seq NIE
(agent zobaczy pomijeta ramke w nastepnej rundzie).

Czego node NIE robi: nie ma obiektu activation, nie kolejkuje wzmianek
(przychodzace w trakcie pracy runtime'u zostaja w oknie/logu — kolejny
obieg petli je zlapie), nie parsuje odpowiedzi agenta, nie zarzadza
worktree.
"""
import asyncio
import dataclasses
import json
import os
import time
import uuid
from pathlib import Path

import websockets

from chat import protocol

BACKOFF_START, BACKOFF_MAX = 1.0, 30.0
HELLO_TIMEOUT = 10.0

WAKE_PREAMBLE = """\
Jestes {nick} na kanale agentmachi (grupy: {groups}). Obowiazuja rules:
{rules}
Ponizej rozmowa od twojego ostatniego kontekstu (najstarsze pierwsze);
ostatnia ramka to wzmianka, ktora cie obudzila. Odpowiadasz na kanale
przez `agentmachi send`; prace konczysz ramka z [koniec].
"""


@dataclasses.dataclass
class NodeState:
    nick: str
    runtime: str
    workspace: str
    session_id: str | None
    last_wake_seq: int
    last_context_seq: int
    wake_times: list

    def save(self, path):
        path = Path(path)
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(dataclasses.asdict(self), f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    @classmethod
    def load(cls, path):
        return cls(**json.loads(Path(path).read_text()))


class RateLimiter:
    """Bezpiecznik przebudzen — fizyka (dziala, gdy nikt nie patrzy)."""

    def __init__(self, max_wakes_per_hour=6, cooldown_after_agent_wake=60.0):
        if max_wakes_per_hour <= 0 or cooldown_after_agent_wake < 0:
            raise ValueError("limity musza byc dodatnie")
        self.max_wakes_per_hour = max_wakes_per_hour
        self.cooldown = cooldown_after_agent_wake

    def check(self, now, wake_times, sender_is_human):
        recent = [t for t in wake_times if now - t < 3600.0]
        if len(recent) >= self.max_wakes_per_hour:
            return min(recent) + 3600.0
        if not sender_is_human and recent:
            last = max(recent)
            if now - last < self.cooldown:
                return last + self.cooldown
        return None


class ClaudeRuntime:
    """Adapter Claude Code headless. argv0 podmienialne w testach."""

    def __init__(self, workspace, max_duration=1200.0, argv0=("claude",)):
        self.workspace = workspace
        self.max_duration = max_duration
        self.argv0 = list(argv0)

    def _argv(self, session_id):
        argv = self.argv0 + ["-p", "--output-format", "stream-json",
                             "--verbose"]
        if session_id:
            argv += ["--resume", session_id]
        return argv

    async def run(self, prompt, session_id, on_session_id):
        proc = await asyncio.create_subprocess_exec(
            *self._argv(session_id), cwd=self.workspace,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        proc.stdin.write(prompt.encode()); await proc.stdin.drain()
        proc.stdin.close()

        async def pump():
            async for raw in proc.stdout:
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue  # nie-JSON na stdout nie jest bledem node'a
                if msg.get("type") == "system" and msg.get("subtype") == "init" \
                        and msg.get("session_id"):
                    on_session_id(msg["session_id"])  # [zapis 2] u wolajacego

        try:
            await asyncio.wait_for(pump(), timeout=self.max_duration)
            return await proc.wait()
        except asyncio.TimeoutError:
            proc.kill()          # MAX_WAKE_DURATION — twardy sufit rundy
            await proc.wait()
            return -9


def _is_wake(frame, nick, groups):
    if frame.get("type") != "chat":
        return False
    text = frame.get("text", "")
    mentions = protocol.parse_mentions(text)
    return (nick in mentions or "all" in mentions
            or bool(set(protocol.parse_groups(text)) & set(groups)))


def _has_seq(frame):
    seq = frame.get("seq") if isinstance(frame, dict) else None
    return isinstance(seq, int) and not isinstance(seq, bool)


def _should_wake(frame, nick, groups, last_wake_seq):
    if not isinstance(frame, dict) or not _has_seq(frame):
        return False
    return frame["seq"] > last_wake_seq and _is_wake(frame, nick, groups)


def _new_state(nick, runtime):
    # "runtime" to string opisujacy adapter (na razie jedyny: claude) —
    # workspace bierzemy z adaptera (informacyjnie, w state.json).
    return NodeState(nick=nick, runtime="claude",
                      workspace=str(getattr(runtime, "workspace", "")),
                      session_id=None, last_wake_seq=0, last_context_seq=0,
                      wake_times=[])


async def _say(ws, nick, text):
    await ws.send(json.dumps({"type": "chat", "from": nick, "ts": 0.0,
                              "text": text}))


async def _hello(ws, nick, token, last_seq):
    # instance_id swiezy per polaczenie (nie trzymany w state.json): po
    # realnym crashu (bez czystego zamkniecia socketu) nowy instance_id
    # wywoluje takeover — serwer natychmiast zamyka osierocony stary
    # socket (niezmiennik c w chat/server.py). To pozadane samoleczenie,
    # wiec NodeState nie potrzebuje dodatkowego pola.
    await ws.send(json.dumps({
        "type": "hello", "from": nick, "ts": 0.0,
        "instance_id": f"node-{uuid.uuid4().hex}",
        "token": token, "last_seq": last_seq, "role": "agent"}))
    reply = json.loads(await asyncio.wait_for(ws.recv(), HELLO_TIMEOUT))
    if not isinstance(reply, dict) or reply.get("type") == "error":
        raise OSError(f"hello odrzucone przez hub: {reply}")
    return reply


async def _handle_wake(ws, nick, frame, state, state_path, runtime, humans,
                       limiter, now, groups, rules, window):
    verdict = limiter.check(now(), state.wake_times, frame["from"] in humans)
    if verdict is not None:
        state.last_wake_seq = frame["seq"]
        state.save(state_path)
        await _say(ws, nick, "rate-limited do "
                   f"{time.strftime('%H:%M', time.localtime(verdict))}")
        return
    state.last_wake_seq = frame["seq"]                      # [zapis 1]
    state.wake_times = [t for t in state.wake_times
                        if now() - t < 3600.0] + [now()]
    state.save(state_path)
    context = [f for f in window if _has_seq(f)
               and f["seq"] > state.last_context_seq
               and f["seq"] <= frame["seq"]]
    prompt = WAKE_PREAMBLE.format(nick=nick, groups=",".join(sorted(groups)),
                                  rules=rules or "(brak)") \
        + "\n".join(json.dumps(f, ensure_ascii=False) for f in context)

    def _persist_sid(sid):
        state.session_id = sid; state.save(state_path)      # [zapis 2]

    await runtime.run(prompt, state.session_id, _persist_sid)
    state.last_context_seq = frame["seq"]                   # [zapis 3]
    state.save(state_path)
    window[:] = [f for f in window if _has_seq(f)
                and f["seq"] > state.last_context_seq]


async def _one_connection(url, nick, token, state_path, runtime, humans,
                          limiter, now):
    state = NodeState.load(state_path) if Path(state_path).exists() \
        else _new_state(nick, runtime)
    async with websockets.connect(url) as ws:
        reply = await _hello(ws, nick, token, state.last_context_seq)
        groups = reply.get("groups", [])
        rules = reply.get("rules")
        window = []
        if reply.get("type") == "resync_required":
            # historia skompaktowana: kursor kontekstu = snapshot_seq,
            # stanu kolejki/rejestru node nie obchodzi (nie ma wlasnej
            # kopii taskow) — jedzie dalej od tego punktu.
            snapshot_seq = reply.get("snapshot_seq")
            if isinstance(snapshot_seq, int) and not isinstance(snapshot_seq, bool):
                state.last_context_seq = snapshot_seq
                state.save(state_path)
        else:
            window = [f for f in reply.get("backlog", []) if isinstance(f, dict)]
            for frame in list(window):
                if _should_wake(frame, nick, groups, state.last_wake_seq):
                    await _handle_wake(ws, nick, frame, state, state_path,
                                       runtime, humans, limiter, now, groups,
                                       rules, window)

        async for raw in ws:
            try:
                frame = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(frame, dict):
                continue  # defensywnie ignoruj nieznane/nie-obiektowe ramki
            window.append(frame)
            if _should_wake(frame, nick, groups, state.last_wake_seq):
                await _handle_wake(ws, nick, frame, state, state_path,
                                   runtime, humans, limiter, now, groups,
                                   rules, window)


async def node_loop(url, nick, token, state_path, runtime, humans,
                    limiter=None, now=time.time):
    limiter = limiter or RateLimiter()
    backoff = BACKOFF_START
    while True:            # reconnect z backoffem jak send.py (1..30 s)
        try:
            await _one_connection(url, nick, token, state_path, runtime,
                                  humans, limiter, now)
            backoff = BACKOFF_START
        except (OSError, asyncio.TimeoutError,
                websockets.exceptions.ConnectionClosed):
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX)
