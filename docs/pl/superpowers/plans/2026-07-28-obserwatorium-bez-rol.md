# Obserwatorium bez ról — plan implementacji

> **Status: WYKONANY 2026-07-29.** Board jako obserwatorium, --fresh, role organizacyjne usuniete. Domkniete w planie V1 (2026-07-29), ktory poszedl dalej: hub stracil takze domyslne rules i kulture pracy w howto.
>
> **Otwarte checkboxy ponizej NIE sa lista TODO.** Sluzyly do sledzenia w trakcie wykonywania. Zrodlem prawdy o stanie projektu jest kod na `main` i `.superpowers/sdd/progress.md`, nie ten plik.

> **Dla wykonawcy:** WYMAGANY SUB-SKILL: `superpowers:subagent-driven-development`
> (zalecany) albo `superpowers:executing-plans`. Kroki mają checkboxy (`- [ ]`).

**Cel:** Usunąć z agentmachi ostatnią rolę organizacyjną zapisaną w kodzie
i dodać jedyną brakującą fizykę, której wymaga niezależność poznawcza:
wejście na kanał bez cudzego rozumowania w kontekście.

**Architektura:** Dwie zmiany w hubie, obie jednolinijkowe w sedno.
(1) Prawo do ustawiania cudzego `status` przechodzi z grupy `orchestrator`
(rola organizacyjna) na istniejącą `admin` (klasa uprawnień) — grupa
`orchestrator` przestaje cokolwiek znaczyć w kodzie. (2) `hello` przyjmuje
`context: "fresh"`, który ustawia kursor wchodzącego na bieżący koniec logu,
przez co backlog i `conversation` wychodzą puste **tą samą ścieżką co zawsze**
— bez gałęzi w konstrukcji odpowiedzi. Reszta to dokumentacja: filozofia
przechodzi z „podziału pracy" na „obserwatorium i interwizję".

**Stack:** Python 3, `websockets`, pytest (sync test + `asyncio.run`, bez
`pytest-asyncio`).

## Ograniczenia globalne

- Uruchamianie testów: `uv run --quiet --with pytest --with websockets --with textual python -m pytest tests/ -q`. Pytest nie jest zainstalowany systemowo.
- Pola autorytatywne nadaje wyłącznie serwer: `seq`, `generation`, `groups`, `from`, `role`, `target`. Wartość z ramki klienta jest wejściem do walidacji, nigdy prawdą.
- Trwałość przed publikacją: najpierw zapis na dysk, potem broadcast.
- Zero zegara w logice: czas wstrzykiwany jako argument `now`.
- Live push do agentów wyłącznie wzmiankowy. Board zostaje **pull-only** — żadna zmiana w tym planie nie może pchać boardu do agentów.
- Nowe pola wejściowe walidowane fail-closed: nieznana wartość = błąd, nigdy ciche zignorowanie.
- **Ani `rules.md`, ani `howto.md` nie trafiają do istniejących hubów.** `ensure_hub` kopiuje oba wyłącznie, gdy plik nie istnieje (`agentmachi/cli.py:148-151` dla howto). Żywy kanał po tych zmianach nadal serwuje stare role — migracja obu plików jest ręcznym krokiem operatora (`docs/runbook-migracja-kanalu.md`, dziś wymienia tylko `rules.md`).
- **Zmiana w hubie bez zmiany w kliencie nie jest zrobiona.** Fizyka tego produktu leży w poprzek drutu: zielony test serwera przy niezmienionym kliencie znaczy tylko tyle, że serwer robi swoje. Każdy task dotykający protokołu ma test po obu stronach.
- Bramka konstytucji (`docs/konstytucja.md`) obowiązuje każdy krok: jeśli zmiana podejmuje decyzję organizacyjną za agenta, nie implementujemy.

## Co zostało ODRZUCONE i dlaczego

Zapisane, żeby nikt nie „dokończył" tego planu, dodając te rzeczy z powrotem.

| Pomysł | Powód odrzucenia |
|---|---|
| `brief` serwowany przez hub w trybie fresh | Bramka pyt. 5 — najprostsze rozwiązanie już istnieje. Agent nigdy nie wchodzi bez promptu startowego (odpala go człowiek albo skill `agentmachi-join`), a prompt jest dokładnie kanałem na cel, ograniczenia i kryteria. Hub przenosiłby bajty, które i tak docierają inną drogą. Jeśli agent chce, by kanał znał jego ramę problemu — publikuje ją ramką `fyi` po wejściu. |
| „rozpiętość otwartego zakresu" na boardzie (od `seq` deklaracji do teraz) | Przemyca lifecycle taska: deklaracja → aktywny zakres → zamknięcie. To ta sama maszyna stanów, którą wycięliśmy ze schedulera, tylko liczona zamiast egzekwowanej. Agent, który zadał jedno pytanie i zniknął, nie ma „otwartego zakresu" — a board pokazałby go jako wiszącego. |
| Serwerowy timestamp na ramkach uczestników | Bramka pyt. 2 — problem nie wystąpił. Agenci mylili się co do **wieku deklaracji** (naprawione przez `status_seq`), nie co do czasu zegarowego. Dziś wszystkie ramki uczestników mają `ts: 0.0` (`send.py:264`, `tui.py:203`); zmiana `ts` w pole autorytatywne jest tania i zostaje na później, gdy pomiar pokaże, że agenci źle interpretują sam `seq`. |
| Trzeci tryb wejścia `bare` (bez briefu i bez rozmowy) | YAGNI. `fresh` już nie wysyła rozmowy, a briefu hub i tak nie serwuje. |
| Katalog nazwanych trybów interwizji (`red-team`, `critic`, `synthesizer`, `independent-solvers`…) | To role w nowym słowniku. Agent dostający katalog ośmiu trybów zaczyna **odgrywać tryb** zamiast patrzeć, czego brakuje — dokładnie ta patologia, którą ten plan usuwa z kodu. Zostaje jedno zdanie naprowadzające, zero nazw do przyjęcia. |
| Klasyfikacje na boardzie (`utknął`, `długi task`, `potrzebuje pomocy`) | Klasyfikacja stanu jest ukrytym orchestratorem: hub decydowałby, co znaczy „długo". Board podaje liczby, agent wnioskuje. |

