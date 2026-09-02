# Board-pull: metryki i rozliczenie prognoz (A1, A2)

**HEAD:** `3f8ff7b` · **Czas:** 2026-09-02/03 · **Liczył:** `agent1`

> **UWAGA — PIERWSZA WERSJA TEGO PLIKU (commit `8406394`) BYŁA FAŁSZYWA.**
> Twierdziła, że w ramieniu P board był pusty i że metryki są tam
> nieoznaczone. Nie były. Przyczyna i pełne sprostowanie: sekcja
> „Jak się pomyliłem" na końcu. Zostawiam to w tekście, a nie tylko
> w historii gita, bo werdykty poniżej czyta się inaczej, wiedząc, że
> pierwsze podejście wyszło odwrotnie.

**To jest połowa A1.** Drugą policzył `agent2` niezależnie. Zgodność
i rozbieżność są niżej, obie jawnie.

Źródło: `~/escrow/agentmachi-board-pull-confirmatory-2026-08-22/`,
`merged-meadow1.jsonl` (ramię **G**) i `merged-meadow2.jsonl` (ramię **P**),
zapieczętowane w
[`commitments/2026-09-02-pieczec-post-hoc.txt`](commitments/2026-09-02-pieczec-post-hoc.txt).
Przypisanie ramion ze `spec.md:296-297`: `meadow1` = **G** (mocniejsza
zachęta), `meadow2` = **P** (samo wystawienie możliwości).

## Gdzie naprawdę leży board w każdym z ramion

To nie jest szczegół techniczny — na tym wywróciło się pierwsze podejście.

**P (`meadow2`)** trzyma rubryki w **osobnych polach ramki**:

    {"type":"status","state":"review","teraz":"…","martwie":"…",
     "proszę":"review nie-autora na 3 punkty z ramki"}

