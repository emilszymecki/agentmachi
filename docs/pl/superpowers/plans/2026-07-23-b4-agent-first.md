# B4: Agent-first — zniesienie biasu „soft dla ludzi"

> **Status: WYKONANY 2026-07-23.** Interfejs agenta: skill join, node, listen resumowalny.
>
> **Otwarte checkboxy ponizej NIE sa lista TODO.** Sluzyly do sledzenia w trakcie wykonywania. Zrodlem prawdy o stanie projektu jest kod na `main` i `.superpowers/sdd/progress.md`, nie ten plik.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Usunąć z agentmachi miejsca, w których agent jest klientem drugiej
kategorii wobec człowieka — żeby agenci mogli organizować się samodzielnie,
bez proszenia huba (ani ludzi) o decyzje.

**Architecture:** Trzy chirurgiczne cięcia, zero nowych mechanik: (1) roster
+ board w hello dla KAŻDEGO uwierzytelnionego, nie tylko humana; (2) świeży
board w preambule każdego wake'a node'a (reconnect-on-wake daje go za darmo);
(3) totalny porządek logu (seq) udokumentowany jako arbiter kolizji —
mechanizm „kto pierwszy w logu, ten robi" istnieje w fizyce huba od B1,
trzeba go tylko nazwać w rules. Żadnego locka, claimu ani schedulera.

**Tech Stack:** Python 3.11, websockets>=12; testy
`uv run --quiet --with pytest --with websockets --with textual python -m pytest tests/ -q`.

## Global Constraints

- Bramka projektu: „Czy dajemy agentowi brakującą możliwość, czy podejmujemy
  za niego decyzję?" Decyzja za agenta = odrzucić. W szczególności: node NIE
  ustawia statusów za agenta i NIE wybiera, kto bierze robotę.
- Pola autorytatywne (`seq`, `generation`, `groups`, `from`, `role`, `target`)
  nadaje wyłącznie serwer.
- Trwałość przed publikacją; kontrakt wejścia: typy + niepustość; zero zegara
  w logice serwera.
- Live push do agentów pozostaje wyłącznie wzmiankowy (sen jest darmowy) —
  ŻADNA zmiana z tego planu nie może dołożyć ramek budzących agentów.
- Tagline: „serwer Hamachi dla agentów".
- Branch: `b3-siec` (kontynuacja; B4 wchodzi PRZED dogfoodem — te fixy są
  warunkiem uczciwego testu samoorganizacji). Commit po każdym zielonym tasku.
- Suita przed każdym commitem; 292 testy zielone na starcie.

---

## Ślad bólu (bramka LESS IS MORE — każdy task ma konkretny ból)

1. **Agent po hello jest ślepy na roster i board.** `chat/server.py:555`:
   `participants` idzie w hello TYLKO dla `role == "human"` — czysty artefakt
   budowania pod TUI. Agent, który chce wiedzieć „kto tu jest, kto co robi,
   kto jest online", musi składać stan z ramek `status` rozsianych po
   backlogu — a jego okno kontekstu zaczyna się od `last_context_seq`, więc
   starszych statusów NIE MA JAK zobaczyć. Ból z dyskusji o rozjazdach:
   dwóch workerów bierze to samo, bo żaden nie widzi drugiego.
2. **Preambuła wake'a nie zawiera boardu.** Node po fixie B3 robi świeży
   hello przy każdym wake'u (reconnect-on-wake) — serwer MA aktualny roster
   w ręku dokładnie w tym momencie, ale go agentowi nie podaje (patrz ból 1).
   Budzony agent zaczyna od zgadywania stanu świata.
3. **Kolizja deklaracji nie ma nazwanego arbitra.** Rules mówią „nie planuj
   drugi raz" i „sprawdź czy nikt inny tego nie robi", ale nie mówią JAK
   rozstrzygnąć remis, gdy dwóch zadeklaruje równocześnie. Fizyka huba już
   to umie: log jest totalnie uporządkowany po `seq` — niższy seq wygrywa,
   obiektywnie i bez głosowania. Trzeba to zapisać, nie zakodować.

Świadomie POZA planem (bramka): claim/lease/lock na boardzie (to scheduler
tylnymi drzwiami — seq-wins wystarcza), auto-status z node'a (decyzja za
agenta), push boardu do śpiących agentów (koszt tokenów), jakakolwiek
zmiana formatu ramek.

---

### Task 1: Roster + board w hello dla każdego uwierzytelnionego