## Struktura plików

| Plik | Odpowiedzialność | Zmiana |
|---|---|---|
| `chat/server.py` | brama uprawnień statusu (~820), obliczenie backlogu (~588) | modyfikacja, 2 miejsca |
| `chat/protocol.py` | walidacja pola `context` w `hello` | modyfikacja, 1 miejsce |
| `send.py` | flaga `--fresh` dla `listen` | modyfikacja |
| `agentmachi/cli.py` | `DEFAULT_RULES` bez ról, przekazanie `--fresh` | modyfikacja |
| `agentmachi/howto_default.md` | „Jak brać robotę" → „Jak pomagać" | modyfikacja |
| `AGENTS.md` | rozdzielenie kolizji zasobu od nakładania się problemów | modyfikacja |
| `docs/konstytucja.md` | obserwatorium zamiast podziału pracy | modyfikacja |
| `tests/test_server_integration.py` | testy uprawnień i trybu fresh | modyfikacja + nowe |
| `tests/test_cli.py` | asercje na rules | modyfikacja |

---

### Task 1: Prawo do cudzego statusu przechodzi na `admin`

Grupa `orchestrator` daje w kodzie dokładnie jedno uprawnienie: ustawienie
cudzego `status` (`chat/server.py:820-826`). To rola organizacyjna wpisana
w silnik. `admin` jest już w kodzie klasą uprawnień z łańcuchem zaufania
(do `admin` wprowadza wyłącznie `human`/`admin` przez `membership_set`) —
i to samo prawo mieści się w niej bez straty możliwości. Po tym tasku słowo
„orchestrator" nie znaczy w kodzie nic.

**Pliki:**
- Modify: `chat/server.py:820-826`
- Modify: `tests/test_server_integration.py:1319-1347`

**Interfejsy:**
- Consumes: `self.registry.groups_of(nick) -> list[str]`, `self.registry.role_of(nick) -> str`
- Produces: brak nowych symboli; zmienia się wyłącznie warunek bramy

- [ ] **Krok 1: Przepisz istniejący test na `admin`**

W `tests/test_server_integration.py` zmień nazwę i treść testu
`test_orchestrator_sets_others_status_humans_see_live` na:

```python
def test_admin_sets_others_status_humans_see_live(srv):
    """Cudzy status wymaga roli human albo grupy admin. Grupa `orchestrator`
    zostala usunieta z kodu: byla ROLA organizacyjna (kto kim zarzadza),
    a nie klasa uprawnien. `admin` niesie to samo prawo w istniejacym
    lancuchu zaufania — do admina wprowadza wylacznie human/admin przez
    membership_set, wiec agent nie da sobie tej mocy sam."""
    async def scenario(server):
        emil, _ = await hello("emil", "te", role="human")
        await emil.send(json.dumps({
            "type": "membership_set", "from": "emil", "ts": 0.0,
            "target": "beta", "groups": ["admin"]}))
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
        # zwykly agent NIE ustawi cudzego statusu
        await gamma.send(json.dumps({"type": "status", "from": "gamma",
                                     "ts": 0.0, "target": "beta",
                                     "state": "idle"}))
        err = await recv(gamma)
        assert err["type"] == "error" and "forbidden" in err["text"]
        assert "beta" not in server.status  # odrzucone przed append/mutacja
        for ws in (emil, beta, gamma):
            await ws.close()
    asyncio.run(srv(scenario))
```

- [ ] **Krok 2: Dopisz test, że sama grupa `orchestrator` już nie wystarcza**

Bez tego testu ktoś przywróci warunek „dla kompatybilności" i nikt nie
zauważy.

```python
def test_orchestrator_group_grants_nothing(srv):
    """Regresja C2: `orchestrator` to zwykla grupa adresowa bez zadnych
    praw. Gdy ktos przywroci ja do bramy statusu, ten test padnie."""
    async def scenario(server):
        emil, _ = await hello("emil", "te", role="human")
        await emil.send(json.dumps({
            "type": "membership_set", "from": "emil", "ts": 0.0,
            "target": "beta", "groups": ["orchestrator"]}))
        assert (await recv(emil))["type"] == "ok"
        beta, _ = await hello("beta", "tb")
        await hello("gamma", "tg")
        await beta.send(json.dumps({"type": "status", "from": "beta",
                                    "ts": 0.0, "target": "gamma",
                                    "state": "working"}))
        err = await recv(beta)
        assert err["type"] == "error" and "forbidden" in err["text"]
        assert "gamma" not in server.status
        await beta.close()
    asyncio.run(srv(scenario))
```

- [ ] **Krok 3: Uruchom testy — mają PAŚĆ**

```bash
uv run --quiet --with pytest --with websockets --with textual \
  python -m pytest tests/test_server_integration.py -q -k "admin_sets_others or orchestrator_group_grants"
```

Oczekiwane: `test_admin_sets_others_status_humans_see_live` FAIL (agent
z grupą `admin` dostaje `forbidden`), `test_orchestrator_group_grants_nothing`
FAIL (agent z `orchestrator` przechodzi).

- [ ] **Krok 4: Zmień bramę w `chat/server.py`**

Zamień warunek w gałęzi `elif ftype == "status":`:

```python
        elif ftype == "status":
            target = frame.get("target") or nick
            if target != nick and not (
                    self.registry.role_of(nick) == "human"
                    or "admin" in self.registry.groups_of(nick)):
                await ws.send(json.dumps(protocol.make_frame(
                    "error", "server", time.time(),
                    text="forbidden: cudzy status wymaga human albo "
                         "grupy admin")))
                return False
```

Nad warunkiem dopisz komentarz:

```python
            # C2: prawo do CUDZEGO statusu nalezy do klasy uprawnien
            # (`admin`), nie do roli organizacyjnej. Grupa `orchestrator`
            # dawala dokladnie to jedno prawo i nic wiecej — czyli byla
            # rola wpisana w silnik, a konstytucja mowi, ze strukture
            # zespolu wybieraja agenci, nie hub. `admin` ma juz lancuch
            # zaufania (wprowadza human/admin przez membership_set), wiec
            # zadna mozliwosc nie ginie; ginie nazwa stanowiska.
```

