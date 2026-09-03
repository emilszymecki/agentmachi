# Changelog

Format: tematycznie, nie commit po commicie. Każdy wpis opisuje ZMIANĘ
ZACHOWANIA, którą widzi użytkownik albo agent — nie refaktor, który jej nie
zmienia.

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
