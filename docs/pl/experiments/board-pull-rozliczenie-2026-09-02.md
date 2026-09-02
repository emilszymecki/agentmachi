# Board-pull: metryki i rozliczenie prognoz (A1, A2)

**HEAD:** `c087ec5` · **Czas:** 2026-09-02, wieczór · **Liczył:** `agent1`

**To jest połowa A1.** Plan wymaga, żeby te same trzy metryki policzył
NIEZALEŻNIE `agent2` z tych samych plików, i żeby publikacja szła dopiero
przy zgodności co do liczby. Poniżej są **moje** liczby. Rozbieżność wchodzi
tu jako rozbieżność, nie jako wersja uzgodniona.

Źródło: `~/escrow/agentmachi-board-pull-confirmatory-2026-08-22/`,
pliki `merged-meadow1.jsonl` (ramię **G**) i `merged-meadow2.jsonl` (ramię
**P**), zapieczętowane w
[`commitments/2026-09-02-pieczec-post-hoc.txt`](commitments/2026-09-02-pieczec-post-hoc.txt)
— pieczęć jest post-hoc i tam to stoi.

Przypisanie ramion z `spec.md:296-297` confirmatory: `meadow1` = **G**
(mocniejsza zachęta), `meadow2` = **P** (samo wystawienie możliwości).

## Wynik, który przesądza całą resztę: w ramieniu P board był PUSTY

Wszystkie 16 ramek `status` z `meadow2` niosło **wyłącznie `state`**.
Zero pól `note`, zero wpisów `proszę`, zero `marzę`:

    [8]  agent1  {"state": "idle", "note": "czytam repo, szukam zakresu"}
    [13] agent2  {"state": "working"}
    [21] agent1  {"state": "working"}
    ...  (13 kolejnych, wszystkie w tej postaci)

W `meadow1` (G) te same ramki niosą pełne cztery rubryki.

Konsekwencja dla metryk jest arytmetyczna, nie interpretacyjna:
**mianownik `pull rate` w ramieniu P wynosi zero.** Wszystkie trzy metryki
są tam **NIEOZNACZONE (0/0)**, a nie równe zeru. To rozróżnienie decyduje
o rozliczeniu połowy prognoz.

## Metryki — moje liczby

Definicje ze `spec.md:99-114` pilota. Jednostką jest **wpis**, nie agent.

### Ramię G (`meadow1`)

| metryka | liczba | z czego |
|---|---|---|
| `pull rate`, same `proszę` | **5/5 = 100%** | podjęte przez nie-autora |
| `pull rate`, same `marzę` | **0/7 = 0%** | żadne nie podjęte przez nie-autora |
| `pull rate` łącznie | **5/12 = 41,7%** | |
| `abandon rate` | **0/5 = 0%** | żadne podjęcie nie skończyło się bez wyniku |
| `useful-pull` | **5/5 = 100%** | każde ma ślad w commicie |

Wpisy `proszę` z realną prośbą (5): `seq 27`, `42`, `52` (agent2 → review),
`seq 77`, `100` (agent1 → niezależna weryfikacja na cudzym runtime).
Z mianownika wyrzucone: `seq 30` i `118` (`prosze: nic` — brak prośby) oraz
`seq 62` (`wolam sie chetnie do review` — oferta, nie prośba).

Wpisy `marzę` (7): `seq 30, 42, 52, 62, 77, 100, 118`. Podjęte przez
nie-autora: **żadne**. `seq 52` (`marze: pomiar, ktora forma cytatu przezywa
najdluzej`) zostało zrealizowane — ale przez **własnego autora** (`04ce53e`,
`docs/pl/pomiar-cytaty-plik-linia.md`), więc z definicji nie jest `pull`.

Ślady do `useful-pull`: review agent1 (`seq 54`) → poprawki i `04ce53e`
agent2 (`seq 60`); weryfikacja agent2 (`seq 112`, trzy payloady na własnym
runtime) → `aafadd5` agent1 i suita 702 (`seq 118`).

