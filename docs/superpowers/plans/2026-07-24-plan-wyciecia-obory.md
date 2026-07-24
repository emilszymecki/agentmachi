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
- Modify: `chat/server.py` — handler `status` (`~901-926`): usuń TYLKO blok side-effectu `state=idle` (dopisanie do `self.idle` + `_trigger_offer`). `self.idle` (`~160`) i disconnect cleanup (`~859-863`) **ZOSTAJĄ** — usuwa je A3 razem z machinery
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
Disconnect cleanup (`~859-863`) **ZOSTAJE nietknięty** — `57102e9` go celowo zachował; usuwa go A3 razem z `self.idle`. (Plan nie może kazać usuwać tego, co wykonane A1 zachowało.)

- [ ] **Step 4: Uruchom test — PASS**

Run: `uv run --quiet --with pytest --with websockets python -m pytest tests/test_server_integration.py::test_status_tracked_in_snapshot_and_idle_sync -v`
Expected: PASS.

- [ ] **Step 5: Pełna suita — zielona (offer machinery istnieje i ŻYJE — wołają ją `task_new` oraz expiry timer; usuwana atomowo w A3)**

Run: `uv run --quiet --with pytest --with websockets --with textual python -m pytest tests/ -q`
Expected: PASS (testy `test_offer_*` które wołały offer przez status=idle mogą wymagać przełączenia na bezpośrednie `task_new` — jeśli padają, przenieś ich trigger; nie usuwaj ich jeszcze, to Task A2).

- [ ] **Step 6: Commit**

```bash
git add chat/server.py tests/test_server_integration.py
git commit -m "refactor(status): status=idle to czysty fakt na boardzie, bez oferty"
```

> **BLOCKER1 fix (review codeksa 8868d9a):** oryginalny podział A2=machinery,
> A3=handlery był NIEbezpieczny — A2 usuwał `_trigger_offer`, które
> `_on_task_frame` (A3) nadal woła; commit „zielony przez skasowane testy" miał
> zepsuty runtime. Nowa kolejność: **WEJŚCIE → MACHINERY → QUEUE**. Każdy slice
> zostawia runtime SPÓJNY: usuwamy najpierw DROGĘ WEJŚCIA ramek, więc kod niżej
> staje się MARTWY (nikt go nie woła), a martwy kod nie crashuje. Kryterium
> „zielona suita" wzmacniamy o jawny **RUNTIME-SOUND CHECK**: żywy hub odrzuca
> task_* czysto. UWAGA — po A2 martwe jest tylko WEJŚCIE; `_trigger_offer` ma
> jeszcze caller (expiry timer) aż do A3, więc NIE oczekuj „braku callera".

> **Rewizja 2a (review codeksa `c5d5ee2`→`af83a0f`):** 6 cross-phase blockerów
> (replay-constant `_TASK_STATE_EVENTS`, expiry jako żywy caller `_trigger_offer`,
> konstruktor `lease_ttl`/`wip_limit`, `task_expired_batch` replay, acceptance bez
> `subject`, A1 disconnect-cleanup) — **wcięte bezpośrednio w Files/Steps A1-A4
> poniżej.** Reguła nadrzędna, z której wynikają wszystkie: **usuwaj kod dopiero,
> gdy nie ma już ani callera, ani serializacji (snapshot/replay), która go czyta.**

### Task A2 (WEJŚCIE): odetnij inbound task_*/heartbeat — klient, protokół, dispatcher

