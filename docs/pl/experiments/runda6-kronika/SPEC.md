# kronika — specyfikacja (zamrożona)

Narzędzie CLI: z historii repozytorium git robi raport.

Wywołanie (z katalogu tego projektu, pakiet `kronika/`):

    python -m kronika <ścieżka-repo> [--json] [--top N]

Python ≥ 3.10, **tylko biblioteka standardowa** (git wołany jako proces).
Własne testy w `tests/` (pytest). Istnieje osobny zestaw testów
akceptacyjnych, którego nie widzisz; liczy się wyłącznie zachowanie opisane
tutaj.

## Dane

Wszystkie commity osiągalne z `HEAD` repo pod `<ścieżka-repo>`, łącznie
z merge'ami. Daty i godziny **autora, w strefie czasowej autora** (nie UTC,
nie strefa maszyny).

## Błędy

`<ścieżka-repo>` nie istnieje albo nie jest repozytorium git → kod wyjścia 2,
jedno zdanie na stderr, **nic** na stdout.

## `--json` — jeden obiekt JSON na stdout, kod wyjścia 0

    {
      "commits": int,          // wszystkie commity, z merge'ami
      "merges": int,           // commity mające ≥ 2 rodziców
      "first": "YYYY-MM-DD" | null,   // najwcześniejsza data autora
      "last":  "YYYY-MM-DD" | null,   // najpóźniejsza data autora
      "authors": [ {"name": str, "email": str,
                    "commits": int, "added": int, "deleted": int} ],
      "files":   [ {"path": str, "commits": int,
                    "added": int, "deleted": int} ],
      "by_weekday": {"Mon": int, "Tue": int, "Wed": int, "Thu": int,
                     "Fri": int, "Sat": int, "Sun": int},
      "by_hour": {"0": int, "1": int, ..., "23": int}
    }

Reguły:

- **Autor** = adres e-mail (dokładnie jak w commicie). `name` = imię
  z najnowszego (wg daty autora) commita z tym adresem.
- `authors[].commits` liczy wszystkie commity autora, także merge'e.
  `added`/`deleted` = suma linii dodanych/usuniętych w commitach
  **niebędących merge'ami**. Plik binarny liczy się jako 0 linii.
- `authors` sortowane: `commits` malejąco, przy remisie `email` rosnąco.
- `files` — wyłącznie commity niebędące merge'ami. Plik liczy się w commicie,
  jeśli commit go zmienia (także zmiana binarna albo samo przemianowanie).
  Przemianowanie liczy się pod **nową** ścieżką; wcześniejsze commity zostają
  pod starą. `commits` = liczba takich commitów, `added`/`deleted` jak wyżej.
- `files` sortowane: `commits` malejąco, przy remisie `path` rosnąco
  (zwykłe porównanie napisów); obcięte do pierwszych `N` (`--top N`,
  domyślnie 10, `N ≥ 1`).
- `by_weekday`, `by_hour`: liczba commitów (z merge'ami) wg dnia tygodnia
  i godziny daty autora. Zawsze wszystkie 7 i wszystkie 24 klucze.
- Repo bez commitów: `commits` i `merges` 0, `first`/`last` `null`, puste
  listy, wszystkie liczniki 0. Kod wyjścia 0.
- Ścieżki, imiona i treść commitów mogą zawierać spacje, znaki spoza ASCII,
  cudzysłowy i nowe linie.

## Bez `--json` — raport Markdown na stdout, kod wyjścia 0

- Pierwsza linia: `# Kronika: <nazwa katalogu repo>`
- Sekcje (nagłówki dokładnie tak): `## Autorzy`, `## Najgorętsze pliki`,
  `## Rytm`.
- `## Autorzy`: tabela, wiersz na autora, w wierszu jego `name` i `commits`.
- `## Najgorętsze pliki`: tabela, wiersz na plik z `files`, w wierszu `path`
  i `commits`.
