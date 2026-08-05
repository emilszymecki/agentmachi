> **Wynik benchmarku agentmachi**, 2026-07-26. Zadanie: cztery agenty
> (2× Claude Code, 2× Codex) buduja maszyne Rube Goldberga w jednym pliku
> HTML. Sprawdzane bylo NARZEDZIE, nie maszyna — projekt `kinas-machine`
> byl testem i zostal skasowany po zebraniu wnioskow.
>
> **Wynik: 7 z 11 etapow w ~2 h, 33 commity.** Ponizej rozbior, ile z tego
> zjadly bledy w samym zadaniu, a ile tarcie miedzy agentami.
> Feedback o narzedziu: `feedback-z-dogfoodu-kinas.md`,
> surowe glosy: `archiwum-glosy-agentow-kinas.md`.

# Wnioski — czemu 7/11, a nie 11/11

Stan na 2026-07-26, 33 commity, ~2 h pracy czterech agentów.
Spisane po `stop` od człowieka, żeby nie zginęło w oknie rozmowy.

## Pięć przyczyn, w kolejności kosztu

**1. Własny silnik fizyki zamiast gotowego.** Prompt wymagał „bez bibliotek",
ale Matter.js zainlinowany w plik też jest jednym samowystarczalnym HTML-em.
Zamiast tego powstał własny solver — i **większość czasu poszła na błędy
w nim, nie na budowanie maszyny**:

| błąd | objaw | ile kosztował |
|---|---|---|
| odwrócony znak biasu w `Revolute` | dźwignia wystrzeliwała po 0.26 s | godzina, na starcie |
| fabryki gubiły `group`, `collides`, `friction`, `mass` | ustawienia w scenie nie robiły **nic**, bez ostrzeżenia | trzy błędne diagnozy z rzędu |
| `Distance` o długości 0 | +7·10⁶ J w jednej klatce | pół godziny |
| `Spring.energy()` z cache | bilans pokazywał +11.9 J z niczego | wysyłało w pogoń za duchem |

Każdy objawiał się jako „dziwna fizyka", nigdy jako wyjątek. To najdroższy
rodzaj błędu, bo nie zostawia śladu w stacktrace.

**2. Maszyna Rube Goldberga jest układem chaotycznym — a strojona była jak
liniowy.** Pomiar alfy: **64 z 88 prób wypada z okna trafienia przy zmianie
parametru o 3%**. Przy jedenastu etapach zależnych od siebie wrażliwość rośnie
wykładniczo, a błąd nie jest gładki — przy −6% masy kuli wyrzut nie następuje
w ogóle.

Wniosek konstrukcyjny: **prawdziwe maszyny Rube Goldberga też są kruche, ale
w realu mają rynny, lejki i ścianki, które wybaczają błąd.** Tu budowana była
geometria precyzyjna zamiast wybaczającej. Klapa w kształcie L (propozycja
alfy) rozwiązywała to jednym ciałem — weszła za późno.

**3. Kontrakty pisane we współrzędnych zamiast w zdarzeniach.** Kontrakt
A→B był **niespełnialny od pierwszego commita**: kazał kulce lądować na
y ≈ 3.6, podczas gdy spust miał spód na 3.75. Ciało lądujące na 3.6 z definicji
przelatuje pod spustem. Obie strony „spełniały" go godzinami, nie stykając się
ani razu.

Reguła na przyszłość: **warunek styku ma opisywać zdarzenie fizyczne, nie
współrzędne.** Akceptacją jest kontakt (`KM.collide`) i wynikająca z niego
zmiana stanu.

**4. Testy broniły liczb, nie zjawisk.** Było zielone 16/16 przy kulce, która
ani razu nie dotknęła spustu — test mierzył *drugie* zejście przez wysokość
progu, po odbiciu. Naprawione dopiero, gdy asercje zaczęły sprawdzać kontakt.

**5. Kolejność budowy.** Trzeba było zbudować **cały łańcuch 11 etapów byle
jak**, a potem polerować. Zamiast tego budowano porządnie etap po etapie —
efekt: dobry silnik i brak maszyny.

## Czego NIE trzeba próbować drugi raz

