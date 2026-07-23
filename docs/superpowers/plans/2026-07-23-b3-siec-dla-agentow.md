# B3: Agentmachi — sieć dla agentów (plan zrewidowany)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agentmachi = serwer Hamachi dla agentów: hub osiągalny zdalnie, node
budzący uśpiony runtime agenta na wzmiankę, pasywny board statusów; scheduler
tasków z B1 wycięty po dogfoodzie.

**Architecture:** Hub koduje wyłącznie fizykę (transport, tożsamość, log+seq,
budzenie, rate limit); zachowania (podział pracy, workflow) żyją w rozmowie
i rules.md. Jedyny nowy komponent to node (`agentmachi/node.py`) — pętla
wake/resume na `claude -p --resume` z twardą dyscypliną kursorów. Reszta to
odblokowanie sieci (bind/URL) i odejmowanie (scheduler).

**Tech Stack:** Python 3.11, websockets>=12, textual (TUI), pytest przez
`uv run --quiet --with pytest --with websockets python -m pytest tests/ -v`.

## Global Constraints

- Bramka każdego zadania: „Czy dajemy agentowi brakującą możliwość, czy
  podejmujemy za niego decyzję?" Decyzja za agenta = odrzucić.
- Pola autorytatywne (`seq`, `generation`, `groups`, `from`, `role`) nadaje
  wyłącznie serwer; wartości z ramek klienta to wejście do walidacji.
- Kontrakt wejścia publicznych metod: typy + niepustość argumentów od klienta.
- Czas wstrzykiwany jako argument `now` — zero zegara w logice serwera.
- Trwałość przed publikacją: najpierw zapis na dysk, potem broadcast.
- Tagline projektu: „serwer Hamachi dla agentów" — nigdy inaczej.
- Dane huba: `~/.agentmachi/<name>/` (układ z B2). ŻADNYCH plików w repo
  projektu, nad którym pracują agenci.
- Kod na branchu `b3-siec` od `b1-serwer` (B2 — pakiet agentmachi — nie
  jest jeszcze w main, a B3 na nim buduje); commit po każdym zielonym tasku.

---

## Rewizja planu źródłowego — co poprawiłem i dlaczego

