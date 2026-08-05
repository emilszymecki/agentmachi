# agentmachi — otwarcie repozytorium

Data: 2026-08-05
Status: zatwierdzony kierunek (przed planem wykonawczym)

## Cel

Repo `github.com/emilszymecki/agentmachi` przestaje być prywatne i staje się
projektem, którego **obcy człowiek użyje bez kontaktu z autorem**.

Miara sukcesu jest jedna i jest wąska: **ktoś, kto nigdy nie widział tego
repo, przechodzi od `pip install` do dwóch rozmawiających agentów bez
klonowania repozytorium i bez pytania kogokolwiek o pomoc.**

To NIE jest cel „zdobyć kontrybutorów" ani „zrobić launch". Oba są
świadomie odłożone — patrz *Poza zakresem*.

## Stan wyjściowy (pomiar 2026-08-05)

| Wymiar | Stan |
|---|---|
| kod | 6300 LOC Pythona, 332 commity, 14 plików testowych |
| historia gita | **czysta z sekretów** — `git ls-files` bez tokenów, `.gitignore` wzorcowy |
| `LICENSE` | **brak** — użycie przez osoby trzecie jest formalnie nielegalne |
| `.github/` | **brak** — zero CI |
| nazwa na PyPI | **wolna** (`GET /pypi/agentmachi/json` → 404) |
| język | całość PL: README, docs, skille, komunikaty CLI |
| komunikaty CLI | kilkadziesiąt stringów, kod pisany bez diakrytyków |
| demo | brak screenshotów i nagrań, mimo że produkt ma TUI |

## Rozpoznanie: gdzie naprawdę jest tarcie

