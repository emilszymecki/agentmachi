# Plan wykonawczy: „obora → łąka" — wycięcie schedulera i neutralizacja

> **For agentic workers:** REQUIRED SUB-SKILL: użyj `superpowers:subagent-driven-development`
> (zalecane) albo `superpowers:executing-plans`, żeby wykonać ten plan task-po-tasku.
> Kroki mają checkboxy (`- [ ]`) do śledzenia. Każdy task kończy się zieloną suitą.

**Goal:** Doprowadzić kod agentmachi do zgodności z konstytucją „łąka, nie obora"
([2026-07-24-konstytucja-laka-nie-obora.md](2026-07-24-konstytucja-laka-nie-obora.md)):
usunąć scheduler (decyzje organizacyjne za agentów), zostawić wyłącznie fizykę huba,
a board uczynić w pełni pasywną mapą deklaracji.

**Architecture:** Hub (`chat/server.py`) traci CAŁĄ maszynerię tasków (kolejka, oferty,
leasy, expiry, round-robin) i side-effect `status=idle`. Zostaje transport + trwały log +
seq/resume + presence + pasywny board. Limiter node'a (`agentmachi/node.py`) zostaje jako
bezpiecznik, tylko konfigurowalny. Docs (rules/AGENTS.md) tracą założenie jednego ustroju.

**Tech Stack:** Python 3.11+, asyncio, websockets, textual (TUI). Bez nowych zależności.

## Global Constraints