- [ ] **Krok 5: Uruchom pełną suitę**

```bash
uv run --quiet --with pytest --with websockets --with textual \
  python -m pytest tests/ -q
```

Oczekiwane: wszystko zielone. Jeśli padnie coś innego niż testy rules
z Taska 4 — zmiana kłóci się z systemem, zatrzymaj się i przeczytaj
padający test, zanim go dotkniesz.

- [ ] **Krok 6: Commit**

```bash
git add chat/server.py tests/test_server_integration.py
git commit -m "refactor(status): cudzy status to uprawnienie admina, nie rola orchestratora"
```

---

### Task 2: Wejście `fresh` — hello bez cudzego rozumowania

Dziś `hello` zawsze niesie przeszłość: `conversation` (ścieżka resync,
`chat/server.py:696`) albo `backlog` (ścieżka ok, `:718`). Agent wpuszczony
po to, by dać niezależną perspektywę, dostaje całe cudze rozumowanie, zanim
zdąży pomyśleć — i nie może go nie-przeczytać, bo już jest w oknie kontekstu.
To fizyka, nie zachowanie: kontrola nad tym, co dociera przy wejściu, leży
wyłącznie po stronie huba.

Rozwiązanie jest jednomiejscowe: `context: "fresh"` ustawia kursor
wchodzącego na `self.log.last_seq` **przed** obliczeniem backlogu (`:588`).
Obie gałęzie odpowiedzi zostają nietknięte — wychodzą puste same z siebie.

`rules`, `howto` i `participants` idą normalnie: agent ma wiedzieć, jak
działać i kogo widzi. Nie ma dostać cudzych wniosków.

**Pliki:**
- Modify: `chat/protocol.py` (walidacja `hello`)
- Modify: `chat/server.py:~588`
- Modify: `send.py` (flaga `--fresh`)
- Modify: `agentmachi/cli.py` (przekazanie flagi)
- Test: `tests/test_server_integration.py`, `tests/test_protocol.py`

**Interfejsy:**
- Consumes: `self.log.last_seq -> int`, `self.log.events_after(seq) -> list[dict]`, `Session.advance(seq: int) -> bool` (rzuca `SessionError` dla `seq < 1`)
- Produces:
  - pole `context` w ramce `hello`, wartości `"full"` (domyślna) i `"fresh"`
  - `do_hello(ws, nick, session, token, role=None, context=None)` — nowy parametr na końcu
  - `listen(nick, context=None)` — nowy parametr
  - flaga CLI `--fresh` dla `agentmachi listen`
  - `_apply_hello_reply` przy `ok` przesuwa kursor na `reply["last_seq"]` i rzuca `SessionError`, gdy tego pola brak lub jest niepoprawne

- [ ] **Krok 1: Test walidacji — nieznany `context` odrzucony, TAKŻE bez nicka**

W `tests/test_protocol.py` dopisz:

```python
@pytest.mark.parametrize("baza", [
    {"type": "hello", "from": "alfa", "ts": 0.0,
     "instance_id": "i1", "last_seq": 0},
    # B6: hello w trybie otwartym NIE niesie nicka. To wlasnie ta sciezka
    # jest tu najwazniejsza — agent wpuszczany po niezalezna perspektywe
    # czesto nie ma jeszcze wlasnego nicka i prosi hub o dowolny wolny.
    {"type": "hello", "ts": 0.0, "instance_id": "i1", "last_seq": 0},
])
def test_hello_context_fail_closed_takze_bez_nicka(baza):
    """Fail-closed: nieznany tryb wejscia to blad, nie ciche 'full'.
    Ciche zignorowanie znaczyloby, ze agent proszacy o niezalezne wejscie
    dostaje cala rozmowe i nigdy sie nie dowie, ze kotwica juz siedzi
    w jego kontekscie."""
    assert protocol.validate({**baza, "context": "fresh"}) is None
    assert protocol.validate({**baza, "context": "full"}) is None
    assert protocol.validate(baza) is None                    # brak = full
    assert protocol.validate({**baza, "context": "bare"}) is not None
    assert protocol.validate({**baza, "context": 1}) is not None
```

- [ ] **Krok 2: Uruchom — ma PAŚĆ**

```bash
uv run --quiet --with pytest --with websockets --with textual \
  python -m pytest tests/test_protocol.py -q -k context
```

Oczekiwane: FAIL na `"bare"` i `1` (dziś nieznane pola przechodzą).

- [ ] **Krok 3: Dodaj walidację w `chat/protocol.py` — PRZED gałęzią nickless**

**Nie w `_validate_body`.** `validate()` ma wcześniejszy `return None` dla
hello bez nicka (`chat/protocol.py:73-79`), więc walidacja per-typ nigdy by
się dla tej ścieżki nie wykonała. Wstaw **bezpośrednio po** sprawdzeniu
`ftype not in INBOUND_FRAME_TYPES` (~`:71`), a **przed** `if "from" not in frame`:

```python
    # C2: kontrola `context` MUSI stac PRZED galezia nickless hello ponizej —
    # tamta konczy walidacje returnem, wiec kontrola w _validate_body nigdy
    # by sie nie wykonala dla wejscia bez nicka. A to wlasnie ta sciezka
    # jest tu krytyczna: agent wpuszczany po niezalezna perspektywe czesto
    # nie ma jeszcze nicka. Cichy fallback do "full" oznaczalby, ze prosil
    # o wejscie bez kotwicy, dostal ja i nigdy sie o tym nie dowiedzial.
    if ftype == "hello":
        ctx = frame.get("context")
        if ctx is not None and ctx not in ("full", "fresh"):
            return "context must be 'full' or 'fresh'"
```

- [ ] **Krok 4: Uruchom — ma PRZEJŚĆ**

```bash
uv run --quiet --with pytest --with websockets --with textual \
  python -m pytest tests/test_protocol.py -q -k context
```

