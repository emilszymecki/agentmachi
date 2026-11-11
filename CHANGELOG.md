# Changelog

Format: tematycznie, nie commit po commicie. Każdy wpis opisuje ZMIANĘ
ZACHOWANIA, którą widzi użytkownik albo agent — nie refaktor, który jej nie
zmienia.

## 0.6.0 — 2026-11-11

### Paczka zajmuje jedną nazwę: `agentmachi`

Do 0.5.0 koło instalowało na najwyższym poziomie `site-packages` także
`chat/`, `send.py` i `tui.py`. Każdy projekt z własnym `chat` albo `send`
w tym samym środowisku gryzł się z paczką; zmierzone 2026-11-11 na 0.5.0
z PyPI: `python -m agentmachi.cli list` w katalogu z własnym `chat/` →
`ModuleNotFoundError: No module named 'chat.client_session'` (`ae02933`
łatał objaw tej samej przyczyny przy starcie huba).

Teraz: `agentmachi.chat`, `agentmachi.send`, `agentmachi.tui`. Komendy CLI
bez zmian. Kto importował `send`/`chat` wprost albo wołał
`python -m chat.server` — zmienia na `agentmachi.send` / `agentmachi.chat.server`.

## 0.5.0 — 2026-11-03

Zakres: `8bbf299..HEAD` (po wydaniu 0.4.0), 50 commitów. Większość z badania
„less is more" 2026-11-02 — tarcie zmierzone w logach dwóch pokojów,
w dogfoodzie subagentów i w weryfikacji krzyżowej dwóch sesji Claude Code
oraz Codeksa: [`docs/pl/experiments/less-is-more-2026-11-02.md`](docs/pl/experiments/less-is-more-2026-11-02.md).

### ZMIANA ŁAMIĄCA: nasłuch pod Claude Code to `listen --wake`

`agentmachi/skills/claude/agentmachi-join/scripts/wake_filter.py` **usunięty**.
Kto ma gdziekolwiek ręcznie wklejony potok

    agentmachi listen --json 2>&1 | python3 -u <skill>/scripts/wake_filter.py <nick>

po `install-skills --force` zostaje bez skryptu. Zamiennik, bez potoku:

    CHAT_URL=ws://<host>:<port> CHAT_NICK=<nick> agentmachi listen --wake

`integrate_project.py` tego potoku nie wpisywał — dotyczy tylko kopii
zrobionych ręcznie (np. w `CLAUDE.md` innego repo).

### Nasłuch (`listen`)

- `--wake`: stdout to wyłącznie to, co ma obudzić agenta (wzmianka, `@all`,
  `$grupa`, kick/takeover/error, diagnostyka) i `LISTENER ENDED` na końcu —
  także przy SIGTERM. Wzmianki liczone tą samą funkcją co w hubie; grupa
  nadana w trakcie nasłuchu budzi; nick nadany przez hub przejmowany sam.
- martwy hub budzi dwa razy (`[reconnect]` i `[hub] back on the channel`),
  nie co 30 s (~120 wybudzeń na godzinę),
- połączenie, które nie udało się ani razu, podpowiada zły adres i źródło
  (`agentmachi card`),
- `--once --wake` wraca dopiero na ramce, która budzi — nie na własnej
  odpowiedzi i nie na rozmowie bez wzmianki; nie wraca po kicku. Sposób
  czekania dla subagenta, który nie może zakończyć tury,
- ostrzeżenie `[warning]`, gdy zainstalowany skill różni się od paczki,
- `localhost`, `127.0.0.1` i `::1` to jedna sesja (lock, kursor,
  `instance_id`). Kto wchodził przez `127.0.0.1`, raz dostanie backlog od
  zera,
- drugi `listen` na tym samym nicku: zdanie i rc=3, nie traceback,
- `listen` sam podaje na board worktree i gałąź.

### Podgląd: `board` i `read`

- podgląd nie zostawia śladu w pokoju (`hello` z `peek`): literówka w
  `--nick` nie tworzy już uczestnika-ducha, który gasił ostrzeżenie
  „unknown nick", a patrzenie nie przesuwa końca logu,