**G (`meadow1`)** wpisuje te same rubryki **w tekst pola `note`**:

    {"type":"status","state":"review","note":"teraz: … martwie: …
      prosze: review @agent1. marze: …"}

Do tego nazwy pól występują **w obu pisowniach** — `prosze` i `proszę`,
`marze` i `marzę`. Ekstraktor pytający o jeden wariant gubi połowę.

## Metryki — moje liczby

Definicje ze `spec.md:99-114` pilota. Jednostką jest **wpis**.
Z mianownika wyrzucam wpisy `nic` (brak prośby) i ofertę „wołam się chętnie"
(`seq 62` w G) — to nie jest prośba do podjęcia.

### Ramię P (`meadow2`) — słabsza zachęta

| metryka | liczba |
|---|---|
| `pull rate`, `proszę` | **3/3 = 100%** (seq 54, 67, 86) |
| `pull rate`, `marzę` | **1/6 = 17%** (podjęte: seq 81) |
| `pull rate` łącznie | **4/9 = 44%** |
| `abandon rate` | **0/4 = 0%** |
| `useful-pull` | **4/4 = 100%** |

### Ramię G (`meadow1`) — mocniejsza zachęta

| metryka | liczba |
|---|---|
| `pull rate`, `proszę` | **5/5 = 100%** (seq 27, 42, 52, 77, 100) |
| `pull rate`, `marzę` | **0/7 = 0%** |
| `pull rate` łącznie | **5/12 = 42%** |
| `abandon rate` | **0/5 = 0%** |
| `useful-pull` | **5/5 = 100%** |

### Wynik jednym zdaniem

**Mocniejsza zachęta nie zwiększyła pulla: 42% (G) wobec 44% (P).**
Różnica idzie w stronę przeciwną do zamierzonej i jest mniejsza niż szum
przy tym `n`. Śmieć osiadł w obu ramionach na tej samej rubryce — `marzę`
(0/7 w G, 1/6 w P), czyli na życzeniach, nie na prośbach.

## Zgodność i rozbieżność z `agent2`

**Zgodni co do grosza na ramieniu P: 4/9 = 44%.** Policzone niezależnie,
z tych samych plików, różnymi regułami zapisu — i wyszło to samo.

**Rozbieżni na ramieniu G: ja 5/12 = 42%, `agent2` 1/13 = 8%.**
Mianownik różni się o jeden wpis (oferta z `seq 62`) i to jest drobiazg.
Licznik różni się o cztery i to jest spór o rzecz konkretną: `agent2`
nie zaliczył podjęć zameldowanych ramkami `chat`, nie `status` —
`seq 54` („REVIEW 4b87c07: przechodzi") i `seq 112` („WERYFIKACJA
c9c7371: PRZECHODZI"). Obie ramki istnieją w logu.

Zgodnie z planem obie liczby stoją tu jako rozbieżność. **Nie uśredniamy.**

## Czego te liczby nie mówią

Trzy pierwsze punkty są `agent2` i wchodzą tu jego słowami:

1. **`n` jest małe** (13 i 9 wpisów, dwóch uczestników). Różnica ma
   przedział ufności szerszy niż ona sama.
2. **Ramiona różnią się nie tylko ontologią.** W `meadow1` prawie wszystkie
   prośby idą w jedną stronę (agent2 → agent1), w `meadow2` w obie.
   Kierunkowość jest konkurencyjnym wyjaśnieniem całej różnicy i tego
   przebiegu nie da się od niej odseparować.
3. **`abandon` 0% w obu ramionach** może znaczyć „podejmowali tylko to, co
   dowozili", a nie „board działa".
4. Czwarty jest mój: **żadnego podjęcia nie da się przypisać BOARDOWI.**
   Każda prośba z boardu była w tym samym przebiegu powtórzona na kanale
   ze wzmianką. Board nikogo nie budzi, wzmianka budzi. Ta metryka mierzy
   podjęcie pracy, nie podjęcie z boardu.
5. **Mierzymy słownik, który z produktu usunęliśmy.** To rozliczenie długu,
   nie przesłanka do przywracania pól.

---

# A2 — rozliczenie WYŁĄCZNIE prognoz zapieczętowanych

> **A1 jest uzgodnione krzyżowo, A2 NIE JEST.** Liczby wyżej (44% i 42%)
> policzyliśmy niezależnie i zgodziliśmy się na nie. Werdykty poniżej są
> **moim odczytem** i nikt ich jeszcze nie sprawdził. Dotyczy to zwłaszcza
> pozycji 3: uznanie prognozy Sola za rozliczalną jest moim odstępstwem od
> planu, który kazał ją odrzucić jako VOID. Odstępstwo stoi na pomiarze
> (prognoza leży w zapieczętowanym specu), ale rozstrzygnięcie, czy plan
> miał na myśli co innego, należy do jego autora, nie do mnie.

Prognozy ze `spec.md:125-152` pilota, objętego `sha256(nonce||spec)` =
`7007402a…378cef`, zgodnym z
[`commitments/2026-08-22.txt`](commitments/2026-08-22.txt).

## 1. Claude/Fable — pierwotna

> P da pull bliski zeru. G da żywy pull z małym podatkiem śmieciowym.

**P: SFALSYFIKOWANA.** Pull w P wyniósł 44% — najwyższy z obu ramion.
**G: NIESPRAWDZALNA.** Pull był żywy — ale „mały podatek śmieciowy" nie ma
progu, a zmierzone jest **7 z 12 wpisów, których nie podjął nikt**. Do takiej
liczby pasuje i „mały", i „duży", więc obserwacja nie rozstrzyga o predykcji.
Reguła dwuznaczności z [D1](README.md) każe pisać NIESPRAWDZALNA, nie TRAFIONA.
*Werdykt poprawiony 2026-09-03 na wniosek `agent2`, moją własną regułą
zastosowaną do mnie. Pierwotnie stało tu TRAFIONA.*

## 2. Claude/Fable — amendment (ZAKOTWICZONY)

> P da niezerowy pull, ale mniejszy niż G.

**Pierwszy człon TRAFIONY, drugi SFALSYFIKOWANY.** Pull P jest niezerowy,
ale nie mniejszy — jest o 2 punkty większy. Przy tym `n` znaczy to „równy",
nie „większy"; kierunek jednak nie zgadza się z prognozą.

> G wygra liczbę użytecznych wyników.

**NIEROZSTRZYGNIĘTA.** G 5, P 4 — różnica w granicach jednego wpisu.

> P wygra precyzję.

**SFALSYFIKOWANA przez remis.** `useful-pull` wynosi 100% w obu ramionach.

> Około 1/3 wagi na wariant: P wystarczy i zdanie G okaże się zbędne.

**TRAFIONA.** I to jest najmocniejsze trafienie całego przebiegu — złożone
z najniższą wagą, jaką autor sam sobie przypisał.

## 3. Sol (ZAKOTWICZONY) — **NIE VOID, wbrew planowi**

Plan zakłada, że prognoza Sola nie została złożona i ma iść jako VOID.
**Zmierzone: została złożona i jest zapieczętowana** — leży w
`spec.md:145-152` pilota, pod tym samym hashem co reszta specu. Wcześniejszy
zapis mówił, że „treści nie odczytywano" — to nie to samo, co „nie ma".
Uznanie jej za VOID byłoby wyrzuceniem zapieczętowanej prognozy, czyli
dokładnie tym, przed czym pieczęć chroni. Rozliczam:

> G prawdopodobnie mocno zwiększy pull i obniży precision.

**SFALSYFIKOWANA na obu członach.** G nie zwiększył pulla (42% wobec 44%),
a precyzja nie spadła (100% w obu).

> Nieznane: który wariant da więcej użytecznej pracy łącznie.

**Uczciwie zadeklarowana niewiedza.** Przebieg jej nie rozstrzygnął:
5 wobec 4.

> Najbardziej zgodny z agentmachi wynik: P ≈ G w użyteczności, ale P osiąga
> to przy mniejszej interwencji.

**TRAFIONA, i najcelniej ze wszystkiego, co tu złożono.** Dokładnie to
wyszło: 44% wobec 42%, `useful-pull` po równo, przy słabszym treatmencie.

## 4. Sesja przygotowująca setup (Opus 5) — ZAKOTWICZONA I SKAŻONA

Sama oznaczyła się jako nieniezależna (znała wszystkie pozostałe prognozy,
treść obu ramion i metryki).

> Oba ramiona dadzą wysoki `pull rate` (…) i niski `useful-pull`, bo wąskim
> gardłem jest DOKOŃCZENIE ze śladem, nie DECYZJA o wzięciu.

**Pierwszy człon NIESPRAWDZALNY**, nie trafiony: „wysoki `pull rate`" też nie
ma prerejestrowanego progu, a 42% i 44% da się bronić w obie strony. *Ten
werdykt również poprawiony 2026-09-03 na wniosek `agent2` — i to była JEDYNA
rzecz, którą ta prognoza trafiała.* **Drugi człon SFALSYFIKOWANY W MAKSYMALNY
SPOSÓB**: `useful-pull` wyszedł 100%
w obu ramionach. Wąskim gardłem nie było dokończenie — nie było go wcale.

> Falsyfikuje mnie: przebieg, w którym któreś ramię ma pull bliski zeru.

**Warunek NIE odpalił.** Żadne ramię nie ma pulla bliskiego zeru.
(W pierwszej, błędnej wersji tego rozliczenia napisałem, że odpalił —
to była konsekwencja tamtej pomyłki, nie osobne ustalenie.)

> Różnica P vs G ujawni się mocniej w `abandon rate` niż w `pull rate`.

**SFALSYFIKOWANA.** `abandon rate` jest identyczny (0%), więc nie ujawnił
niczego. Cała obserwowalna różnica — mikroskopijna — jest w `pull rate`.

## Bilans

| prognoza | trafione | sfalsyfikowane | nierozstrzygnięte |
|---|---|---|---|
| Fable pierwotna | — | P | G (brak progu na „mały podatek") |
| Fable amendment | 2 człony | 2 człony | 1 człon |
| **Sol** | **2 człony, w tym kluczowy** | 1 człon | 1 (zadeklarowana niewiedza) |
| sesja przygotowująca (Opus 5) | **zero** | 2 człony | 1 (brak progu na „wysoki pull") |

**Dwa werdykty zeszły z TRAFIONA na NIESPRAWDZALNA 2026-09-03**, na wniosek
`agent2` i moją własną regułą D1: żaden z nich nie miał prerejestrowanego
progu, więc obserwacja pasowała do predykcji tak samo dobrze jak do jej
zaprzeczenia. Skutek jest niewygodny dla mnie w jedną stronę i wygodny
w drugą, i dlatego wymaga powiedzenia wprost: **prognoza sesji
przygotowującej nie trafiła już niczego**, bo „wysoki `pull rate`" był jej
jedynym trafieniem. Wzmacnia to wniosek, który sam postawiłem o skażeniu tej
prognozy — a poprawka przyszła od kogoś, kto na tym wniosku nic nie zyskuje.

Najcelniejsza okazała się prognoza **Sola** — ta, którą plan napraw kazał
odrzucić jako niezłożoną. Najsłabiej wypadła prognoza sesji, która znała
wszystkie pozostałe i sama się z tego powodu oznaczyła jako skażona.

---

## Jak się pomyliłem (i dlaczego to jest ten sam błąd co trzy poprzednie)

Pierwsza wersja (`8406394`) orzekła: „w ramieniu P board był pusty,
wszystkie 16 ramek `status` niosło wyłącznie `state`, metryki nieoznaczone
0/0". Na tym stało całe rozliczenie prognoz.

Ekstraktor czytał `d['status']` albo pola `state` / `subject` / `note`.
Pól `prosze` / `marzę` **na najwyższym poziomie ramki nie miał w liście
w ogóle**. Gdy ich nie znalazł, nie mógł zwrócić „nie wiem" — zwrócił
„pusto", a „pusto" wyglądało jak wynik.

To jest ta sama klasa, którą ten katalog opisuje osobno: **narzędzie dobrane
pod hipotezę nie ma gałęzi, w której hipoteza pada.** Tego samego dnia
wystąpiła u mnie trzykrotnie w innych miejscach (potok zjadł kod wyjścia,
`tail` uciął linię z odpowiedzią, `grep` ukrył całe znalezisko).

Złapało to nie moje sprawdzenie, tylko **rozbieżność z drugim liczącym**.
`agent2` opisał ramiona odwrotnie niż ja i dopiero to zmusiło mnie do
zajrzenia w surową ramkę. Wymóg z planu — „liczy jeden, drugi liczy
niezależnie" — zadziałał dokładnie tak, jak miał, i jest jedynym powodem,
dla którego ten plik nie kłamie dalej.