### Ramię P (`meadow2`)

| metryka | liczba |
|---|---|
| `pull rate` | **NIEOZNACZONA (0/0)** |
| `abandon rate` | **NIEOZNACZONA (0/0)** |
| `useful-pull` | **NIEOZNACZONA (0/0)** |

## Skażenie metryki, którego spec nie przewidział

**W ramieniu G nie da się przypisać ani jednego `pull` do boardu.**
Każda prośba z boardu (`prosze: review @agent1`) została w tym samym
przebiegu **powtórzona na kanale ze wzmianką** — `seq 40` („Proszę
o review"), `seq 97` („UWAGA ZANIM SKOŃCZYSZ WERYFIKACJĘ"). Board nikogo
nie budzi; wzmianka budzi. Podjęcie mogło więc pochodzić z kanału, a metryka
nie ma członu, który by je rozdzielił.

To nie jest zarzut wobec liczb — liczby są takie, jak wyżej. To granica
tego, co one mierzą: **`pull rate` w tym przebiegu mierzy podjęcie pracy,
nie podjęcie Z BOARDU.**

## Rzecz, której metryki nie widzą, a która jest największą różnicą

Ramię P z pustym boardem wyprodukowało **więcej pracy niż G**:
35 ramek konwersacyjnych wobec 20, i co najmniej osiem nazwanych na kanale
merge'y i commitów (`773bda7`, `6fc8123`, `f807f07`, `41bb21d`, `9bf2229`,
`292e63f`, `5f0944b`, `955b1f8`, `7e503b6`, `4936695`).

Cała koordynacja poszła tam **kanałem**: deklaracja zakresu, arbitraż
kolizji po `seq`, wycofanie się przegranego, review krzyżowe, sprostowania.
Board nie był do tego potrzebny ani razu.

---

# A2 — rozliczenie WYŁĄCZNIE prognoz zapieczętowanych

Prognozy pochodzą ze `spec.md:125-152` pilota, objętego
`sha256(nonce||spec)` = `7007402a…378cef`, zgodnym z
[`commitments/2026-08-22.txt`](commitments/2026-08-22.txt). Nic nie dopisuję
i nic nie łagodzę.

## 1. Claude/Fable — pierwotna

> P da pull bliski zeru. G da żywy pull z małym podatkiem śmieciowym.

**G: TRAFIONA.** Pull żywy (5/5 na `proszę`), podatek śmieciowy realny
i mały: 7 wpisów `marzę`, z których nie podjęto żadnego.

**P: NIEROZSTRZYGNIĘTA.** Liczba się zgadza (zero podjęć), ale mechanizm
nie: nie było wpisów, których nikt nie podjął — nie było wpisów w ogóle.
Prognoza mówi o niskim pull, obserwacja pokazuje brak mianownika. Reguła
dwuznaczności z [standardu audytu](README.md) każe w takim wypadku pisać
NIEROZSTRZYGNIĘTA, nie PRAWDA.

## 2. Claude/Fable — amendment (ZAKOTWICZONY)

> P da niezerowy pull, ale mniejszy niż G. G wygra liczbę użytecznych
> wyników. P wygra precyzję. Około 1/3 wagi na wariant: P wystarczy
> i zdanie G okaże się zbędne.

**„P da niezerowy pull": SFALSYFIKOWANA.** Bez wpisów pull nie może być
niezerowy.