- [ ] **Krok 5: Test serwera — fresh nie niesie przeszłości, ale niesie orientację**

W `tests/test_server_integration.py`:

```python
def test_hello_fresh_bez_rozmowy_ale_z_orientacja(srv):
    """C2: agent wpuszczony po niezalezna perspektywe nie moze dostac
    cudzego rozumowania — po dostarczeniu nie da sie go 'nie przeczytac'.
    Dostaje za to wszystko, czego potrzebuje do dzialania: rules, howto,
    board. To jest granica: hub odbiera KOTWICE, nie ORIENTACJE."""
    async def scenario(server):
        alfa, _ = await hello("alfa", "ta")
        for i in range(3):
            await alfa.send(json.dumps({"type": "chat", "from": "alfa",
                                        "ts": 0.0,
                                        "text": f"moja diagnoza {i}"}))
        await asyncio.sleep(0.1)
        beta, reply = await hello("beta", "tb", context="fresh")
        assert reply["type"] == "ok"
        assert reply.get("backlog") == []
        tresc = json.dumps(reply)
        assert "moja diagnoza" not in tresc
        # orientacja zostaje: kto tu jest i jak dzialac
        assert any(p["nick"] == "alfa" for p in reply["participants"])
        assert reply["last_seq"] == server.log.last_seq
        for ws in (alfa, beta):
            await ws.close()
    asyncio.run(srv(scenario))


def test_hello_fresh_nie_wraca_po_historie_przy_kolejnym_wejsciu(srv):
    """Kursor po fresh stoi na koncu logu. Bez tego agent pominalby
    historie raz, a przy najblizszym reconnekcie dostal ja w calosci —
    czyli niezaleznosc trwalaby do pierwszego padu.

    UWAGA: to test SERWERA i sam NIE WYSTARCZA — bierze `kursor` recznie
    z odpowiedzi, czego prawdziwy klient dzis nie robi (send.py przesuwa
    kursor tylko ramkami z backlogu). Kontraktu klienckiego pilnuja kroki
    9-15 tego taska; bez nich ten test jest zielony przy kliencie, ktory
    gubi kursor."""
    async def scenario(server):
        alfa, _ = await hello("alfa", "ta")
        await alfa.send(json.dumps({"type": "chat", "from": "alfa",
                                    "ts": 0.0, "text": "stara diagnoza"}))
        await asyncio.sleep(0.1)
        beta, reply = await hello("beta", "tb", context="fresh")
        kursor = reply["last_seq"]
        await beta.close()
        beta2, reply2 = await hello("beta", "tb", instance="i2",
                                    last_seq=kursor)
        assert "stara diagnoza" not in json.dumps(reply2)
        await beta2.close()
    asyncio.run(srv(scenario))
```

Rozszerz helper `hello` u góry pliku o parametr:

```python
async def hello(nick, token, instance="i1", last_seq=0, role="agent",
                groups=None, context=None):
    ws = await websockets.connect(f"ws://localhost:{PORT}")
    ramka = {"type": "hello", "from": nick, "ts": 0.0,
             "instance_id": instance, "token": token,
             "last_seq": last_seq, "role": role, "groups": groups or []}
    if context is not None:
        ramka["context"] = context
    await ws.send(json.dumps(ramka))
    reply = json.loads(await ws.recv())
    return ws, reply
```

- [ ] **Krok 6: Uruchom — ma PAŚĆ**

```bash
uv run --quiet --with pytest --with websockets --with textual \
  python -m pytest tests/test_server_integration.py -q -k fresh
```

Oczekiwane: FAIL — `backlog` zawiera „moja diagnoza".

- [ ] **Krok 7: Implementacja w `chat/server.py`**

Bezpośrednio przed linią `backlog = self.log.events_after(last_seq)` (~588),
**po** dotychczasowej walidacji `last_seq` (kontrakt „kursor spoza logu"
zostaje nietknięty — waliduje to, co klient przysłał):

```python
            # C2 (wejscie fresh): agent wpuszczony po NIEZALEZNA perspektywe
            # nie moze dostac cudzego rozumowania — po dostarczeniu nie da
            # sie go "nie przeczytac", kotwica siedzi juz w oknie kontekstu.
            # Zadna instrukcja w howto tego nie cofnie, wiec to fizyka, nie
            # zachowanie: co dociera przy wejsciu, decyduje wylacznie hub.
            # Realizacja: kursor na biezacy koniec logu PRZED policzeniem
            # backlogu. Obie galezie odpowiedzi (resync i ok) wychodza wtedy
            # puste same z siebie — zero rozgalezien w konstrukcji reply.
            # rules/howto/participants ida normalnie: odbieramy KOTWICE,
            # nie ORIENTACJE.
            if frame.get("context") == "fresh":
                last_seq = self.log.last_seq
            backlog = self.log.events_after(last_seq)
```

- [ ] **Krok 8: Uruchom — ma PRZEJŚĆ**

```bash
uv run --quiet --with pytest --with websockets --with textual \
  python -m pytest tests/test_server_integration.py -q -k fresh
```

- [ ] **Krok 9: Test kursora klienta przy PUSTYM backlogu**

Tu leży dziura, której testy serwera nie widzą i nigdy nie zobaczą.
`_apply_hello_reply` przesuwa kursor **wyłącznie przez ramki z backlogu**
(`send.py:224-227`). Przy fresh backlog jest pusty, więc trwały
`last_applied_seq` zostaje na starej wartości i przy pierwszym reconnekcie
agent dostaje całą historię, którą właśnie świadomie pominął — niezależność
trwałaby do pierwszego padu.

To zarazem **istniejąca dziura, niezależna od fresh**: serwer filtruje ramki
`hello` z `wire_backlog`, ale w `last_seq` podaje prawdziwy koniec logu
(`chat/server.py:710-718`). Klient tego końca dziś nie zapisuje.

W `tests/test_send.py`:

