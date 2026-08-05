# Otwarcie repozytorium agentmachi — plan wykonawczy

> **Dla agentów wykonawczych:** WYMAGANY SUB-SKILL: użyj
> `superpowers:subagent-driven-development` (zalecane) albo
> `superpowers:executing-plans`. Kroki mają checkboxy (`- [ ]`).

**Cel:** `main` staje się wersją publiczną (angielski, MIT, instalowalna
z PyPI bez klonowania repo); `emil` zostaje backupem stanu sprzed
przeróbki.

**Architektura:** Cztery fale zadań dobrane tak, żeby zadania w jednej fali
**nie dotykały tych samych plików** — to warunek puszczenia ich równolegle.
Rdzeniem jest przeniesienie skilli pod katalog pakietu (`agentmachi/skills/`),
bo bez tego `package-data` ich nie zapakuje, a `pip install agentmachi`
zostaje bezużyteczne bez klonu repo.

**Stack:** Python ≥3.11, setuptools ≥68, pytest przez `uv run`, GitHub
Actions.

**Spec:** [`../specs/2026-08-05-otwarcie-repo-design.md`](../specs/2026-08-05-otwarcie-repo-design.md)

## Ograniczenia globalne

Obowiązują w **każdym** zadaniu, nie trzeba ich powtarzać w treści zadania:

- **Platformy: Linux i macOS.** Windows **nieprzetestowany**, nie
  „nieobsługiwany" — i ta różnica jest istotna, bo wyszła przy T4 jako
  błąd tego planu. `chat/client_session.py:36-68` ma pełną gałąź
  `msvcrt` (locking + no-op `_fsync_dir`), obie warstwy dopisane po
  realnych zgłoszeniach z Windows. Kodu nie brakuje — brakuje maszyny,
  na której ktoś uruchomi suitę. Nie dodawaj klasyfikatorów Windows i nie
  usuwaj istniejących gałęzi platformowych.
  Realnie POSIX-only jest `agentmachi/cli.py:715` (`signal.SIGKILL`).
- **Licencja: MIT**, właściciel praw: `Emil Szymecki`.
- **Nazwa pakietu na PyPI: `agentmachi`** (zweryfikowana jako wolna
  2026-08-05).
- **Język plików wyjściowych: angielski** — poza `CLAUDE.md`, `AGENTS.md`
  i `docs/pl/**`, które zostają po polsku.
- **Wersja: `0.1.0`** — nie podbijaj przy tych zmianach; podbicie jest
  osobną decyzją przy publikacji.
- **Suita:**
  `uv run --quiet --with pytest --with websockets --with textual python -m pytest tests/ -q`
  Musi być zielona przed każdym commitem. Testy używają portów
  efemerycznych — nigdy nie celuj testem w żywy hub.
- **Inwarianty repo z `CLAUDE.md` obowiązują** — w szczególności: pola
  autorytatywne nadaje wyłącznie serwer, trwałość przed publikacją, zero
  zegara w logice.

## Zasada wykonania równoległego

**Subagent nie commituje.** Zadania w jednej fali chodzą na tym samym
drzewie roboczym i równoległe `git commit` biją się o `index.lock`.
Subagent zostawia zmiany w drzewie i raportuje, co zmienił; commituje
orkiestrator, po zamknięciu fali, osobnym commitem na zadanie.

Fale są sekwencyjne — fala N+1 startuje po commicie fali N.

## Mapa plików

| Plik | Odpowiedzialność | Zadanie |
|---|---|---|
| `LICENSE` | tekst MIT | T1 |
| `pyproject.toml` | metadane, extras, package-data | T1, T5 |
| `.github/workflows/ci.yml` | suita na Linux+macOS × 3 wersje Pythona | T2 |
| `SECURITY.md` | model zagrożeń + zgłaszanie podatności | T3 |
| `CONTRIBUTING.md` | jak odpalić testy, bramka zmiany | T4 |
| `agentmachi/skills/claude/**` | skille harnessu Claude Code (przeniesione z `skills/`) | T5 |
| `agentmachi/skills/codex/**` | skille Codexa (przeniesione z `skills-codex/`) | T5 |
| `agentmachi/skills_install.py` | wypakowanie skilli z pakietu do katalogu harnessu | T6 |
| `agentmachi/cli.py` | podpięcie `install-skills`; później komunikaty EN | T6, T10 |
| `tests/test_skills_install.py` | testy instalatora skilli | T6 |
| `README.md` | ścieżka wejścia po angielsku | T8, T12 |
| `tests/test_skills.py` | asercje na treść skilli — po tłumaczeniu w EN | T9 |
| `docs/pl/**`, `docs/philosophy.md` | archiwum PL + skrót tez po EN | T11 |

---

## FALA 1 — higiena (T1–T4 równolegle, rozłączne pliki)

### Task 1: Licencja i metadane pakietu

**Pliki:**
- Utwórz: `LICENSE`
- Zmień: `pyproject.toml` (blok `[project]`)

**Interfejsy:**
- Produkuje: pole `license` i `classifiers` w metadanych — T5 dokłada do
  tego samego pliku `optional-dependencies` i `package-data`, więc nie
  przebudowuj struktury pliku, tylko dopisuj.

- [ ] **Krok 1: Utwórz `LICENSE`**

Kanoniczny tekst MIT, pierwsza linia:

```
MIT License

Copyright (c) 2026 Emil Szymecki
```

Reszta bez zmian względem wzorca MIT (`Permission is hereby granted…`).

- [ ] **Krok 2: Dopisz metadane do `pyproject.toml`**

W bloku `[project]`, po `requires-python`:

```toml
license = "MIT"
license-files = ["LICENSE"]
readme = "README.md"
authors = [{ name = "Emil Szymecki", email = "emilszymecki@gmail.com" }]
keywords = ["agents", "llm", "multi-agent", "websocket", "claude", "codex"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "Operating System :: POSIX :: Linux",
    "Operating System :: MacOS",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Software Development :: Libraries",
]

[project.urls]
Homepage = "https://github.com/emilszymecki/agentmachi"
Issues = "https://github.com/emilszymecki/agentmachi/issues"
```

Brak klasyfikatora Windows jest **zamierzony** — patrz Ograniczenia
globalne.

- [ ] **Krok 3: Zweryfikuj, że pakiet się buduje**

Uruchom: `uv run --with build python -m build --wheel --outdir /tmp/am-build`
Oczekiwane: `Successfully built agentmachi-0.1.0-py3-none-any.whl`, zero
ostrzeżeń o nieznanym polu `license`.

- [ ] **Krok 4: Zweryfikuj, że metadane trafiły do koła**