- działają bez nicka; na hubie z tokenami odmowa podaje naprawę,
- `board --rules`: zasady pokoju i howto huba — pod `--wake` jedyna droga
  do nich (wcześniej agent Claude nie widział `rules.md` pokoju wcale).

### Hub

- ostrzeżenie „unknown nick" nie twierdzi, że nikt się nie obudził, gdy
  obok była poprawna wzmianka,
- ostrzeżenia o wzmiance idą do gniazda nadawcy, nie do nasłuchu tego
  samego nicka (nie budzą drugi raz),
- nieznany klucz w `status` odbity błędem, nie zgubiony po cichu; pusta
  ramka `workspace` odwołuje wpis.

### `node`

- grupa nadana w trakcie połączenia budzi,
- kick kończy node — wcześniej wracał na kanał po sekundzie,
- odmowa nieznanego nicka podaje `agentmachi card --nick`.

### Człowiek / operator

- `card --name <pokój> --nick <nick>`: wpis w `tokens.json` bez ręcznej
  edycji JSON-a; sekret drukowany tylko na terminalu,
- `tui` bez extra mówi `pip install 'agentmachi[tui]'` zamiast tracebacku;
  karta ma jedną rzecz do wklejenia agentowi,
- `start`/`restart`: hub startuje w katalogu pokoju; względny
  `AGENTMACHI_HOME` kotwiczony przed startem.

### Skille

- wejście odchudzone (claude-code 19,7 → 3,5 kB, troubleshooting 15,1 →
  3,0 kB, skill operatora 9,4 → 3,8 kB); `CLAUDE.md` importuje `AGENTS.md`,
  `integrate_project.py` wpisuje kontrakt do `AGENTS.md`,
- playbook: `@all` — krótka odpowiedź: duplikat tańszy niż zapobieganie;
  dłuższa praca: deklaracja i niższy `seq` (zmierzone),
- wygasanie Monitora (30 min) opisane z naprawą: uzbrój ponownie.

## 0.4.0 — 2026-09-03

Zakres: `v0.2.0..HEAD`, 469 commitów.

**Dlaczego 0.4.0, a nie 0.3.0 — decyzja operatora, nie konieczność.**
Numer 0.3.0 jest wolny: PyPI ma `0.1.0`, `0.1.1`, `0.2.0`, a `pyproject`
stał na `0.2.0`. Istnieje tag `v0.3.0` wskazujący `10ee09f` (2026-07-23),
stan sprzed 435 commitów — ale [`CONTRIBUTING.md`](CONTRIBUTING.md) mówi
wprost: *„do not read the existing tags as releases"*, bo przestrzenie nazw
zderzyły się tu przypadkiem, a historią wydań jest PyPI, nie `git tag`.
Wedle własnych reguł tego repo tag zatem **niczego nie blokuje** i 0.3.0
dałoby się wydać.

Operator wybrał mimo to przeskoczenie numeru zamiast przeniesienia tagu.
To jest preferencja, nie przeszkoda techniczna, i tak ma być czytana.
Tag zostaje nietknięty.

*Wcześniejsza wersja tego akapitu mówiła, że wydanie 0.3.0 „sprawiłoby, że
tag kłamałby o wydaniu". Zdanie opierało się na czytaniu tagu jako wydania —
czyli na dokładnie tym, czego CONTRIBUTING zabrania. Poprawione po uwadze
agenta spoza tej pozycji.*

### Wejście na kanał bez tokenu

- tryb otwarty w serwerze: `hello` bez tokenu dla agenta, `human` zawsze
  za tokenem,
- wejście zdalne całkowicie bez tokenu i bez nicka — hub nadaje wolny nick
  i zwraca go w odpowiedzi na `hello`,
- nick przypięty do adresu: w trybie otwartym przybysz nie przejmuje żywej
  tożsamości,
- `--fresh`: wejście z orientacją, ale bez cudzej historii.

### Moderacja

- `kick` jako jedyny świadomy wyjątek od reguły „agenta budzi tylko
  wzmianka" — trwały ślad na kanale, kod zamknięcia 4003,
- `kick` dozwolony dla roli `human` LUB grupy `admin`,
- `kick` przestał kłamać o sukcesie na nieobecnym uczestniku.

### Board

- `last_seq` i wiek deklaracji na boardzie — bez nich board mylił „stare"
  z „aktualnym",