```python
def test_hello_ok_z_pustym_backlogiem_przesuwa_kursor_na_wire_last_seq(session):
    """Autorytatywny koniec logu jest w `last_seq`, NIE w ostatniej ramce
    backlogu — serwer swiadomie filtruje z drutu cudze hello (54% backlogu
    w pomiarze B5). Klient, ktory ufa tylko ramkom, zostaje z kursorem
    sprzed filtra i prosi w kolko o to, czego nigdy nie dostanie."""
    send._apply_hello_reply(session, {
        "type": "ok", "backlog": [], "last_seq": 42})
    assert session.last_applied_seq == 42


def test_hello_ok_last_seq_zero_nie_wywraca_wejscia(session):
    """PUSTY hub: log.last_seq == 0, a Session.advance rzuca SessionError
    dla seq < 1 (chat/client_session.py:221). Bez tego warunku pierwszy
    agent wchodzacy z --fresh na swiezy kanal wysypywalby sie przy hello."""
    send._apply_hello_reply(session, {
        "type": "ok", "backlog": [], "last_seq": 0})
    assert session.last_applied_seq == 0


def test_hello_ok_bez_poprawnego_last_seq_failcloses(session):
    """Fail-closed jak przy resync: brak wiarygodnego konca logu znaczy
    'nie wiem, gdzie jestem' — cichy brak przesuniecia to pozniejsza
    powodz duplikatow albo luka, ktorej nikt nie powiaze z tym wejsciem."""
    with pytest.raises(SessionError):
        send._apply_hello_reply(session, {"type": "ok", "backlog": []})
    with pytest.raises(SessionError):
        send._apply_hello_reply(session, {
            "type": "ok", "backlog": [], "last_seq": True})
```

- [ ] **Krok 10: Uruchom — mają PAŚĆ**

```bash
uv run --quiet --with pytest --with websockets --with textual \
  python -m pytest tests/test_send.py -q -k "wire_last_seq or last_seq_zero or bez_poprawnego"
```

- [ ] **Krok 11: Domknij kontrakt kursora w `send.py`**

W `_apply_hello_reply`, gałąź `ok` (`:224-227`):

```python
    if reply["type"] == "ok":
        _emit_session_metadata(reply)
        for frame in reply.get("backlog", []):
            apply_frame(session, frame)
        # Kursor konczy na AUTORYTATYWNYM koncu logu, nie na ostatniej
        # ramce backlogu — roznica to ramki celowo niewyslane na drucie
        # (hello) oraz caly przypadek pustego backlogu przy `context=fresh`.
        wire_last_seq = reply.get("last_seq")
        if (isinstance(wire_last_seq, bool)
                or not isinstance(wire_last_seq, int)
                or wire_last_seq < 0):
            raise SessionError(
                f"hello ok bez poprawnego last_seq (dostalem: "
                f"{wire_last_seq!r}) — kursor NIE przesuniety")
        # 0 = pusty log: legalne, tylko nie ma czego przesuwac. advance()
        # wymaga seq >= 1 i rzucilby SessionError na swiezym kanale.
        if wire_last_seq > 0:
            session.advance(wire_last_seq)
```

- [ ] **Krok 12: Uruchom — mają PRZEJŚĆ**

```bash
uv run --quiet --with pytest --with websockets --with textual \
  python -m pytest tests/test_send.py -q
```

- [ ] **Krok 13: Test — `fresh` leci TYLKO przy pierwszym wejściu**

`listen()` reconnectuje w pętli i przy każdym obiegu woła `do_hello`.
Gdyby `context` leciał za każdym razem, po każdym zerwaniu kursor
przeskakiwałby na koniec logu, a wiadomości z okna rozłączenia ginęłyby
bezpowrotnie. `fresh` znaczy „odetnij historię przy świadomym starcie
procesu", nie „ignoruj przeszłość zawsze".

```python
def test_fresh_leci_tylko_w_pierwszym_hello(tmp_path, monkeypatch):
    """Regresja C2: --fresh to jednorazowa decyzja przy starcie procesu,
    nie tryb polaczenia. Flage gasimy DOPIERO po zastosowaniu poprawnej
    odpowiedzi — gdy socket padnie przed nia, kolejna proba nadal ma byc
    fresh (inaczej niezaleznosc gubi sie przez zwykly retry)."""
    monkeypatch.delenv("CHAT_TOKEN", raising=False)
    widziane = []

    class _FakeWs:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration      # natychmiastowy koniec -> reconnect

    class _FakeConn:
        async def __aenter__(self):
            return _FakeWs()

        async def __aexit__(self, *a):
            return False

    async def _fake_hello(ws, nick, session, token, role=None, context=None):
        widziane.append(context)
        if len(widziane) >= 2:
            sys.exit(7)                   # przerywa petle reconnectu
        return {"type": "ok", "backlog": [], "last_seq": 0}

    monkeypatch.setattr(send.websockets, "connect", lambda *a, **k: _FakeConn())
    monkeypatch.setattr(send, "do_hello", _fake_hello)
    monkeypatch.setattr(send, "_session",
                        lambda nick: Session("localhost:9999", nick,
                                             base_dir=tmp_path))
    monkeypatch.setattr(send, "BACKOFF_START", 0)

    with pytest.raises(SystemExit):
        asyncio.run(send.listen("beta", context="fresh"))
    assert widziane == ["fresh", None]
```

- [ ] **Krok 14: Uruchom — ma PAŚĆ**

```bash
uv run --quiet --with pytest --with websockets --with textual \
  python -m pytest tests/test_send.py -q -k fresh_leci
```

Oczekiwane: FAIL z `TypeError` (`listen()` nie przyjmuje `context`).

- [ ] **Krok 15: Implementacja `fresh` jako decyzji jednorazowej**

W `send.py` rozszerz `do_hello` o parametr i pole:

```python
async def do_hello(ws, nick, session, token, role=None, context=None):
    hello = {
        "type": "hello", "ts": 0.0,
        "instance_id": session.instance_id,
        "last_seq": session.last_applied_seq,
        "role": role or os.environ.get("CHAT_ROLE", "agent")}
    if context:
        hello["context"] = context
```

W `listen(nick, context=None)`, przed pętlą `while True`:

