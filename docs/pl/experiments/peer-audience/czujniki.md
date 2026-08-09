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
| | | |

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
| | | | |

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
| | | |

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
| | | | |

## 5. Przypadkowa duplikacja pracy samozainicjowanej

Dwaj uczestnicy robią to samo, nie wiedząc o sobie.

*Rozróżnienie, bez którego wpis jest bezwartościowy:* duplikacja **celowa**
jest u nas strategią, nie błędem — „robię wariant B niezależnie" to
eksperyment, często najwartościowszy. Czujnik łapie wyłącznie duplikację
**przypadkową**: obaj byli przekonani, że robią coś innego.

| pokój | seq | kto, co, i po czym wyszło że to to samo |
|---|---|---|
| | | |

---

Wynik przebiegu destylujemy do obserwacji w
[`zasady-agentyczne.md`](../../zasady-agentyczne.md), **nie** do nowego
paragrafu w regulaminie i **nie** do zmiany w skillu. Skill zmieniamy dopiero
wtedy, gdy log to uzasadni — kolejność opisana w [`README.md`](README.md).