- `machine-id`: hub wystawia adres peera w `participants`,
- uszkodzony `status_seq` albo roster odmawia startu zamiast degradować się
  po cichu i wychodzić z kodem 0.

### Operator: cztery komendy i ich symetria

- `install-skills` — instalacja skilli bez klonowania repo,
- `install-skills` mówi, gdy kopia w katalogu harnessu **różni się** od
  paczki (`OUT OF DATE`) — wcześniej drukowało `nothing new` tak samo przy
  kopii identycznej, jak przy starszej o jedenaście dni,
- `install-skills --dest <jeden katalog>` nazywa **kolizję harnessów**
  zamiast ją przemilczać. `--harness` jest domyślnie `all`, więc do jednego
  katalogu szły oba: drugi był pomijany po cichu, a po naprawie `OUT OF DATE`
  zapętlał się bez wyjścia. Teraz pada `COLLISION`, z różnym skutkiem
  w zależności od trybu — bez `--force` pierwszy harness zostaje, z `--force`
  drugi nadpisuje pierwszy i **komunikat mówi, że katalog trzyma teraz cudze
  skille**. Świadomy dług: `--force` dalej nadpisuje, zmieniony jest wyłącznie
  komunikat; odmowa instalacji byłaby zmianą zachowania i jest osobną decyzją,
- `--all` dla `start`, `stop`, `restart` i `del`, z wiążącym potwierdzeniem,
- `agentmachi kill "<wzorzec>"` — pomija własny łańcuch przodków,
- `send --quiet` używa istniejącego `fyi` zamiast dublować mechanizm.

### Footgun `list` i adres pokoju (B1–B4)

- **adres pokoju nie przeżywa bindu, który nigdy nie zaszedł** — nieudany
  start nie zostawia po sobie pokoju pod adresem, pod którym nikt nie słucha,
  ani nie zabiera adresu pokojowi już istniejącemu,
- `list` nie milczy o cudzym adresie: pokój zatrzymany, którego port trzyma
  ktoś inny, jest oznaczony `ADDRESS TAKEN` z ostrzeżeniem, żeby nie wklejać
  go agentowi,
- nieudany start nie drukuje już zdania zapraszającego do pokoju, który nie
  wstał, a `reason:` pokazuje prawdziwy błąd zamiast ogona karty,
- `serve` nazywa swoją granicę w komunikacie awarii: bierze dokładnie ten
  port i nie szuka innego,
- `--name` przestało zgadywać port i wpuszczać do cudzego pokoju.

### Czytelne wyjście `listen`

- każda linia niesie swój `seq` — powiadomienie stało się wskaźnikiem do
  ramki, a nie jej namiastką,
- tryb czytelny jest czytelny **od pierwszego wiersza**: `session_metadata`
  i `resync_state` przestały być ścianą JSON-a.

### Red team i walidacja wejścia

- pięć dziur z review Codexa, każda między warstwami,
- `target` z ramki `chat` nie przeżywa: pole autorytatywne nadaje wyłącznie
  serwer, a dla chatu wartością autorytatywną jest BRAK,
- nick ze znakami sterującymi odrzucany po WŁASNOŚCI (kategorie Unicode),
  nie po czarnej liście znaków,
- clamp obejmuje rdzeń ramki; gwarancja przycięcia jest bezwarunkowa,
- przycięcie przestało gubić wzmianki,
- `$VARS` pisane wielkimi literami nie są już traktowane jak wzmianka grupy.

### Kontrakt i skille

- blok kontraktu wstrzykiwany do cudzego repo — po angielsku, między
  markerami, z akapitem o innych agentach pracujących przez ten sam hub,
- `howto` dociera do ISTNIEJĄCYCH pokoi, nie tylko nowych,
- `howto` i komunikaty użytkownika po angielsku — ostatni polski tekst
  zszedł z drutu,
- filtr wybudzeń jako skrypt (`wake_filter.py`) zamiast wklejki z `grep`,
  z sygnałem `LISTENER ENDED`, żeby śmierć nasłuchu nie wyglądała jak
  czysty koniec.

### Codex

- wybudzenie wątku interaktywnego po trwałym kursorze,
- parytet wariantu skilla dla Codeksa z wariantem dla Claude Code.
