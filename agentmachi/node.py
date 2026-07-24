"""Node agentmachi: budzi uspiony runtime agenta na wzmianke i wznawia
TE SAMA sesje. Fizyka, nie workflow: zadnych decyzji za agenta.

Kontrakt kursorow (kolejnosc zapisow jest czescia kontraktu):
  [1] last_wake_seq = S      PRZED startem runtime'u  (redelivery nie budzi 2x)
  [2] session_id             GDY TYLKO znany           (crash nie gubi sesji)
  [3] last_context_seq       PO zakonczeniu rundy      (kontekst sie nie rwie)

Petla (node_loop -> _one_connection): polacz (hello z last_seq=
last_context_seq) -> backlog. KONTRAKT OKNA KONTEKSTU: kontekst wake'a
budowany jest WYLACZNIE z tego backlogu (niefiltrowanego — zadanie 2),
NIGDY z ramek live. Live push dostarcza agentowi wylacznie wzmianki
(@nick/$grupa/@all — fizyka huba, chat/server.py._publish_chat), wiec
zywa ramka jest tylko SYGNALEM: gdy przejdzie _should_wake (seq >
last_wake_seq), node zamyka polaczenie i wraca do node_loop, ktory
NATYCHMIAST (bez eskalacji backoffu — to nie jest blad) reconnectuje;
swiezy hello zwraca w backlogu pelna rozmowe razem z budzaca wzmianka
(trwalosc-przed-publikacja gwarantuje, ze jest juz w logu), i wake
obsluzy sie ta sama scieszka backlogu. Budowanie kontekstu z okna
backlog+live bylo amnezja tylnymi drzwiami: chat bez wzmianki wyslany PO
polaczeniu node'a nigdy nie dociera live. Koszt: jeden reconnect na
wake — pomijalny przy limicie kilku wake'ow/h.

Dla kazdej ramki chat z backlogu z seq > last_wake_seq spelniajacej
wzmianke budzi sie runtime; kontekst przekazany runtime'owi to ramki
(last_context_seq, S] z tego backlogu, verbatim (jedna linia JSON na
ramke). Rate limiter moze zablokowac start runtime'u — wtedy
last_wake_seq i tak sie przesuwa (wzmianka skonsumowana odpowiedzia
rate-limit), ale last_context_seq NIE (agent zobaczy pomijeta ramke w
nastepnej rundzie).

Czego node NIE robi: nie ma obiektu activation, nie kolejkuje wzmianek
(przychodzace w trakcie pracy runtime'u zostaja w logu — kolejny obieg
petli/reconnect je zlapie), nie parsuje odpowiedzi agenta, nie zarzadza
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
BOARD (stan z chwili obudzenia):
{board}

Ponizej rozmowa od twojego ostatniego kontekstu (najstarsze pierwsze);
ostatnia ramka to wzmianka, ktora cie obudzila. Zanim wezmiesz robote,
zadeklaruj ja na kanale — przy kolizji deklaracji wygrywa nizszy seq
w logu. Odpowiadasz na kanale przez `agentmachi send`; prace konczysz
ramka z [koniec].
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
        self._window = 3600.0        # okno capa godzinowego (sekundy)

    def check(self, now, wake_times, sender_is_human):
        recent = [t for t in wake_times if now - t < self._window]
        # Etap5: cap godzinowy to circuit breaker chroniacy zasoby PRZED petla
        # AGENTOW, gdy nikt nie patrzy — NIE przed czlowiekiem. Czlowiek
        # MODERUJE; jego wzmianka budzi bez limitu (cooldown tez go nie dotyczy,
        # nizej). Bez tego moderacja czlowieka dusila sie na wlasnym bezpieczniku.
        if not sender_is_human and len(recent) >= self.max_wakes_per_hour:
            return min(recent) + self._window
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

        async def round_():
            # KONTRAKT (fix po review taska 3): CALA runda (stdin
            # write+drain, pump stdout, wait) pod JEDNYM timeoutem.
            # Wypchniecie samego pump() pod wait_for (stara wersja) zostawia
            # drain() i koncowy wait() POZA sufitem — pipe-deadlock: duzy
            # prompt (wiekszy niz pipe buffer, domyslnie 64KB) + dziecko
            # piszace na stdout (albo w ogole nie czytajace stdin) PRZED
            # dojechaniem calego stdin wisi wtedy w nieskonczonosc mimo
            # "twardego sufitu". Stdin pisany WSPOLBIEZNIE z czytaniem
            # stdout, nie przed nim.
            async def feed():
                proc.stdin.write(prompt.encode())
                await proc.stdin.drain()
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
                await asyncio.gather(feed(), pump())
            except OSError:
                # I2(b) fix: dziecko, ktore pada/nie czyta stdin, zamyka
                # swoj koniec pipe'u — feed() dostaje wtedy surowy
                # BrokenPipeError (OSError) bez return_exceptions=True,
                # a proc.wait() ponizej NIGDY sie nie wykonuje (zombie).
                # kill() zamiast terminate(): dziecko juz najczesciej martwe,
                # ProcessLookupError tolerowany; wait() reapuje w kazdym razie.
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                await proc.wait()
                return -1
            return await proc.wait()

        try:
            return await asyncio.wait_for(round_(), timeout=self.max_duration)
        except asyncio.TimeoutError:
            proc.kill()          # MAX_WAKE_DURATION — twardy sufit rundy
            await proc.wait()
            return -9


def _is_wake(frame, nick, groups):
    if frame.get("type") != "chat":
        return False
    if frame.get("from") == nick:
        # I1 fix: backlog jest niefiltrowany i zawiera WLASNE ramki agenta
        # (np. "@all zrobione") — nie moga wywolywac spurious wake po
        # reconnect + spam rate-limited (cooldown nie dotyczy, bo
        # from == nick nie jest w `humans`). Kontekst dalej je zawiera
        # (budowany osobno z last_context_seq, bez filtra _is_wake) —
        # tylko GATE wake'a ma je odrzucac.
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
                       limiter, now, groups, rules, participants, backlog):
    verdict = limiter.check(now(), state.wake_times, frame["from"] in humans)
    if verdict is not None:
        state.last_wake_seq = frame["seq"]
        state.save(state_path)
        await _say(ws, nick, "rate-limited do "
                   f"{time.strftime('%H:%M', time.localtime(verdict))}")
        return
    state.last_wake_seq = frame["seq"]                      # [zapis 1]
    state.wake_times = [t for t in state.wake_times
                        if now() - t < limiter._window] + [now()]
    state.save(state_path)
    context = [f for f in backlog if _has_seq(f)
               and f["seq"] > state.last_context_seq
               and f["seq"] <= frame["seq"]]
    board = "\n".join(json.dumps(p, ensure_ascii=False)
                      for p in participants) or "(pusty)"
    prompt = WAKE_PREAMBLE.format(nick=nick, groups=",".join(sorted(groups)),
                                  rules=rules or "(brak)", board=board) \
        + "\n".join(json.dumps(f, ensure_ascii=False) for f in context)

    def _persist_sid(sid):
        state.session_id = sid; state.save(state_path)      # [zapis 2]

    try:
        await runtime.run(prompt, state.session_id, _persist_sid)
    except Exception as e:
        # I2(a) fix: runtime.run moze rzucic (np. FileNotFoundError -
        # brak binarium claude). Bez tego wyjatek propagowalby do
        # node_loop -> backoff, wzmianka juz skonsumowana ([zapis 1] wyzej)
        # i ZERO sladu na kanale. Zero szczegolow/sciezek w tresci (nie
        # wyciekamy internaliow) — tylko nazwa typu wyjatku. last_context_seq
        # ([zapis 3]) CELOWO nie wykonujemy: kontekst ma wrocic w
        # nastepnym wake'u. Petla wraca normalnie (bez raise) do
        # kolejnej ramki backlogu / live-loopa.
        await _say(ws, nick, f"runtime error: {type(e).__name__}")
        return
    state.last_context_seq = frame["seq"]                   # [zapis 3]
    state.save(state_path)
    # UWAGA: `backlog` to ta sama lista, po ktorej iteruje wolajacy
    # (`for frame in backlog:` w _one_connection) — NIE mutowac jej tutaj
    # (dawne `window[:] = ...` przycinanie z ery wspolnego okna backlog+live
    # psulo iteracje wolajacego: obcinanie listy W TRAKCIE iteracji po niej
    # przez indeks powodowalo CICHE, przedwczesne zakonczenie petli po
    # pierwszej wzmiance — bug znaleziony przy naprawie kontraktu okna
    # kontekstu). Kontekst i tak jest liczony na biezaco z
    # `state.last_context_seq`, wiec przycinanie nie bylo potrzebne do
    # poprawnosci — tylko do (juz nieaktualnego) ograniczania pamieci
    # rosnacego live-okna.


async def _one_connection(url, nick, token, state_path, runtime, humans,
                          limiter, now):
    """KONTRAKT OKNA KONTEKSTU (fix po kontroli, patrz raport): kontekst
    wake'a budowany jest WYLACZNIE z backlogu tego hello (niefiltrowanego —
    zadanie 2). Live push dostarcza agentowi tylko wzmianki, wiec zywa
    ramka jest wylacznie SYGNALEM: gdy przejdzie _should_wake, node NIE
    buduje z niej kontekstu — zamyka polaczenie (return, bez wyjatku) i
    node_loop natychmiast reconnectuje (bez eskalacji backoffu, bo to nie
    jest blad). Swiezy hello(last_context_seq) zwraca w backlogu PELNA
    rozmowe razem z budzaca wzmianka (trwalosc-przed-publikacja gwarantuje,
    ze jest juz w logu), i wake obsluzy sie ponizsza scieszka backlogu.
    Budowanie kontekstu z okna backlog+live bylo amnezja tylnymi drzwiami:
    chat bez wzmianki, wyslany PO polaczeniu node'a, nigdy nie dociera live
    (fizyka huba — patrz CLAUDE.md/chat/server.py._publish_chat)."""
    state = NodeState.load(state_path) if Path(state_path).exists() \
        else _new_state(nick, runtime)
    async with websockets.connect(url) as ws:
        reply = await _hello(ws, nick, token, state.last_context_seq)
        groups = reply.get("groups", [])
        rules = reply.get("rules")
        participants = reply.get("participants", [])
        if reply.get("type") == "resync_required":
            # historia skompaktowana: kursor kontekstu = snapshot_seq,
            # stanu kolejki/rejestru node nie obchodzi (nie ma wlasnej
            # kopii taskow) — jedzie dalej od tego punktu.
            snapshot_seq = reply.get("snapshot_seq")
            if isinstance(snapshot_seq, int) and not isinstance(snapshot_seq, bool):
                state.last_context_seq = snapshot_seq
                state.save(state_path)
        else:
            backlog = [f for f in reply.get("backlog", []) if isinstance(f, dict)]
            for frame in backlog:
                if _should_wake(frame, nick, groups, state.last_wake_seq):
                    await _handle_wake(ws, nick, frame, state, state_path,
                                       runtime, humans, limiter, now, groups,
                                       rules, participants, backlog)

        async for raw in ws:
            try:
                frame = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(frame, dict):
                continue  # defensywnie ignoruj nieznane/nie-obiektowe ramki
            if _should_wake(frame, nick, groups, state.last_wake_seq):
                # SYGNAL, nie kontekst: zamknij i wroc do node_loop, ktore
                # natychmiast reconnectuje (celowy powrot — nie wyjatek).
                return


async def node_loop(url, nick, token, state_path, runtime, humans,
                    limiter=None, now=time.time):
    limiter = limiter or RateLimiter()
    backoff = BACKOFF_START
    while True:
        try:
            # Normalny (nie-wyjatkowy) powrot z _one_connection oznacza
            # ALBO czyste zamkniecie, ALBO celowy reconnect-na-sygnal-wake
            # (patrz _one_connection) — zaden z nich nie jest bledem
            # polaczenia, wiec backoff resetuje sie i petla wraca NATYCHMIAST
            # (brak sleep) bez eskalacji. Backoff z prawdziwym opoznieniem
            # (1..30 s, jak send.py) dotyczy WYLACZNIE wyjatkow ponizej.
            await _one_connection(url, nick, token, state_path, runtime,
                                  humans, limiter, now)
            backoff = BACKOFF_START
        except (OSError, asyncio.TimeoutError,
                websockets.exceptions.ConnectionClosed):
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX)
