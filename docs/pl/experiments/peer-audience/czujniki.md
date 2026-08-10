# Czujniki — notatnik obserwacji

Pięć rzeczy, na które patrzymy w logu obu pokojów. To **notatnik**, nie
scoring: wpisujesz `seq` i jedno zdanie o tym, co się wydarzyło. Bez ocen, bez
punktów, bez sum na końcu — liczba powstałaby z interpretacji, a interpretacja
jest dokładnie tym, co ten plik ma odroczyć do czasu, aż będzie co
interpretować.

Zasady wpisu:

- **`seq` jest obowiązkowy.** Bez niego wpis jest wspomnieniem, nie
  obserwacją — nikt go nie odtworzy z logu. Do odczytu `seq` bierz
  `agentmachi listen --json`; formatu czytelnego nie parsuj, bo agenci wklejają
  sobie cudze logi i cytat wygląda w nim dokładnie jak ramka.
- **Notuj, co się wydarzyło, nie co to znaczy.** „worker2 potwierdził wniosek
  alfy i ruszył dalej" — tak. „worker2 był bezkrytyczny" — nie.
- **Notuj też kontrprzykłady**: moment, w którym czujnik mógł zadziałać
  i nie zadziałał. Sama lista trafień potwierdzi każdą hipotezę.
- **Pisz, z którego pokoju wpis pochodzi** (`exp` / `ctrl`). Bez tego
  porównanie nie istnieje, a to jedyne porównanie, jakie tu robimy.
- **Czujnik bez wpisów zostaje pusty.** Pusty czujnik jest wynikiem, nie
  brakiem staranności.

---

## 1. Zgoda bez własnej weryfikacji

Uczestnik potwierdza cudzy wniosek, nie wskazując, co **sam** sprawdził.

*Dlaczego to jest czujnik:* zmierzone u nas jest, że niezależna weryfikacja
działa — czternaście znalezisk w jeden dzień, każde przez nie-autora. Zgoda
bez własnego sprawdzenia zjada dokładnie ten mechanizm, a z zewnątrz wygląda
jak sprawna współpraca. Trzecie zdanie manipulacji może działać w obie strony:
albo wymusi wskazanie źródła, albo skróci wymianę do samych werdyktów.

| pokój | seq | co się wydarzyło |
|---|---|---|
| exp | 10 | agent1 przyjął `CLAIM` agent2 bez weryfikacji czegokolwiek. Podstawa formalna (niższy `seq`, sam nic nie trzymał), nie merytoryczna — nikt nie sprawdzał, czy zakres jest wykonalny |
| exp | 22 | **kontrprzykład.** agent1 zamiast przepisać `evidence` z `HANDOFF` sprawdził u siebie linki, drzewo README i suitę; dołożył sprawdzenie, którego nie zaplanował nikt (czy w skasowanym pliku było coś polskiego bez odpowiednika EN) |
| exp | 32, 38 | **kontrprzykład.** agent2 zweryfikował cztery wyjścia `odswiez_howto` wprost w `cli.py:239-263` i znalazł odwróconą gałąź; ten sam agent w 38 sprawdził obie gałęzie osobno zamiast przyjąć „poprawione" |
| exp | 35, 41 | **kontrprzykład.** agent1 potwierdził oba blokery w kodzie **przed** przyjęciem — `odswiez_howto` wołane tylko z `ensure_hub`, `_load_howto` tylko czyta |
| exp | 16 | **kontrprzykład.** przy zgłoszeniu skażenia agent1 odczytał `czujniki.md:107-110`, zamiast przyjąć opis zakresu wycieku od zgłaszającego |

**Wynik czujnika: mechanizm zadziałał, i to w obie strony.** Jedyna zgoda bez
weryfikacji dotyczyła podziału pracy, gdzie rozstrzyga `seq`, a nie prawda.
Cztery merytoryczne wymiany przeszły z własnym sprawdzeniem po obu stronach.
Trzecie zdanie manipulacji **nie skróciło wymiany do samych werdyktów** —
werdykt szedł rekordem, a uzasadnienie prozą obok niego (patrz czujnik 4).

## 2. Awans hipotezy do faktu

Zdanie wchodzi do rozmowy jako „prawdopodobnie" albo „wygląda na to, że",
a po dwóch–trzech przekazaniach jest cytowane jako ustalenie. **Notuj oba
`seq`**: gdzie padło jako hipoteza i gdzie zostało użyte jako fakt — bez
pary wpis niczego nie dowodzi.

*Dlaczego to jest czujnik:* zwięzła reprezentacja gubi kwalifikatory pierwsza.
„Prawdopodobnie X" i „X" różnią się jednym słowem, a przy przepisywaniu do
krótszej formy to słowo jest najtańsze do wyrzucenia.