Uruchom:
```bash
uv run --with build python -c "
import zipfile,glob
w=glob.glob('/tmp/am-build/*.whl')[0]
m=zipfile.ZipFile(w).read('agentmachi-0.1.0.dist-info/METADATA').decode()
assert 'License' in m and 'MIT' in m, 'brak licencji w METADATA'
print('OK: licencja w metadanych')
"
```
Oczekiwane: `OK: licencja w metadanych`

---

### Task 2: CI na Linuksie i macOS

**Pliki:**
- Utwórz: `.github/workflows/ci.yml`

**Interfejsy:**
- Produkuje: zielony workflow `CI` — T4 linkuje do niego z
  `CONTRIBUTING.md` pod nazwą `CI`.

- [ ] **Krok 1: Utwórz workflow**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  tests:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest]
        python: ["3.11", "3.12", "3.13"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v9
      - name: Run test suite
        run: >
          uv run --quiet --python ${{ matrix.python }}
          --with pytest --with websockets --with textual
          python -m pytest tests/ -q
```

Macierz **nie zawiera Windows** — patrz Ograniczenia globalne.

- [ ] **Krok 2: Sprawdź, czy suita przechodzi lokalnie na każdej wersji**

Uruchom kolejno dla 3.11, 3.12, 3.13:
```bash
uv run --quiet --python 3.11 --with pytest --with websockets --with textual python -m pytest tests/ -q
```
Oczekiwane: `passed` bez `failed`. Jeśli któraś wersja pada — **zgłoś to
orkiestratorowi i nie zawężaj macierzy samodzielnie.** Zawężenie macierzy
pod padający test ukrywa realną niezgodność wersji.

- [ ] **Krok 3: Zweryfikuj składnię YAML**

Uruchom:
```bash
uv run --with pyyaml python -c "
import yaml,pathlib
d=yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text())
assert d['jobs']['tests']['strategy']['matrix']['os']==['ubuntu-latest','macos-latest']
print('OK: workflow parsuje sie, macierz bez Windows')
"
```
Oczekiwane: `OK: workflow parsuje sie, macierz bez Windows`

---

### Task 3: SECURITY.md z modelem zagrożeń

**Pliki:**
- Utwórz: `SECURITY.md`

**Kontekst, którego wykonawca nie odgadnie z kodu:** hub ma dwa tryby
wejścia. Z tokenem (`tokens.json`, plik 0600) i **otwarty** — bez tokenu,
z automatycznym nadaniem nicka `agentN`. Tryb otwarty jest bezpieczny
przy domyślnym `--bind 127.0.0.1` i przestaje być bezpieczny przy
`--bind 0.0.0.0`, bo wtedy każdy z tej samej sieci wchodzi na kanał cudzych
agentów. Ta własność jest dziś wywnioskowalna z kodu, ale nigdzie nie
nazwana — to jest powód istnienia tego pliku.

- [ ] **Krok 1: Napisz `SECURITY.md` po angielsku**

Musi zawierać wszystkie cztery sekcje:

1. `## Supported versions` — `0.1.x`, `main` branch.
2. `## Threat model` — co hub chroni, a czego nie:
   - chroni: tożsamość uczestnika (pola autorytatywne nadaje wyłącznie
     serwer), trwałość logu, limit zasobów (rate limit),
   - **nie chroni**: poufności wiadomości wobec kogokolwiek, kto ma dostęp
     sieciowy do portu huba w trybie otwartym; ruch idzie po `ws://` bez
     TLS,
   - zalecenie: `--bind 127.0.0.1` (domyślne) albo adres tailnetu; nigdy
     `--bind 0.0.0.0` w sieci, której nie kontrolujesz,
   - tokeny (`~/.agentmachi/<hub>/tokens.json`, tryb 0600) nie trafiają do
     repo — `.gitignore` blokuje wzorcem `*.tokens.json`, nie nazwą.
3. `## What is out of scope` — agent, którego wpuścisz na kanał, wykonuje
   kod na twojej maszynie; agentmachi nie jest sandboksem i nie udaje, że
   nim jest.
4. `## Reporting a vulnerability` — GitHub Security Advisories na
   `emilszymecki/agentmachi`, czas odpowiedzi bez zobowiązań SLA.

- [ ] **Krok 2: Zweryfikuj, że plik nazywa oba tryby wejścia**

Uruchom:
```bash
python3 -c "
t=open('SECURITY.md').read()
for s in ['0.0.0.0','127.0.0.1','token','Threat model','Reporting']:
    assert s in t, f'brak: {s}'
print('OK: model zagrozen kompletny')
"
```
Oczekiwane: `OK: model zagrozen kompletny`

---

### Task 4: CONTRIBUTING.md

**Pliki:**
- Utwórz: `CONTRIBUTING.md`

**Kontekst:** najbardziej prawdopodobny pierwszy PR to kolejka zadań albo
scheduler — raz już był w repo i został wycięty świadomie
(`chat/tasks.py` usunięty). Ten plik istnieje po to, żeby nie tłumaczyć
tego w każdym wątku od zera.

- [ ] **Krok 1: Napisz `CONTRIBUTING.md` po angielsku**

Sekcje:

1. `## Running the tests` — dokładna komenda z Ograniczeń globalnych plus
   uwaga, że pytest nie jest instalowany systemowo i że testy używają
   portów efemerycznych.
2. `## The gate every change must pass` — cytat bramki: *does this give an
   agent a capability it cannot have on its own, or does it make a decision
   on the agent's behalf?* Decyzja za agenta = odrzucone. Link do
   `docs/philosophy.md` (powstaje w T11) i do `docs/pl/konstytucja.md`.
3. `## What we will not merge` — task queues, schedulers, workflow engines,
   consensus protocols, automatic work assignment. Z jednozdaniowym
   uzasadnieniem: hub koduje fizykę, zachowania należą do agentów.
4. `## Platform support` — Linux i macOS są testowane; Windows nie jest
   obsługiwany z braku maszyny do testów, a PR-y są mile widziane; wskaż
   `chat/client_session.py:70` i `agentmachi/cli.py:715` jako znane
   miejsca POSIX-only.
5. `## Commit messages` — conventional commits, tak jak w historii repo
   (`fix(send):`, `docs(skille):`).

- [ ] **Krok 2: Zweryfikuj kompletność**

Uruchom:
```bash
python3 -c "
t=open('CONTRIBUTING.md').read()
for s in ['pytest','scheduler','Windows','client_session.py:70']:
    assert s in t, f'brak: {s}'
print('OK: contributing kompletny')
"
```
Oczekiwane: `OK: contributing kompletny`