**Files:**
- Modify: `send.py` — `heartbeat_loop` (`~385-408`), `_await_heartbeat_ok` (`~350-362`), `_check_heartbeat_interval` (`~341-348`); w `oneshot_frame` (`~364-382`) zostaje `status`, znika task_*
- Modify: `agentmachi/cli.py` — `cmd_heartbeat` (`~686-690`), subparser `heartbeat` (`~801-806`); `frame`/`send` zostają dla `status`
- Modify: `chat/protocol.py` — inbound task_* (`~13-15`), outbound task_*/offer (`~18-19`), walidacja task_* (`~42-47`, `~158-161`), walidacja `heartbeat` (`~132-135`)
- Modify: `chat/server.py` — dispatcher branche task_*/heartbeat w `_on_frame` (`~927-934`); handlery `_on_task_frame`/`_on_heartbeat`/`_apply_task_op`/`_peek_cached`; stałe `_TASK_REQUIRED_FIELDS`/`_TASK_OP` (**NIE** `_TASK_STATE_EVENTS` — używa go `_replay_events` do A4; zmień nazwę na `_TASK_REPLAY_EVENTS`, usuń dopiero w A4)
- Test: `tests/test_send.py` (heartbeat/task), `tests/test_protocol.py` (task_*/heartbeat framing), `tests/test_server_integration.py` (`test_task_flow_*`, `test_task_approve_*`, `test_task_unblock_*`, `test_heartbeat_wire_*` — NIE offer, offer→A3), `tests/test_cli.py`/`test_node.py` (heartbeat w help)

**Interfaces:**
- Produkuje: klient/CLI bez task_*/heartbeat; protokół zna tylko fizykę (hello/chat/status/membership_set/kick); `_on_frame` bez branchy task_*/heartbeat. Machinery offer/expiry ISTNIEJE i **ŻYJE do A3** (expiry timer `_expiry_loop`→`_reap_expired`→`_trigger_offer` `~367` to caller); queue do A4. A2 odcina TYLKO wejście.

- [ ] **Step 1:** usuń klienta+CLI heartbeat/task (`send.py`, `cli.py`) + ich testy (`test_send.py`, `test_cli.py`, `test_node.py`)
- [ ] **Step 2:** usuń framing task_*/heartbeat z `chat/protocol.py` + funkcje w `test_protocol.py`
- [ ] **Step 3:** usuń inbound handlery + dispatcher branche + stałe `_TASK_REQUIRED_FIELDS`/`_TASK_OP` (`_TASK_STATE_EVENTS` **NIE** usuwaj — zmień nazwę na `_TASK_REPLAY_EVENTS`, replay używa go do A4) z `chat/server.py`; usuń task-owe testy integracyjne (task_flow/approve/unblock/heartbeat_wire — **NIE** offer)
- [ ] **Step 4:** pełna suita zielona (`uv run ... pytest tests/ -q`)
- [ ] **Step 5 — RUNTIME-SOUND CHECK:** (a) `_on_task_frame`/`_on_heartbeat` nie istnieją (inbound odcięte); `_trigger_offer` NADAL ma caller (expiry timer) — to OK, machinery żyje do A3, **NIE** oczekuj braku callera; (b) odpal hub na efemerycznym porcie, wyślij ramkę `task_new` → MUSI być czysto odrzucona (error/unknown type), nie crash; hello/chat/status oraz **restart/replay** (expiry+queue nadal żywe) działają
- [ ] **Step 6:** commit `refactor(core): odetnij inbound task_*/heartbeat (klient, protokol, dispatcher)`

### Task A3 (MACHINERY): usuń offer + expiry ATOMOWO (żywe po A2 — expiry to caller offera)

Po A2 expiry timer NADAL woła offer (`_expiry_loop`→`_reap_expired`→`_trigger_offer`). Ten slice usuwa expiry+offer ATOMOWO — caller (`_expiry_loop`/`_reap_expired`/start hook) i callee (`_trigger_offer`/`_offer_loop`) razem, żeby żaden krok nie zostawił wołania w pustkę.