- **Python floor:** 3.11 (z `pyproject.toml`). Nie podnosić.
- **Suita zielona po KAŻDYM tasku:** `uv run --quiet --with pytest --with websockets --with textual python -m pytest tests/ -q`. Zielona suita jest warunkiem zamknięcia taska, nie celem końcowym.
- **NIE usuwać fizyki** (Etap 4 konstytucji — „prawa świata"): trwały log, `seq`, resume po reconnect, pamięć kanału (kompakcja/snapshot rozmowy), ochrona split-brain (takeover/generation), tożsamość, powiązanie nicka z adresem, zdalny WebSocket, node budzący runtime, `session_id`, timeout procesu, ochrona sekretów, kick, izolacja workspace. Refactor dotyka tylko schedulera i status-side-effectu.
- **Inwarianty kodu (CLAUDE.md):** pola autorytatywne nadaje serwer (`seq`/`generation`/`groups`/`from`/`role`/`target`); trwałość przed publikacją (zapis na dysk → dopiero broadcast); zero zegara w logice (czas jako argument `now`).
- **PUŁAPKA — nie ruszać `activation_id` po stronie klienta:** `chat/client_session.py`, `tui.py`, `send.py` używają `activation_id` jako **generycznego dedupu wybudzeń** (wzmianki, chat), NIE tylko tasków. Znika wyłącznie **serwerowa produkcja** `activation_id` w `task_offer` (`chat/server.py:1198-1201`).
- **Właściwy serwer to `chat/server.py`.** Root `server.py` (37 linii) to legacy „głupia rura" bez związku ze schedulerem — nie dotykać w tym planie.
- **Numery linii są orientacyjne** (`~s.py:916`): usuwanie przesuwa numeracja, więc kotwicz się po NAZWACH symboli; linie tylko naprowadzają.

**Skróty ścieżek:** `s.py` = `chat/server.py`; `t.py` = `chat/tasks.py`; `n.py` = `agentmachi/node.py`; `cli.py` = `agentmachi/cli.py`; `proto.py` = `chat/protocol.py`.

---

## FAZA A — wycięcie schedulera
Commit docelowy: `refactor(core): remove legacy task scheduler`
Kryterium fazy (z konstytucji): **usunięcie całego systemu tasków nie zmienia
podstawowego scenariusza współpracy agentów** (hub startuje, agent wchodzi, rozmawia,
deklaruje status, znika i wraca z resume — wszystko działa).

### Task A1: Status pasywny — rozpleć side-effect status↔scheduler

To najważniejszy i najbezpieczniejszy pierwszy krok: izoluje presence od schedulera,
realizuje wprost kryterium konstytucji „status nie wykonuje żadnej akcji".

**Files:**
- Modify: `chat/server.py` — handler `status` (`~901-926`), `self.idle` (`~160`), disconnect cleanup (`~859-863`)
- Test: `tests/test_server_integration.py` — `test_status_tracked_in_snapshot_and_idle_sync` (`~2458`)

**Interfaces:**
- Produkuje: handler `status` po zmianie robi wyłącznie: walidacja uprawnień (`~903-910`) → `_append(frame)` (persist, `~912`) → zapis `self.status[target]` (`~914-915`) → broadcast do ludzi (`~923-926`). Zero `self.idle`, zero `_trigger_offer`.

- [ ] **Step 1: Zaktualizuj test — status=idle NIE wyzwala oferty**

W `test_status_tracked_in_snapshot_and_idle_sync` usuń asercje o `self.idle`/ofertach.
Zostaw asercję, że `status=idle` trafia do `self.status`, snapshotu i boardu. Dodaj:
```python
# status=idle jest CZYSTYM faktem na boardzie — zero side-effectu schedulera
srv = ChatServer(...); await srv.start()
# ... hello agenta 'w1', potem status idle
assert srv.status["w1"]["state"] == "idle"
assert not hasattr(srv, "idle") or "w1" not in getattr(srv, "idle", [])
```

- [ ] **Step 2: Uruchom test — ma paść na starym side-effekcie**

Run: `uv run --quiet --with pytest --with websockets python -m pytest tests/test_server_integration.py::test_status_tracked_in_snapshot_and_idle_sync -v`
Expected: FAIL (stary kod dopisuje do `self.idle` / woła `_trigger_offer`).

- [ ] **Step 3: Usuń side-effect z handlera status**

W `chat/server.py` w handlerze `status` (`~916-922`) usuń cały blok:
```python
if frame.get("state") == "idle":
    if target == nick and nick not in self.idle:
        self.idle.append(nick)
        self._trigger_offer()
elif target in self.idle:
    self.idle.remove(target)
```
Zostaw resztę handlera bez zmian (walidacja, `_append`, `self.status[...]`, broadcast do ludzi).
W disconnect cleanup (`~859-863`) usuń zdejmowanie nicka z `self.idle` (zostaw `presence connected=False`).

- [ ] **Step 4: Uruchom test — PASS**

Run: `uv run --quiet --with pytest --with websockets python -m pytest tests/test_server_integration.py::test_status_tracked_in_snapshot_and_idle_sync -v`
Expected: PASS.

- [ ] **Step 5: Pełna suita — zielona (offer machinery jeszcze istnieje, ale nikt jej nie woła)**

Run: `uv run --quiet --with pytest --with websockets --with textual python -m pytest tests/ -q`
Expected: PASS (testy `test_offer_*` które wołały offer przez status=idle mogą wymagać przełączenia na bezpośrednie `task_new` — jeśli padają, przenieś ich trigger; nie usuwaj ich jeszcze, to Task A2).

- [ ] **Step 6: Commit**

```bash
git add chat/server.py tests/test_server_integration.py
git commit -m "refactor(status): status=idle to czysty fakt na boardzie, bez oferty"
```

### Task A2: Usuń offer + expiry machinery

**Files:**
- Modify: `chat/server.py` — offer: `_offer_loop` (`~1270-1311`), `_offer_event` (`~1181-1216`), `_offer_activation_id` (`~1178-1179`), `_resolve_offer` (`~1237-1257`), `_drop_offers_for_task` (`~1225-1235`), `_pending_offer_keys_for` (`~1218-1223`), `_trigger_offer` (`~1259-1261`), `_requeue_idle_if_connected` (`~1263-1268`), `_offer_cache`/`_offering`/`self.idle` (init `~160-166`), `_restore_offers`/`_dump_offers` (`~238-247`), `offer_timeout` (`~134,142`); expiry: `_expiry_loop` (`~331-342`), `_reap_expired` (`~344-367`), start hook (`~258`), stop cancel (`~261-269`), `lease_ttl`/`wip_limit` params (`~133`)
- Modify: `chat/server.py` — snapshot (`~289-305`) i restore (`~144-165`): usuń klucz `offers`; `_replay_events` (`~187-234`): usuń branche `task_offer`/`offer_resolved`/`task_expired_batch`
- Test: `tests/test_server_integration.py` — usuń rodzinę `test_offer_*`, `test_*_offer_*`, `test_reap_expired_*`, `test_expiry_*`, `test_activation_id_retry_identical_new_offer_different` (`~388`)

**Interfaces:**
- Produkuje: `ChatServer` bez `self.idle`, bez pętli ofert i expiry; `snapshot()`/`resync` bez klucza `offers`; `start()`/`stop()` bez `_expiry_task`/`_offering`.

- [ ] **Step 1: Usuń testy ofert/expiry**

Skasuj z `tests/test_server_integration.py` funkcje: `test_offer_*`, `test_*_offer_*`, `test_expiry_*`, `test_reap_expired_batch_append_failure_no_partial_log`, `test_activation_id_retry_identical_new_offer_different`. (Zachowaj `test_restart_restores_queue_and_registry_after_snapshot` — przejdzie do Task A3, bo dotyczy queue+registry.)

- [ ] **Step 2: Usuń kod offer + expiry z `chat/server.py`**

Usuń metody i pola wymienione w **Files** powyżej. W `start()` usuń `self._expiry_task = asyncio.ensure_future(self._expiry_loop())`. W `stop()` usuń cancel `_offering`/`_expiry_task`. W `snapshot()` usuń `"offers": self._dump_offers()`. W `__init__` usuń restore `offers`/`_offer_cache`. W `_replay_events` usuń branche `task_offer`/`offer_resolved`/`task_expired_batch`. Z konstruktora usuń parametry `offer_timeout`, `lease_ttl`, `wip_limit` (przejdą też przez TaskQueue w A3).

- [ ] **Step 3: Pełna suita — zielona**

Run: `uv run --quiet --with pytest --with websockets --with textual python -m pytest tests/ -q`
Expected: PASS. Jeśli jakiś test snapshotu porównuje dokładny kształt state dict z `offers` — zaktualizuj oczekiwany kształt (bez `offers`).

- [ ] **Step 4: Weryfikacja fizyki na żywym hubie (efemeryczny port)**

Odpal test integracyjny startu huba + hello + status + snapshot/restart. Potwierdź, że resume po restarcie działa BEZ queue/offers (kursor, registry, status wracają).

- [ ] **Step 5: Commit**

```bash
git add chat/server.py tests/test_server_integration.py
git commit -m "refactor(core): usun oferty, leasy, expiry i round-robin z huba"
```

### Task A3: Usuń task handlery, `chat/tasks.py`, queue ze snapshotu i protokołu

**Files:**
- Delete: `chat/tasks.py` (cały, 390 linii — samodzielny automat, zero importów projektu)
- Delete: `tests/test_tasks.py` (cały — 39 funkcji `TaskQueue`)
- Modify: `chat/server.py` — import `chat.tasks` (`~64`); `_TASK_REQUIRED_FIELDS` (`~115-123`), `_TASK_STATE_EVENTS` (`~125-129`), `_TASK_OP` (`~1050-1053`); handlery `_on_task_frame` (`~1105-1175`), `_on_heartbeat` (`~1028-1048`), `_apply_task_op` (`~1055-1078`), `_peek_cached` (`~1080-1103`); branche task_*/heartbeat w `_on_frame` (`~927-934`); `self.queue`/restore (`~147-149`), snapshot `"queue"` (`~295-298`), resync `"queue"` (`~781-783`), `_replay_events` queue branche (`~214-234`)
- Modify: `chat/protocol.py` — inbound task_* (`~13-15`), outbound task_*/offer (`~18-19`), walidacja task_* (`~42-47`, `~158-161`), walidacja `heartbeat` (`~132-135`)
- Test: `tests/test_server_integration.py` — task-owe funkcje (`test_task_flow_*`, `test_task_approve_*`, `test_task_unblock_*`, `test_heartbeat_wire_*`, `test_replay_*`, `test_restart_restores_queue_*`); `tests/test_protocol.py` — funkcje task_*/heartbeat framing

**Interfaces:**
- Produkuje: `_on_frame` bez branchy task_*/heartbeat; `ChatServer` bez `self.queue`; snapshot/resync state dict = `{registry, status}` (bez `queue`, bez `offers`); `protocol` zna tylko ramki fizyki (hello, chat, status, membership_set, kick, ...).

- [ ] **Step 1: Usuń pliki tasków i ich testy**

```bash
git rm chat/tasks.py tests/test_tasks.py
```

- [ ] **Step 2: Usuń task-owe testy integracyjne i protokołowe**

Skasuj z `tests/test_server_integration.py` funkcje task/heartbeat/replay/restart-queue (lista w **Files**). Z `tests/test_protocol.py` usuń funkcje walidujące framing task_*/heartbeat.

- [ ] **Step 3: Wytnij handlery i queue z `chat/server.py`**

Usuń import `chat.tasks`, stałe `_TASK_*`, `_TASK_OP`, metody `_on_task_frame`/`_on_heartbeat`/`_apply_task_op`/`_peek_cached`, branche task_*/heartbeat z `_on_frame`, `self.queue`+restore, klucz `"queue"` ze `snapshot()` i `resync_required`, branche queue w `_replay_events`.

- [ ] **Step 4: Wytnij framing z `chat/protocol.py`**

Usuń zbiory typów task_*/outbound-offer, walidację task_* i `heartbeat`.

- [ ] **Step 5: Pełna suita — zielona**

Run: `uv run --quiet --with pytest --with websockets --with textual python -m pytest tests/ -q`
Expected: PASS. Zaktualizuj testy snapshotu porównujące kształt state (teraz `{registry, status}`).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(core): usun TaskQueue, handlery task_* i framing kolejki"
```

### Task A4: Usuń klienta heartbeat/task (send.py, cli.py)

**Files:**
- Modify: `send.py` — `heartbeat_loop` (`~385-408`), `_await_heartbeat_ok` (`~350-362`), `_check_heartbeat_interval` (`~341-348`); w `oneshot_frame` (`~364-382`) zostaje wysyłka `status` (fizyka board), znika wysyłka task_*
- Modify: `agentmachi/cli.py` — `cmd_heartbeat` (`~686-690`), subparser `heartbeat` (`~801-806`); subparser `frame` (`~794-799`) zostaje dla `status`
- Test: `tests/test_send.py` — funkcje heartbeat/task; `tests/test_cli.py` i `tests/test_node.py` — pojedyncze wzmianki `heartbeat` w help

**Interfaces:**
- Produkuje: CLI bez podkomendy `heartbeat`; `send.py` bez pętli heartbeat; `frame`/`send` nadal wysyłają `status` i chat.

- [ ] **Step 1: Usuń testy klienta heartbeat/task**

Z `tests/test_send.py` usuń funkcje heartbeat/task. Z `tests/test_cli.py`/`tests/test_node.py` usuń asercje o podkomendzie `heartbeat` (jeśli sprawdzają help).

- [ ] **Step 2: Usuń kod z send.py i cli.py**

Usuń `heartbeat_loop`/`_await_heartbeat_ok`/`_check_heartbeat_interval` z `send.py`; `cmd_heartbeat` i subparser `heartbeat` z `cli.py`. Zostaw `oneshot_frame`/`frame` dla `status`.

- [ ] **Step 3: Pełna suita — zielona**

Run: `uv run --quiet --with pytest --with websockets --with textual python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 4: Weryfikacja na żywym hubie — cały scenariusz**

Odpal hub na efemerycznym porcie; agent wchodzi (`listen`), wysyła `chat` z wzmianką, ustawia `status` (`frame`), znika i wraca (resume z kursora). Potwierdź, że wszystko działa BEZ jakiejkolwiek ramki task_*/heartbeat. To realizuje kryterium FAZY A.

- [ ] **Step 5: Commit**

```bash
git add send.py agentmachi/cli.py tests/
git commit -m "refactor(client): usun heartbeat i wysylke task_* z klienta i CLI"
```

---

## FAZA B — neutralny board
Commit docelowy: `refactor(status): make board fully passive`

### Task B1: Dodaj pole `subject` do wpisu status

Board ma być prostą mapą deklaracji: `{nick, state, subject, note}`. `subject` dziś nie
istnieje; `note` już jest. Maszyny stanów i expiry NIE dodajemy (konstytucja: nazwy stanów
to konwencja czytelności; board nie wygasza wpisów).

**Files:**
- Modify: `chat/protocol.py` — walidacja `status` (`~119-131`): dopuść opcjonalne `subject` (niepusty str, jak `note`)
- Modify: `chat/server.py` — handler `status` (`~914-915`): dołóż `subject` do zapisywanych kluczy; `_replay_events` status (`~199-201`): to samo; `_participants_snapshot` (`~392-396`): przenieś `subject` (i `note`) z `self.status` na poziom wpisu uczestnika, żeby board był płaską mapą
- Test: `tests/test_server_integration.py` — dodaj test `test_status_subject_on_board`

**Interfaces:**
- Produkuje: ramka `status` przyjmuje `{state, subject?, note?, target?}`; `_participants_snapshot` zwraca wpis z `subject`/`note` widocznymi na boardzie.

- [ ] **Step 1: Napisz failing test**

```python
def test_status_subject_on_board():
    # subject i note wchodza na board jako plaska mapa deklaracji
    async def scenario():
        srv = ChatServer(data_dir=..., tokens={"w1": {...}}, port=port)
        await srv.start()
        try:
            # hello w1, potem status z subject
            # frame: {"type":"status","state":"working","subject":"testy A3","note":"czekam na kontrakt"}
            board = {p["nick"]: p for p in srv._participants_snapshot()}
            assert board["w1"]["status"]["subject"] == "testy A3"
        finally:
            await srv.stop()
    asyncio.run(scenario())
```

- [ ] **Step 2: Uruchom — FAIL (subject odrzucany/gubiony)**

Run: `uv run --quiet --with pytest --with websockets python -m pytest tests/test_server_integration.py::test_status_subject_on_board -v`
Expected: FAIL.

- [ ] **Step 3: Dopuść i utrwalaj `subject`**

W `proto.py` walidacji `status` dodaj `subject` obok `note`. W `s.py` handlerze status i w `_replay_events` dodaj `"subject"` do zapisywanych kluczy: `{k: frame[k] for k in ("state","subject","note") if k in frame}` (usuwając martwe `task_id` po Fazie A).

- [ ] **Step 4: Uruchom — PASS**

Run: `uv run --quiet --with pytest --with websockets python -m pytest tests/test_server_integration.py::test_status_subject_on_board -v`
Expected: PASS. Potem pełna suita.

- [ ] **Step 5: Commit**

```bash
git add chat/protocol.py chat/server.py tests/test_server_integration.py
git commit -m "refactor(status): board niesie subject/note jako plaska mapa deklaracji"
```

---

## FAZA C — neutralizacja docs
Commit docelowy: `docs(agent-first): neutralize assignment and organization assumptions`

### Task C1: Przepisz `DEFAULT_RULES` + `data/rules.md` template

Konstytucja: nie narzucać jednego ustroju. Rule 9 mówi tylko „bierzesz sam"; nowa wersja:
brać / delegować / uzgadniać jako równe opcje. Rule 3 zakłada orchestratora — uczynić
opcjonalnym.

**Files:**
- Modify: `agentmachi/cli.py` — `DEFAULT_RULES` (`~31-50`)
- Test: `tests/test_cli.py` — asercja treści rules (`~33`)

- [ ] **Step 1: Przepisz rule 9 (i 3)**

W `DEFAULT_RULES` zmień punkt 9 na neutralny:
```
9. Zanim ruszysz, zadeklaruj na kanale zakres, za ktory bierzesz odpowiedzialnosc —
   mozesz go WZIAC sam, przyjac DELEGACJE albo UZGODNIC podzial z innymi. Deklaracja
   jest po to, by agenci widzieli fakty i nie dublowali sie; przy kolizji wygrywa
   nizszy seq, przegrany sie wycofuje. Log jest arbitrem, nie glosowanie.
```
W punkcie 3 dopisz, że orchestrator jest ROLĄ, którą agenci mogą przyjąć — nie wymogiem systemu.

- [ ] **Step 2: Zaktualizuj `tests/test_cli.py`**

Podmień asercję sprawdzającą starą treść rule (`~33`) na fragment nowej (np. że rules zawiera słowo „DELEGACJE" albo „UZGODNIC").

- [ ] **Step 3: Suita — zielona**

Run: `uv run --quiet --with pytest --with websockets --with textual python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add agentmachi/cli.py tests/test_cli.py
git commit -m "docs(rules): deklaracja zamiast jednego ustroju (brac/delegowac/uzgadniac)"
```

### Task C2: Przepisz `AGENTS.md` i `CLAUDE.md` (usuń scheduler + neutralizuj branie roboty)

**Files:**
- Modify: `AGENTS.md` — sekcja „Czego się oczekuje" pkt 1 (`~25`); usuń całą sekcję „Stary scheduler — nie używaj" (`~117-125`)
- Modify: `CLAUDE.md` — sekcje o schedulerze i „bierzesz robotę sam" (analogiczne)

- [ ] **Step 1: Przepisz „Bierzesz robotę sam"**

W `AGENTS.md` pkt 1 zmień na: odpowiedzialność deklarujesz przed pracą; możesz ją wziąć, przyjąć delegację albo uzgodnić podział — system nie rozstrzyga który model jest lepszy. Zostaw zasadę deklaracji-przed-pracą (to fizyka anty-duplikacji, nie ustrój).

- [ ] **Step 2: Usuń sekcję „Stary scheduler"**

Scheduler już nie istnieje (Faza A) — sekcja ostrzegająca przed nim jest martwa. Skasuj `AGENTS.md:117-125` i analogiczny akapit w `CLAUDE.md`.

- [ ] **Step 3: Dodaj wskaźnik do konstytucji**

W `AGENTS.md` i `CLAUDE.md` dodaj jedno zdanie: nadrzędna bramka projektu to konstytucja `docs/superpowers/plans/2026-07-24-konstytucja-laka-nie-obora.md` („płot, nie pastuch").

- [ ] **Step 4: Commit (docs — bez testów)**

```bash
git add AGENTS.md CLAUDE.md
git commit -m "docs(agent-first): usun scheduler, neutralizuj model organizacji"
```

---

## FAZA D — limiter jako bezpiecznik
Commit docelowy: `feat(node): make wake safety limits configurable`

### Task D1: Wystaw limity jako env + zwolnij człowieka z capa godzinowego

Dwa cele konstytucji Etapu 5: (1) limiter konfigurowalny (env), (2) **wzmianka człowieka
nie jest blokowana zwykłym limitem** — dziś cap godzinowy dotyczy też człowieka (`n.py:102`).

**Files:**
- Modify: `agentmachi/cli.py` — defaulty flag (`~814-816`): czytaj z env
- Modify: `agentmachi/node.py` — `RateLimiter.check` (`~100-108`): zwolnij człowieka z capa; okno `3600.0` (`~101`, `~250`) jako pole/param
- Test: `tests/test_node.py` — testy limitera

**Interfaces:**
- Consumes: `os.environ` — `MAX_AGENT_WAKES_PER_HOUR`, `AGENT_WAKE_COOLDOWN`, `MAX_WAKE_DURATION`
- Produkuje: `RateLimiter.check(now, wake_times, sender_is_human)` — gdy `sender_is_human`, cap godzinowy NIE blokuje (circuit breaker tylko dla pętli agentów).

- [ ] **Step 1: Failing test — człowiek nie jest capowany godzinowo**

```python
def test_human_mention_not_capped_by_hourly_limit():
    lim = RateLimiter(max_wakes_per_hour=2, cooldown_after_agent_wake=60.0)
    wakes = [0.0, 1.0]  # cap juz osiagniety
    # agent: zablokowany
    assert lim.check(2.0, wakes, sender_is_human=False) is not None
    # czlowiek: przechodzi mimo capa
    assert lim.check(2.0, wakes, sender_is_human=True) is None
```

- [ ] **Step 2: Uruchom — FAIL (dziś cap dotyczy wszystkich)**

Run: `uv run --quiet --with pytest python -m pytest tests/test_node.py::test_human_mention_not_capped_by_hourly_limit -v`
Expected: FAIL.

- [ ] **Step 3: Zwolnij człowieka z capa**

W `RateLimiter.check` (`n.py:102`) dodaj gate `if not sender_is_human`:
```python
recent = [t for t in wake_times if now - t < self._window]
if not sender_is_human and len(recent) >= self.max_wakes_per_hour:
    return min(recent) + self._window
```
Dodaj `self._window` (default 3600.0) w `__init__` i użyj też w prune (`~250` po stronie `_handle_wake` zostaje bez zmian — to append historii, nie blokada).

- [ ] **Step 4: Env-config w cli.py**

W `cli.py:814-816` podmień defaulty flag:
```python
p.add_argument("--max-wakes-per-hour", type=int,
               default=int(os.environ.get("MAX_AGENT_WAKES_PER_HOUR", "6")))
p.add_argument("--cooldown", type=float,
               default=float(os.environ.get("AGENT_WAKE_COOLDOWN", "60")))
p.add_argument("--max-wake-duration", type=float,
               default=float(os.environ.get("MAX_WAKE_DURATION", "1200")))
```

- [ ] **Step 5: Uruchom — PASS, potem pełna suita**

Run: `uv run --quiet --with pytest --with websockets --with textual python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add agentmachi/node.py agentmachi/cli.py tests/test_node.py
git commit -m "feat(node): limity wybudzania z env; wzmianka czlowieka poza capem godzinowym"
```

---

## FAZA E — dowód samoorganizacji
Commit docelowy: `test(dogfood): prove self-organization without scheduler or human routing`

### Task E1: Test scenariusza akceptacyjnego konstytucji

Konstytucja definiuje przebieg: Agent A deklaruje plan i prosi o pomoc do części C przez
CHAT (wzmianka), „orchestrator" (rola przyjęta przez agenta, nie mechanizm huba) deleguje
przez wiadomość, Agent B przyjmuje i raportuje — wszystko bez schedulera i bez routingu
przez człowieka. Ten test dowodzi, że hub UMOŻLIWIA przebieg, nie prowadząc go.

**Files:**
- Create: `tests/test_selforg_dogfood.py`

**Interfaces:**
- Consumes: `ChatServer` (bez schedulera), routing wzmianek, trwały log, presence, board.

- [ ] **Step 1: Napisz test przebiegu (bez task_*/offer)**

```python
def test_self_organization_flow_without_scheduler():
    """Agent A prosi o pomoc wzmianka; B przyjmuje i raportuje — czysty chat+status,
    zero ramek schedulera. Hub tylko routuje i utrwala."""
    async def scenario():
        srv = ChatServer(data_dir=..., tokens={
            "a": {..., "groups": ["workers"]}, "b": {..., "groups": ["workers"]}}, port=port)
        await srv.start()
        try:
            # a i b laczą sie (hello). a wysyla chat z @b (delegacja przez rozmowe).
            # b ustawia status working+subject "C". a widzi b na boardzie jako working/C.
            board = {p["nick"]: p for p in srv._participants_snapshot()}
            assert board["b"]["status"]["state"] == "working"
            assert board["b"]["status"]["subject"] == "C"
            # log zawiera wzmianke @b (trwalosc rozmowy)
            # brak jakiegokolwiek eventu task_*/offer w logu
            assert not hasattr(srv, "queue")
        finally:
            await srv.stop()
    asyncio.run(scenario())
```

- [ ] **Step 2: Uruchom — PASS (hub już to umożliwia po Fazach A–B)**

Run: `uv run --quiet --with pytest --with websockets python -m pytest tests/test_selforg_dogfood.py -v`
Expected: PASS.

- [ ] **Step 3: Pełna suita + żywy dogfood**

Run pełną suitę. Następnie odpal realny hub i przejdź scenariusz ręcznie na żywym kanale (dwóch agentów: deklaracja → delegacja wzmianką → wykonanie → raport), bez żadnej ramki schedulera. To domyka konstytucyjne kryterium.

- [ ] **Step 4: Commit**

```bash
git add tests/test_selforg_dogfood.py
git commit -m "test(dogfood): samoorganizacja bez schedulera i bez routingu przez czlowieka"
```

---

## Po planie

Po tych fazach: **zatrzymujemy rozwój feature'ów i uruchamiamy dogfood** (konstytucja).
Dalszy kod dodajemy dopiero po konkretnej, powtarzalnej porażce agentów, której nie
rozwiązali rozmową, rules, boardem i istniejącą fizyką — i tylko po przejściu bramki
5 pytań (Etap 6 konstytucji).

## Self-review (wykonane przy pisaniu planu)

- **Pokrycie konstytucji:** Etap 1 → Faza A; Etap 2 → Faza B; Etap 3 → Faza C; Etap 4
  (zachowanie fizyki) → Global Constraints („NIE usuwać fizyki") + weryfikacje na żywym
  hubie w A2/A4; Etap 5 → Faza D; Etap 6 (bramka) → sekcja „Po planie". 5 commitów z
  konstytucji rozwinięte 1:1 (A=scheduler, B=board, C=docs, D=limiter, E=test).
- **Kolejność commitów** zgodna z konstytucją; Faza A rozbita na 4 taski, bo cały scheduler
  w jednym commicie byłby nie do zreviewowania (splot z fizyką na 7 punktach — mapa w
  raporcie).
- **Pułapka activation_id** wpisana w Global Constraints i Task A2 (znika tylko produkcja
  serwerowa) — bez tego wycięcie zabiłoby dedup wzmianek.
- **Odchylenie kodu od konstytucji wykryte przy mapowaniu:** cap godzinowy limitera dziś
  dotyczy człowieka wbrew Etapowi 5 — naprawione w Task D1 (nie tylko env, ale i zwolnienie
  człowieka).
