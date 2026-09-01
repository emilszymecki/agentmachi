# Weryfikacja escrow board-pull — protokół, nie publikacja AFTER

**HEAD pomiaru:** `c8f9fa8`
**Czas pomiaru:** 2026-09-01, pokój `interwizja`
**Wykonał:** sesja Claude Code deklarująca się jako `agent2`, deklaracja `seq 83`.
Której z dwóch równoległych sesji odpowiada — **nie da się ustalić z artefaktów**
(patrz `zasady-agentyczne.md`, wniosek o nierozdzielności sesji). Dlatego poniżej
liczy się wyłącznie to, co każdy odtworzy sam z plików.

**To NIE jest rozliczenie prognoz.** Do niego brakuje prognoz Sola w postaci
złożonej. Poniżej jest wyłącznie to, co dało się sprawdzić 2026-09-01, i to,
czego się nie dało.

## 1. Zobowiązania — OBA ZGODNE

    pilot         sha256(nonce||spec) = 7007402a34a975ef…378cef  == commitments/2026-08-22.txt
    confirmatory  sha256(nonce||spec) = 71efb22b6dbbd291…089feb  == commitments/2026-08-22-2.txt

Metoda konkatenacji jest **przypięta pomiarem, nie przyjęta**: surowe
`cat nonce.txt spec.md` (z newline). Dwa warianty ze `strip()` dają
`e462a48a…` i `77e5cd45…`, czyli nie trafiają w żaden zacommitowany hash.

Odtworzysz:

    cd ~/escrow/<katalog> && cat nonce.txt spec.md | sha256sum

Spec obu przebiegów jest zatem nietknięty od prerejestracji.

## 2. Co NIE jest objęte żadnym hashem

`capture-final-sha256.txt` pokrywa wyłącznie `capture-workspace1.jsonl`
i `capture-workspace2.jsonl`. Poza zamkiem zostają:

    events-meadow1-final.jsonl   events-meadow2-final.jsonl
    merged-meadow1.jsonl         merged-meadow2.jsonl

To są logi po stronie huba — czyli dokładnie te, na których stoi punktacja.

## 3. Skasowanie pokojów źródłowych — co naprawdę przepadło

2026-09-01 na polecenie operatora wykonano `agentmachi del --all --yes-delete`
na sześciu pokojach, w tym `meadow1` i `meadow2`. Sesji wykonującej nie da się
ustalić z artefaktów.

Zmierzone, i to **osłabia ograniczenie, a nie wzmacnia**:

| plik | rekordów | ramek konwersacyjnych | `del` zgłosił |
|---|---|---|---|
| events-meadow1-final.jsonl | 32 | **20** | **20** |
| merged-meadow1.jsonl | 124 | **20** | **20** |
| events-meadow2-final.jsonl | 61 | **37** | **37** |
| merged-meadow2.jsonl | 183 | **37** | **37** |

Liczby zgadzają się co do jednej. Escrow trzyma **dokładnie te ramki
konwersacyjne**, które pokoje miały w chwili kasowania. Różnica w sumie
rekordów to `hello` i `status` (`merged` ma 87 `hello` przy 10 w `events`),
a `merged` jest ścisłym nadzbiorem `events` — sprawdzone po zbiorach `seq`.

**Wniosek:** kasowanie nie zniszczyło treści rozmowy, której nie ma w escrow.
Straciliśmy możliwość NIEZALEŻNEGO re-eksportu z huba, nie zawartość.

## 4. Źródło do weryfikacji krzyżowej — jedno, nie dwa

Poza escrow żyją transkrypty sesji obu workspace'ów confirmatory. Zmierzone
nakładanie treści (bloki >80 znaków) między dwoma plikami w każdym katalogu:

    workspace1: 35 vs 54 bloków -> 2 wspólne (2%)
    workspace2: 17 vs 59 bloków -> 2 wspólne (2%)

Nakładanie jest, więc **niezależnymi świadkami nie są**; jest małe, więc nie są
też dwoma zapisami tego samego. To jeden świadek pocięty na dwa pliki ze szwem
2%. Liczy się je jako JEDNO źródło i sprawdza **pokrycie czasowe**, nie zgodność
między nimi — zgodność na 2% wspólnej treści nie mierzy niczego.

Pokrycie czasowe wystarcza:

    logi huba:            17:32:02 .. 19:00:22
    transkrypt workspace1: 17:28:32 .. 22:50:02
    transkrypt workspace2: 17:28:42 .. 22:50:02

Transkrypty zaczynają się przed pierwszym wpisem huba i kończą po ostatnim.

## 5. Skażenia — zgłoszone same na siebie

- **Kolejność czytania.** Sekcja `## Prognozy` z `spec.md` pilota została
  przeczytana PRZED policzeniem hashu, przy sprawdzaniu cudzego twierdzenia.
  Nie narusza to własności, której hash pilnuje (hash dowodzi, że spec nie
  zmienił się od prerejestracji — to cecha plików, nie kolejności czytania),
  ale deklarowanej dyscypliny „hash najpierw" nie ma już w stanie czystym.
- **Ujawnienie atrybucji.** Drugi uczestnik wymienił na kanale, komu przypisane
  są prognozy, bez cytowania treści. Uznane za nieszkodliwe: znajomość
  autorstwa nie pozwala dopasować specu do wyniku.
- **Rodowód modelu.** Czwarta prerejestrowana prognoza w `spec.md` pilota jest
  podpisana „Sesja przygotowująca setup (Opus 5, Claude Code)", a punktujący
  pracuje na Opus 5. Po sesji stawki nie ma, po modelu jest. Zapisane tutaj,
  nie w przypisie.

## 6. Czego brakuje do rozliczenia

Prognoz Sola w postaci złożonej. `spec.md` ma nagłówek `**Sol — ZAKOTWICZONY**`;
treści nie odczytywano i nie zgadywano.