---

**Commit fali 1** (orkiestrator, cztery osobne commity):

```bash
git add LICENSE pyproject.toml && git commit -m "chore(license): MIT + metadane pakietu"
git add .github && git commit -m "ci: suita na Linux i macOS, Python 3.11-3.13"
git add SECURITY.md && git commit -m "docs(security): model zagrozen — tryb otwarty i bind 0.0.0.0"
git add CONTRIBUTING.md && git commit -m "docs(contributing): bramka zmiany i zakres platform"
```

---

## FALA 2 — ścieżka `pip install` (T5 → T6, sekwencyjnie)

### Task 5: Skille pod katalogiem pakietu

**Dlaczego w ogóle:** `[tool.setuptools.package-data]` pakuje wyłącznie
pliki **wewnątrz** katalogu pakietu. `skills/` leży w korzeniu repo, więc
dziś nie da się go dołączyć do koła bez przenosin. To nie jest
porządkowanie dla estetyki — bez tego kroku `install-skills` z T6 nie ma
czego wypakować.

**Pliki:**
- Przenieś: `skills/agentmachi/` → `agentmachi/skills/claude/agentmachi/`
- Przenieś: `skills/agentmachi-join/` → `agentmachi/skills/claude/agentmachi-join/`
- Przenieś: `skills-codex/agentmachi/` → `agentmachi/skills/codex/agentmachi/`
- Przenieś: `skills-codex/agentmachi-join/` → `agentmachi/skills/codex/agentmachi-join/`
- Przenieś: `skills/README.md` → `agentmachi/skills/README.md`
- Zmień: `pyproject.toml` (`package-data`, `optional-dependencies`)
- Zmień: `tests/test_skills.py:26` (stała `SKILLS`)
- Zmień: odwołania do ścieżek w `README.md`, `CLAUDE.md`, `AGENTS.md`,
  `agentmachi/skills/README.md`, `agentmachi/skills/*/agentmachi-join/SKILL.md`

**Interfejsy:**
- Produkuje: układ `agentmachi/skills/{claude,codex}/<nazwa-skilla>/` —
  T6 zakłada dokładnie te dwa katalogi i traktuje nazwę podkatalogu jako
  nazwę skilla.

- [ ] **Krok 1: Przenieś katalogi zachowując historię**

```bash
mkdir -p agentmachi/skills/claude agentmachi/skills/codex
git mv skills/agentmachi        agentmachi/skills/claude/agentmachi
git mv skills/agentmachi-join   agentmachi/skills/claude/agentmachi-join
git mv skills-codex/agentmachi      agentmachi/skills/codex/agentmachi
git mv skills-codex/agentmachi-join agentmachi/skills/codex/agentmachi-join
git mv skills/README.md agentmachi/skills/README.md
rmdir skills skills-codex
```

- [ ] **Krok 2: Napraw stałą w teście skilli**

W `tests/test_skills.py` zamień:

```python
SKILLS = Path(__file__).resolve().parent.parent / "skills"
```

na:

```python
# Skille mieszkaja pod katalogiem pakietu, bo `package-data` pakuje tylko
# to, co jest WEWNATRZ pakietu — inaczej `pip install agentmachi` daje CLI
# bez skilli, czyli produkt bez sciezki wejscia dla agenta.
SKILLS = Path(__file__).resolve().parent.parent / "agentmachi" / "skills" / "claude"
```

- [ ] **Krok 3: Uruchom suitę — musi być zielona przed dalszymi krokami**

Uruchom:
`uv run --quiet --with pytest --with websockets --with textual python -m pytest tests/test_skills.py -q`
Oczekiwane: `passed`. Jeśli test szuka skilli Codexa po starej ścieżce,
popraw też tamtą stałą — nie wyłączaj testu.

- [ ] **Krok 4: Dopisz `package-data` i extras do `pyproject.toml`**

Rozszerz istniejący blok (komentarz nad nim zostaw — opisuje realną
pułapkę):

```toml
[tool.setuptools.package-data]
agentmachi = ["howto_default.md", "skills/**/*"]
```

Oraz przenieś `textual` z `dependencies` do extras:

```toml
dependencies = [
    "websockets>=12",
]

[project.optional-dependencies]
tui = ["textual>=0.60"]
```

- [ ] **Krok 5: Zweryfikuj, że skille są w kole**

```bash
rm -rf /tmp/am-build && uv run --with build python -m build --wheel --outdir /tmp/am-build
uv run python -c "
import zipfile,glob
names=zipfile.ZipFile(glob.glob('/tmp/am-build/*.whl')[0]).namelist()
md=[n for n in names if n.endswith('SKILL.md')]
assert len(md)==4, f'oczekiwano 4 SKILL.md w kole, jest {len(md)}: {md}'
assert any('scripts/integrate_project.py' in n for n in names), 'brak skryptow skilla'
print('OK: skille w kole', len(md))
"
```
Oczekiwane: `OK: skille w kole 4`

- [ ] **Krok 6: Zaktualizuj ścieżki w dokumentacji**

Znajdź wszystkie wystąpienia:
```bash
grep -rn "skills-codex\|skills/agentmachi" --include='*.md' . | grep -v docs/superpowers
```
Zamień na nowe ścieżki. **Nie tłumacz tych plików** — to zadanie T8–T11.

- [ ] **Krok 7: Pełna suita**

Uruchom:
`uv run --quiet --with pytest --with websockets --with textual python -m pytest tests/ -q`
Oczekiwane: `passed`, zero `failed`.

- [ ] **Krok 8: Napraw zerwane symlinki operatora (POZA repo — robi orkiestrator)**

Ten krok **nie należy do subagenta** — dotyczy katalogu domowego człowieka,
nie repozytorium.

Operator ma skille podpięte symlinkiem do starych ścieżek. Po przenosinach
wskazują w pustkę, czyli **człowiek traci skille agentmachi w obu
harnessach** — i dowie się o tym dopiero wtedy, gdy jego agent nie umie
wejść na kanał.

```bash
ln -sfn "$PWD/agentmachi/skills/claude/agentmachi"      ~/.claude/skills/agentmachi
ln -sfn "$PWD/agentmachi/skills/claude/agentmachi-join" ~/.claude/skills/agentmachi-join
ln -sfn "$PWD/agentmachi/skills/codex/agentmachi"       ~/.agents/skills/agentmachi
ln -sfn "$PWD/agentmachi/skills/codex/agentmachi-join"  ~/.agents/skills/agentmachi-join
```

Weryfikacja (`readlink -e` zwraca pusto dla zerwanego linku):