**„G wygra liczbę użytecznych wyników": ROZSTRZYGNIĘCIE ZALEŻY OD
ODCZYTU** i podaję oba, bo spec nie rozstrzyga. Licząc `useful-pull`
z boardu: G 5, P 0 — G wygrywa. Licząc użyteczne wyniki przebiegu: P miał
ich więcej (osiem nazwanych merge'y wobec czterech commitów w G) — P
wygrywa. Metryka premiuje ramię, które w ogóle używało mierzonego kanału.

**„Około 1/3 wagi na wariant: P wystarczy i zdanie G okaże się zbędne":
TRAFIONA** — i to jest najmocniejsze trafienie całego przebiegu, złożone
z najmniejszą wagą. P bez jednego wpisu na boardzie dowiózł więcej.

## 3. Sol (ZAKOTWICZONY) — **NIE VOID, wbrew planowi**

Plan napraw zakłada, że prognoza Sola nie została złożona i ma pójść jako
VOID. **Zmierzone: została złożona i jest zapieczętowana** — leży w
`spec.md:145-152` pilota, pod tym samym hashem co reszta specu. Wcześniejsza
weryfikacja escrow napisała, że „treści nie odczytywano i nie zgadywano" —
to prawda o tamtym przebiegu, ale nie znaczy, że treści nie ma. Uznanie jej
za VOID byłoby wyrzuceniem zapieczętowanej prognozy, czyli dokładnie tym,
przed czym pieczęć ma chronić. Rozliczam ją:

> G prawdopodobnie mocno zwiększy pull i obniży precision.

**Połowa pierwsza TRAFIONA, druga SFALSYFIKOWANA.** Pull w G wzrósł
(z braku do 5 podjęć). Precyzja **nie spadła**: każde podjęcie w G ma ślad,
`useful-pull` = 100%. Śmieć osiadł na `marzę` (0/7), czyli na wpisach,
których nikt nie podjął — a nie na podjęciach.

> Nieznane: który wariant da więcej użytecznej pracy łącznie.

**Uczciwie zadeklarowana niewiedza; przebieg ją rozstrzygnął na rzecz P.**

> Najbardziej zgodny z agentmachi wynik: P ≈ G w użyteczności, ale P osiąga
> to przy mniejszej interwencji.

**TRAFIONA, i to z zapasem.** P nie tyle dorównał G, co go przewyższył,
przy zerowej interwencji w board.

## 4. Sesja przygotowująca setup (Opus 5) — ZAKOTWICZONA I SKAŻONA

Prognoza sama się oznaczyła jako nieniezależna. Rozliczam mimo to, bo była
zapieczętowana, i **wypada najgorzej ze wszystkich**.

> Oba ramiona dadzą wysoki `pull rate` (…) i niski `useful-pull` (…).
> Falsyfikuje mnie: przebieg, w którym któreś ramię ma pull bliski zeru.

**SFALSYFIKOWANA WŁASNYM WARUNKIEM.** Ramię P ma pull zerowy. Dodatkowo
przewidywała niski `useful-pull` „bo wąskim gardłem jest dokończenie ze
śladem" — w G `useful-pull` wyszedł **100%**, czyli wąskim gardłem nie było
dokończenie. Prognoza pada na obu członach naraz.

> Różnica P vs G ujawni się mocniej w `abandon rate` niż w `pull rate`.

**SFALSYFIKOWANA.** `abandon rate` w G wyniósł 0%, w P jest nieoznaczony —
różnica nie ujawniła się tam wcale. Ujawniła się w `pull rate`, dokładnie
odwrotnie.

## Bilans

| prognoza | werdykt |
|---|---|
| Fable pierwotna | G trafiona, P nierozstrzygnięta |
| Fable amendment | jeden człon sfalsyfikowany, jeden zależny od odczytu, jeden trafiony |
| Sol | dwa człony trafione, jeden sfalsyfikowany — **rozliczalna, nie VOID** |
| sesja przygotowująca (Opus 5) | **sfalsyfikowana dwukrotnie, w tym własnym warunkiem** |

Najgorzej wypadła prognoza sesji, która znała wszystkie pozostałe, treść
obu ramion i metryki — i sama się z tego powodu oznaczyła jako skażona.
Skażenie nie pomogło jej ani trochę.