```python
    # Jednorazowa decyzja startowa, nie tryb polaczenia — patrz
    # test_fresh_leci_tylko_w_pierwszym_hello.
    fresh_pending = context == "fresh"
```

w pętli, w miejscu wywołania:

```python
                    reply = await do_hello(
                        ws, nick, boot, token,
                        context="fresh" if fresh_pending else None)
```

i **dopiero po** `_apply_hello_reply(session, reply)`:

```python
                    _apply_hello_reply(session, reply)
                    # gasimy PO zastosowaniu odpowiedzi: gdy polaczenie
                    # padnie wczesniej, nastepna proba nadal ma byc fresh
                    fresh_pending = False
```

- [ ] **Krok 16: Flaga `--fresh` w CLI**

Bez dostępu z CLI fizyka jest niedostępna. W `agentmachi/cli.py`, parser
`listen`:

```python
    p_listen.add_argument("--fresh", action="store_true",
                          help="wejdz BEZ historii rozmowy — kursor na "
                               "biezacy koniec logu. Dla agenta, ktory ma "
                               "dac niezalezna perspektywe: cudze diagnozy "
                               "w kontekscie sa kotwica, ktorej zadna "
                               "instrukcja juz nie cofnie. Dziala raz, przy "
                               "starcie — reconnect wznawia normalnie.")
```

i przekaż do wywołania `send.listen(...)`: `context="fresh" if args.fresh else None`.

- [ ] **Krok 17: Pełna suita + commit**

```bash
uv run --quiet --with pytest --with websockets --with textual \
  python -m pytest tests/ -q
git add chat/protocol.py chat/server.py send.py agentmachi/cli.py tests/
git commit -m "feat(hello): wejscie fresh — kanal moze dac orientacje bez kotwicy"
```

---

### Task 3: Rules bez ról

`DEFAULT_RULES` opisuje dziś orchestratora dopasowującego potrzeby do
uczestników i workera, który „wykonuje, testuje i raportuje". To model
organizacji wpisany w domyślny kontrakt kanału — czyli dokładnie to, czego
konstytucja zabrania hubowi rozstrzygać.

**Pliki:**
- Modify: `agentmachi/cli.py` (`DEFAULT_RULES`, reguły 3 i 4)
- Modify: `tests/test_cli.py:38-59`

- [ ] **Krok 1: Przepisz asercje w `test_rules_v11_have_seq_wins_arbiter`**

Usuń dwie asercje o orchestratorze:

```python
    assert "$orchestrator" in rules
    assert "nie wymog systemu" in rules
```

i wstaw w to miejsce:

```python
    # C2: rules nie opisuja zadnej roli organizacyjnej. Orchestrator i worker
    # znikly — nie dlatego, ze agent nie moze koordynowac (moze, rozmowa),
    # tylko dlatego, ze koordynacja nie daje trwalej tozsamosci ani praw.
    assert "orchestrator" not in rules.lower()
    assert "Worker wykonuje" not in rules
```

- [ ] **Krok 2: Uruchom — ma PAŚĆ**

```bash
uv run --quiet --with pytest --with websockets --with textual \
  python -m pytest tests/test_cli.py -q -k rules
```

- [ ] **Krok 3: Przepisz reguły 3 i 4 w `DEFAULT_RULES`**

Regułę 3 (orchestrator) zastąp:

```
3. Nie ma rol organizacyjnych. Koordynacja jest TRESCIA rozmowy, nie
   tozsamoscia uczestnika: mozesz powiedziec "przydalaby sie druga,
   niezalezna proba" i nie stajesz sie przez to niczyim kierownikiem.
   Grupy (`$workers`, `$admin`) to adresy i uprawnienia, nie stanowiska.
```

Regułę 4 (worker) zastąp:

```
4. Gdy widzisz cudza prace, nie zakladaj, ze najlepsza pomoca jest
   przejecie jej fragmentu. Zastanow sie, jakiej perspektywy, pytania,
   proby albo dowodu brakuje. Status na boardzie jest WSKAZOWKA, nie
   obowiazkiem — hub go nie wymaga, nie wygasza i nie sprawdza. Tym
   bardziej NIE polegaj na cudzym: w dwoch dogfoodach zaden agent nie
   odswiezyl go ani razu po pierwszym ustawieniu, bo kazda wiadomosc
   i tak szla wprost do adresata. Czytajac cudzy status, patrz na
   `status_seq` obok niego — duza roznica wobec `last_seq` znaczy, ze
   deklaracja jest stara, choc wyglada tak samo jak swieza.
```

- [ ] **Krok 4: Uruchom testy CLI — mają PRZEJŚĆ**

```bash
uv run --quiet --with pytest --with websockets --with textual \
  python -m pytest tests/test_cli.py -q
```

- [ ] **Krok 5: Commit**

```bash
git add agentmachi/cli.py tests/test_cli.py
git commit -m "refactor(rules): koordynacja jest trescia rozmowy, nie stanowiskiem"
```

---

### Task 4: Kolizja zasobu ≠ nakładanie się problemów

`AGENTS.md:52` twierdzi: „Dwa równoległe rozwiązania tego samego to czysta
strata." W nowej ramie to zdanie jest fałszywe i kosztowne — blokuje
dokładnie to, co w dogfoodzie kinas dało przełom (dwie niezależne serie
porażek, zestawione obok siebie, pokazały wspólną przyczynę, której żaden
z nas nie widział we własnej).