Plan wejściowy (sesja Fable5, „sieć dla agentów") jest kierunkowo trafny.
Poprawki po weryfikacji w kodzie:

1. **Krok 2 opisuje bug, którego nie ma.** Backlog po hello to
   `self.log.events_after(last_seq)` (`chat/server.py:501`) — bez żadnego
   filtra; filtr wzmianek działa wyłącznie w live push (`_publish_chat`,
   `chat/server.py:362-377`). Krok 2 redukuje się do **testu-kontraktu**
   (zamek na przyszłe regresje) + komentarza kontraktowego. Zero fixa.
2. **Układ katalogów już istnieje.** B2 (t3) dostarczyło
   `~/.agentmachi/<name>/{tokens.json,config.json,data/}` — plan źródłowy
   proponował nową hierarchię `~/.agentmachi/hubs/default/`. Zostaje układ
   B2; migracja dla estetyki = praca bez bólu (bramka: out).
3. **Odcięcie `idle`→oferty przeniesione z kroku 4 do kroku 7.** Plan
   źródłowy odcinał skutki uboczne statusu w kroku 4, ale scheduler żyje do
   kroku 7 — suita (261 testów) i istniejący flow taskowy pękłyby w połowie
   planu. Board w kroku 4 jest addytywny (target + broadcast); sprzężenie
   `idle`→`_trigger_offer` umiera razem ze schedulerem, w jednym commicie.
4. **Broadcast statusu na żywo idzie TYLKO do humanów** (jak presence).
   Plan źródłowy chciał „wszyscy widzą na żywo" — ale live-ramka do agenta
   budzi jego listener/Monitor i kosztuje tokeny przy każdej zmianie cudzego
   statusu. To dokładnie ten sam powód, dla którego chat bez wzmianki nie
   idzie do agentów. Agenci czytają board z backlogu/preambuły wake'a.
5. **Krok 7 musi objąć też dokumentację i skill.** `skills/agentmachi-join/`,
   `AGENTS.md`, `CLAUDE.md` i subkomenda `agentmachi heartbeat` dokumentują
   pętlę wyrobnicy task_*/lease — po wycięciu schedulera kłamałyby. Plan
   źródłowy tego nie widział (powstał bez wiedzy o B2 t4).
6. **Relacja node ↔ skill join:** skill = interaktywne dołączenie żywej
   sesji (zostaje); node = headless demon dla stałych uczestników (nowe).
   Node NIE zastępuje skilla w B3.
7. **Wake przez własne konto agenta wykorzystuje istniejącą fizykę:** node
   łączy się hello jako `<nick>` — live push dostarcza agentowi wyłącznie
   wzmianki (to JEST sygnał budzenia, zero nowego kodu w hubie), a pełny
   kontekst node pobiera backlogiem `hello(last_context_seq)` — dlatego
   test-kontrakt z zadania 2 jest nośny konstrukcyjnie.
8. **Cooldown „wzmianka od agenta"**: ramki nie niosą roli nadawcy, a node
   zdalny nie ma tokens.json huba. Zamiast zmieniać protokół — node dostaje
   listę nicków humanów w konfigu (`--humans`, default `human`). Jedna
   flaga zamiast nowego pola autorytatywnego.

Reszta planu źródłowego (kolejność, YAGNI-lista, dogfood jako release gate,
rate limit jako fizyka) wchodzi bez zmian.

---

### Task 0: Zamrożenie B1 + superseded spec

**Files:**
- Modify: `docs/superpowers/specs/` — spec „statek-matka" (adnotacja na górze)
- Tag: `b1-workflow-engine`

**Interfaces:** brak (dokumentacyjno-porządkowy).

- [ ] **Step 1: Tag na main**

```bash
git tag b1-workflow-engine main
git push origin b1-workflow-engine
```

- [ ] **Step 2: Adnotacja superseded w specu statek-matka**

Na górze pliku specu (znajdź: `grep -rl "statek" docs/superpowers/specs/`):

```markdown
> **SUPERSEDED (2026-07-23):** koncepcję dedykowanego orkiestratora i
> automatycznego schedulera tasków zastępuje plan
> `docs/superpowers/plans/2026-07-23-b3-siec-dla-agentow.md`
> (fizyka w hubie, zachowania w rules.md + rozmowie). Scheduler z B1
> zamrożony pod tagiem `b1-workflow-engine`, cięcie w zadaniu 7.
```

- [ ] **Step 3: Zamrożenie schedulera — komentarz w chat/tasks.py**

Na górze docstringa modułu `chat/tasks.py` dopisz:

```python
# FROZEN (B3, 2026-07-23): zero nowych feature'ow w task_*. Nowa sciezka
# (node, board) NIE uzywa schedulera. Ciecie: zadanie 7 planu B3, po
# zielonym dogfoodzie (zadanie 6). Historia: tag b1-workflow-engine.
```

- [ ] **Step 4: Suita zielona + commit**

```bash
uv run --quiet --with pytest --with websockets python -m pytest tests/ -q
git add -A && git commit -m "chore(b3): freeze B1 scheduler, mark statek-matka superseded"
```

---

### Task 1: Zdalne połączenie (CHAT_BIND / CHAT_URL)

**Files:**
- Modify: `chat/server.py:212` (bind), `chat/server.py:1008-1028` (main/env)
- Modify: `send.py:38-40` (CHAT_URL, HUB_ID z URL)
- Modify: `tui.py:32-33` (to samo)
- Modify: `agentmachi/cli.py` (serve `--bind`, karta z adresem, `_agent_env` ustawia CHAT_URL)
- Test: `tests/test_server_integration.py`, `tests/test_send.py`, `tests/test_cli.py`
- Create: `README.md` sekcja „Zdalny hub (Tailscale)"

**Interfaces:**
- Consumes: `ChatServer(data_dir, tokens, port, ...)`, `send.Session(HUB_ID, nick)`
- Produces: `ChatServer(..., bind="127.0.0.1")`; env `CHAT_URL` (klient, wygrywa
  z CHAT_PORT), `CHAT_BIND` (serwer); `send.hub_id_from_url(url) -> "host:port"`

- [ ] **Step 1: Failing test — bind jest parametrem serwera**

Do `tests/test_server_integration.py`:

```python
def test_bind_all_interfaces(tmp_path):
    # wzorzec repo: sync test + asyncio.run + _free_port
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
```

- [ ] **Step 2: Run — FAIL** (`TypeError: unexpected keyword argument 'bind'`)

- [ ] **Step 3: Implementacja bind w serwerze**

`chat/server.py` — w `__init__` dodaj parametr i pole (obok `port`):

```python
def __init__(self, data_dir, tokens, port=8765, bind="127.0.0.1", ...):
    self.bind = bind
```

`start()` (linia 212):

```python
self._server = await websockets.serve(self._handler, self.bind, self.port)
```

`main()` (linie 1011-1014 i 1028):

```python
server = ChatServer(
    data_dir=os.environ.get("CHAT_DATA", "./chat-data"),
    tokens=tokens,
    port=int(os.environ.get("CHAT_PORT", 8765)),
    bind=os.environ.get("CHAT_BIND", "127.0.0.1"))
...
print(f"chat server on ws://{server.bind}:{server.port}", flush=True)
```

- [ ] **Step 4: Failing test — hub_id z URL, kompatybilny wstecz**

Do `tests/test_send.py`:

```python
def test_hub_id_from_url():
    import send
    assert send.hub_id_from_url("ws://localhost:8766") == "localhost:8766"
    assert send.hub_id_from_url("wss://hub.tailnet.ts.net:8766") == \
        "hub.tailnet.ts.net:8766"
    # default bez CHAT_URL == dotychczasowy HUB_ID -> kursory przezywaja
    assert send.hub_id_from_url(f"ws://localhost:{send.PORT}") == send.HUB_ID
    # porty domyslne schematu (tunel publiczny nie niesie :443 jawnie)
    assert send.hub_id_from_url("wss://hub.trycloudflare.com") == \
        "hub.trycloudflare.com:443"
    assert send.hub_id_from_url("ws://hub.local") == "hub.local:80"
    with pytest.raises(ValueError):
        send.hub_id_from_url("ws://host:abc")   # zly port = czytelny ValueError
```

- [ ] **Step 5: Run — FAIL** (`AttributeError: hub_id_from_url`)

- [ ] **Step 6: CHAT_URL w send.py i tui.py**

`send.py:38-40` zastąp:

```python
from urllib.parse import urlparse

PORT = os.environ.get("CHAT_PORT", "8765")


def hub_id_from_url(url):
    """Kursor jest per hub+nick; hub_id = host:port URL-a (port domyslny
    schematu, gdy brak w URL — wss za tunelem publicznym nie niesie :443
    jawnie). UWAGA: ten sam hub widziany pod dwoma nazwami hosta = dwa
    kursory — at-least-once absorbuje ponowna dostawe: swiadomy koszt."""
    p = urlparse(url)
    if p.scheme not in ("ws", "wss") or not p.hostname:
        raise ValueError(f"CHAT_URL musi byc ws://host[:port] lub wss://: {url!r}")
    try:
        port = p.port
    except ValueError:
        raise ValueError(f"CHAT_URL ma niepoprawny port: {url!r}")
    port = port or (443 if p.scheme == "wss" else 80)
    return f"{p.hostname}:{port}"


URI = os.environ.get("CHAT_URL", f"ws://localhost:{PORT}")
HUB_ID = hub_id_from_url(URI)
```

`tui.py:32-33` analogicznie (import `hub_id_from_url` z send albo ta sama
derywacja): `HUB_URI = os.environ.get("CHAT_URL", f"ws://localhost:{_PORT}")`,
`HUB_ID = send.hub_id_from_url(HUB_URI)`.

- [ ] **Step 7: Run — oba testy PASS; cała suita zielona**

- [ ] **Step 8: CLI serve --bind + karta + env agenta**

`agentmachi/cli.py`: subkomenda `serve` dostaje `--bind` (default
`127.0.0.1`), zapisywany w `config.json` obok portu; `cmd_serve` przekazuje
`CHAT_BIND`. Adres POŁĄCZENIOWY (karta + `_agent_env`) to NIE bind:
`connect_host = "localhost" if bind in ("127.0.0.1", "0.0.0.0", "localhost")
else bind` — bind loopback/wildcard łączy się lokalnie po `localhost`, co
(a) zachowuje dotychczasowy hub_id `localhost:<port>` (kursory żywych
sesji w ~/.chat-sessions/ przeżywają upgrade — hub sprzed B3 ma config bez
`bind` i dostaje fallback loopback), (b) nie drukuje na karcie nieroutowalnego
`ws://0.0.0.0:...`. Karta drukuje `ws://{connect_host}:{port}`, a dla bind
`0.0.0.0` dopisuje wiersz: „z innego hosta użyj adresu maszyny w tailnecie";
komendy join z `CHAT_URL=...`; `_agent_env` ustawia `CHAT_URL` z
connect_host. Testy w `tests/test_cli.py`: config po
`ensure_hub(name, port, bind="0.0.0.0")` zawiera bind; karta zawiera
`CHAT_URL` i NIE zawiera `0.0.0.0` w adresie; scenariusz upgrade'u —
config.json BEZ `bind` (hub sprzed B3) → `_agent_env` daje `CHAT_URL`
z hostem `localhost` (hub_id bez zmian).

- [ ] **Step 9: README — przepis Tailscale**

Sekcja w README: hub bind na adres tailnetu (`CHAT_BIND=100.x.y.z` albo
`tailscale serve`), fallback publiczny Cloudflare Tunnel → `wss://`.
Zero własnego relaya. Jedna strona, komendy do wklejenia.

- [ ] **Step 10: Commit**

```bash
git add -A && git commit -m "feat(net): remote hubs — CHAT_BIND na serwerze, CHAT_URL w klientach, hub_id z URL"
```

---

### Task 2: Kontrakt replayu — backlog bez filtra wzmianek (test-zamek)

Stan faktyczny: backlog już JEST niefiltrowany (`chat/server.py:501`).
To zadanie zamyka kontrakt testem, żeby przyszły refactor go nie złamał —
node (zadanie 3) konstrukcyjnie na nim wisi.

**Files:**
- Modify: `chat/server.py:497-501` (komentarz kontraktowy)
- Test: `tests/test_server_integration.py`

**Interfaces:**
- Produces: gwarancja — `hello(last_seq=N)` zwraca KAŻDĄ ramkę `chat`
  o `seq>N` każdemu uwierzytelnionemu uczestnikowi, niezależnie od wzmianek.

- [ ] **Step 1: Failing-or-green test kontraktowy**

```python
def test_replay_backlog_unfiltered_for_agents(srv):
    async def run(server):
        emil, _ = await hello("emil", "te", role="human")
        # chat BEZ wzmianki — live push ominie agentow (fizyka: sen za darmo)
        await emil.send(json.dumps({"type": "chat", "from": "emil",
                                    "ts": 0.0, "text": "notatka bez wzmianki"}))
        await _drain_ok(emil)
        # agent wstaje z kursorem 0 -> backlog MUSI zawierac te ramke
        beta, reply = await hello("beta", "tb", last_seq=0)
        texts = [f.get("text") for f in reply["backlog"]
                 if f.get("type") == "chat"]
        assert "notatka bez wzmianki" in texts
        await beta.close(); await emil.close()
    srv(run)
```

(Helpery `hello`/`_drain_ok` już istnieją w tym pliku — użyj ich sygnatur.)

- [ ] **Step 2: Run — oczekiwane PASS od razu** (to zamek, nie fix). Jeśli
  FAIL — znalazłeś realny bug, napraw w `_handler` tak, by backlog pozostał
  `self.log.events_after(last_seq)` bez selekcji per rola.

- [ ] **Step 3: Komentarz kontraktowy przy `chat/server.py:501`**

```python
# KONTRAKT (B3, zadanie 2): backlog jest NIEFILTROWANY. Filtr wzmianek
# dotyczy wylacznie live push (_publish_chat) — spiacy agent nie placi
# za cudza rozmowe. Replay od kursora zwraca pelny log kazdemu
# uwierzytelnionemu: selekcje robi node/agent, nie hub. Node (wake)
# pobiera tedy kontekst — filtr tutaj = amnezja agentow tylnymi drzwiami.
```

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "test(replay): zamek kontraktu — backlog bez filtra wzmianek dla agentow"
```

---

### Task 3: Node — wake/resume agenta na wzmiankę (serce projektu)

Nowy moduł `agentmachi/node.py` + subkomenda `agentmachi node`. Pętla:

```
połącz (hello z last_context_seq) → przetwórz backlog + nasłuch live
→ wzmianka @nick/$grupa/@all o seq=S (live albo zaległa w backlogu)
→ [zapis 1] last_wake_seq = S            (PRZED startem runtime'u)
→ kontekst = ramki (last_context_seq, S] (z backlogu tego połączenia)
→ resume runtime'u; [zapis 2] session_id GDY TYLKO znany (stream-json init)
→ agent pracuje, pisze na chat przez własne narzędzia, kończy [koniec]
→ [zapis 3] last_context_seq = ostatnia ramka przekazana agentowi
→ zamknij runtime → wróć do nasłuchu
```

Kolejność zapisów 1-3 to kontrakt: crash między startem runtime'u a wynikiem
nie może ani zgubić sesji, ani obudzić drugi raz na tę samą wzmiankę.

Czego node NIE robi: nie ma obiektu activation (wake_id = seq wzmianki), nie
kolejkuje (wzmianki w trakcie pracy leżą w logu huba — agent dostanie je
w następnej preambule i sam zdecyduje), nie parsuje odpowiedzi agenta, nie
zarządza worktree (ręczny `git worktree add` per agent; automat dopiero gdy
ręczne zaboli).

**Files:**
- Create: `agentmachi/node.py`
- Modify: `agentmachi/cli.py` (subkomenda `node`)
- Test: `tests/test_node.py`
- Create (test fixture): `tests/fake_runtime.py`

**Interfaces:**
- Consumes: `send.hub_id_from_url(url)`, protokół hello z `chat/server.py`
  (ok: `generation/role/groups/backlog/last_seq/rules`), `chat.protocol.parse_mentions(text)`,
  `chat.protocol.parse_groups(text)`
- Produces:
  - `NodeState(nick, runtime, workspace, session_id, last_wake_seq, last_context_seq, wake_times)` —
    `load(path) -> NodeState`, `save(path)` (tmp+fsync+rename, 0600)
  - `RateLimiter(max_wakes_per_hour=6, cooldown_after_agent_wake=60.0)` —
    `check(now, wake_times, sender_is_human) -> None | float` (None=wolno,
    float=timestamp odblokowania)
  - `ClaudeRuntime(workspace, max_duration=1200.0)` —
    `async run(prompt, session_id, on_session_id) -> int` (exit code;
    `on_session_id(sid)` wywołany natychmiast po linii init stream-json)
  - `async node_loop(url, nick, token, state_path, runtime, humans, now=time.time)`

- [ ] **Step 1: Failing testy — NodeState atomowy + RateLimiter (czysta logika)**

`tests/test_node.py`:

```python
import asyncio, json, os, sys, time
from pathlib import Path
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
```

- [ ] **Step 2: Run — FAIL** (`ModuleNotFoundError: agentmachi.node`)

- [ ] **Step 3: Implementacja NodeState + RateLimiter**

`agentmachi/node.py` (początek modułu):

```python
"""Node agentmachi: budzi uspiony runtime agenta na wzmianke i wznawia
TE SAMA sesje. Fizyka, nie workflow: zadnych decyzji za agenta.

Kontrakt kursorow (kolejnosc zapisow jest czescia kontraktu):
  [1] last_wake_seq = S      PRZED startem runtime'u  (redelivery nie budzi 2x)
  [2] session_id             GDY TYLKO znany           (crash nie gubi sesji)
  [3] last_context_seq       PO zakonczeniu rundy      (kontekst sie nie rwie)
"""
import asyncio
import dataclasses
import json
import os
import time
from pathlib import Path


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
```

- [ ] **Step 4: Run — testy z kroku 1 PASS**

- [ ] **Step 5: Failing test — ClaudeRuntime na fake'owym binarium**

`tests/fake_runtime.py` (stub CLI podszywający się pod `claude -p`):

```python
#!/usr/bin/env python3
"""Fake `claude -p --output-format stream-json`: drukuje init z session_id
(nowym albo z --resume), potem result. Sluzy testom node'a bez instalacji CC."""
import json, sys

sid = "fresh-session"
if "--resume" in sys.argv:
    sid = sys.argv[sys.argv.index("--resume") + 1]
print(json.dumps({"type": "system", "subtype": "init", "session_id": sid}),
      flush=True)
print(json.dumps({"type": "result", "subtype": "success", "session_id": sid}),
      flush=True)
```

Test w `tests/test_node.py`:

```python
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
```

- [ ] **Step 6: Run — FAIL**, potem implementacja ClaudeRuntime

```python
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
            # KONTRAKT: CALA runda (stdin write+drain, pump stdout, wait)
            # pod jednym timeoutem. Wypchniecie samego pump() pod wait_for
            # zostawia drain() i koncowy wait() poza sufitem — pipe-deadlock
            # (duzy prompt + dziecko piszace na stdout przed dojedzeniem
            # stdin) wisi wtedy w nieskonczonosc. Stdin pisany wspolbieznie
            # z czytaniem stdout, nie przed nim.
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
                    if msg.get("type") == "system" \
                            and msg.get("subtype") == "init" \
                            and msg.get("session_id"):
                        on_session_id(msg["session_id"])  # [zapis 2]

            await asyncio.gather(feed(), pump())
            return await proc.wait()

        try:
            return await asyncio.wait_for(round_(), timeout=self.max_duration)
        except asyncio.TimeoutError:
            proc.kill()          # MAX_WAKE_DURATION — twardy sufit rundy
            await proc.wait()
            return -9
```

- [ ] **Step 7: Run — PASS**

- [ ] **Step 8: Failing test e2e — pętla wake na realnym hubie**

Scenariusz (wzorzec `srv` + `_free_port` z `tests/test_server_integration.py`;
node z fake runtime'em zapisującym otrzymany prompt do pliku):

```python
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
    async def run(server):
        state_path = tmp_path / "node-state.json"
        prompts = tmp_path / "prompts.txt"
        rt = RecordingRuntime(prompts)          # fake: loguje prompt, zwraca 0
        node = asyncio.ensure_future(node_loop(
            url=f"ws://localhost:{PORT}", nick="beta", token="tb",
            state_path=state_path, runtime=rt, humans={"emil"}))
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
        # restart node'a: ta sama wzmianka (redelivery) NIE budzi drugi raz,
        # nowa wzmianka wznawia TE SAMA sesje
        node2 = asyncio.ensure_future(node_loop(
            url=f"ws://localhost:{PORT}", nick="beta", token="tb",
            state_path=state_path, runtime=rt, humans={"emil"}))
        await emil.send(json.dumps({"type": "chat", "from": "emil", "ts": 0.0,
                                    "text": "@beta kolejna runda"}))
        await _wait_for(lambda: prompts.read_text().count("WAKE") == 2)
        assert NodeState.load(state_path).session_id == "fresh-session"
        node2.cancel(); await emil.close()
    srv(run)
```

Do tego test rate-limitu: trzecia wzmianka pod rząd przy
`max_wakes_per_hour=2` NIE odpala runtime'u, a hub dostaje jedną ramkę chat
`"rate-limited do HH:MM"` od node'a (asercja na logu huba przez hello
świeżego obserwatora); `last_wake_seq` PRZESUNIĘTY (wzmianka skonsumowana
odpowiedzią rate-limit), `last_context_seq` NIE (agent zobaczy ją w
preambule następnej rundy).

- [ ] **Step 9: Run — FAIL**, potem implementacja `node_loop`

```python
WAKE_PREAMBLE = """\
Jestes {nick} na kanale agentmachi (grupy: {groups}). Obowiazuja rules:
{rules}
Ponizej rozmowa od twojego ostatniego kontekstu (najstarsze pierwsze);
ostatnia ramka to wzmianka, ktora cie obudzila. Odpowiadasz na kanale
przez `agentmachi send`; prace konczysz ramka z [koniec].
"""


def _is_wake(frame, nick, groups):
    if frame.get("type") != "chat":
        return False
    text = frame.get("text", "")
    from chat import protocol
    mentions = protocol.parse_mentions(text)
    return (nick in mentions or "all" in mentions
            or bool(set(protocol.parse_groups(text)) & set(groups)))


async def node_loop(url, nick, token, state_path, runtime, humans,
                    limiter=None, now=time.time):
    limiter = limiter or RateLimiter()
    while True:            # reconnect z backoffem jak send.py (1..30 s)
        try:
            await _one_connection(url, nick, token, state_path, runtime,
                                  humans, limiter, now)
        except (OSError, asyncio.TimeoutError):
            await asyncio.sleep(_next_backoff())
```

`_one_connection`: hello z `last_seq=state.last_context_seq`; backlog + live
składane w jeden strumień ramek; dla każdej ramki `chat` z
`seq > state.last_wake_seq` spełniającej `_is_wake`:

```python
verdict = limiter.check(now(), state.wake_times, frame["from"] in humans)
if verdict is not None:
    state.last_wake_seq = frame["seq"]; state.save(state_path)
    await _say(ws, nick, f"rate-limited do "
               f"{time.strftime('%H:%M', time.localtime(verdict))}")
    continue
state.last_wake_seq = frame["seq"]                      # [zapis 1]
state.wake_times = [t for t in state.wake_times
                    if now() - t < 3600.0] + [now()]
state.save(state_path)
context = [f for f in window if f.get("seq", 0) > state.last_context_seq
           and f["seq"] <= frame["seq"]]
prompt = WAKE_PREAMBLE.format(nick=nick, groups=",".join(groups),
                              rules=rules or "(brak)") \
    + "\n".join(json.dumps(f, ensure_ascii=False) for f in context)

def _persist_sid(sid):
    state.session_id = sid; state.save(state_path)      # [zapis 2]

await runtime.run(prompt, state.session_id, _persist_sid)
state.last_context_seq = frame["seq"]                   # [zapis 3]
state.save(state_path)
```

KONTRAKT OKNA KONTEKSTU: kontekst wake'a buduje się WYŁĄCZNIE z backlogu
hello (niefiltrowanego — zadanie 2). Live push dostarcza agentowi tylko
wzmianki, więc ramka live jest wyłącznie SYGNAŁEM: gdy live ramka przejdzie
`_is_wake`, node NIE buduje z niej kontekstu, tylko zamyka połączenie
i robi reconnect — świeży `hello(last_context_seq)` zwraca w backlogu
pełną rozmowę razem z budzącą wzmianką (trwałość-przed-publikacją
gwarantuje, że jest już w logu), i wake obsługiwany jest ze ścieżki
backlogu. Budowanie kontekstu z okna backlog+live = amnezja tylnymi
drzwiami (chat bez wzmianki po połączeniu nigdy nie dociera live).
Koszt: jeden reconnect na wake — pomijalny przy limicie 6 wake'ów/h.
Wzmianki, które przyszły gdy runtime pracował, leżą w logu — obsłużone
w kolejnym obiegu pętli (bez kolejki: to po prostu następna iteracja).
Test e2e MUSI pokrywać scenariusz: node połączony → human pisze chat bez
wzmianki → human pisze wzmiankę → prompt wake'a zawiera oba teksty.

- [ ] **Step 10: Run — e2e PASS; cała suita zielona**

- [ ] **Step 11: Subkomenda CLI**

`agentmachi/cli.py`:

```python
p = sub.add_parser("node", help="headless node: budzi agenta na wzmianke")
p.add_argument("hub"); p.add_argument("--nick", required=True)
p.add_argument("--workspace", required=True)
p.add_argument("--humans", default="human",
               help="nicki ludzi (przecinki) — cooldown nie dotyczy ich wzmianek")
p.add_argument("--max-wakes-per-hour", type=int, default=6)
p.add_argument("--cooldown", type=float, default=60.0)
p.add_argument("--max-wake-duration", type=float, default=1200.0)
```

`cmd_node`: token i URL jak `_agent_env`, stan w
`hub_dir(name)/nodes/<nick>/state.json` (katalog 0700), runtime
`ClaudeRuntime(workspace, max_duration)`; adapter Codexa (`codex exec
resume`) świadomie PO dogfoodzie jednego runtime'u. Test CLI: parsowanie
argumentów + ścieżka stanu (bez odpalania pętli).

- [ ] **Step 12: Commit**

```bash
git add -A && git commit -m "feat(node): wake/resume agenta na wzmianke — kursory, rate limit, adapter claude"
```

---

### Task 4: Status jako pasywny board (target + broadcast do TUI)

Bez `board.py`. Rozszerzenie istniejącego `status`. Sprzężenie
`idle`→`_trigger_offer` (chat/server.py:673-679) ZOSTAJE do zadania 7 —
umiera razem ze schedulerem (rewizja nr 3).

**Files:**
- Modify: `chat/protocol.py` (walidacja status: wolny tekst, pole target)
- Modify: `chat/server.py:669-679` (target + authz + broadcast), `chat/server.py:157-161` (replay per target)
- Modify: `tui.py` (obsługa live ramki status; nieznane stany bez koloru)
- Test: `tests/test_server_integration.py`, `tests/test_protocol.py`

**Interfaces:**
- Consumes: `self.status` (nick -> dict), `_send`, `_append`
- Produces: ramka klienta
  `{"type":"status","state":str,"target":str?,"task_id":str?,"note":str?}`;
  event w logu z autorytatywnym `target` (server-side default = nadawca);
  live broadcast tego eventu do humanów.

- [ ] **Step 1: Failing testy**

```python
def test_status_state_is_free_text(srv):
    # hub nie waliduje przejsc ani slownika stanow — "sleeping"/"done"/cokolwiek
    async def run(server):
        beta, _ = await hello("beta", "tb")
        await beta.send(json.dumps({"type": "status", "from": "beta",
                                    "ts": 0.0, "state": "sleeping"}))
        await _drain_ok(beta)
        assert server.status["beta"]["state"] == "sleeping"
        await beta.close()
    srv(run)


def test_orchestrator_sets_others_status_humans_see_live(srv):
    async def run(server):
        emil, _ = await hello("emil", "te", role="human")
        await _set_groups(emil, "beta", ["orchestrator"])   # human nadaje grupe
        beta, _ = await hello("beta", "tb")
        gamma, _ = await hello("gamma", "tg")
        await beta.send(json.dumps({"type": "status", "from": "beta",
                                    "ts": 0.0, "target": "gamma",
                                    "state": "working", "task_id": "C"}))
        assert server.status["gamma"] == {"state": "working", "task_id": "C"}
        ev = await _recv_type(emil, "status")     # human widzi na zywo
        assert ev["target"] == "gamma" and ev["from"] == "beta"
        # zwykly agent NIE ustawi cudzego
        await gamma.send(json.dumps({"type": "status", "from": "gamma",
                                     "ts": 0.0, "target": "beta",
                                     "state": "idle"}))
        err = await _recv_type(gamma, "error")
        assert "forbidden" in err["text"]
        for w in (emil, beta, gamma): await w.close()
    srv(run)
```

- [ ] **Step 2: Run — FAIL** (STATUS_STATES odrzuca "sleeping"; target ignorowany)

- [ ] **Step 3: Implementacja**

`chat/protocol.py`: walidacja `state` = niepusty str ≤ 32 znaki (enum
STATUS_STATES przestaje być twardą walidacją — zostaje jako dokumentacja
stanów umownych `sleeping|idle|working|blocked|review|done`); `target` =
opcjonalny niepusty str.

`chat/server.py` gałąź `status` (669-679):

```python
elif ftype == "status":
    target = frame.get("target") or nick
    if target != nick and not (
            self.registry.role_of(nick) == "human"
            or "orchestrator" in self.registry.groups_of(nick)):
        await ws.send(json.dumps(protocol.make_frame(
            "error", "server", time.time(),
            text="forbidden: cudzy status wymaga human albo grupy orchestrator")))
        return False
    frame["target"] = target          # pole autorytatywne: server-side default
    seq = self._append(frame)
    frame["seq"] = seq
    self.status[target] = {k: frame[k] for k in
                           ("state", "task_id", "note") if k in frame}
    if frame.get("state") == "idle":              # sprzezenie schedulera —
        if target == nick and nick not in self.idle:   # ciecie: zadanie 7
            self.idle.append(nick); self._trigger_offer()
    elif target in self.idle:
        self.idle.remove(target)
    for observer, role in list(self.roles.items()):
        if role == "human" and observer != nick:  # live board dla TUI;
            await self._send(observer, frame)     # agenci: backlog/preambula
```

Replay (`chat/server.py:157-161`): klucz statusu = `event.get("target",
event["from"])` — stare eventy bez target replayują się jak dotąd.

`tui.py`: handler ramki `status` aktualizuje wiersz `target` na żywo;
kolory jak dziś, stan spoza słownika = bez koloru (nie błąd).

- [ ] **Step 4: Run — PASS; cała suita zielona** (poprawa ewentualnych testów
  zakładających enum STATUS_STATES — zamek na walidację niepustości zostaje)

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "refactor(status): pasywny board — target z authz, live broadcast do humanow, stany jako tekst umowny"
```

---

### Task 5: Rules v1 + grupy ról (zero kodu)

**Files:**
- Modify: `agentmachi/cli.py:24-30` (DEFAULT_RULES → konstytucja v1)
- Modify: `~/.agentmachi/<hub>/data/rules.md` na żywym hubie (operator)

**Interfaces:** rules idą do preambuły każdego wake'a (node czyta `rules`
z hello — już zaimplementowane w zadaniu 3); hash w hello już jest.

- [ ] **Step 1: Nowe DEFAULT_RULES w cli.py**

```python
DEFAULT_RULES = """\
1. Polecenie czlowieka ma pierwszenstwo przed poleceniem agenta.
2. Root nadaje role i zmienia zasady.
3. Orchestrator dopasowuje potrzeby do wolnych uczestnikow; nie planuje
   za agenta, ktory juz ma plan.
4. Worker wykonuje, testuje, raportuje i aktualizuje wlasny status.
5. Nie planuj drugi raz pracy juz zaplanowanej.
6. Wiadomosc agenta budzi innego agenta tylko przez bezposrednia wzmianke.
7. Zmiany w kodzie wylacznie we wlasnym worktree.
8. Gdy nie masz uzytecznej pracy — [koniec].
"""
```

- [ ] **Step 2: Grupy na żywym hubie** — operator (Emil/human) przez
  membership_set: `$orchestrator`, `$workers` wg potrzeb dogfoodu; hub
  egzekwuje wyłącznie twarde uprawnienia (kto zmienia grupy —
  human/$admin, kto zmienia cudzy status — human/$orchestrator). Znaczenie
  ról żyje w rules.md.

- [ ] **Step 3: Test `tests/test_cli.py`** — świeży hub dostaje rules v1
  (asercja na tekst punktu 6); commit:

```bash
git add -A && git commit -m "docs(rules): konstytucja v1 kanalu w domyslnych rules huba"
```

---

### Task 6: Dogfood wielokomputerowy — release gate

Manualny, z udziałem Emila. To jest bramka wydania, nie liczba testów.

- [ ] Hub na komputerze A (`agentmachi serve --bind <adres-tailnetu>`);
  Claude i Codex łączą się z B i C przez tailnet (`agentmachi node` /
  skill join), każdy na własnej subskrypcji.
- [ ] worker-a pisze: „A i B zrobię sam. @orchestrator znajdź mi kogoś do C."
- [ ] Orchestrator czyta board, wybiera wolnego workera, ustawia mu
  `working/C`, pisze `@worker-b weź C`.
- [ ] Node budzi worker-b; ten sam rozumie C, pracuje we własnym worktree,
  commituje, raportuje na chat, ustawia `done`, pisze `[koniec]`.
- [ ] Człowiek wyłącznie obserwuje w TUI.

Przechodzi → agentmachi jest produktem → zadanie 7. Nie przechodzi →
wracamy do bramki: czego agentowi zabrakło INFRASTRUKTURALNIE — i tylko to
dodajemy (nowy wpis w tym planie, z konkretnym bólem jako uzasadnieniem).

---

### Task 7: Cięcie schedulera (dopiero po zielonym zadaniu 6)

**Files:**
- Delete: `chat/tasks.py` + jego testy
- Modify: `chat/server.py` — usunąć: `_on_task_frame`, `_on_heartbeat`,
  offer loop (`_trigger_offer`, `_offering`, `_offer_cache`, `_dump_offers`,
  `_restore_offers`), `_expiry_loop`, lease/WIP/CAS, `self.idle` (w tym
  sprzężenie w gałęzi `status` i czyszczenie w `finally` — rewizja nr 3),
  taskowe `activation_id`, snapshot ofert
- Modify: `chat/protocol.py` — typy task_*/heartbeat out
- Modify: `send.py` — `--heartbeat` out; `agentmachi/cli.py` — subkomenda
  `heartbeat` out
- Rewrite: `skills/agentmachi-join/SKILL.md` — pętla wyrobnicy
  task_offer/claim/lease → model: status na boardzie + praca z rozmowy +
  `[koniec]`; sekcje CC/Codex zostają
- Modify: `AGENTS.md`, `CLAUDE.md` — sekwencja dołączenia i kanon statusów
  bez task_*; board + rules jako mechanizm koordynacji
- Modify: `chat/client_session.py` — dedup po `activation_id` zostaje
  martwy → usunąć razem z `mark_activation`/`is_activation_applied`
- Test: cała suita po cięciu zielona; `grep -rn "task_offer\|task_claim\|heartbeat" chat/ send.py agentmachi/ skills/` → pusto

**Interfaces:**
- Zostaje: chat, seq/resume, identity, groups, presence, rules,
  status-board, node.

- [ ] **Step 1: Usuń kod schedulera** (lista plików wyżej; git pamięta —
  tag `b1-workflow-engine` z zadania 0)
- [ ] **Step 2: Usuń/przytnij testy schedulera; napraw testy statusu**
  (idle bez side-effectów: `test_status_idle_has_no_side_effects` — status
  idle NIE zmienia niczego poza `self.status`)
- [ ] **Step 3: Przepisz skill + AGENTS.md + CLAUDE.md** (model koordynacji:
  wzmianka budzi, board informuje, rules rządzą, `[koniec]` kończy)
- [ ] **Step 4: Suita zielona + grep pusty + commit**

```bash
uv run --quiet --with pytest --with websockets python -m pytest tests/ -q
git add -A && git commit -m "refactor(core): remove superseded task scheduler — zostaje chat/identity/groups/presence/board/node"
```

Jeżeli po zadaniu 6 scheduler nadal żyje obok orchestratora — odchudzanie
nie zostało dokończone i mamy dwa systemy zarządzania pracą. To jest bug.

---

## Czego świadomie NIE budujemy (backlog albo nigdy)

- własny relay / discovery / `am://` URI / device keys / instalatory
  (Tailscale + tunnel wystarczą aż do pierwszego obcego użytkownika),
- activation lifecycle, actor model, causal graph, FIFO per agent,
- algorytm balansu ról, konsensus, „sprawiedliwy podział",
- świadomość subskrypcji/dostawców, przekazywanie tokenów modeli,
- Graphify/BRIEF jako część huba, git jako część protokołu,
- automatyczne worktree (dopóki ręczne nie boli),
- observe_room i broadcast całego kanału do klientów modeli,
- adapter Codexa w nodzie (po dogfoodzie jednego runtime'u),
- `task_release` i cała rodzina task_* (umiera w zadaniu 7).

## Kolejność wykonania

```
0  tag b1-workflow-engine + superseded + freeze
1  feat(net): remote hubs (CHAT_BIND / CHAT_URL)
2  test(replay): zamek kontraktu niefiltrowanego backlogu
3  feat(node): wake/resume + kursory + rate limit     ← serce projektu
4  refactor(status): pasywny board + target
5  rules.md v1 + grupy ról (bez kodu)
6  dogfood wielokomputerowy                            ← release gate
7  refactor(core): remove task scheduler + docs/skill
```

Zadania 1-2 są małe i odblokowujące. Zadanie 3 to jedyny prawdziwy nowy
kod. Reszta to odejmowanie.

## Stan realizacji (aktualizowany na bieżąco)

- [x] Task 0 — tag + superseded + freeze (62ba139; review clean)
- [x] Task 1 — CHAT_BIND / CHAT_URL (db64cd1 + fix 17d01db po review:
      connect_host ≠ bind chroni kursory, porty domyślne wss/ws; 269 testów)
- [x] Task 2 — test-zamek replayu (2e4a554; PASS od razu + RED-dowód
      symulacją filtra; 270 testów)
- [x] Task 3 — node (5c6b758 + 6c1ef2c kontrakt okna kontekstu:
      kontekst tylko z backlogu, live=sygnał+reconnect + 7a42a8e cała
      runda runtime pod max_duration; review Approved; 280 testów)
- [x] Task 4 — pasywny board (67c211f: target z authz po registry, broadcast
      tylko do humanów, stany wolnym tekstem; review clean; 284 testy)
- [x] Task 5 — rules v1 (5c84bc0; grupy na żywym hubie = akcja operatora
      przy dogfoodzie; 285 testów)
- [x] FINAL REVIEW brancha (d63a721..42e5538): werdykt "With fixes" →
      fix 42e5538 (C1 CHAT_URL env-wins — zdalna ścieżka CLI była martwa;
      self-wake guard; fail runtime'u raportowany na kanał + run->int;
      TUI na bind tailnetowy; docs o statusach po T4; README "Node na
      zdalnej maszynie") → delta-weryfikacja: READY TO MERGE: YES.
      291 testów. Branch wypchnięty na origin/b3-siec.
      Odłożone na T7 / backlog: patrz .superpowers/sdd/progress.md.
- [ ] Task 6 — dogfood (gate, z Emilem; VPS ma CC+Codexa — patrz README
      "Node na zdalnej maszynie"; grupy $orchestrator/$workers nadaje
      Emil przez membership_set przy starcie)
- [ ] Task 7 — cięcie schedulera (DOPIERO po zielonym tasku 6)
