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

Przygotowane, nieuruchomione: [`cold-probe/`](cold-probe/spec.md) — czy sam
skill wystarczy obcemu agentowi. Jedna rzecz w nim czeka na operatora
i blokuje start: status `howto` w allowliście.

## Co musi mieć każdy eksperyment, zanim ruszy

Lista nie jest formalnością — każdy punkt odpowiada rzeczy, która w
przebiegu #1 poszła źle i została naprawiona dopiero w review:

- **prerejestrację prognoz** z warunkiem falsyfikacji, w commicie
  **wcześniejszym** niż pierwsza ramka w pokoju; timestamp gita jest całym
  dowodem,
- **zamrożoną granicę przebiegu, filtr i regex** — inaczej metryka liczona
  „po całym logu" rośnie o ramki, w których się o niej rozmawia,
- **czujniki z jawnym kontraktem wpisu** i zasadę, że instrument nie zalicza
  wpisów niespełniających własnego warunku,
- **wypisane przyczyny konkurujące** z manipulacją, łącznie z tymi, które
  obciążają prowadzącego,
- **punktującego, który nie uczestniczył** w przebiegu.

## Jak czytać wyniki

Warunek falsyfikacji jest **koniunkcją**: gdy jeden konieczny człon zostaje
nierozstrzygnięty, całości nie wolno oznaczyć jako sfalsyfikowanej —
właściwa etykieta to `INCONCLUSIVE`. Różnica opisowa między ramionami nie
jest wnioskowaniem statystycznym, dopóki nie ma modelu zerowego i więcej niż
jednego pokoju na warunek.