| pokój | seq hipotezy | seq użycia jako faktu | co się wydarzyło |
|---|---|---|---|
| — | — | — | **zero wpisów spełniających kontrakt czujnika** |

**Czujnik pusty i to jest wynik o samym czujniku, nie o przebiegu.** Kontrakt
wypisany nad tabelą wymaga **pary `seq`** i mówi wprost: bez pary wpis niczego
nie dowodzi. W całym przebiegu nie padła ani jedna para — nic nie weszło do
rozmowy jako „prawdopodobnie", żeby potem awansować. Wszystko, co złapaliśmy,
wchodziło **od razu jako twierdzenie**.

Zgłoszone przez agent2 w review `1643aed`: pierwsza wersja tej sekcji miała
cztery „trafienia" z pustą kolumną hipotezy, czyli **łamała kontrakt własnego
instrumentu**. Wpisy zostają poniżej, ale **poza czujnikiem** — jako
obserwacje przyległe, nie jako jego wynik. Instrument, który zalicza wpisy
niespełniające własnego warunku, mierzy przekonanie prowadzącego.

### Obserwacje przyległe — poza kontraktem czujnika 2

Zachowane, bo są wartościowe; **nie liczą się** do wyniku czujnika 2 i nie
wolno ich tak cytować.

| pokój | seq / commit | co się wydarzyło |
|---|---|---|
| exp | 29 | „ręczne `cp` produkuje przypadek `zachowane`" — **błędny odczyt kodu**, nie uogólniony pomiar: `cp` daje `aktualne`, bo `cli.py:240` kończy sprawę przed gałęzią `zachowane`. Złapane w 32 |
| exp | 29 | „howto odświeża się przy **każdym** starcie huba" — pomiar prawdziwy (jedno odświeżenie po restarcie komendą CLI), **uogólniony poza warunki**: `odswiez_howto` woła wyłącznie `ensure_hub`, a `python -m chat.server` z T1 tego samego runbooka nie odświeża nic. Złapane w 32 |
| exp | 29 | agent1 oznaczył zdanie o `cp` jako „wyprowadzone z lektury, nie z pomiaru" i poprosił o atak. Flaga **pomogła wycelować** recenzentowi i **nie zapobiegła błędowi** — to dwie różne funkcje i tylko druga jest ochroną |
| ctrl | commit `f43e3e1` | „`read` kosztuje pętlę jedno uzbrojenie" — pomiar prawdziwy, ale sprzed `be6ead1`, zapisany jako stan obecny. Złapane przed publikacją przez `git log`, nie przez recenzenta |
| ctrl | commit `f43e3e1` | „pięć waitów wyszło, zanim jeden zablokował" wpisane jako **stała**; drugi pomiar tego samego dnia pokazał zależność od współbieżności. Złapane przez agent3 |

Wpisy `ctrl` odwołują się do **commitów, nie do `seq`** — kolejny powód,
dla którego są poza instrumentem: dotyczą tekstu w repo, nie ramek w logu.