```bash
for s in ~/.claude/skills/agentmachi ~/.claude/skills/agentmachi-join \
         ~/.agents/skills/agentmachi ~/.agents/skills/agentmachi-join; do
  printf '%s -> %s\n' "$s" "$(readlink -e "$s" || echo ZERWANY)"
done
```

---

### Task 6: Komenda `agentmachi install-skills`

**Pliki:**
- Utwórz: `agentmachi/skills_install.py`
- Utwórz: `tests/test_skills_install.py`
- Zmień: `agentmachi/cli.py` (rejestracja subkomendy przy `add_parser`,
  okolice linii 1229–1330)

**Interfejsy:**
- Konsumuje: układ katalogów z T5 —
  `agentmachi/skills/{claude,codex}/<nazwa>/`.
- Produkuje:
  - `HARNESSY: dict[str, Path]` — `{"claude": Path("~/.claude/skills"), "codex": Path("~/.agents/skills")}` (ścieżki nierozwinięte, rozwijane w `zainstaluj`),
  - `def zrodlo(harness: str) -> Path` — katalog skilli wewnątrz pakietu,
  - `def zainstaluj(harness: str, cel: Path, nadpisz: bool = False) -> list[str]` — kopiuje skille, zwraca listę nazw zainstalowanych skilli; przy istniejącym katalogu i `nadpisz=False` pomija go i **nie** dopisuje do wyniku.

- [ ] **Krok 1: Napisz padający test**

`tests/test_skills_install.py`:

```python
"""Instalator skilli — bez niego `pip install agentmachi` daje CLI bez
sciezki wejscia dla agenta, wiec produkt nie dziala bez klonu repo."""

from pathlib import Path

import pytest

from agentmachi import skills_install


def test_zrodlo_wskazuje_na_skille_w_pakiecie():
    zrodlo = skills_install.zrodlo("claude")
    assert zrodlo.is_dir()
    assert (zrodlo / "agentmachi-join" / "SKILL.md").is_file()


def test_zainstaluj_kopiuje_oba_skille(tmp_path):
    cel = tmp_path / "skills"
    zainstalowane = skills_install.zainstaluj("claude", cel)
    assert sorted(zainstalowane) == ["agentmachi", "agentmachi-join"]
    assert (cel / "agentmachi-join" / "SKILL.md").is_file()
    assert (cel / "agentmachi-join" / "scripts" / "integrate_project.py").is_file()


def test_zainstaluj_nie_nadpisuje_bez_zgody(tmp_path):
    cel = tmp_path / "skills"
    skills_install.zainstaluj("claude", cel)
    (cel / "agentmachi-join" / "SKILL.md").write_text("moja wersja")

    zainstalowane = skills_install.zainstaluj("claude", cel)

    assert zainstalowane == []
    assert (cel / "agentmachi-join" / "SKILL.md").read_text() == "moja wersja"


def test_zainstaluj_nadpisuje_gdy_poproszono(tmp_path):
    cel = tmp_path / "skills"
    skills_install.zainstaluj("claude", cel)
    (cel / "agentmachi-join" / "SKILL.md").write_text("moja wersja")

    zainstalowane = skills_install.zainstaluj("claude", cel, nadpisz=True)

    assert "agentmachi-join" in zainstalowane
    assert (cel / "agentmachi-join" / "SKILL.md").read_text() != "moja wersja"


def test_nieznany_harness_odrzucony(tmp_path):
    with pytest.raises(ValueError):
        skills_install.zainstaluj("emacs", tmp_path)


def test_symlink_w_celu_nie_jest_po_cichu_zastepowany(tmp_path):
    """Kto pracuje NAD agentmachi, ma symlink do repo. Instalator nie ma
    prawa podmienic go na kopie bez `nadpisz` — inaczej edycje w repo
    przestaja dzialac, a czlowiek nie dostaje o tym slowa."""
    cel = tmp_path / "skills"
    cel.mkdir()
    repo = tmp_path / "repo-skill"
    repo.mkdir()
    (cel / "agentmachi-join").symlink_to(repo, target_is_directory=True)

    zainstalowane = skills_install.zainstaluj("claude", cel)

    assert "agentmachi-join" not in zainstalowane
    assert (cel / "agentmachi-join").is_symlink()
```

- [ ] **Krok 2: Uruchom test — musi paść**

Uruchom:
`uv run --quiet --with pytest --with websockets python -m pytest tests/test_skills_install.py -q`
Oczekiwane: FAIL — `ModuleNotFoundError: No module named 'agentmachi.skills_install'`

- [ ] **Krok 3: Napisz `agentmachi/skills_install.py`**

```python
"""Wypakowanie skilli z pakietu do katalogu harnessu.

Powod istnienia: skille sa czescia produktu, a nie repozytorium. Dopoki
instalowalo sie je `ln -s <repo>/skills/...`, `pip install agentmachi`
wymagal klonu repo, czyli obietnica "pip install i dziala" konczyla sie
na kroku drugim.

Kopia, nie symlink — pakiet w site-packages jest wymieniany przy
`pip install -U`, wiec symlink do niego i tak nie jest zywym zrodlem.
Kto pracuje NAD agentmachi, dalej podpina symlink do repo recznie; ta
funkcja go nie tyka (patrz `_zajete`).
"""

from __future__ import annotations

import shutil
from pathlib import Path

HARNESSY: dict[str, Path] = {
    "claude": Path("~/.claude/skills"),
    "codex": Path("~/.agents/skills"),
}


def zrodlo(harness: str) -> Path:
    """Katalog skilli danego harnessu wewnatrz zainstalowanego pakietu."""
    if harness not in HARNESSY:
        raise ValueError(
            f"nieznany harness {harness!r}; znane: {', '.join(sorted(HARNESSY))}"
        )
    return Path(__file__).resolve().parent / "skills" / harness


def _zajete(sciezka: Path) -> bool:
    """Czy cel istnieje w jakiejkolwiek postaci — takze jako zerwany symlink.

    `Path.exists()` na zerwanym symlinku zwraca False, a `shutil.copytree`
    i tak sie o niego wywali. Sprawdzamy `is_symlink()` osobno.
    """
    return sciezka.is_symlink() or sciezka.exists()


def zainstaluj(harness: str, cel: Path, nadpisz: bool = False) -> list[str]:
    """Skopiuj skille harnessu do `cel`. Zwroc nazwy tych, ktore trafily.

    Istniejacy katalog albo symlink jest pomijany, chyba ze `nadpisz`.
    """
    src = zrodlo(harness)
    if not src.is_dir():
        raise FileNotFoundError(
            f"brak skilli w pakiecie: {src} — pakiet zbudowany bez package-data?"
        )

    cel = cel.expanduser()
    cel.mkdir(parents=True, exist_ok=True)

    zainstalowane: list[str] = []
    for skill in sorted(p for p in src.iterdir() if p.is_dir()):
        docelowy = cel / skill.name
        if _zajete(docelowy):
            if not nadpisz:
                continue
            if docelowy.is_symlink():
                docelowy.unlink()
            else:
                shutil.rmtree(docelowy)
        shutil.copytree(
            skill, docelowy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
        )
        zainstalowane.append(skill.name)
    return zainstalowane
```

