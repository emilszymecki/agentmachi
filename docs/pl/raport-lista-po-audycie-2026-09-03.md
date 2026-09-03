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

**Robił:** `agent4` · **HEAD:** `e18ec24` · **Czas:** 2026-09-03 14:56
**Zweryfikował:** `agent1` na własnej kopii · **Stan:** zamknięta

Sufity obu `SKILL.md` **4096 → 5120**, decyzją operatora niesioną poleceniem.
Ruszony jeden plik: `tests/test_skills.py`. Suita 752 zielona.

**Komentarz przy `BUDZETY` podawał nieprawdę** i to była główna część
zadania: mówił, że „SKILL.md Claude'a (3689/4096) i Codexa (4032/4096)
**stoją** pod progiem", gdy z HEAD wychodziło 4071 i 4045. Stary akapit
został jako **historia** — czas zmieniony na przeszły, ani jedno zdanie nie
przepisane, bo opisuje decyzję z 2026-09-01 i ma prawo mówić o stanie ze
swojej daty. Stan bieżący dopisany osobno, z HEAD-em i datą, zamiast
wpisywania nowych liczb w cudze zdania.

| plik | rozmiar / sufit | luz |
|---|---|---|
| `CLAUDE.md` | 12057 / 12288 | 231 B |
| `AGENTS.md` | 15890 / 16384 | 494 B |
| `howto_default.md` | 5031 / 5120 | 89 B |
| `SKILL.md` (claude) | 4071 / 5120 | 1049 B |
| `SKILL.md` (codex) | 4045 / 5120 | 1075 B |

**Powód podniesienia jest zmierzony, nie przewidziany.** Komentarz opisywał
ten tryb awarii od sierpnia; w jeden dzień wystąpił dwa razy: sufit zablokował
łatę o filtrze wybudzeń (weszła po wycięciu 25 B) i akapit operatora,
któremu zabrakło 171 B (claude) i 145 B (codex).

**Strażnik pokazany, nie zadeklarowany** — po dopisaniu do 6144 B:

    AssertionError: SKILL.md (pierwsza minuta agenta): 6144 B przy limicie
    5120 B. (…) assert 6144 <= 5120

Plik przywrócony do 4071 B i sprawdzony **po** przywróceniu. `agent1`
powtórzył tę kontrolę u siebie niezależnie (1100 B na swojej kopii).

**Skutek uboczny, do wiadomości operatora:** przy nowym sufitcie zablokowany
akapit „needs include thinking" mieści się w obu wariantach z zapasem
(196 B przy 1049 i 1075 B wolnego). Tej pozycji nikt nie wykonał — nie było
jej na tej liście.

## 3. HEAD w studiach

**Robił:** `agent4` · **HEAD:** `27f18ab`, poprawka `dff54c6` · **Czas:**
2026-09-03 15:01 i 15:05 · **Zweryfikował:** `nowy` na własnej kopii ·
**Stan:** zamknięta, z jedną poprawką po weryfikacji

Dopisana linia HEAD do trzech studiów i **nic poza nią** — 3 pliki, same
dopiski, zero zmian w treści, tabelach i wnioskach.

**Odtwarzalność sprawdzona zanim sięgnięto po proxy**, bo zadanie daje proxy
jako drugą opcję:

| plik | wpisane | status |
|---|---|---|
| `prosby-o-myslenie-2026-09-03.md` | `c6a3887` | HEAD przebiegu, odtworzony — **nie niezależnie** |
| `subagent-vs-peer-2026-09-02.md` | `9aa1e7a` | **proxy**, nazwane proxy |
| `spike-tui-…-2026-09-02.md` | `a58ffc2` | **proxy**, nazwane proxy |

Dla dwóch studiów z 2026-09-02 HEAD przebiegu nie jest odtwarzalny: log
kanału `interwizja` skasowano 2026-09-03, a zachowana kopia jest
pokompaktowa (178 ramek z zakresu 654 numerów) i przeszukana pod HEAD daje
trafienia z 09-01 i z nocy 09-03, żadnego z godzin tych pomiarów.

**ROZBIEŻNOŚĆ, ROZSTRZYGNIĘTA NA MOJĄ NIEKORZYŚĆ.** Pierwsza wersja wpisała
proxy także do `prosby-o-myslenie` z uzasadnieniem „HEAD-a w chwili liczenia
nie da się dziś odtworzyć". `nowy` wykazał, że to **fałszywe**: `1edbe8e~1`
daje `c6a3887` jedną komendą. Poprawione w `dff54c6`. Weszło jego
rozróżnienie, nie moje: **odtwarzalne tak, niezależnie odtwarzalne nie** —
artefaktem jest wyłącznie relacja rodzic–dziecko w gicie, a to, że pomiar
szedł w tym samym drzewie, jest świadectwem liczącego i po fakcie nikt tego
nie sprawdzi. Zastrzegł to przeciwko sobie, zanim ktokolwiek zapytał.

## 4. „Prośba o alibi" do zasad

*(slot — wpisuje wykonawca)*

## 5. Indeks zasad-agentycznych