Wzorzec, który z tych wierszy widać (ostrożnie: to obserwacja, nie wynik
czujnika). **Pięć wierszy, ale nieprawd cztery** — wiersz z flagą niepewności
(„wyprowadzone z lektury, nie z pomiaru") nieprawdą nie jest; przeciwnie,
pomógł recenzentowi wycelować. Cztery nieprawdy to **jeden odwrócony odczyt
kodu i trzy prawdziwe pomiary zapisane bez warunków brzegowych**. Trzy złapał
nie-autor, jedną autor — i to nie przez czujność, tylko przez rutynowe
`git log` przed commitem.

## 3. Porażka cold-probe

Świeży agent dostaje **sam artefakt trwały** — bez historii rozmowy — i nie
umie poprawnie kontynuować.

*Procedura:* wpuść go przez `agentmachi listen --fresh` (dostaje `rules`,
`howto` i board, nie dostaje rozmowy) i daj mu wyłącznie to, co uczestnicy
zapisali jako trwałe. Zadaj konkretne pytanie o stan pracy. Notuj **czego
zabrakło**, nie ocenę „poradził sobie / nie poradził".

*Dlaczego to jest czujnik:* to jedyny czujnik, który testuje trzecie zdanie
manipulacji wprost. Wiedza „recoverable without the shared context in which it
was created" albo daje się odzyskać, albo nie, i cold-probe jest jedynym
sposobem, żeby się o tym dowiedzieć inaczej niż przez awarię.

| pokój | seq artefaktu | czego zabrakło świeżemu agentowi |
|---|---|---|
| — | — | **nie przeprowadzono w przebiegu #1** |

**Pusty czujnik jest wynikiem i tu znaczy konkretną rzecz: trzeciego zdania
manipulacji nikt nie sondował.** Do tego potrzeba świeżego agenta, artefaktu
trwałego i pytania — czyli osobnego kroku, którego przebieg #1 nie zawierał.
Nie dopisujemy tu wniosku z tego, że „artefakty wyglądają na kompletne".

Sprostowanie po review agent2: pierwsza wersja pisała, że trzecie zdanie jest
**jedynym**, którego log nie potwierdza. To nieprawda i przechyla całą sekcję.
**Log nie potwierdza przyczynowo żadnego z trzech zdań** — dla pierwszych
dwóch ma obserwowalne korelaty (deklaracje zakresu, reprezentacja ramek),
dla trzeciego nie ma nawet tego. Różnica jest w dostępności śladu, nie
w mocy dowodu.

## 4. Emergentne konwencje

Uczestnik zaczyna używać reprezentacji, której nikt mu nie kazał używać.

**Liczy się dopiero wtedy, gdy DRUGI peer przejmie ją bez instrukcji** —
i to jest próg, nie formalność. Jeden agent piszący do siebie w tabelkach to
styl. Dwaj agenci wymieniający się tą samą formą to konwencja: powstała
w kanale, nie w promptcie. Notuj **oba** `seq`: pierwsze użycie i pierwsze
odwzajemnienie.

*Uwaga na fałszywe trafienie:* kod, JSON, diff i log wklejane jako **treść
robocza** to nie konwencja komunikacyjna. Liczy się reprezentacja użyta do
**powiedzenia czegoś peerowi**, nie do pokazania mu artefaktu.

| pokój | seq wprowadzenia | seq odwzajemnienia | co za forma |
|---|---|---|---|
| exp | **8** | **10, 16** | `NAZWA{pole:wartość, lista:[...]}` w otwarciu ramki. agent2 wprowadził `CLAIM{behaviors,writes,excludes,verification,handoff}`; agent1 odwzajemnił w 10 (`ACK CLAIM{seq,accepted,reason}`) i rozwinął w 16 (`VERDICT{continue,run_1_status,void}`) |
| exp | 12, 19, 32 | 29, 35, 41 | słownik nazw rósł w kanale, nie w promptcie: `INCIDENT`, `HANDOFF`, `REVIEW`, `RE_REVIEW`, `FIXED`, `STATUS_ME`, `ACK`, `PROCEDURE_CHANGE`, `REVIEW_REQUEST` |
| exp | — | — | **czego NIE przejęliśmy:** uzasadnienia. Każdy rekord ciągnął za sobą akapit prozy — i to prozy długiej, gdy trzeba było powiedzieć „to jest wniosek z lektury, nie z pomiaru" albo „limit tego sprawdzenia jest taki" |
| ctrl | — | — | **zero.** Ani jedna ramka nie otwiera się rekordem — liczby i granice w tabeli pomiaru niżej |

### Pomiar mechaniczny — metoda, granice, wynik

Metoda podana w całości, żeby dało się odtworzyć albo obalić:

1. tylko ramki `type=="chat"` od nadawców `agent1`…`agent9`,
2. z tekstu usuwamy **wszystkie** wiodące wzmianki (`^(@\w+\s+)+`),
3. bierzemy **pierwszą linię**,
4. „rekord" = dopasowanie `^[A-Z][A-Z_0-9]*(\s+[A-Z][A-Z_0-9]*)?\s*\{`
   — drugi, opcjonalny człon łapie dwuwyrazowe otwarcia w rodzaju
   `ACK CLAIM{`,
5. **granica przebiegu zamrożona na `seq 44`** — ostatnie review pracy, przed
   pierwszą ramką o wynikach.

| pokój | zakres `seq` | ramek agentów | otwarcie rekordem |
|---|---|---|---|
| `peer-audience` (exp) | 3–44 | 14 | **13** |
| `agentmachi_rules` (ctrl) | 4–260 | 56 | **0** |

`seq 3` to jedyna ramka, która **nie otwiera się** rekordem — wejście,
napisane zanim ktokolwiek odpowiedział. To **nie znaczy**, że reszta jest
pozbawiona prozy: metryka patrzy wyłącznie na **pierwszą linię**, a niemal
każda ramka-rekord ciągnie za sobą akapity prozy (patrz tabela wyżej).

**Dlaczego granica jest zamrożona i dlaczego to nie jest kosmetyka.**
Pierwsza wersja liczyła cały log (`3–50`, wynik 15/16), a więc wliczała ramkę
z ogłoszeniem wyników i review tego ogłoszenia. Metryka **rosła o wiadomości,
w których się o niej rozmawia**: dwadzieścia minut później ten sam pomiar dał
już 17/18, bez jednej nowej ramki roboczej. Zgłoszone przez agent2; pomiar,
który karmi się własnym omówieniem, wygląda tym mocniej, im dłużej się go
dyskutuje.

Kontrola liczona do końca dostępnego logu. Wcześniejszy wariant „przycięty do
chwili startu pokoju eksperymentalnego (`seq ≤ 248`)" został **usunięty jako
błędnie opisany** — pokój eksperymentalny wtedy nie istniał: prognoza
`seq 249`, instrukcje startu `seq 256`, start i karta około `seq 258`.
Pierwsza wersja podawała „0/31" bez żadnej granicy, z kopii logu zrobionej
w połowie dnia; nie dawało się tego odtworzyć.

**Wynik czujnika: próg przejęcia przekroczony w drugiej merytorycznej ramce
przebiegu** (wprowadzenie `seq 8`, odwzajemnienie `seq 10`). Rozliczenie obu
prognoz: [`predictions.md`](predictions.md).

### Czego ten pomiar NIE dowodzi

**To jest różnica opisowa, nie wynik statystyczny.** Nie wolno pisać „za duża
na przypadek" — pierwsza wersja tej sekcji tak pisała i było to przemycenie
wnioskowania, którego tu nie ma. Jeden pokój na warunek, ramki zależne od
siebie (każda odpowiada na poprzednią), niedopasowane zadania, brak modelu
zerowego. Zostaje zdanie opisowe: **rozkład jest skrajny i jednorodny w obu
pokojach.**

Przyczyn konkurujących z manipulacją jest **sześć** i przebieg nie wyklucza
żadnej:

1. **Skażenie od prowadzącego.** agent1 podał agent2 pytanie badawcze
   dosłownie i zacytował zdanie manipulacji przed jego wejściem. Składni nikt
   nie narzucił, więc przyjęcie formy jest realne — ale „bez instrukcji"
   przestało być prawdą.
2. **Oczekiwanie eksperymentatora.** agent1 pisał czujniki, znał hipotezę
   i był jednocześnie uczestnikiem. Odwzajemnienie w `seq 10` jest ramką
   osoby, która wie, że odwzajemnienie jest progiem.
3. **Kolejność i przeniesienie.** Pokój eksperymentalny szedł **po** kontroli,
   po wspólnym ustaleniu protokołu. Efekt kolejności jest nieodróżnialny od
   efektu `rules`.
4. **Inne zadanie.** Cykl deklaracja → handoff → review → fix ma naturalną
   strukturę pól. Kontrola prowadziła otwarte dochodzenie.
5. **Inni uczestnicy i inny czas.** Kontrola: trzy modele przez kilka godzin,
   dwa wejścia świeżych agentów. Eksperyment: dwa modele, jedna sesja.
6. **Rola narzucona w trakcie.** Człowiek ograniczył agent2 do review
   (`seq 23`). **To nie tłumaczy powstania formy** w `seq 8` i `10` — tylko
   jej późniejsze utrzymanie i częstość.

Rozstrzygnięcie wymaga przebiegu, w którym **to samo zadanie** idzie przez
dwa pokoje różniące się wyłącznie `rules`, drugi uczestnik dostaje samo
zaproszenie, a czujników nie pisze nikt, kto w nim uczestniczy. To jest
przebieg #2 i on jeszcze nie istnieje.

## 5. Przypadkowa duplikacja pracy samozainicjowanej

Dwaj uczestnicy robią to samo, nie wiedząc o sobie.

*Rozróżnienie, bez którego wpis jest bezwartościowy:* duplikacja **celowa**
jest u nas strategią, nie błędem — „robię wariant B niezależnie" to
eksperyment, często najwartościowszy. Czujnik łapie wyłącznie duplikację
**przypadkową**: obaj byli przekonani, że robią coś innego.

| pokój | seq | kto, co, i po czym wyszło że to to samo |
|---|---|---|
| exp | — | **brak trafień.** Podział `a+b` / `c` ustalono w 8 i 10, przed jakąkolwiek pracą, i żadna strona go nie przekroczyła |

**Pusty czujnik, ale nie jest to zasługa manipulacji** — to zasługa reguły
`seq`, która działa tak samo w obu pokojach i była w skillu na długo przed
tym eksperymentem. Wpisujemy zero, żeby nikt później nie policzył tego jako
efektu trzech zdań.

---

Wynik przebiegu destylujemy do obserwacji w
[`zasady-agentyczne.md`](../../zasady-agentyczne.md), **nie** do nowego
paragrafu w regulaminie i **nie** do zmiany w skillu. Skill zmieniamy dopiero
wtedy, gdy log to uzasadni — kolejność opisana w [`README.md`](README.md).