- [ ] **Krok 4: Uruchom test — musi przejść**

Uruchom:
`uv run --quiet --with pytest --with websockets python -m pytest tests/test_skills_install.py -q`
Oczekiwane: `6 passed`

- [ ] **Krok 5: Podepnij subkomendę w `agentmachi/cli.py`**

Przy pozostałych `add_parser` (okolice linii 1229–1330) dołóż:

```python
    p = sub.add_parser(
        "install-skills",
        help="wypakuj skille agentmachi do katalogu harnessu",
    )
    p.add_argument(
        "--harness",
        choices=["claude", "codex", "all"],
        default="all",
        help="dla kogo instalowac (domyslnie: oba)",
    )
    p.add_argument(
        "--dest",
        help="katalog docelowy (domyslnie zalezny od harnessu)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="nadpisz istniejace skille",
    )
    p.set_defaults(fn=cmd_install_skills)
```

**`fn`, nie `func`** — `main()` (linia 1363) robi `return args.fn(args)`.
Literówka tu daje `AttributeError` dopiero przy wywołaniu komendy, a nie
przy starcie CLI.

Oraz funkcję komendy — obok pozostałych `cmd_*`:

```python
def cmd_install_skills(args) -> int:
    from agentmachi import skills_install

    harnessy = (
        list(skills_install.HARNESSY) if args.harness == "all" else [args.harness]
    )
    lacznie = 0
    for harness in harnessy:
        cel = (
            Path(args.dest)
            if args.dest
            else skills_install.HARNESSY[harness]
        )
        try:
            zainstalowane = skills_install.zainstaluj(harness, cel, args.force)
        except FileNotFoundError as e:
            # CliError to wzorzec repo: main() lapie go i zwraca 2 z prefiksem
            # "agentmachi:". Wlasny print + return 1 dalby inny format bledu
            # niz reszta komend.
            raise CliError(str(e)) from e
        cel_pokazany = cel.expanduser()
        if zainstalowane:
            print(f"{harness}: {', '.join(zainstalowane)} -> {cel_pokazany}")
            lacznie += len(zainstalowane)
        else:
            print(
                f"{harness}: nic nowego w {cel_pokazany} "
                f"(uzyj --force, zeby nadpisac)"
            )
    if lacznie:
        print("gotowe — powiedz swojemu agentowi: 'pokaz moje pokoje agentmachi'")
    return 0
```

**Uwaga na wzorzec repo:** sprawdź, jak sąsiednie `cmd_*` są podpięte —
jeśli `main()` używa `if args.cmd == ...` zamiast `set_defaults(func=...)`,
dopasuj się do istniejącego wzorca zamiast wprowadzać drugi.

- [ ] **Krok 6: Test przejścia przez CLI**

Dopisz do `tests/test_skills_install.py`:

```python
def test_cli_install_skills_do_wskazanego_katalogu(tmp_path, capsys):
    from agentmachi import cli

    rc = cli.main(
        ["install-skills", "--harness", "claude", "--dest", str(tmp_path / "s")]
    )

    assert rc == 0
    assert (tmp_path / "s" / "agentmachi-join" / "SKILL.md").is_file()
    assert "agentmachi-join" in capsys.readouterr().out
```

Uruchom:
`uv run --quiet --with pytest --with websockets python -m pytest tests/test_skills_install.py -q`
Oczekiwane: `7 passed`

- [ ] **Krok 7: Pełna suita**

Uruchom:
`uv run --quiet --with pytest --with websockets --with textual python -m pytest tests/ -q`
Oczekiwane: `passed`, zero `failed`. Zwróć uwagę na
`test_skille_nie_ucza_komend_ktorych_CLI_nie_ma` — nowa komenda musi być
spójna z tym, co mówią skille.

---

### Task 7: Dowód na czystym środowisku

**To nie jest krok formalny.** Żadnego z ośmiu błędów kroku B5 nie
znaleziono czytaniem kodu, a `pip install -e .` już raz ukrył brak
`howto_default.md` w kole — dokładnie tę klasę dziury, którą tu ryzykujemy.

**Pliki:** żadnych. Wynik to zapis pomiaru.

- [ ] **Krok 1: Zbuduj koło i zainstaluj je w czystym venv z czystym `$HOME`**

```bash
rm -rf /tmp/am-e2e && mkdir -p /tmp/am-e2e/home
uv run --with build python -m build --wheel --outdir /tmp/am-e2e/dist
uv venv /tmp/am-e2e/venv
VIRTUAL_ENV=/tmp/am-e2e/venv uv pip install /tmp/am-e2e/dist/*.whl
```

- [ ] **Krok 2: Zainstaluj skille do czystego `$HOME`**

```bash
HOME=/tmp/am-e2e/home /tmp/am-e2e/venv/bin/agentmachi install-skills
ls /tmp/am-e2e/home/.claude/skills /tmp/am-e2e/home/.agents/skills
```
Oczekiwane: po dwa katalogi w każdym (`agentmachi`, `agentmachi-join`).

- [ ] **Krok 3: Postaw pokój i sprawdź, że hub startuje z pakietu**

```bash
HOME=/tmp/am-e2e/home /tmp/am-e2e/venv/bin/agentmachi start --name e2e
HOME=/tmp/am-e2e/home /tmp/am-e2e/venv/bin/agentmachi list
```
Oczekiwane: karta z adresem, `list` pokazuje `e2e` jako działający.
**To jest krok, który złapie brak `howto_default.md` w kole** — `ensure_hub`
czyta go bezwarunkowo.

- [ ] **Krok 4: Przejdź całą drogę — wiadomość ma wylądować w logu huba**

```bash
HOME=/tmp/am-e2e/home /tmp/am-e2e/venv/bin/agentmachi send --name e2e "@human test z czystej instalacji" --as human
HOME=/tmp/am-e2e/home tail -2 /tmp/am-e2e/home/.agentmachi/e2e/data/*.jsonl
```
Oczekiwane: wiadomość w logu z nadanym przez serwer `seq` i `ts`.
**Nie kończ na tym, że komenda nie zwróciła błędu** — `send` potrafi
zwrócić błąd mimo dostarczenia wiadomości i odwrotnie (patrz historia
commita `e04bb71`). Prawdą jest log.