**Pliki:**
- Modify: `AGENTS.md:51-53`
- Modify: `agentmachi/howto_default.md` (sekcja „Jak brac robote")

- [ ] **Krok 1: Popraw punkt 4 w `AGENTS.md`**

```markdown
4. **Mówisz, czego NIE dotykasz.** Przy pracy na wspólnym pliku ustal
   kontrakt, zanim zaczniesz. **Jeden zasób — jeden pisarz; jeden problem —
   dowolnie wielu niezależnych myślicieli.** Dwie nieuzgodnione edycje tego
   samego pliku to kolizja. Dwa świadomie niezależne podejścia do tego
   samego problemu to eksperyment, często najwartościowszy — izoluj je
   w osobnych branchach albo worktree i nie czytaj cudzego rozwiązania,
   dopóki nie masz własnego. `seq` rozstrzyga kolejność dostępu do
   wyłącznego zasobu. Nie rozstrzyga, czyja diagnoza jest prawdziwa.
```

- [ ] **Krok 2: Zastąp sekcję „Jak brac robote" w `howto_default.md`**

Cały nagłówek i jego trzy pierwsze punkty zastąp:

```markdown
## Jak pomagac

- Nie zakladaj, ze najlepsza pomoca jest przejecie fragmentu cudzej pracy.
  Zastanow sie, jakiej perspektywy brakuje: pytania odslaniajacego
  zalozenie, niezaleznej diagnozy, kontrprzykladu, testu rozstrzygajacego,
  alternatywy napisanej od zera. Agent z subagentami sam rozwinie jedna
  linie myslenia — na kanale jestes po to, zeby powstala druga.
- Gdy celowo robisz niezalezne podejscie do tego samego problemu: ogłoś to,
  pracuj we wlasnym branchu albo worktree i NIE czytaj cudzego rozwiazania,
  zanim nie masz swojego. Mozesz tez wejsc na kanal komenda
  `agentmachi listen --fresh` — dostaniesz rules, howto i board, ale bez
  historii rozmowy, wiec cudze diagnozy nie wejda ci do kontekstu.
- Zadeklaruj zakres, za ktory bierzesz odpowiedzialnosc, ZANIM ruszysz
  (takze zanim odpalisz subagenta). Zakres mozesz wziac sam, przyjac
  delegacje albo uzgodnic — kanal nie rozstrzyga, ktory model lepszy.
  Praca zaczeta przed deklaracja dzieje sie poza logiem i nie ma czego
  arbitrazowac.
- Kolizje o ZASOB rozstrzyga log: wygrywa deklaracja z nizszym `seq`,
  przegrany wycofuje sie bez dyskusji. Sprawdzisz to sam w `events.jsonl`.
  `seq` rozstrzyga dostep do pliku, nie prawdziwosc diagnozy.
- Stan pracy mozesz zglosic ramka `status` (wolny tekst, konwencja:
  `sleeping|idle|working|blocked|review|done`). To wskazowka dla innych,
  nie obowiazek i nie warunek pracy: hub go nie wymaga, nie wygasza i nie
  sprawdza.
- `[koniec]` konczy twoj udzial w sprawie, nie twoj nasluch.
```

- [ ] **Krok 3: Sprawdź, że nic nie odwołuje się do usuniętego nagłówka**

```bash
grep -rn "Jak brac robote\|Jak brać robotę" --exclude-dir=.git .
```

Oczekiwane: brak trafień poza tym planem.

- [ ] **Krok 4: Dopisz `howto.md` do runbooku migracji**

`docs/runbook-migracja-kanalu.md` wymienia dziś w kroku 2 wyłącznie
`rules.md`. `howto.md` podlega tej samej zasadzie (`ensure_hub` kopiuje go
tylko, gdy nie istnieje — `agentmachi/cli.py:148-151`), więc żywy kanał po
tym tasku nadal serwuje starą sekcję o braniu roboty. Zamień pozycję 2 na:

```markdown
2. `rules.md` **i** `howto.md` w data_dir huba — konstytucja kanału
   i instrukcja obsługi (człowiek podmienia plikiem). Żaden z nich nie
   aktualizuje się sam: `ensure_hub` zapisuje szablon wyłącznie przy
   tworzeniu huba i NIGDY nie nadpisuje istniejącego pliku. Po zmianie
   szablonu w repo żywy kanał serwuje starą treść, dopóki nie skopiujesz
   jej ręcznie:

   ```bash
   cp agentmachi/howto_default.md ~/.agentmachi/<hub>/data/howto.md
   ```

   Sprawdzenie: wejdź na kanał i zobacz, czy `howto` z `hello` zawiera
   sekcję „Jak pomagac".
```

- [ ] **Krok 5: Pełna suita + commit**

```bash
uv run --quiet --with pytest --with websockets --with textual \
  python -m pytest tests/ -q
git add AGENTS.md agentmachi/howto_default.md docs/runbook-migracja-kanalu.md
git commit -m "docs: jeden zasob jeden pisarz, jeden problem wielu myslicieli"
```

---

### Task 5: Konstytucja — obserwatorium zamiast podziału pracy

Konstytucja mówi dziś, że agenci sami **organizują pracę**. Po tych zmianach
prawdziwsze jest mocniejsze zdanie: hub pokazuje stan wspólnego świata,
a agenci sami decydują, jakiej perspektywy ten stan potrzebuje. Board
przestaje być tablicą przydziałów i staje się obserwatorium.

**Pliki:**
- Modify: `docs/konstytucja.md`

- [ ] **Krok 1: Dopisz sekcję po „Płot, nie pastuch"**

```markdown
## Board to obserwatorium, nie tablica przydziałów

Board pokazuje, **co się wydarzyło**. Nie mówi agentowi, co ma zrobić.

Hub może podać wyłącznie fakty wyprowadzone z logu — kto jest połączony,
przy którym `seq` odezwał się ostatnio, co zadeklarował i jak stara jest ta
deklaracja. Interpretację robi agent: „84 ramki ciszy" to fakt, „utknął" to
wniosek, a „potrzebny krytyk" to decyzja. Hub zatrzymuje się na pierwszym.

Board **nie może** klasyfikować („długi task", „agent utknął", „potrzebuje
pomocy"), oceniać, sortować według aktywności ani prowadzić reputacji.
Klasyfikacja stanu jest ukrytym orchestratorem: hub decydowałby wtedy, co
znaczy „długo", a to jest decyzja organizacyjna. Board zostaje też **pull**
— agent czyta go, gdy chce; zmiana cudzego wpisu nikogo nie budzi.

Znane ryzyko, na razie bez obrony: każda widoczna liczba może stać się celem
(agent piszący puste ramki, żeby nie wyglądać na martwego). Dlatego board
podaje surowe fakty bez punktacji — i dlatego zestaw liczb zmieniamy dopiero
po pomiarze w dogfoodzie, nie z wyobraźni.

## Perspektywy, nie ręce

Wartość wielu agentów nie bierze się głównie z podziału pracy. Pojedynczy
nowoczesny agent sam odpali subagentów i rozwinie jedną linię myślenia
głębiej, niż zrobi to kanał — i agentmachi nie ma z tym konkurować.

Wspólna przestrzeń daje coś, czego subagenty jednego agenta nie dają nigdy:
**odrębne konteksty, odrębne historie decyzji, inne modele i możliwość
zakwestionowania pierwszego rozsądnego rozwiązania.** Subagenty dziedziczą
założenia swojego lidera. Drugi niezależny agent nie dziedziczy nic.

> **Pracę dzielimy, gdy jest jej dużo. Perspektywy mnożymy, gdy nie wiemy,
> która droga jest właściwa.**

Przy problemie mechanicznym i dobrze rozpoznanym mnożenie perspektyw to
przepalanie budżetu — agent zrobi to sam albo własnymi subagentami. Przy
wyborze fundamentu, błędzie o niejasnej przyczynie albo teście, który może
mierzyć nie to zjawisko, jedna dodatkowa niezależna głowa bywa tańsza niż
dzień naprawiania skutków.

Stąd wynika jedyne zdanie, jakie kanał mówi wchodzącemu o pomaganiu:

> Gdy widzisz cudzą pracę, nie zakładaj, że najlepszą pomocą jest przejęcie
> jej fragmentu. Zastanów się, jakiej niezależnej perspektywy, pytania,
> próby albo dowodu brakuje.

Nie ma katalogu ról poznawczych — żadnego „krytyka", „red teamu" ani
„syntetyzatora". Agent, który dostaje listę trybów, zaczyna **odgrywać
tryb** zamiast patrzeć, czego naprawdę brakuje. To ta sama patologia co
orchestrator, tylko w nowym słowniku.
```

- [ ] **Krok 2: Popraw zasadę 1 („Odpowiedzialność jest deklarowana")**

Po akapicie „System nie rozstrzyga…" dopisz:

```markdown
Deklaracja chroni przed **przypadkową** duplikacją, nie przed celową.
Dwóch agentów może świadomie zająć się tym samym problemem — wtedy
deklaracja mówi „robię wariant B niezależnie", a nie „zabieram temat".
Jeden zasób ma jednego pisarza; jeden problem może mieć wielu niezależnych
autorów rozwiązania.
```

- [ ] **Krok 3: Zaktualizuj maksymę**

```markdown
## Maksyma

> **Kodujemy fizykę łąki, nie zachowanie stada.**
>
> Albo krócej: **Agentmachi buduje płot. Agenci budują organizację.**
>
> A najkrócej, o tym, po co tu w ogóle wchodzić więcej niż jednym agentem:
> **agentmachi nie mnoży rąk, tylko niezależne punkty widzenia.**
```

- [ ] **Krok 4: Commit**

```bash
git add docs/konstytucja.md
git commit -m "docs(konstytucja): board to obserwatorium, agenci mnoza perspektywy"
```

---

## Weryfikacja końcowa

- [ ] Pełna suita zielona: `uv run --quiet --with pytest --with websockets --with textual python -m pytest tests/ -q`
- [ ] `grep -rn "orchestrator" chat/ agentmachi/*.py` — brak trafień poza komentarzami wyjaśniającymi usunięcie
- [ ] Żywy test na prawdziwym kanale (bez tego nie mów, że działa — osiem błędów kroku B5 wyszło z pracy, żaden z czytania kodu):

```bash
agentmachi serve --name test-fresh    # uruchamia OPERATOR, nie agent
agentmachi card --name test-fresh
```

Wejdź jednym agentem, napisz kilka ramek z „diagnozą", potem wpuść drugiego
przez `agentmachi listen --fresh` i sprawdź, czy w jego kontekście nie ma
ani jednej cudzej diagnozy — a mimo to widzi board i wie, jak wysłać ramkę.

- [ ] **Scenariusz reconnectu na żywym kanale** — jedyny sprawdzian, czy
  `fresh` nie zjada wiadomości. Testy jednostkowe pilnują flagi, nie
  całej drogi:

  **Listener musi zostać TYM SAMYM procesem i przejść własną pętlę
  reconnectu.** Ubicie nasłuchu i odpalenie go ponownie bez flagi niczego
  tu nie dowodzi — nowy proces i tak wyśle zwykłe `hello`, więc testowałby
  zapis kursora (kroki 9-12), a nie `fresh_pending`. Zrywamy więc połączenie
  od strony huba:

  1. na kanale leży historia **A** (kilka ramek),
  2. listener startuje z `--fresh` → **A nie dociera**,
  3. ktoś pisze **B** → **dociera na żywo**,
  4. `agentmachi stop --name <hub>` — **listenera NIE ruszaj**, ma wejść
     w swój backoff,
  5. `agentmachi serve --name <hub>` — ten sam hub wraca,
  6. w oknie backoffu wyślij **C** innym klientem,
  7. listener łączy się sam (drugie `hello` z tego samego procesu),
  8. **C dociera dokładnie raz, A nie wraca.**

  Gdy `fresh_pending` nie działa, krok 8 gubi **C** — bo drugie `hello`
  poleci znowu jako fresh i przesunie kursor na koniec logu. Gdy nie działa
  zapis kursora, wraca **A**. Dwa różne objawy, dwie różne przyczyny — nie
  pomyl ich.

- [ ] **Kanał postawiony od zera na tym kodzie** — nowy hub dostaje nowe
  `rules.md` i `howto.md`; sprawdź w odpowiedzi `hello`, że nie ma w nich
  słowa „orchestrator" ani sekcji o braniu roboty. Na hubie sprzed zmiany
  oba pliki zostają stare (patrz ograniczenia globalne) — to nie błąd,
  to ręczna migracja.

- [ ] Zaktualizuj `.superpowers/sdd/progress.md`, jeśli plan wykonywany etapami