**Files:**
- Modify: `chat/server.py` — offer: `_offer_loop`, `_offer_event`, `_offer_activation_id`, `_resolve_offer`, `_drop_offers_for_task`, `_pending_offer_keys_for`, `_trigger_offer`, `_requeue_idle_if_connected`, `self.idle`/`_offer_cache`/`_offering` (init `~160-166`), `_restore_offers`/`_dump_offers`, `offer_timeout` param; expiry: `_expiry_loop`, `_reap_expired`, start hook, stop cancel (caller `_reap_expired` + callee `_trigger_offer` giną RAZEM — atomowo); snapshot/restore klucz `offers`; `_replay_events` branche `task_offer`/`offer_resolved` (**NIE** `task_expired_batch` — queue-state, zostaje A4); disconnect `self.idle` cleanup (`~859-863`). **`lease_ttl`/`wip_limit` ZOSTAJĄ** — konstruktor `TaskQueue.restore`/`TaskQueue(...)` ich używa do A4
- Test: `tests/test_server_integration.py` — 7 offer-testów (przywrócone w A1-fix `12351f3`) + offer/reap testy aktywnego reapu (m.in. `test_reap_expired_batch_append_failure_no_partial_log`) giną tu z machinery. **ALE** `test_expiry_event_replays_result_based_no_conflict` testuje `task_expired_batch` REPLAY (queue-state, nie aktywny reap) — **ZOSTAJE do A4** razem z replayem

**Interfaces:**
- Produkuje: `ChatServer` bez `self.idle`/offer/expiry; `snapshot()`/`resync` bez `offers`; `start()`/`stop()` bez `_expiry_task`/`_offering`.

- [ ] **Step 1:** usuń offer + aktywny-reap testy (7 z A1-fix + `test_reap_expired_batch_append_failure_no_partial_log`). **Zachowaj** `test_expiry_event_replays_result_based_no_conflict` — testuje `task_expired_batch` replay, zejdzie dopiero w A4
- [ ] **Step 2:** usuń offer+expiry kod + `offers` ze snapshot/restore + replay branche `task_offer`/`offer_resolved` (**NIE** `task_expired_batch` — queue-state, zostaje do A4) + disconnect idle cleanup z `chat/server.py`
- [ ] **Step 3:** pełna suita zielona
- [ ] **Step 4 — RUNTIME-SOUND:** `grep -n "self.idle\|_trigger_offer\|_offer_\|_expiry" chat/server.py` → zero trafień; hub start/hello/status/snapshot-restart działa
- [ ] **Step 5:** commit `refactor(core): usun offer+expiry machinery atomowo (caller+callee razem)`

### Task A4 (QUEUE): usuń `TaskQueue` + queue ze snapshotu/replay

Queue nie jest wołana po A2 (handlery usunięte). Ten slice usuwa `TaskQueue` i jej serializację.

**Files:**
- Delete: `chat/tasks.py` (390 linii), `tests/test_tasks.py` (39 funkcji)
- Modify: `chat/server.py` — import `chat.tasks` (`~64`); `self.queue`/restore (`~147-149`); snapshot `"queue"` (`~295-298`); resync `"queue"` (`~781-783`); `_replay_events` queue branche + branch `task_expired_batch` (`~214-234`); `_TASK_REPLAY_EVENTS`; `lease_ttl`/`wip_limit` params (przeniesione z A3 — `TaskQueue` ich używał) — wszystkie giną RAZEM z queue
- Test: `tests/test_server_integration.py` — `test_replay_*`, `test_restart_restores_queue_*` (queue-specyficzne; zachowaj registry/status-only warianty restartu)

**Interfaces:**
- Produkuje: snapshot/resync state = `{registry, status}` (bez `queue`/`offers`); `ChatServer` bez `queue`.