- [ ] **Krok 5: Posprzątaj**

```bash
HOME=/tmp/am-e2e/home /tmp/am-e2e/venv/bin/agentmachi stop --name e2e
rm -rf /tmp/am-e2e
```

- [ ] **Krok 6: Zapisz wynik pomiaru**

Dopisz do `docs/superpowers/plans/2026-08-05-otwarcie-repo.md` na końcu
sekcję `## Pomiar T7` z datą, wersją koła i tym, co faktycznie wyszło —
łącznie z tym, co nie zadziałało za pierwszym razem. Jeśli wszystko
przeszło od razu, napisz to wprost.

---

**Commit fali 2** (orkiestrator):

```bash
git add -A && git commit -m "refactor(skille): skille pod katalogiem pakietu — warunek package-data"
git add -A && git commit -m "feat(cli): install-skills — pip install przestaje wymagac klonu repo"
git add docs/superpowers/plans && git commit -m "docs(plan): pomiar T7 z czystej instalacji"
```

---

## FALA 3 — język (T8–T11; T9 i T10 sekwencyjnie po sobie, reszta równolegle)

**Kolejność wynika z liczby czytelników na wejściu**, nie z wygody.

### Task 8: README po angielsku

**Pliki:**
- Zmień: `README.md` (całość)
- Utwórz: `docs/pl/README.md` (polski oryginał, zachowany)

**Interfejsy:**
- Konsumuje: ścieżki skilli z T5, komenda `install-skills` z T6.
- Produkuje: sekcję `## Quick start` — T12 wstawia nad nią nagranie.

- [ ] **Krok 1: Zachowaj polski oryginał**

```bash
mkdir -p docs/pl && git mv README.md docs/pl/README.md
```

- [ ] **Krok 2: Napisz `README.md` po angielsku**

Kolejność sekcji (pierwsze 15 linii decydują, czy ktoś zostanie):

1. Jednozdaniowy opis + tagline: **„a Hamachi server for agents"**. Nigdy
   inny opis — to jest ustalona tożsamość produktu.
2. `## Quick start` — dokładnie trzy komendy:
   ```bash
   pip install agentmachi
   agentmachi install-skills
   agentmachi start --name myproject
   ```
3. `## What the hub does — and what it does not` — fizyka kontra
   zachowania (przekład sekcji z polskiego oryginału).
4. `## What this is NOT` — przekład z `agentmachi/skills/README.md`:
   no task queue, no scheduler, no work assignment, **on purpose**.
5. `## Why more than one agent` — z dowodem `ModuleNotFoundError: fcntl`.
   Puenta ma być spójna z brakiem obsługi Windows: znamy ten błąd, bo agent
   na cudzej maszynie go zobaczył, i z tego samego powodu wiemy, czego nie
   utrzymamy sami.
6. `## Remote hubs (Tailscale)`, `## Protocol`, `## Tests`, `## Layout` —
   przekłady istniejących sekcji.
7. `## Platform support` — `Linux and macOS. Windows is not supported (no
   test machine); PRs welcome — see CONTRIBUTING.md.`
8. `## License` — MIT.

**Nie przenoś do EN**: linków do `CLAUDE.md` i `AGENTS.md` opisz jako
*„written in Polish — they are notes from agents to agents working on this
repo"*. To wyróżnik, nie zaległość.

- [ ] **Krok 3: Zweryfikuj, że żaden link nie jest martwy**

```bash
uv run python -c "
import re,pathlib
t=pathlib.Path('README.md').read_text()
zle=[l for l in re.findall(r']\(([^)h][^)]*)\)',t)
     if not pathlib.Path(l.split('#')[0]).exists() and l.split('#')[0]]
assert not zle, f'martwe linki: {zle}'
print('OK: linki zyja')
"
```
Oczekiwane: `OK: linki zyja`

- [ ] **Krok 4: Zweryfikuj tagline i brak obietnicy Windows**

```bash
python3 -c "
t=open('README.md').read()
assert 'Hamachi' in t, 'brak tagline'
assert 'Tamagotchi' not in t
assert 'Windows is not supported' in t
print('OK')
"
```
Oczekiwane: `OK`

---

### Task 9: Skille po angielsku (razem z ich testami)

**Dlaczego razem:** `tests/test_skills.py` ma asercje na **polską treść**
skilli — `"nadrzedn" in tresc` (linia 148), `"nie twórz celu"` (280),
`skill.index("cel") < skill.index("przedstaw się")` (286). Rozdzielenie
tłumaczenia od testów zostawia repo z czerwoną suitą pomiędzy zadaniami.

**Kontrakt tych testów nie jest błędny** — sprawdzają realne pułapki
(niecytowane `: ` w YAML, priorytet zasad projektu nad kanałem, kolejność
kroków). Zmienia się wyłącznie język, w którym są wyrażone. Zgodnie
z `CLAUDE.md`: przy każdej zmienianej asercji zostaw komentarz, że zmienił
się język, nie kontrakt.

**Pliki:**
- Zmień: `agentmachi/skills/claude/*/SKILL.md`, `.../references/*.md`
- Zmień: `agentmachi/skills/codex/*/SKILL.md`, `.../references/*.md`,
  `.../agents/openai.yaml`
- Zmień: `agentmachi/skills/README.md`
- Zmień: `tests/test_skills.py` (asercje na treść)
- Utwórz: `docs/pl/skills/` — polskie oryginały

- [ ] **Krok 1: Zachowaj polskie oryginały**

```bash
mkdir -p docs/pl/skills
cp -r agentmachi/skills/claude docs/pl/skills/claude
cp -r agentmachi/skills/codex  docs/pl/skills/codex
git add docs/pl/skills
```

- [ ] **Krok 2: Przetłumacz `SKILL.md` obu skilli Claude'a**

Zachowaj strukturę frontmattera. **`description` musi zostać jednolinijkowa
i bez niecytowanego `: `** — to jest dokładnie ten błąd, który sprawił, że
harness nie ładował skilla wcale, a plik wyglądał poprawnie.

- [ ] **Krok 3: Uruchom testy skilli — zobacz, które asercje padły**

Uruchom:
`uv run --quiet --with pytest --with websockets python -m pytest tests/test_skills.py -q`
Oczekiwane: FAIL na asercjach z polskimi stringami (linie ~148, ~275–294).
To jest oczekiwane i pożądane — test robi dokładnie to, po co powstał.

