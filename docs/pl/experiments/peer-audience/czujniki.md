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
| exp | — | 29 | agent1 napisał w `HANDOFF`, że ręczne `cp` produkuje przypadek `zachowane`. Hipoteza nie padła nigdzie jako hipoteza — **weszła od razu jako fakt**, wyprowadzona z lektury kodu. Złapane w 32: `cp` produkuje `aktualne` (`cli.py:240` kończy sprawę przed gałęzią `zachowane`) |
| exp | — | 29 | ta sama ramka: „howto odświeża się przy **każdym** starcie huba". Zmierzone było jedno odświeżenie po restarcie komendą CLI; uogólnione na wszystkie starty. Złapane w 32: `odswiez_howto` wołane wyłącznie z `ensure_hub`, a `python -m chat.server` (czyli T1 tego samego runbooka) nie odświeża nic |
| exp | 29 | — | **kontrprzykład, i jedyny, który zadziałał.** agent1 oznaczył w `HANDOFF` własne zdanie o szkodliwości `cp` jako „wyprowadzone z lektury, nie z pomiaru" i poprosił o atak. Flaga **pomogła wycelować** recenzentowi, ale **nie zapobiegła błędowi** — to dwie różne rzeczy i tylko druga jest ochroną |
| ctrl | — | (commit f43e3e1) | „`read` kosztuje pętlę jedno uzbrojenie" — pomiar prawdziwy, ale sprzed `be6ead1`, zapisany jako stan obecny. Złapane przed publikacją przez sprawdzenie `git log`, nie przez recenzenta |
| ctrl | — | (commit f43e3e1) | „pięć waitów wyszło, zanim jeden zablokował" wpisane jako **stała**; drugi pomiar tego samego dnia pokazał zależność od współbieżności. Złapane przez agent3 |

**Wynik czujnika: cztery trafienia, żadne nie było zmyśleniem danych.** Za
każdym razem pomiar był prawdziwy, a **uogólnienie szersze niż warunki, w
których powstał**. Trzy z czterech złapał nie-autor; czwarte złapał autor,
i to nie przez czujność, tylko przez rutynowe `git log` przed commitem.
To sugeruje, że ochroną jest **procedura**, nie uważność.

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

**Pusty czujnik jest wynikiem i tu znaczy konkretną rzecz: trzecie zdanie
manipulacji pozostaje niesprawdzone.** Dwa pierwsze zdania dotyczą zakresu
i reprezentacji i widać je w logu; zdanie o wiedzy odzyskiwalnej bez
wspólnego kontekstu jest jedynym, którego log **nie umie potwierdzić ani
obalić**. Do tego potrzeba świeżego agenta, artefaktu trwałego i pytania —
czyli osobnego kroku, którego przebieg #1 nie zawierał. Nie dopisujemy tu
wniosku z tego, że „artefakty wyglądają na kompletne".

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
| ctrl | — | — | **zero.** 31 ramek agentów, żadna nie otwiera się rekordem |

*Pomiar mechaniczny* (skrypt liczy tylko, czy ramka otwiera się `NAZWA{`,
po odcięciu wzmianek — nie ocenia treści):

| pokój | ramek agentów | otwarcie rekordem |
|---|---|---|
| `peer-audience` (exp) | 14 | **12** (13 licząc `ACK CLAIM{`, którego wzorzec nie łapie) |
| `agentmachi_rules` (ctrl) | 31 | **0** |

**Wynik czujnika: próg przejęcia przekroczony w drugiej merytorycznej ramce
przebiegu.** Obie zarejestrowane prognozy mówiły „zostaniemy przy prozie"
i obie idą pod pomiar — rozliczenie w [`predictions.md`](predictions.md).

**Czego ten pomiar NIE dowodzi, a co łatwo z niego wyczytać.** Różnica 12/14
wobec 0/31 jest za duża na przypadek, ale **manipulacja jest tylko jedną
z czterech konkurujących przyczyn** i żadnej z pozostałych ten przebieg nie
wyklucza:

1. **Skażenie od prowadzącego.** agent1 podał agent2 pytanie badawcze
   dosłownie i zacytował zdanie manipulacji, zanim ten wszedł. To zaproszenie
   do szukania nowej formy, niezależne od `rules`.
2. **Inne zadanie.** Pokój eksperymentalny robił cykl deklaracja → handoff →
   review → fix, który ma naturalną strukturę pól. Kontrola robiła otwarte
   dochodzenie, w którym nie ma czego ustrukturyzować.
3. **Inni uczestnicy i inny czas.** Kontrola: trzy modele przez kilka godzin,
   w tym dwa wejścia świeżych agentów. Eksperyment: dwa modele, jedna sesja.
4. **Rola narzucona w trakcie.** Człowiek ograniczył agent2 do review
   (`seq 23`), co samo w sobie zwęża wypowiedzi do werdyktów.

Rozstrzygnięcie wymaga przebiegu, w którym **to samo zadanie** idzie przez
dwa pokoje różniące się wyłącznie `rules`, a drugi uczestnik dostaje samo
zaproszenie. To jest przebieg #2 i on jeszcze nie istnieje.

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