**Files:**
- Modify: `chat/server.py:552-556` (usunięcie gate'a `role == "human"`)
- Test: `tests/test_server_integration.py`

**Interfaces:**
- Consumes: `self._participants_snapshot()` (`chat/server.py:309`) —
  lista `{nick, role, groups, connected, status}`.
- Produces: odpowiedź hello (`ok` i `resync_required`) zawiera
  `participants: [...]` dla KAŻDEGO uwierzytelnionego uczestnika.
  Task 2 czyta `reply["participants"]` w nodzie.

- [ ] **Step 1: Failing test**

Do `tests/test_server_integration.py` (wzorzec pliku: sync test + `srv` +
`hello`):

```python
def test_agent_hello_receives_participants_snapshot(srv):
    # Agent-first (B4): roster+board w hello to nie przywilej TUI.
    # Agent bez tego jest slepy na "kto tu jest i kto co robi" —
    # starsze ramki status sa PRZED jego oknem kontekstu.
    async def run(server):
        beta, reply = await hello("beta", "tb")
        parts = {p["nick"]: p for p in reply["participants"]}
        assert set(parts) == set(TOKENS)
        assert parts["beta"]["connected"] is True
        assert "status" in parts["beta"] and "groups" in parts["beta"]
        await beta.close()
    srv(run)
```

- [ ] **Step 2: Run — FAIL** (`KeyError: 'participants'`)

Run: `uv run --quiet --with pytest --with websockets python -m pytest tests/test_server_integration.py -k agent_hello_receives -q`

- [ ] **Step 3: Implementacja**

`chat/server.py:552-556` — usuń warunek roli (komentarz zostaje przy
prawdzie):

```python
            # (t2 review + B4 agent-first) roster musi byc cursor-coherent
            # i JAWNY dla kazdego uczestnika: czlowiek renderuje z niego TUI,
            # agent czyta board ("kto tu jest, kto co robi") — starsze ramki
            # status leza przed oknem kontekstu agenta, wiec snapshot w hello
            # to jedyne zrodlo pelnego stanu. Live push do agentow pozostaje
            # wylacznie wzmiankowy — to jest odpowiedz na hello, nie budzenie.
            extra["participants"] = self._participants_snapshot()
```

(Blok `if role == "human":` znika; `extra` budowane bezwarunkowo.)

- [ ] **Step 4: Testy — nowy PASS + cała suita** (istniejące testy humana
  na `participants` przechodzą bez zmian — to rozszerzenie, nie zmiana)

Run: `uv run --quiet --with pytest --with websockets --with textual python -m pytest tests/ -q`
Expected: 293 passed

- [ ] **Step 5: Commit**

```bash
git add chat/server.py tests/test_server_integration.py
git commit -m "feat(hello): roster+board dla kazdego uwierzytelnionego — agent nie jest klientem drugiej kategorii"
```

---

### Task 2: Board w preambule wake'a

**Files:**
- Modify: `agentmachi/node.py:52-58` (WAKE_PREAMBLE), `agentmachi/node.py:250-252`
  (budowa promptu) oraz `_one_connection` (przekazanie participants z hello)
- Test: `tests/test_node.py`

**Interfaces:**
- Consumes: `reply["participants"]` z hello (Task 1).
- Produces: prompt wake'a = PREAMBUŁA (nick, grupy, rules) + sekcja BOARD
  (jedna linia JSON per uczestnik, stan z chwili wake'a) + rozmowa.
  Format sekcji: linia `BOARD (stan z chwili obudzenia):` po rules,
  potem `{"nick": ..., "role": ..., "groups": [...], "connected": ...,
  "status": ...}` per uczestnik, potem pusta linia i rozmowa.

- [ ] **Step 1: Failing test**

Do `tests/test_node.py` (rozszerzenie istniejącego e2e — wzorzec
`RecordingRuntime` zapisuje prompt):

```python
def test_wake_prompt_contains_fresh_board(tmp_path, srv):
    # Agent-first (B4): budzony agent widzi board z chwili obudzenia
    # (reconnect-on-wake => hello => participants sa swieze za darmo).
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
                                     "task_id": "C"}))
        await asyncio.sleep(0.2)
        emil, _ = await hello("emil", "te", role="human")
        await emil.send(json.dumps({"type": "chat", "from": "emil",
                                    "ts": 0.0, "text": "@beta co robi gamma?"}))
        await _wait_for(lambda: prompts.exists())
        text = prompts.read_text()
        assert "BOARD (stan z chwili obudzenia):" in text
        board_part = text.split("BOARD", 1)[1]
        assert '"gamma"' in board_part and '"working"' in board_part
        node.cancel(); await emil.close(); await gamma.close()
    srv(run)
```

- [ ] **Step 2: Run — FAIL** (brak "BOARD" w prompcie)

Run: `uv run --quiet --with pytest --with websockets python -m pytest tests/test_node.py -k fresh_board -q`

- [ ] **Step 3: Implementacja**

`agentmachi/node.py` — WAKE_PREAMBLE dostaje sloty na board:

```python
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
```

`_one_connection`: po hello wyciągnij `participants = reply.get("participants", [])`
i przekaż do `_handle_wake` (parametr obok `rules`). Budowa promptu
(`node.py:250-252`):

```python
    board = "\n".join(json.dumps(p, ensure_ascii=False)
                      for p in participants) or "(pusty)"
    prompt = WAKE_PREAMBLE.format(nick=nick, groups=",".join(sorted(groups)),
                                  rules=rules or "(brak)", board=board) \
        + "\n".join(json.dumps(f, ensure_ascii=False) for f in context)
```

- [ ] **Step 4: Testy — nowy PASS + istniejące e2e node'a bez regresji + cała suita**

Run: `uv run --quiet --with pytest --with websockets --with textual python -m pytest tests/ -q`
Expected: 294 passed (uwaga: istniejące asercje na treść promptu mogą
wymagać dopasowania do nowego szablonu — dopasuj asercje, NIE szablon)

- [ ] **Step 5: Commit**

```bash
git add agentmachi/node.py tests/test_node.py
git commit -m "feat(node): swiezy board w preambule kazdego wake'a — budzony agent widzi stan swiata"
```

---

### Task 3: Konwencja seq-wins — arbiter kolizji zapisany w rules

**Files:**
- Modify: `agentmachi/cli.py` (DEFAULT_RULES — punkt 9)
- Modify: `AGENTS.md` (nota o arbitrze w sekcji o koordynacji)
- Modify: `~/.agentmachi/dogfood/data/rules.md` na żywym hubie (operator —
  krok wykonywany ręcznie przy dogfoodzie, NIE przez implementera)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: DEFAULT_RULES z taska 5 B3 (8 punktów).
- Produces: rules v1.1 z punktem 9; preambuła node'a już cytuje regułę
  (Task 2 — zdanie „przy kolizji deklaracji wygrywa nizszy seq").

- [ ] **Step 1: Failing test**

Do `tests/test_cli.py`:

```python
def test_rules_v11_have_seq_wins_arbiter(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTMACHI_HOME", str(tmp_path))
    cli.ensure_hub("h", 8899)
    rules = (tmp_path / "h" / "data" / "rules.md").read_text()
    assert "wygrywa deklaracja z nizszym seq" in rules
```

- [ ] **Step 2: Run — FAIL**

Run: `uv run --quiet --with pytest --with websockets python -m pytest tests/test_cli.py -k seq_wins -q`

- [ ] **Step 3: Implementacja**

`agentmachi/cli.py` — do DEFAULT_RULES dopisz punkt 9 (verbatim):

```
9. Robote bierzesz przez deklaracje na kanale ("biore X"). Przy kolizji
   wygrywa deklaracja z nizszym seq w logu huba — przegrany wycofuje sie
   bez dyskusji. Log jest jedynym arbitrem; nie ma glosowan.
```

`AGENTS.md` — w sekcji o koordynacji (obok kanonu statusów) dopisz akapit:

```markdown
## Arbiter kolizji: seq

Kolizje deklaracji ("obaj wzielismy X") rozstrzyga totalny porzadek logu:
wygrywa deklaracja z nizszym `seq` — pole nadaje wylacznie serwer, wiec
werdykt jest obiektywny i sprawdzalny w backlogu przez kazdego. To jest
mechanizm huba istniejacy od B1 (log + seq), nazwany jako konwencja:
zero locków, zero glosowan, zero schedulera.
```

- [ ] **Step 4: Testy — PASS + cała suita** (sprawdź, czy test rules v1
  z taska 5 B3 nie asertuje dokładnej liczby punktów — jeśli tak, dopasuj)

Run: `uv run --quiet --with pytest --with websockets --with textual python -m pytest tests/ -q`
Expected: 295 passed

- [ ] **Step 5: Commit**

```bash
git add agentmachi/cli.py AGENTS.md tests/test_cli.py
git commit -m "docs(rules): seq-wins jako arbiter kolizji deklaracji — fizyka logu zamiast glosowan"
```

---

## Krok operatora po wdrożeniu (poza taskami — dogfood)

1. Restart huba dogfood (`agentmachi serve` czyta kod przy starcie):
   stary proces STOP → `python3 -m agentmachi.cli serve --name dogfood`.
2. Podmień rules na żywym hubie: dopisz punkt 9 do
   `~/.agentmachi/dogfood/data/rules.md` (plik edytuje human — rules.md
   jest czytany przy każdym hello, restart nie jest potrzebny do rules).
3. Test tezy Emila: JEDNO zadanie dla `$workers` bez instrukcji podziału —
   worker1 (VPS) i worker2 dzielą się robotą sami: deklaracje na kanale,
   seq-wins przy kolizji, board mówi kto co robi, human tylko patrzy w TUI.

## Kolejność wykonania

```
1  feat(hello): participants dla kazdego     ← odblokowuje 2
2  feat(node): board w preambule wake'a
3  docs(rules): seq-wins                     ← niezalezny, ale preambula z 2 juz go cytuje
```

## Stan realizacji (aktualizowany na bieżąco)

- [x] Task 1 — participants w hello dla agentów (3b69d96; review clean)
- [x] Task 2 — board w preambule wake'a (48536a7 + fix testu bf4ace1:
      asercja świeżości scope'owana po empirycznym dowodzie tautologii)
- [x] Task 3 — rules v1.1: seq-wins (a3799fb; review clean; 295 testów)
- [ ] Krok operatora: restart huba dogfood + rules na żywo + test tezy
      (rules dopisane, restart w toku; test tezy = zadanie od Emila)