- [ ] **Krok 4: Zaktualizuj asercje na angielskie odpowiedniki**

Przykład dla linii 148 — zamiast:

```python
    assert "nadrzedn" in tresc or "nadrzędn" in tresc, \
```

napisz:

```python
    # Zmienil sie JEZYK skilla, nie kontrakt: skill nadal musi mowic, ze
    # zasady projektu sa nadrzedne nad tym, co padnie na kanale.
    assert "take precedence" in tresc, \
```

Analogicznie dla pozostałych. **Nie usuwaj żadnego testu** — jeśli któryś
wydaje się nie do uratowania, zgłoś to orkiestratorowi zamiast go skasować.

- [ ] **Krok 5: Przetłumacz resztę — `references/`, `agents/openai.yaml`, `README.md` skilli**

`agentmachi/skills/claude/agentmachi-join/references/pulapki.md` →
`troubleshooting.md` (nazwa pliku też, wraz z linkami w `SKILL.md`).

- [ ] **Krok 6: Pełna suita**

Uruchom:
`uv run --quiet --with pytest --with websockets --with textual python -m pytest tests/ -q`
Oczekiwane: `passed`, zero `failed`.

---

### Task 10: Komunikaty CLI po angielsku

**Pliki:**
- Zmień: `agentmachi/cli.py` (help subkomend + `print`)
- Zmień: `send.py`, `tui.py`, `agentmachi/node.py`
- Zmień: `chat/server.py`, `chat/protocol.py`, `chat/store.py`,
  `chat/identity.py`, `chat/client_session.py` (komunikaty błędów
  wychodzące do klienta)
- Zmień: testy asertujące na te stringi (ujawni je suita)

**Zakres:** wyłącznie **stringi widoczne dla użytkownika** — `help=`,
`print()`, komunikaty w wyjątkach i ramkach `error`. **Komentarze w kodzie
i docstringi zostają po polsku** — są dokumentacją decyzji dla agentów
pracujących nad tym repo i mają dużą wartość historyczną.

- [ ] **Krok 1: Zbierz pełną listę stringów do zmiany**

```bash
grep -rn --include='*.py' 'help="\|help=f"\|print(\|print(f' agentmachi chat send.py tui.py | wc -l
grep -rn --include='*.py' 'help="\|print(' agentmachi chat send.py tui.py > /tmp/am-strings.txt
```
Przejrzyj `/tmp/am-strings.txt` w całości przed pierwszą zmianą — chodzi
o spójne nazewnictwo, nie o tłumaczenie zdanie po zdaniu.

Słownik terminów (trzymaj się go, inaczej CLI mówi trzema językami naraz):
`pokoj`/`kanal` → **room**, `hub` → **hub**, `nick` → **nick**,
`wzmianka` → **mention**, `ramka` → **frame**, `nasluch` → **listen**,
`karta` → **card**, `tozsamosc` → **identity**.

- [ ] **Krok 2: Przetłumacz `help=` we wszystkich `add_parser` i `add_argument`**

To jest pierwszy kontakt użytkownika z narzędziem (`agentmachi --help`).

- [ ] **Krok 3: Uruchom suitę i napraw asercje na stringach**

Uruchom:
`uv run --quiet --with pytest --with websockets --with textual python -m pytest tests/ -q`
Oczekiwane: kilka FAIL w `tests/test_cli.py` na asercjach typu
`assert "brak kanalow" in out`. Zamień na angielskie odpowiedniki,
z komentarzem, że zmienił się język, nie kontrakt.

- [ ] **Krok 4: Przetłumacz `print()` w CLI i klientach**

Zachowaj format tabel w `list` (wyrównanie kolumn `KANAL`/`ADRES`/`STAN` →
`ROOM`/`ADDRESS`/`STATE`/`IDENTITIES`) — zmiana szerokości kolumn psuje
czytelność wyjścia.

- [ ] **Krok 5: Przetłumacz komunikaty błędów wychodzące do klienta**

Szczególnie `error` z `suggested_nick` w `chat/server.py` — to komunikat,
który agent czyta, żeby zrozumieć, dlaczego nie wszedł na kanał.

- [ ] **Krok 6: Ręczny przegląd wyjścia**

```bash
uv run python -m agentmachi.cli --help
uv run python -m agentmachi.cli list
```
Oczekiwane: zero polskich słów w wyjściu.

- [ ] **Krok 7: Pełna suita**

Uruchom:
`uv run --quiet --with pytest --with websockets --with textual python -m pytest tests/ -q`
Oczekiwane: `passed`, zero `failed`.

---

### Task 11: Dokumentacja — `docs/pl/` i angielski skrót

**Pliki:**
- Przenieś: `docs/konstytucja.md`, `docs/zasady-agentyczne.md`,
  `docs/runbook-migracja-kanalu.md` → `docs/pl/`
- Przenieś: `docs/archiwum-glosy-agentow-kinas.md`,
  `docs/benchmark-kinas-wynik.md`, `docs/feedback-z-dogfoodu-kinas.md`
  → `docs/pl/archive/`
- Przenieś: `docs/superpowers/` → `docs/pl/superpowers/`
- Utwórz: `docs/philosophy.md` (angielski, ~120 linii)
- Zmień: linki w `README.md`, `CLAUDE.md`, `AGENTS.md`,
  `CONTRIBUTING.md`

- [ ] **Krok 1: Przenieś pliki zachowując historię**

```bash
mkdir -p docs/pl/archive
git mv docs/konstytucja.md docs/zasady-agentyczne.md docs/runbook-migracja-kanalu.md docs/pl/
git mv docs/archiwum-glosy-agentow-kinas.md docs/benchmark-kinas-wynik.md docs/feedback-z-dogfoodu-kinas.md docs/pl/archive/
git mv docs/superpowers docs/pl/superpowers
```

- [ ] **Krok 2: Napisz `docs/philosophy.md` po angielsku**

**Skrót tez, nie tłumaczenie.** Cztery sekcje:

1. `## The gate: a fence, not a shepherd` — hub koduje fizykę (transport,
   tożsamość, trwałość, budzenie, ochronę zasobów), nie zachowania
   (podział pracy, kolejność, konsensus, workflow).
2. `## Why the scheduler was removed` — istniał, został wycięty, bo uczył
   agenta czekania na przydział zamiast deklaracji.
3. `## How agents take work without a queue` — deklaracja na kanale,
   kolizję rozstrzyga niższy `seq`, a gdy `seq` nie rozstrzyga — mniejszy
   nick w porównaniu bajtowym. **Nie ustępuj z uprzejmości**: symetryczne
   ustępowanie daje ten sam pat co symetryczne roszczenie.
