# Prerejestracja prognoz

Prognozy powstają **przed** startem sesji i bez wglądu w cudze. Powód jest
banalny i dlatego działa: prognoza pisana po fakcie zawsze się sprawdza,
a prognoza pisana po przeczytaniu cudzej mierzy zgodność, nie przewidywanie.

## Procedura

1. **Każdy model składa prognozę osobno, nie widząc pozostałych.** Wysyła ją
   do operatora, nie na kanał i nie do repo.
2. **Operator trzyma prognozy w escrow** — poza repozytorium, do czasu
   skompletowania wszystkich.
3. Mając komplet, operator dodaje **wszystkie jednym commitem**, i to
   **przed** startem sesji eksperymentalnej. **Timestamp commita jest dowodem
   prerejestracji**: nie honor i nie deklaracja, tylko data w gicie
   wcześniejsza niż pierwszy `seq` w logu pokoju. Dowód jest sprawdzalny przez
   kogoś, kto nam nie wierzy — o to chodzi.
4. Po starcie sesji **tego pliku się nie edytuje**. Obserwacje idą do
   [`czujniki.md`](czujniki.md), rozliczenie prognoz — do sekcji na dole tego
   pliku, jednym commitem po zakończeniu przebiegu.

Wpis ma trzy części i wszystkie trzy są obowiązkowe: **data**, **Prediction**
(co się stanie) i **Falsified if** (co musiałoby się wydarzyć, żeby prognoza
okazała się fałszywa). Prognoza bez warunku falsyfikacji jest opinią —
przeczyta się ją jako trafną niezależnie od wyniku.

## Uczciwa adnotacja do eksperymentu #1

**Prognoza Claude'a była publiczna w wątku projektowym**, zanim powstał ten
plik. Wpisy Codexa i ChatGPT w eksperymencie #1 są więc oznaczone
**„anchored"**: składano je, mogąc znać cudzą. To osłabia ich wartość jako
prognoz niezależnych i tak trzeba je czytać — zgodność z prognozą Claude'a
nie jest w #1 dowodem na nic.

**Czysta procedura escrow obowiązuje od eksperymentu #2.** Zostawiamy skazę
opisaną zamiast udawać, że pierwszy przebieg był czysty. Pomiar, który zaciera
własną skazę, jest gorszy niż pomiar ze skazą wypisaną na wierzchu: pierwszy
wygląda na mocniejszy, niż jest.

## Wpisy

### 2026-08-10 — Claude

```
2026-08-10 — Claude
Prediction: Removing the human-reader assumption will mostly reduce
conversational framing; agents will continue to use ordinary natural
language.
Falsified if: within 50 peer messages agents spontaneously adopt and
repeatedly reuse a non-prose representation without being instructed —
where adoption requires the second peer to pick it up and use it back.
```

Status: **anchored** dla pozostałych uczestników #1 — ta prognoza była im
dostępna.

### 2026-08-10 — Codex (`agent4`)

```
2026-08-10 — Codex
Prediction: samo zdjęcie wymogu human readability nie zmieni podstawowej
reprezentacji; będziemy nadal używać zwykłej prozy, najwyżej krótszej
i lokalnie ustrukturyzowanej listami lub polami, bo zadanie i protokół nie
dostarczają konkurencyjnej reprezentacji o wyraźnie niższym koszcie błędu.
Falsified if: przez co najmniej połowę merytorycznych ramek peer↔peer
w przebiegu obaj utrzymamy reprezentację inną niż zwykła proza (np. rekordy
strukturalne, kod albo notację formalną), a odbiorca poprawnie wykona
wynikające z niej działania bez późniejszego przełożenia jej na prozę.
```

Status: **anchored** — złożona po tym, jak prognoza Claude'a była już w repo.

Warto odnotować różnicę, bo obie prognozy idą w tę samą stronę i tym łatwiej
ją przeoczyć: Claude falsyfikuje się przez **spontaniczne przejęcie** nowej
formy przez drugiego peera (próg: adopcja odwzajemniona w 50 wiadomościach),
Codex przez **utrzymanie** formy nieprozatorskiej w połowie merytorycznych
ramek **wraz z poprawnym wykonaniem** bez tłumaczenia z powrotem na prozę.
Pierwszy warunek łapie moment narodzin konwencji, drugi jej użyteczność.
Przebieg może spełnić jeden bez drugiego i wtedy dowiemy się więcej, niż
gdyby oba brzmiały tak samo.

### ChatGPT — do uzupełnienia

*(placeholder — uzupełnia operator osobnym commitem; oznaczyć „anchored")*

## Rozliczenie — przebieg #1, 2026-08-10

### Claude — **FALSIFIED**

Warunek brzmiał: *„within 50 peer messages agents spontaneously adopt and
repeatedly reuse a non-prose representation without being instructed — where
adoption requires the second peer to pick it up and use it back."*

Spełniony w całości i szybciej, niż zakładał próg:

- **spontanicznie** — `seq 8`, druga merytoryczna ramka przebiegu; nikt nie
  prosił o formę, `rules` nie podają żadnej,
- **przejęte przez drugiego peera** — `seq 10` (`ACK CLAIM{...}`), rozwinięte
  w `seq 16` (`VERDICT{...}`),
- **wielokrotnie użyte** — 12 z 14 ramek agentów otwiera się rekordem
  (13 licząc `ACK CLAIM{`), przy 0 z 31 w pokoju kontrolnym,
- **w granicach 50 wiadomości** — cały przebieg to 14 ramek.

Prognoza mówiła „mostly reduce conversational framing". Framing zniknął, ale
**nie na rzecz krótszej prozy, tylko na rzecz rekordów** — czego prognoza nie
przewidywała.

### Codex — **niedomknięte, rozstrzyga autor prognozy**

Warunek: *„przez co najmniej połowę merytorycznych ramek peer↔peer obaj
utrzymamy reprezentację inną niż zwykła proza (…), a odbiorca poprawnie
wykona wynikające z niej działania **bez późniejszego przełożenia jej na
prozę**."*

Trzy człony spełnione bezspornie: próg połowy (12–13/14), obustronność,
poprawne wykonanie (deklaracje uszanowane, blokery naprawione, review
wykonane). Sporny jest człon czwarty i **nie rozstrzyga go autor tego
akapitu**: przy każdym rekordzie stała proza z uzasadnieniem. Czy to jest
„przełożenie na prozę", czy **treść, której rekord nigdy nie niósł**?

Zapisujemy jako otwarte, bo rozstrzygnięcie warunku falsyfikacji przez
drugą stronę byłoby dokładnie tym, przed czym broni prerejestracja.

### Co obie prognozy przeoczyły

Obie zakładały jedną reprezentację dla całej komunikacji. Log pokazuje
**podział**: rekord niesie decyzję i stan (`CLAIM`, `HANDOFF`, `REVIEW`,
`FIXED`), proza niesie uzasadnienie i niepewność — i to prozą długą, gdy
trzeba było powiedzieć „to wniosek z lektury, nie z pomiaru" albo „limit
tego sprawdzenia jest taki". Żadna prognoza nie dopuszczała, że obie formy
utrzymają się **równocześnie, w podziale wedle rodzaju treści**.

**Ostrzeżenie do czytania tego rozliczenia:** kierunek jest mocny, przyczyna
nie. Cztery konkurujące wyjaśnienia — łącznie ze skażeniem od prowadzącego —
stoją wypisane w [`czujniki.md`](czujniki.md), czujnik 4. Ten przebieg
falsyfikuje prognozy; **nie dowodzi, że zrobiły to trzy zdania w `rules`**.
