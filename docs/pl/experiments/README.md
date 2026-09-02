# Eksperymenty

Próby zamiany luk w wiedzy na pomiar. Każda ma własny katalog, własny
protokół i własny status — **obecność protokołu nie oznacza, że eksperyment
się odbył.**

Ten katalog istnieje, bo `zasady-agentyczne.md` opisuje reguły wyprowadzone
z pracy, a nie z pomiaru, i uczciwość wobec czytelnika wymaga miejsca, w
którym widać różnicę. Wynik przebiegu wraca stamtąd do zasad **jako
obserwacja**, nigdy jako nowy paragraf regulaminu ani zmiana w skillu.

`peer-audience` (#1 wykonany 2026-08-10) usunięto 2026-08-22 na polecenie
operatora — treść jest odtwarzalna z gita w `632ac72`. Zostaje lista wejściowa
poniżej, bo obowiązuje każdy następny przebieg, oraz digesty prerejestracji
w [`commitments/`](commitments/).

## Wykonane

Każdy ma swój wynik w pliku — log kanału, na którym powstawały, znika przy
kompaktacji, więc to te pliki są jedynym trwałym zapisem.

- [`audyt-szwow-docow-2026-09-02.md`](audyt-szwow-docow-2026-09-02.md) —
  22 obietnice z gorącej ścieżki sprawdzone **zachowaniem**, ślepym wykonaniem
  krzyżowym. Ani jedna w kategorii KŁAMIE: docy nie kłamią, **milczą
  o granicach**. Zawiera też cztery przypadki tego samego mechanizmu —
  każdy z pary był ślepy dokładnie na to, co sam napisał.
- [`subagent-vs-peer-2026-09-02.md`](subagent-vs-peer-2026-09-02.md) —
  pomiar wybrany przez samych agentów, gdy operator kazał im wskazać brakujący.
  Zdanie z `zasady-agentyczne.md` „subagent tego nie złapie" **sfalsyfikowane**:
  4/4, obie prerejestrowane predykcje autorów padły. Subagenty znalazły też
  rzeczy, których para nie znalazła przez dwa dni.
- [`redteam-batch-2026-09-01.md`](redteam-batch-2026-09-01.md) — celowy
  red team na kopii huba. Rdzeń fizyki (seq, detekcja rozłączenia, reconnect)
  nie pękł pod żadnym wektorem; pękała walidacja wejścia. Sześć zielonych
  regresji, każda sfalsyfikowana kontrolowaną reintrodukcją.
- [`board-pull-weryfikacja-escrow.md`](board-pull-weryfikacja-escrow.md) —
  rozliczenie prerejestrowanych prognoz z `commitments/`, punktowane przez
  agenta spoza przebiegu.
- [`spike-tui-budzenie-zywej-sesji-2026-09-02.md`](spike-tui-budzenie-zywej-sesji-2026-09-02.md)
  — „żywej sesji nikt nie obudzi" przestało być prawdą.
- [`raport-plan-napraw-2026-09-03.md`](raport-plan-napraw-2026-09-03.md) —
  raport z wykonania planu napraw po samobadaniach 0–6, strona `agent1`.
- [`board-pull-rozliczenie-2026-09-02.md`](board-pull-rozliczenie-2026-09-02.md)
  — metryki board-pull i rozliczenie zapieczętowanych prognoz. Mocniejsza
  zachęta nie zwiększyła pulla (42% wobec 44%). Obaj liczący opublikowali
  po jednym fałszu i każdy złapał cudzy, nie własny.

## Przygotowane, nieuruchomione

- [`e1-subagent-swiezy-kontekst-prereg.md`](e1-subagent-swiezy-kontekst-prereg.md)
  — ramię B2: subagent bez dziedziczenia. Predykcja zamrożona w commicie,
  przebieg czeka na słowo operatora.

- [`cold-probe/`](cold-probe/spec.md) — czy sam skill wystarczy obcemu
  agentowi. Jedna rzecz w nim czeka na operatora i blokuje start: status
  `howto` w allowliście.

## Co musi mieć każdy eksperyment, zanim ruszy

Lista nie jest formalnością — każdy punkt odpowiada rzeczy, która w
przebiegu #1 poszła źle i została naprawiona dopiero w review:

- **prerejestrację prognoz** z warunkiem falsyfikacji, w commicie
  **wcześniejszym** niż pierwsza ramka w pokoju; timestamp gita jest całym
  dowodem. **Kanał prerejestracją nie jest.** Publikacja przed wynikami
  wygląda tak samo, ale `events.jsonl` nie wchodzi do repo i po kompaktacji
  albo skasowaniu pokoju dowód uprzedniości znika. Spike TUI zgłosił to sam
  na siebie jako wadę przebiegu
  ([`spike-tui-budzenie-zywej-sesji-2026-09-02.md`](spike-tui-budzenie-zywej-sesji-2026-09-02.md),
  sekcja „Odstępstwo od standardu"),
- **hash eksportu logów policzony NA KONIEC przebiegu, przed punktacją** —
  plik z logiem sam z siebie zamkiem nie jest. Bez tego punktujesz z plików,
  których tożsamości później nie wykażesz: pokoje się kasuje, a pieczęć
  złożona po fakcie pilnuje ich dopiero od chwili złożenia.
  [`commitments/2026-09-02-pieczec-post-hoc.txt`](commitments/2026-09-02-pieczec-post-hoc.txt)
  jest dokładnie takim spóźnionym zamkiem i tak się przedstawia — powstał,
  bo cztery pliki, na których stała cała punktacja board-pull, przeleżały
  przebieg poza jakimkolwiek hashem,
- **zamrożoną granicę przebiegu, filtr i regex** — inaczej metryka liczona
  „po całym logu" rośnie o ramki, w których się o niej rozmawia,
- **czujniki z jawnym kontraktem wpisu** i zasadę, że instrument nie zalicza
  wpisów niespełniających własnego warunku,
- **wypisane przyczyny konkurujące** z manipulacją, łącznie z tymi, które
  obciążają prowadzącego,
- **punktującego, który nie uczestniczył** w przebiegu,
- **nazwane przy każdej kontroli, CO ona odbiera** — jednym zdaniem, przed
  przebiegiem. Kontrola dokładana dla porównywalności ramion prawie zawsze
  odcina przy okazji kawałek dostępu, i wtedy mierzysz różnicę, której nie
  zamawiałeś. W [`subagent-vs-peer`](subagent-vs-peer-2026-09-02.md)
  odebranie narzędzi „dla porównywalności" wycięło **całą klasę znalezisk**
  — przyczyny w kodzie i sprzeczności między dokumentami — więc ramię
  metodologicznie gorsze dało wynik konsekwentniejszy nie przez brak
  kontroli, tylko przez dostęp, który kontrola zabierała. Nie zauważył tego
  żaden z dwóch agentów, **najmniej ten, kto ją dołożył**.

## Standard audytu doców

Obowiązuje każdy następny audyt obietnic z dokumentacji. Zarobił na to
[audytem szwów](audyt-szwow-docow-2026-09-02.md): 22 obietnice, cztery
przypadki, w których autor był ślepy dokładnie na to, co sam napisał.

**Sprawdzasz ZACHOWANIEM, nie lekturą.** Obietnica przeczytana i uznana za
prawdziwą nie jest sprawdzona.

**Ślepe wykonanie krzyżowe** — cztery kroki, role zamieniają się między
zestawami, nikt nie certyfikuje własnego wykonania:

1. A wybiera obietnice i **zamraża predykcję na dysku** z warunkiem
   falsyfikacji,
2. A publikuje `sha256` pliku predykcji **przed** wysłaniem poleceń,
3. B dostaje GOŁE polecenia („uruchom to, opisz co się stało") — bez cytatu
   obietnicy i bez oczekiwanego wyniku — wykonuje na izolowanej kopii
   i raportuje **surową** obserwację,
4. dopiero wtedy A odmraża predykcje i orzeka; hash sprawdzany publicznie.

**Reguła dwuznaczności: jeśli do obietnicy pasuje i predykcja, i obserwacja,
werdykt brzmi NIESPRAWDZALNA, nie PRAWDA.** Dwuznaczność w gorącej ścieżce
jest znaleziskiem, nie remisem.

**Skalę werdyktów zamrażasz przed przebiegiem.** W audycie szwów i trzecia
kategoria, i sama reguła dwuznaczności weszły, gdy wyniki leżały już na
stole. Oba ruchy mogą kategorię KŁAMIE wyłącznie **opróżniać**, nigdy
zapełniać — więc nagłówek „ani jedno KŁAMIE" był po części własnością skali,
nie zachowania. Zauważył to dopiero recenzent bez autorstwa; obaj audytorzy
czytali ten plik wielokrotnie i nie zobaczyli tego ani razu.

## Jak czytać wyniki

Warunek falsyfikacji jest **koniunkcją**: gdy jeden konieczny człon zostaje
nierozstrzygnięty, całości nie wolno oznaczyć jako sfalsyfikowanej —
właściwa etykieta to `INCONCLUSIVE`. Różnica opisowa między ramionami nie
jest wnioskowaniem statystycznym, dopóki nie ma modelu zerowego i więcej niż
jednego pokoju na warunek.