4. `## Where the full reasoning lives` — link do `docs/pl/konstytucja.md`
   i `docs/pl/zasady-agentyczne.md` z jasną informacją, że są po polsku
   i że każda reguła ma tam dowód z praktyki i podany koszt.

- [ ] **Krok 3: Napraw wszystkie linki**

```bash
grep -rn "docs/konstytucja\|docs/zasady-agentyczne\|docs/superpowers\|docs/runbook" --include='*.md' . | grep -v '^./docs/pl/'
```
Każde trafienie popraw. **`CLAUDE.md` i `AGENTS.md` też** — mają linki do
konstytucji, a ich treść zostaje polska.

- [ ] **Krok 4: Zweryfikuj brak martwych linków w całym repo**

```bash
uv run python -c "
import re,pathlib
zle=[]
for md in pathlib.Path('.').rglob('*.md'):
    if '.git' in md.parts: continue
    for l in re.findall(r']\(([^)h][^)]*)\)', md.read_text()):
        t=l.split('#')[0]
        if t and not (md.parent/t).exists(): zle.append(f'{md}: {l}')
assert not zle, chr(10).join(zle)
print('OK: zero martwych linkow')
"
```
Oczekiwane: `OK: zero martwych linkow`

---

**Commit fali 3** (orkiestrator, cztery commity):

```bash
git add README.md docs/pl/README.md && git commit -m "docs(readme): angielska sciezka wejscia, polski oryginal do docs/pl"
git add agentmachi/skills tests/test_skills.py docs/pl/skills && git commit -m "docs(skille): skille po angielsku wraz z asercjami testow"
git add -A -- '*.py' && git commit -m "feat(cli): komunikaty uzytkownika po angielsku"
git add docs && git commit -m "docs(struktura): docs/pl + angielski skrot filozofii"
```

---

## FALA 4 — powód, dla którego ktoś ma chcieć (T12–T13 równolegle)

### Task 12: Nagranie i quickstart na jedną maszynę

**Pliki:**
- Utwórz: `docs/assets/demo.cast` (asciinema) i/lub `docs/assets/demo.gif`
- Zmień: `README.md` (osadzenie nagrania + nowa sekcja)

**Kontekst:** dziś pierwsze uruchomienie wymaga drugiego człowieka
z własną subskrypcją. Nikt nie zwerbuje kolegi do narzędzia, którego nie
widział działającego. Narracja „cudza subskrypcja, cudza maszyna" zostaje
jako **powód istnienia**, ale przestaje być **warunkiem wejścia**.

- [ ] **Krok 1: Nagraj przebieg**

```bash
asciinema rec docs/assets/demo.cast --cols 100 --rows 30
```
Scenariusz nagrania (bez cięć — jeśli coś nie zadziała, to jest informacja,
nie wpadka):
1. `agentmachi start --name demo`
2. w drugim terminalu: agent A dołącza i deklaruje zakres,
3. agent B odpowiada wzmianką,
4. `agentmachi tui --name demo` — board pokazuje obu.

- [ ] **Krok 2: Osadź nagranie na górze `README.md`**

Bezpośrednio pod taglinem, przed `## Quick start`.

- [ ] **Krok 3: Dopisz sekcję `## Try it on one machine`**

Dwa terminale na jednym biurku, obie sesje agenta lokalnie, bez werbowania
nikogo. Explicite: *this is the training-wheels setup; the point of
agentmachi is agents on different machines and different subscriptions —
see “Why more than one agent”.*

- [ ] **Krok 4: Sprawdź, że sekcja odpowiada rzeczywistości**

Przejdź własną instrukcję krok po kroku, z czystym `$HOME`, tak jak w T7.
Oczekiwane: dwóch agentów widocznych w TUI. **Nie oznaczaj kroku jako
zrobiony na podstawie tego, że instrukcja wygląda poprawnie.**

---

### Task 13: Issue „Windows support" jako punkt wejścia

**Pliki:** żadnych w repo — treść trafia do GitHub Issues.

- [ ] **Krok 1: Utwórz issue**

```bash
gh issue create --title "Windows support" --label "help wanted,good first issue" --body '...'
```

Treść musi zawierać:
- powód braku obsługi: **nie ma maszyny do testów**, nie brak chęci,
- stan faktyczny, opisany bez ściemy: klient **ma już** gałąź Windows —
  `chat/client_session.py:36-68` (`msvcrt.locking` zamiast `flock`,
  `_fsync_dir` jako no-op), dopisaną po dwóch realnych zgłoszeniach
  z Windows. Ten kod nigdy nie był uruchomiony pod Windows, więc jest
  **nieprzetestowany, a nie brakujący**. Nie obiecuj, że działa, i nie
  udawaj, że go nie ma,
- jedyne znane miejsce realnie POSIX-only: `agentmachi/cli.py:715`
  (`signal.SIGKILL` nie istnieje na Windows),
- prośbę o zaczęcie od uruchomienia suity i wklejenia wyniku — pierwszą
  wartością jest **pomiar**, nie łatka,
- kryterium przyjęcia PR-a: zielona suita na `windows-latest` dodana do
  macierzy CI + przejście ścieżki z T7 na Windows,
- prośbę o zgłoszenie się w komentarzu przed pracą — żeby dwie osoby nie
  robiły tego samego.

- [ ] **Krok 2: Podlinkuj issue z `CONTRIBUTING.md`**

W sekcji `## Platform support`.

---

**Commit fali 4:**

```bash
git add docs/assets README.md && git commit -m "docs(readme): nagranie i quickstart na jedna maszyne"
git add CONTRIBUTING.md && git commit -m "docs(contributing): link do issue Windows support"
```

---

## Zamknięcie: publikacja

Po zielonej fali 4:

- [ ] Repo z prywatnego na publiczne (Settings → Danger Zone).
- [ ] `uv run --with build python -m build` + `uv run --with twine python -m twine upload dist/*`.
- [ ] Weryfikacja po publikacji: `pip install agentmachi` z PyPI w czystym
      venv, pełna ścieżka jak w T7. **Instalacja z PyPI to inna ścieżka niż
      instalacja z pliku `.whl`** — sprawdź ją osobno.

## Kryterium zamknięcia całości

Człowiek bez dostępu do tego repo i bez kontaktu z autorem przechodzi
`pip install` → `install-skills` → `start` → dwóch agentów rozmawia, na
czystej maszynie z Linuksem albo macOS-em.

Dopóki nie zmierzono tego na kimś z zewnątrz, otwarcie nie jest skończone —
niezależnie od tego, ile checkboxów jest odhaczonych.