Odruchowa lista („licencja, README, CI") pomija blocker, który sam unieważnia
obrany cel.

**`pip install agentmachi` dziś nie wystarcza do niczego.** Pakiet daje CLI,
ale skille — bez których agent nie wie, jak wejść na kanał — mieszkają
w repo i instalują się przez `ln -s <repo>/skills/agentmachi-join ...`.
Użytkownik i tak musi sklonować repozytorium. Obietnica „pip install
i działa" pęka na kroku drugim, zanim ktokolwiek dojdzie do wartości
produktu.

Drugie tarcie jest narracyjne: **wartość agentmachi wymaga dwóch agentów
z różnych subskrypcji**, czyli w praktyce drugiego człowieka. Pierwsze
uruchomienie nie może tego wymagać, bo nikt nie zwerbuje kolegi do
narzędzia, którego jeszcze nie widział działającego.

## Decyzje

**D1. Licencja: MIT.** Najkrótsza, najlepiej rozpoznawana, zero tarcia przy
adopcji firmowej. Apache-2.0 dawałby grant patentowy, ale przy narzędziu
deweloperskim tej wielkości to koszt bez odbiorcy.

**D2. Język: angielski na ścieżce wejścia, polski w archiwum.**
README, `skills/README.md`, oba `SKILL.md` i komunikaty CLI → EN.
`docs/konstytucja.md` i `docs/zasady-agentyczne.md` zostają po polsku
w `docs/pl/`, a ich tezy dostają angielski skrót w `docs/philosophy.md`.
Nie tłumaczymy 800 linii dogfoodu — tłumaczymy wnioski.

`CLAUDE.md` i `AGENTS.md` **zostają po polsku i zostają w korzeniu.**
Repozytorium, w którym agenci piszą instrukcje dla następnych agentów, jest
wyróżnikiem tego projektu, a nie jego zawstydzającym marginesem.

**D3. Platformy: Linux i macOS. Windows nieobsługiwany, świadomie.**
Nie ma maszyny do testów, więc obsługa Windows byłaby obietnicą niemożliwą
do utrzymania. README mówi to wprost, a nie przez przemilczenie.

Konsekwencja, którą trzeba unieść uczciwie: README używa dziś
`ModuleNotFoundError: fcntl` na Windows jako **dowodu wartości** pracy
wieloagentowej. Ta historia zostaje — zmienia się tylko puenta: wiemy o tym
błędzie dlatego, że agent na cudzej maszynie go zobaczył, i dlatego wiemy
też, czego nie utrzymamy sami. To spójne, nie sprzeczne.

Znane miejsca zależne od POSIX, do wpisania w issue „Windows support":
- `chat/client_session.py:70` — `import fcntl` (już lokalny w funkcji, nie
  na poziomie modułu),
- `agentmachi/cli.py:715` — `signal.SIGKILL` (nie istnieje na Windows).

**D4. Skille dystrybuowane z pakietem, nie z klonu.** Nowa komenda
`agentmachi install-skills [--claude|--codex]` wypakowuje skille do
`~/.claude/skills/` i `~/.agents/skills/`. Skille wchodzą do
`[tool.setuptools.package-data]`.

Precedens i pułapka są w repo od dawna: `howto_default.md` musiało tam
trafić dokładnie z tego powodu, a dziura przeżyła do pierwszej instalacji
pakietowej, bo `pip install -e .` czyta z drzewa źródeł i wszystko maskuje.
Ta sama pułapka czeka tu.

Świadoma zmiana wobec dzisiejszej instrukcji: `skills/README.md` każe
robić **symlink, nie kopię**, żeby skill nie rozjechał się z repo.
Instalacja z pakietu z definicji jest kopią — rozjazd naprawia
`pip install -U` i ponowne `install-skills`. Symlink pozostaje ścieżką dla
osób pracujących **nad** agentmachi, nie **z** agentmachi.

**D5. `textual` do extras `[tui]`.** Agent na VPS-ie nie potrzebuje
Textuala, żeby dołączyć do pokoju.

## Zakres prac

### Faza 0 — higiena

- `LICENSE` (MIT) + `license` i `classifiers` w `pyproject.toml`
  (bez klasyfikatora Windows).
- `.github/workflows/ci.yml`: pytest na `ubuntu-latest` i `macos-latest`,
  Python 3.11 / 3.12 / 3.13.
- `SECURITY.md` z **modelem zagrożeń**, nie samym adresem do zgłoszeń.
  Rzecz do napisania wprost: `--bind 0.0.0.0` w połączeniu z trybem otwartym
  (wejście bez tokenu) oznacza, że każdy w tej samej sieci wchodzi na kanał
  cudzych agentów. Dziś ta własność jest wywnioskowalna z kodu i z README,
  ale nigdzie nie nazwana.
- `CONTRIBUTING.md`: jak odpalić testy, jaka jest bramka zmiany („fizyka,
  nie zachowanie"), link do konstytucji.

### Faza 1 — ścieżka pierwszego uruchomienia (rdzeń)

- `agentmachi install-skills` + skille w `package-data`.
- `textual` → extras `[tui]`.
- Publikacja na PyPI.
- **Weryfikacja w czystym venv i czystym `$HOME`**, przez faktyczne przejście
  całej ścieżki: instalacja → `install-skills` → `start` → wejście agenta →
  wiadomość w logu huba. Nie przez inspekcję zawartości koła.

  To wymóg z konstytucji repo, nie ostrożność na wszelki wypadek: żadnego
  z ośmiu błędów kroku B5 nie znaleziono czytaniem kodu, a
  `pip install -e .` już raz ukrył dokładnie tę klasę dziury.

Docelowy quickstart:

```bash
pip install agentmachi
agentmachi install-skills
agentmachi start --name myproject
```

### Faza 2 — język

Kolejność wg liczby czytelników na wejściu: README → `SKILL.md` × 2 →
`skills/README.md` → komunikaty CLI → `docs/philosophy.md` (skrót EN).
Przeniesienie do `docs/pl/`: konstytucja, zasady agentyczne.
Do `docs/pl/archive/`: dogfoody, benchmark, archiwum głosów agentów, plany.

### Faza 3 — powód, dla którego ktoś ma chcieć

- **Nagranie (asciinema lub GIF) na górze README**: agent A deklaruje zakres,
  agent B odpowiada, TUI pokazuje board. Produkt jest wizualny, a dziś nie
  widać go wcale.
- **Quickstart na jedną maszynę** — dwa terminale na jednym biurku, bez
  werbowania drugiego człowieka do pierwszego uruchomienia. Narracja
  „cudza subskrypcja, cudza maszyna" zostaje jako *powód istnienia*, ale
  przestaje być *warunkiem wejścia*.
- Sekcja **„What this is NOT"** wyciągnięta do README. Tekst już istnieje
  w `skills/README.md` („nie przydzielają pracy, nie ma kolejki zadań, to
  świadoma decyzja projektowa") i jest jednym z mocniejszych fragmentów
  dokumentacji tego repo.
- Issue **„Windows support"** z listą miejsc z D3 — konkretny, ograniczony,
  realnie wartościowy punkt wejścia dla pierwszego kontrybutora.

## Poza zakresem (świadomie)

Rebranding, strona www, obraz Dockera, `CODE_OF_CONDUCT.md`, roadmapa,
wersja 1.0, tłumaczenie `docs/` w całości, launch na HN/Reddit/X.

Każde z nich to praca wykonana **przed** pierwszym użytkownikiem z zewnątrz,
czyli dokładnie ten rodzaj „na zapas", który ten projekt odrzuca w innych
miejscach. Launch dodatkowo jest jednorazowy — zużyty przed fazą 1 nie
wróci.

## Ryzyka

1. **Instalacja pakietowa wywali się na czymś, czego nie widać w editable.**
   Prawdopodobieństwo wysokie, precedens w `howto_default.md`. Zbijane
   przejściem całej ścieżki w czystym środowisku (Faza 1), nie inspekcją.
2. **Ktoś odpali hub z `--bind 0.0.0.0` w trybie otwartym i zrobi z tego
   incydent.** Zbijane przez `SECURITY.md` w Fazie 0 — przed upublicznieniem,
   nie po.
3. **Pierwszy PR z kolejką zadań albo schedulerem.** Prawdopodobieństwo
   wysokie: to najbardziej oczywista „brakująca funkcja" tego produktu i już
   raz została wycięta. Zbijane przez `CONTRIBUTING.md`, który podaje bramkę
   i link do konstytucji, zamiast tłumaczenia się w każdym wątku od zera.

## Kryterium zamknięcia

Człowiek bez dostępu do tego repo i bez kontaktu z autorem przechodzi
`pip install` → `install-skills` → `start` → dwóch agentów rozmawia,
na czystej maszynie z Linuksem albo macOS-em.

Dopóki tego nie zmierzono na kimś z zewnątrz, otwarcie nie jest skończone —
niezależnie od tego, ile pozycji z listy jest odhaczonych.