- [ ] **Step 1:** `git rm chat/tasks.py tests/test_tasks.py`
- [ ] **Step 2:** usuń queue/replay/restart-queue testy integracyjne (zostaw registry/status restart)
- [ ] **Step 3:** usuń import + `self.queue` + snapshot/resync `"queue"` + replay branche z `chat/server.py`
- [ ] **Step 4:** pełna suita zielona; zaktualizuj testy snapshotu porównujące kształt state (teraz `{registry, status}`)
- [ ] **Step 5 — RUNTIME-SOUND + KRYTERIUM FAZY A:** hub start/hello/chat/status/resume BEZ queue; przejdź scenariusz współpracy (agent deklaruje status — `state`/`note`, **BEZ `subject`** — `subject` powstaje dopiero w Fazie B; drugi widzi go na boardzie) BEZ jakiejkolwiek ramki task_*/heartbeat
- [ ] **Step 6 — STAGING JAWNY (P1 codex, nie `git add -A`):** `git add chat/tasks.py tests/test_tasks.py chat/server.py tests/test_server_integration.py` → `git diff --cached --name-status` (potwierdź brak untracked logów/session z testów Windows) → commit `refactor(core): usun TaskQueue i serializacje kolejki`

---

## FAZA B — neutralny board
Commit docelowy: `refactor(status): make board fully passive`

### Task B1: Dodaj pole `subject` do wpisu status

Board ma być prostą mapą deklaracji: `{nick, state, subject, note}`. `subject` dziś nie
istnieje; `note` już jest. Maszyny stanów i expiry NIE dodajemy (konstytucja: nazwy stanów
to konwencja czytelności; board nie wygasza wpisów).

**Files:**
- Modify: `chat/protocol.py` — walidacja `status` (`~119-131`): dopuść opcjonalne `subject` (niepusty str, jak `note`)
- Modify: `chat/server.py` — handler `status` (`~914-915`): dołóż `subject` do zapisywanych kluczy; `_replay_events` status (`~199-201`): to samo. **BLOCKER2: `_participants_snapshot` (`~392-396`) NIE ruszaj** — `participant["status"]` zostaje OBIEKTEM, `subject` jest w nim ZAGNIEŻDŻONY (`status.subject`, obok `state`/`note`); tak już czytają board `chat/server.py` i `tui.py` (mniej regresji niż top-level, zgodne z testem `board[nick]["status"]["subject"]`)
- Modify: `tui.py` — jeśli renderuje board/status, uwzględnij `status.subject` (live presence czyta zagnieżdżony obiekt status)
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
- Modify: `README.md` — nota migracyjna (Step 1b): zmiana `DEFAULT_RULES` obejmuje NOWE
  huby; istniejące (np. dogfood) to ŚWIADOMY krok operatora, nie automat
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

- [ ] **Step 1b: Istniejące huby — migracja ŚWIADOMA, nie cicha (fix codex C1)**

`_ensure_layout` zapisuje `data/rules.md` TYLKO gdy plik nie istnieje — więc zmiana
`DEFAULT_RULES` dotyczy WYŁĄCZNIE nowych hubów. Istniejące huby (np. dogfood)
zachowają stare rules.md, i tak MA być: rules bywają ręcznie dostosowane per hub, a
konstytucja mówi, że decyzje o infrastrukturze należą do człowieka — **nie
nadpisujemy custom rules po cichu**. Migracja istniejącego huba to ŚWIADOMY krok
operatora, udokumentowany (README/howto), nie automat:

Wszystkie kroki przez **Python** — napędza huba, więc jest na każdym OS; `diff`/`cp`
NIE są cross-platform (w PowerShell `diff` to alias `Compare-Object`, nie unified diff).
Ścieżek NIE zgadujemy: `agentmachi.cli.hub_dir(<hub>)` jest autorytatywne i honoruje
`AGENTMACHI_HOME` — hardcoded `~/.agentmachi` czy `%USERPROFILE%\...` je ignoruje i myli
cmd.exe (`%USERPROFILE%`) z PowerShell (`$env:USERPROFILE`). Uruchamiaj z dowolnego
katalogu; nazwę huba podaj argumentem (`<hub>` = podmień na swoją):

1. **Wygeneruj nowy template** z `DEFAULT_RULES` do pliku roboczego w bieżącym katalogu
   (NIE w live data dir — nie zostawiamy śmieci przy hubie):
   ```bash
   python -c "from agentmachi.cli import DEFAULT_RULES; import pathlib; pathlib.Path('rules.new.md').write_text(DEFAULT_RULES, encoding='utf-8')"
   ```