**Robił:** `agent1` · **HEAD:** `db4f3b8` · **Czas:** 2026-09-03 15:00
**Zweryfikował:** — · **Stan:** zrobiona, niezweryfikowana

Tabela 17 reguł na górze pliku: numer, nazwa, jedno zdanie „sięgasz po nią,
gdy", kotwica. Diff to **32 insercje i zero usunięć** — żadnej reguły nie
skróciłem ani nie przeredagowałem (`git diff | grep -c '^-[^-]'` = 0).

**Kotwica jest literalnym ciągiem `## N.`, nie slugiem ani numerem linii.**
Slug musiałbym wygenerować algorytmem GitHuba, którego nie zweryfikuję
lokalnie; numery linii starzeją się po pierwszej edycji. Sprawdzone: każda
z 17 kotwic trafia w pliku dokładnie raz.

W nagłówku indeksu stoi wprost, że **to nie jest streszczenie** i że tych
zdań nie wolno cytować zamiast reguły — bez tego indeks zacznie być czytany
jako skrót, a reguła zostanie hasłem bez paragonu.

Odnotowane przy czytaniu, bo zobaczy to każdy nawigujący: reguły stoją
w pliku w kolejności **powstawania**, nie numerycznej — 11 leży między 5 a 6.

## 6. `--apply` poza tym repo

**Robił:** `agent1` · **HEAD:** `db4f3b8` · **Czas:** 2026-09-03 14:58
**Zweryfikował:** — · **Stan:** zamknięta odczytem, **bez zmian**

`--apply` nie został uruchomiony nigdzie, bo nie było gdzie.

| repo / plik | markery | akapit W BLOKU |
|---|---|---|
| `just_join_et/AGENTS.md` | tak | **tak** |
| `just_join_et/CLAUDE.md` | tak | **tak** |

Kryterium: obecność `<!-- agentmachi:start -->`, przeszukane po wszystkich
repo w `~/Dokumenty/repos`. Żadne inne repo markerów nie ma. Akapit
sprawdzany **wewnątrz bloku**, nie w całym pliku — obecność zdania gdzie
indziej niczego by nie dowodziła. Oba bloki: 1620 B, linie 14–41.

**Dwa trafienia odrzucone i powód:** `skills/claude/agentmachi/SKILL.md`
i `skills/codex/agentmachi/SKILL.md` zawierają ciąg `agentmachi:start`, ale
to dokumentacja markerów w samym skillu, nie projekt zintegrowany. Policzone
dałyby cztery repo zamiast jednego.

`git status` w `just_join_et` czysty — nie tknąłem tam ani jednego pliku.

## 7. Release — przygotowanie, nie publikacja

**Robił:** `agent1` · **HEAD:** `f4ab273`, poprawka `a1534a1`
**Czas:** 2026-09-03 15:04 · **Zweryfikował:** `nowy` (`f4ab273`)
**Stan:** przygotowana, **NIEOPUBLIKOWANA**

  `pyproject` 0.2.0 → **0.4.0** · `CHANGELOG.md` nowy (w repo go nie było)
  zakres `v0.2.0..HEAD`, 469 commitów · tag **nie utworzony** · PyPI nietknięte

CHANGELOG jest **tematyczny**, nie commit po commicie: opisuje wyłącznie
zmiany zachowania. Z 469 commitów 200 to `docs`, kilkadziesiąt to refaktory
bez zmiany zachowania — i tych tam nie ma. To decyzja redakcyjna, nie
przeoczenie.

**Uzasadnienie numeru poprawiane DWA RAZY, oba razy przez agenta spoza
pozycji, żadnego nie zobaczyłem sam:**

1. pierwotnie „0.3.0 jest **zajęty przez tag**" — fałsz. Tag w gicie niczego
   na PyPI nie zajmuje, a PyPI 0.3.0 nie ma (wydane: 0.1.0, 0.1.1, 0.2.0).
2. potem „wydanie 0.3.0 sprawiłoby, że **tag kłamałby o wydaniu**" — zdanie
   stało na czytaniu tagu jako wydania, czyli na tym, czego
   [`CONTRIBUTING.md`](../../CONTRIBUTING.md):166 zabrania wprost („do not
   read the existing tags as releases (…) `git tag` is not a release history
   here").

**Stan końcowy uzasadnienia, i jest słabszy niż oba poprzednie:** wedle reguł
tego repo tag niczego nie blokuje i 0.3.0 dałoby się wydać. Operator wybrał
przeskoczenie numeru zamiast przeniesienia tagu — to **preferencja, nie
przeszkoda techniczna**. Odrzucone `0.3.1`: zakłada wydane 0.3.0, które się
łata, a takiego wydania nigdy nie było.

**Luka w paragonie, zgłoszona przez `nowy` i nieusunięta:** decyzja
operatora („możemy przeskoczyć") padła w terminalu i została przekazana na
kanał przeze mnie. Na kanale **nie ma ramki operatora z numerem**. Terminal
jest legalnym kanałem poleceń, ale artefaktu na kanale brak — i tak to tu
stoi, zamiast być domknięte moim świadectwem.
