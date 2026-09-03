# Raport: lista po audycie 03.09

Wspólny plik dla siedmiu pozycji zleconych przez operatora na kanale `E1`.
Zasady z polecenia: **pozycję robi jeden, weryfikuje drugi na własnej kopii;
nikt nie ocenia własnego zdania; rozbieżności zostają rozbieżnościami**, nie
uzgodnioną wersją. Każdy wpisuje **swoją** pozycję sam.

Sloty 2–7 są puste celowo — zakładający plik nie streszcza cudzej roboty.

---

## 1. Tag `v0.3.0` — rozpoznanie, bez zmian

**Robił:** `nowy` · **HEAD rozpoznania:** `db4f3b8` · **Czas:** 2026-09-03 14:59
**Weryfikuje:** ktoś inny niż `nowy` · **Stan:** czeka na decyzję operatora

Nic nie zmienione: żaden tag nie utworzony, przeniesiony ani skasowany;
`pyproject.toml` i `.github/` nietknięte.

### Fakty

| co | wartość | jak sprawdzić |
|---|---|---|
| `v0.3.0` wskazuje na | `10ee09f`, 2026-07-23 22:05:42 | `git log -1 v0.3.0` |
| typ tagu | adnotowany | `git cat-file -t v0.3.0` |
| pozycja wobec `main` | przodek, **435 commitów** za czubkiem | `git rev-list --count v0.3.0..origin/main` |
| CI a tagi | **nie czyta** — `on: push: branches: [main]`, brak `tags:` | `.github/workflows/ci.yml` |
| CI a publikacja | **nie publikuje** — `build` + `twine check` + inspekcja artefaktu | brak `upload`/`publish`/`gh release` w `.github/` |
| `pyproject` na `main` | `0.2.0` | `grep '^version' pyproject.toml` |
| `pyproject` w `v0.3.0` | `0.1.0` | `git show v0.3.0:pyproject.toml` |
| `pyproject` w `v0.2.0` | `0.1.0` | `git show v0.2.0:pyproject.toml` |
| PyPI, wydane | `0.1.0`, `0.1.1`, `0.2.0` — **`0.3.0` wolne** | odczyt `pypi.org/pypi/agentmachi/json` |

### Co zmienia postać pytania

[`CONTRIBUTING.md`](../../CONTRIBUTING.md) (sekcja o wydaniach) rozstrzyga to
przed nami i nie naszymi słowami:

> **Do not tag releases in git, and do not read the existing tags as releases.**
> `v0.2.0` and `v0.3.0` are roadmap milestones from July 2026 (the B3–B7
> merges); `pyproject.toml` says `version = "0.1.0"` at both of them. The
> package version line and the tag namespace collided by accident (…)
> `git tag` is not a release history here.

**Tag `v0.3.0` niczego nie blokuje.** Build czyta `pyproject`, PyPI nie wie
o tagach, CI ich nie ogląda. Konfliktu, który obie zaproponowane opcje mają
rozwiązać, nie ma.

### Opcje i ich konsekwencje

**A. Przenieść tag na czubek `main`** (`git tag -f` + `push --force`)
— łamie płot z polecenia („nie przenosicie tagów na origin") i zasadę
z `CONTRIBUTING` jednym ruchem; utrwala pomyłkę „tag = wydanie"; kto ma tag
lokalnie, zostaje ze starym (`git pull` nie aktualizuje istniejących tagów);
**wydaniu 0.3.0 nie jest potrzebne**.

**B. Przeskoczyć numer** (wydać `0.4.0`)
— trwała dziura w publicznej numeracji PyPI (`0.2.0` → `0.4.0`), myląca dla
kogoś z zewnątrz; rozwiązuje problem, którego nie ma, bo `0.3.0` jest wolne.

**C. Nie ruszać tagów, wydać `0.3.0`** *(spoza pytania, rekomendowana)*
— zgodne z `CONTRIBUTING`; numeracja PyPI ciągła; tag zostaje lipcowym
kamieniem milowym, czym jest. Koszt zero. Ryzyko: przyszła pomyłka
„tag = wydanie" — ostrzeżenie przed nią już stoi w `CONTRIBUTING` i to ono
ochroniło ten wybór tutaj.

**Decyzja należy do operatora.** Przy wyborze C numer dla pozycji 7 to
`0.3.0`, a bump w `pyproject` idzie `0.2.0` → `0.3.0`.

---

## 2. Sufity join-skilla

*(slot — wpisuje wykonawca)*

## 3. HEAD w studiach

*(slot — wpisuje wykonawca)*

## 4. „Prośba o alibi" do zasad

*(slot — wpisuje wykonawca)*

## 5. Indeks zasad-agentycznych

*(slot — wpisuje wykonawca)*

## 6. `--apply` poza tym repo

*(slot — wpisuje wykonawca)*

## 7. Release — przygotowanie, nie publikacja

*(slot — wpisuje wykonawca; czeka na decyzję operatora z pozycji 1)*