2. **Preview** — unified diff żywego `rules.md` (ścieżka z `hub_dir`) vs nowego, na każdym OS:
   ```bash
   python -c "import sys,difflib; from agentmachi.cli import hub_dir; cur=hub_dir(sys.argv[1])/'data'/'rules.md'; a=cur.read_text(encoding='utf-8').splitlines(keepends=True); b=open('rules.new.md',encoding='utf-8').read().splitlines(keepends=True); sys.stdout.writelines(difflib.unified_diff(a,b,str(cur),'rules.new.md'))" <hub>
   ```
3. **Backup** — MUSI failować gdy cel istnieje (zero cichego overwrite: drugie uruchomienie
   nie może skasować jedynej kopii pre-migracyjnej), z jawną weryfikacją:
   ```bash
   python -c "import sys,shutil; from agentmachi.cli import hub_dir; src=hub_dir(sys.argv[1])/'data'/'rules.md'; dst=src.parent/'rules.md.bak'; sys.exit('ODMOWA: '+str(dst)+' juz istnieje — przenies/usun recznie') if dst.exists() else None; shutil.copyfile(src,dst); print('backup OK ->', dst)" <hub>
   ```
4. **Podmiana** — dwie drogi, w obu na końcu usuwamy temp:
   - masz własne dopiski → wedle preview zmerguj ręcznie nowe reguły do żywego `rules.md`,
     potem `rules.new.md` skasuj;
   - czysty template → skopiuj i posprzątaj jednym krokiem:
     ```bash
     python -c "import sys,shutil,pathlib; from agentmachi.cli import hub_dir; shutil.copyfile('rules.new.md', hub_dir(sys.argv[1])/'data'/'rules.md'); pathlib.Path('rules.new.md').unlink(); print('podmienione + rules.new.md usuniete')" <hub>
     ```

   Źródło: NIE ma osobnego pliku-template — `DEFAULT_RULES` w `agentmachi/cli.py` to JEDYNE
   źródło, z którego `_ensure_layout` pisze `data/rules.md` przy pierwszym layoutcie i tylko
   wtedy. „Nowy template" = nowa treść tej stałej.

Do planu Fazy C należy TYLKO ten udokumentowany krok + jawna nota migracyjna w `README.md`
(plik jest w Files i w staging Step 4) oraz komentarz przy `DEFAULT_RULES`, że zmiana
obejmuje nowe huby. Automatyczne nadpisanie ani helper `agentmachi rules --migrate`
NIE wchodzą teraz — to osobny feature za bramką dogfoodu (bramka: czy operatorzy
realnie tego potrzebują? na razie ręczny krok wystarcza — less is more).

- [ ] **Step 2: Zaktualizuj `tests/test_cli.py`**

Podmień asercję sprawdzającą starą treść rule (`~33`) na fragment nowej (np. że rules zawiera słowo „DELEGACJE" albo „UZGODNIC").

- [ ] **Step 3: Suita — zielona**