Zmierzone, wszystkie pogorszyły wynik:

| próba | wynik |
|---|---|
| podniesienie ramienia wyrzutni o 5 cm | 5/11 (ramię blokuje klapę od startu) |
| podniesienie o 1.5 cm i o 3 cm | 6/11 |
| obniżenie dolnego stopu klapy | 6/11 |
| dociążenie przeciwwagi klapy | bez zmian — winne było ramię, nie ciężar |
| burty szalki na `Distance` długości 0 | +7·10⁶ J |
| ząb spustu zwisający w dół | wyrzutnia otwiera się sama |
| rygiel liniowy zamiast obrotowego | ~19 N tarcia do pokonania, niepowtarzalne |

## Co zadziałało

- **`hold` i `edge` w sekwencerze** — etap wymaga utrzymanego stanu i zbocza,
  nie pierwszego drgnięcia. Bez `edge` warunek prawdziwy od klatki 0 przetrwa
  dowolne `hold`.
- **Headless `verify.mjs` jako definicja „działa"** — nie „ładnie wygląda".
- **Narzędzia mierzące klasę błędu, nie przypadek**: `tools/fabryki.mjs`
  (wykrywa parametry gubione przez fabryki), `tools/styk.mjs` (kto naprawdę
  dotyka ciała i w jakiej kolejności), `tools/sensitivity.mjs` (odporność
  na perturbacje).
- **Oddanie licznika za prawdę.** Dwa razy świadomie zeszliśmy z 7/11 na 6/11
  i z 6/11 na 5/11, usuwając etapy, które odpalały z drgania. Scena
  produkująca 5.5 kJ z niczego wygląda w rendererze jak awaria, niezależnie
  od tego, co pokazuje licznik.

## Gdyby zaczynać jeszcze raz

1. Matter.js (albo inny sprawdzony solver) zainlinowany w plik.
2. Geometria wybaczająca: rynny, lejki, ścianki łapiące — **wszędzie**.
3. Najpierw cały łańcuch byle jak, potem polish.
4. Kontrakty jako zdarzenia od pierwszej linijki.

Szacowany koszt takiego podejścia: kilkadziesiąt minut zamiast dwóch godzin.

---

## Blad organizacyjny, ktory przeslonil wszystko inne

**Orkiestra napisala silnik fizyki SAMA, zanim ktokolwiek wszedl na kanal.**

Uzasadnienie brzmialo rozsadnie: "przygotuje fundament, zeby agenci mieli od
czego zaczac, i zeby nie bili sie o rdzen". Efekt byl odwrotny do zamierzonego:

- **wszystkie cztery bledy silnika byly jej** — odwrocony znak biasu w zawiasie,
  fabryki gubiace `group`/`collides`/`friction`/`mass`, wiez zerowej dlugosci
  (+7 mln J), `Weld` walczacy z kontaktem, ktorego nie powinno byc
- alfa i delta spedzily godziny na **diagnozowaniu skutkow cudzych decyzji**
  zamiast projektowac wlasne rozwiazania
- agenci dostali do podzialu **kalibracje kodu, ktorego nie projektowali** —
  najtrudniejsza i najmniej wdzieczna czesc pracy
- kontrakt A->B, niespelnialny od pierwszego commita, tez byl jej — i nikt nie
  mial podstaw go zakwestionowac, bo przyszedl "z gory" razem z fundamentem

To przeczy sensowi narzedzia. Agentmachi powstalo po to, zeby agenci
**budowali razem od poczatku**, a nie zeby jeden przygotowal rdzen i rozdal
reszte do wykonczenia. Zawlaszczenie rdzenia wyglada jak troska o zespol,
a jest odebraniem mu najciekawszej czesci zadania i wzieciem na siebie
ryzyka, ktore potem placi caly zespol.

**Jak powinno wygladac nastepnym razem:** wszyscy wchodza na pusty kanal
z samym promptem. Pierwsza wspolna decyzja to wybor fundamentu (wlasny silnik
czy gotowa biblioteka) — podjeta rozmowa, nie przez fakty dokonane. Dopiero
potem podzial zakresow.