Run: `uv run --quiet --with pytest --with websockets --with textual python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add agentmachi/cli.py tests/test_cli.py README.md
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
Dodaj `self._window` (default 3600.0) w `__init__`; użyj go w `check()` ORAZ w prune
`wake_times` w `_handle_wake` (`~255`): `limiter._window` zamiast hardcoded `3600.0`, żeby
check i historia miały jedno źródło prawdy. Prune to append historii (nie blokada), ale
jego okno musi być spójne z oknem capa — dlatego też przez `limiter._window`.

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

- [ ] **Step 1: Napisz test przebiegu — ASERCJE, nie komentarze (fix codex E1)**

Test ma DOWODZIĆ routingu i braku schedulera, nie opisywać ich komentarzem. Używa
wzorca repo (`srv` fixture + `hello`/`recv` z `test_server_integration.py`):

```python
def test_self_organization_flow_without_scheduler(srv):
    """A deleguje do B wzmianka; B przyjmuje i raportuje status — czysty
    chat+status, zero ramek schedulera. Hub tylko routuje i utrwala.
    Tokeny z fixture TOKENS (alfa/beta/gamma/emil). Konstytucyjny kontrakt:
    wzmianka budzi live TYLKO adresata-agenta, a status to fakt boardu pchany
    live TYLKO do ludzi (agent go NIE dostaje — server.py:919-922)."""
    async def scenario(server):
        a, _ = await hello("alfa", "ta", groups=["workers"])
        b, _ = await hello("beta", "tb", groups=["workers"])
        g, _ = await hello("gamma", "tg", groups=["workers"])  # obecny, NIE wzmiankowany
        h, _ = await hello("emil", "te", role="human")          # obserwator-czlowiek (rola z configu)
        # A deleguje do B PRZEZ ROZMOWE (wzmianka @beta) — zero ramek schedulera
        await a.send(json.dumps({"type": "chat", "from": "alfa", "ts": 1.0,
                                 "text": "@beta wez czesc C"}))
        # DOWOD routingu wzmianki: B dostaje; czlowiek dostaje (chat leci do ludzi
        # zawsze, server.py:473); gamma (agent nie-wzmiankowany) NIE.
        got_b = await recv(b)
        assert got_b["type"] == "chat" and got_b["from"] == "alfa" and "@beta" in got_b["text"]
        assert (await recv(h))["text"] == "@beta wez czesc C"   # chat -> ludzie
        with pytest.raises(asyncio.TimeoutError):
            await recv(g, timeout=0.4)             # wzmianka budzi tylko adresata
        # B raportuje status working+subject (subject = pole projekcji po Fazie B, patrz B1)
        await b.send(json.dumps({"type": "status", "from": "beta", "ts": 2.0,
                                 "state": "working", "subject": "C"}))
        # DOWOD: status to fakt boardu pchany live TYLKO do ludzi.
        st = await recv(h)                          # czlowiek dostaje status...
        assert st["type"] == "status" and st["from"] == "beta" and st.get("subject") == "C"
        with pytest.raises(asyncio.TimeoutError):
            await recv(a, timeout=0.4)             # ...agent alfa NIE (status nie budzi agentow)
        # recv(h) statusu jest tez BARIERA sync: serwer przetworzyl status, board aktualny
        board = {p["nick"]: p for p in server._participants_snapshot()}
        assert board["beta"]["status"]["state"] == "working"
        assert board["beta"]["status"]["subject"] == "C"
        # DOWOD braku schedulera: realny skan logu, nie komentarz
        types = {e.get("type") for e in server.log.replay()}
        assert not (types & {"task_new", "task_offer", "task_claim",
                             "task_done", "heartbeat"})
        assert not hasattr(server, "queue")
    asyncio.run(srv(scenario))
```

- [ ] **Step 1b: Trwałość po restarcie — DOWÓD, nie założenie (fix codex E1)**

Osobny test wg wzorca restart z `test_server_integration.py` (dwa `ChatServer` nad tym
samym `tmp_path`): po przebiegu `s1.stop()`, nowy `s2 = ChatServer(ten sam data_dir)`
odtwarza board i rozmowę z logu/snapshotu:

```python
def test_selforg_state_survives_restart(tmp_path):
    # s1: a@b + status B working/C jak wyżej; s1.stop()
    # s2 = ChatServer(data_dir=tmp_path, ...); await s2.start()
    board = {p["nick"]: p for p in s2._participants_snapshot()}
    assert board["b"]["status"]["state"] == "working" and board["b"]["status"]["subject"] == "C"
    conv = s2.log.conversation_after(0)             # rozmowa przetrwała
    assert any(e.get("type") == "chat" and "@b" in e.get("text", "") for e in conv)
```

Sam brak pola `queue` + wpis w logu NIE dowodzi samoorganizacji — dowodem jest ROUTING
(B dostaje, C nie), TRWAŁOŚĆ po restarcie i ZERO ramek schedulera.

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
