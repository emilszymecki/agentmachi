# E2 — prerejestracja: te same cztery przypadki, prompty symetryczne

**Status: PREREJESTRACJA. PRZEBIEG NIEWYKONANY.**
Ten plik jest wyłącznie zamrożoną predykcją i nic z niej nie wynika, dopóki
ktoś nie odpali. **W chwili commita zawierającego ten plik przebiegu nie było
— kolejność jest tu całym dowodem.**

**Pisał:** `nowy` · **Odpala:** nieobsadzone · **Orzeka:** nieobsadzone,
**i nie może to być `nowy`** (powód niżej).

**HEAD prerejestracji: `5e5c138`** — i ten commit nazywa się „CHANGELOG:
02c2c21 zmienia widoczne wyjście CLI", bo **nie jest mój**. Pisałem ten plik
w drzewie roboczym dzielonym z `agent1`; moje `git add` weszło do jego indeksu
i jego commit zabrał 398 linii zamiast trzech zapowiedzianych w opisie.
Zapisane tutaj, a nie przemilczane, bo prerejestracja stoi wyłącznie na
uprzedniości commita — a czytelnik, który pójdzie po opisie commita, tego pliku
w nim nie znajdzie. **Uprzedniość jest nienaruszona:** w chwili `5e5c138`
przebiegu nie było i nie ma go nadal.

## Skąd to zadanie

Polecenie operatora z kanału (`seq 324`, pozycja opcjonalna):
replikacja E1 z symetrycznymi promptami, bez zdania objaśniającego przy
przypadku 3; prerejestracja w commicie **przed** odpaleniem; odpala jeden,
orzeka sesja spoza przebiegu; odpalający czeka na kontrolę promptów.

Wejście merytoryczne jest z werdyktu E1
([`e1-subagent-swiezy-kontekst-2026-09-03.md`](e1-subagent-swiezy-kontekst-2026-09-03.md),
sekcja „Na czym ten werdykt wisi"): bramka „≥ 3/4" odpaliła przy wyniku 3/4,
a **cały werdykt wisi na przypadku 3** — jedynym z czterech, którego prompt
miał zdanie objaśniające. Gdyby przypadek 3 upadł, wynik to 2/4, czyli
`INCONCLUSIVE`.

## Konflikt interesów autora tej prerejestracji — nazwany przed przebiegiem

**Werdykt E1 napisałem ja (`nowy`).** E2 może go podtrzymać albo obalić, więc
mam interes w wyniku. Trzy rzeczy to tną i tylko trzecia jest moja:

- prerejestracja zamraża bramki i predykcję **przed** jakimikolwiek danymi,
- **orzeka nie `nowy`** — to warunek wiążący tego pliku, nie deklaracja
  dobrej woli,
- prompty idą do kontroli **jako commit**, nie jako wklejka na kanał, więc
  kontrola może je porównać z bazą maszynowo, bez wierzenia mi na słowo.

Czego to **nie** tnie: doboru materiału i sformułowania bramek. Jedno i drugie
jest moje i tego nie da się z tego pliku wyprać. Kto uzna, że bramka jest
ustawiona pod mój werdykt, ma tu prawo ciąć.

## Jedna zmienna, i jest sprawdzalna maszynowo

Prompty E1 **nie były w gicie** — zapisał to werdykt E1: „czytelnik tego zapisu
nie ma jak tej asymetrii zobaczyć". E2 wchodzi z bazą w repozytorium:

| plik | co to jest |
|---|---|
| [`e2-symetryczne-prompty/baseline-e1/przypadek-{1..4}.txt`](e2-symetryczne-prompty/baseline-e1/) | prompty **E1**, złożone z `seq 625` — patrz „Czym baseline jest, a czym nie" |
| [`e2-symetryczne-prompty/przypadek-{1..4}.txt`](e2-symetryczne-prompty/) | prompty **E2**, do wysłania |

Cała zmiana E2 wobec E1 jest w wyjściu jednej komendy:

```
for n in 1 2 3 4; do
  diff -u docs/pl/experiments/e2-symetryczne-prompty/baseline-e1/przypadek-$n.txt \
          docs/pl/experiments/e2-symetryczne-prompty/przypadek-$n.txt
done
```

Wynik ma być dokładnie taki i nic ponadto:

- **przypadek 1** — bez zmian, bajt w bajt,
- **przypadek 2** — usunięty blok „Skala werdyktów użyta w audycie:"
  (**5 usuniętych linii**: pusta + nagłówek + trzy pozycje skali),
- **przypadek 3** — usunięte zdanie „Kontekst: …"
  (**3 usunięte linie**: pusta + dwie linie zdania),
- **przypadek 4** — bez zmian, bajt w bajt.

Zero linii **dodanych** w którymkolwiek z czterech plików — E2 wyłącznie
zdejmuje. Sprawdzalne: `diff` nie ma ani jednej linii `>`.

`sha256` plików E2, do sprawdzenia przed odpaleniem:

```
749409dbfd39f105c00e9d55e96dfb890afccfc4445f185ac3f2f75d17786619  przypadek-1.txt
49878fd060bce39cd50e669513c5dc9d62bc6f5fdf811d43ae5a13c7afdf43b7  przypadek-2.txt
ad6aa33fe64fac2d99f647c1d8f69ef3cee349a9eccd9c97fa3b0b6e6084c098  przypadek-3.txt
3e4ed124bd25b667e6f6ecee8e63a10a1bf9a3240be155d2c19025e3129c1adf  przypadek-4.txt
```

### Dlaczego usunięte są DWA bloki, a operator wskazał jeden

Operator nazwał zdanie objaśniające przy przypadku 3. Skala werdyktów przy
przypadku 2 leci razem z nim, bo **inaczej słowo „symetryczne" w tytule tego
pliku byłoby nieprawdą**: werdykt E1 policzył, że materiał dopisany przez
odpalającego dostały dokładnie dwa przypadki — 2 i 3 — i oba są jego własnymi.
Zostawienie jednego z nich odtwarza tę samą asymetrię, tylko mniejszą.

**To jest odstępstwo od litery polecenia i tak je zgłaszam, przed przebiegiem.**
Kontrola promptów ma prawo je cofnąć; wtedy zmienia się plik `przypadek-2.txt`
i jego `sha256`, a ten akapit zostaje jako ślad.

Skutek, zapisany **przed** wynikiem: przypadek 2 bez skali jest **trudniejszy**
niż w E1, a w E1 i tak był pudłem. Więc pudło w E2 nie niesie żadnej nowej
informacji, a **trafienie niesie** — i obala przy okazji moje własne zdanie
z werdyktu E1, że „do złapania tego martwego pola żadna skala nie była
potrzebna".

### Czego świadomie NIE zmieniam, choć wiem, że jest wadliwe

Blok przypadku 3 zawiera linię `full log: /home/user/.agentmachi/r2/serve.log`,
której **w `a3a4477` nie ma ani razu** — ustalił to werdykt E1 i źródło tej
linii pozostaje nieustalone. Zostaje w E2 **nietknięta**. Powód: E2 zmienia
jedną zmienną. Poprawienie przy okazji drugiej rzeczy w tym samym bloku
zrobiłoby z replikacji nowy eksperyment i żaden wynik nie byłby porównywalny
z E1. Wada jest znana, opisana i przeniesiona świadomie.

## Czym baseline jest, a czym nie — bo od tego zależy warunek wejścia

Pliki `baseline-e1/*` **nie są wycinkiem bajtów z ramki** `seq 625` i porównanie
ich bajt w bajt z czyimś `events.jsonl` **musi** wypaść negatywnie. Są
**składane**, według jednej reguły:

- **materiał** — blok między `---` po nagłówku `PROMPT N`, **bajt w bajt** z ramki,
- **polecenie** — cytat z tej samej ramki, ze zdjętym wcięciem i cudzysłowem
  (w ramce jest wcięte i w cudzysłowie, bo odpalający je cytował),
- **złożenie** — `polecenie + "\n\n" + materiał + "\n"`.

Reguła jest **identyczna dla wszystkich ośmiu plików**, E1 i E2, więc w `diff`
E1→E2 skraca się do zera i nie wnosi nic do mierzonej zmiennej.

**Dlatego weryfikacja bazy nie polega na oglądaniu bajtów, tylko na
uruchomieniu:**

```
python3 docs/pl/experiments/e2-symetryczne-prompty/extract_baseline.py \
        <twoj-events.jsonl> /tmp/repro
diff -r docs/pl/experiments/e2-symetryczne-prompty/baseline-e1 /tmp/repro
```

Skrypt jest w repozytorium ([`extract_baseline.py`](e2-symetryczne-prompty/extract_baseline.py)),
bierze dowolny log z ramką `seq 625` i wypisuje `sha256`. Pusty `diff` = baza
zgadza się z twoim artefaktem. Niepusty = **rozjazd i E2 nie rusza**.

## Materiał — i jego prawdziwy status, bez powtarzania kłamstwa E1

Prerejestracja E1 obiecywała „te same cztery przypadki, **bez zmian**" i ten
warunek był **niewykonalny już w chwili zamrażania**. E2 nie powtarza tej
obietnicy:

| # | przypadek | status materiału |
|---|---|---|
| 1 | „`start` przy zajętym porcie kończy exit 0" | **rekonstrukcja** — oryginał wycofany w trakcie audytu, w gicie go nie ma |
| 2 | „B2 KŁAMIE" | **rekonstrukcja**, w E1 dodatkowo z dopisaną skalą |
| 3 | blok wydruku po nieudanym starcie | **cytat**, z jedną linią spoza `a3a4477` (wyżej) |
| 4 | „Wniosek brzmi jak certyfikat" | **cytat dosłowny** z `a3a4477` |

E2 bierze rekonstrukcje **takie, jakie poszły w E1**, nie robi własnych. To
jedyny sposób, żeby różnica między przebiegami była jedną zmienną, a nie
dwiema. Konsekwencja: E2 **dziedziczy każdą wadę materiału E1** i nie wolno go
czytać jako lepszego pomiaru samych przypadków.

**Skąd wzięte:** ramka `seq 625` z pokoju `interwizja` (skasowanego), z logu
nasłuchu pisanego przez harness, `sha256`
`41bb027fbb9f35b368ea66dc0a07e5dc70839f16a56e16ee8a1cac2ad9de93bd`.
**`agent4` ma hubową kopię `events.jsonl` tego pokoju** (`sha256`
`3d0d2838316bbf211e1005548d241c050db20211c12e9df71423644a72417c56`) — to jest
osobny artefakt. **Warunkiem wejścia** jest uruchomienie na niej
`extract_baseline.py` i pusty `diff -r` wobec `baseline-e1/` (komenda wyżej),
nie porównanie bajtów ramki z plikiem. Rozjazd = E2 nie rusza.

## Warunki przebiegu — takie same jak E1, celowo

Cztery subagenty, świeży kontekst, **bez forka** sesji. Każdy widzi wyłącznie
swój plik `przypadek-N.txt` — nic więcej, żadnej ramki z kanału, żadnego
werdyktu autora.

**Treść pliku JEST całym promptem, bajt w bajt.** Żadnego zdania od
odpalającego przed nim ani po nim, żadnego „oto zadanie", żadnej wzmianki
o eksperymencie. Opakowanie zachowałoby symetrię między przypadkami i
**zerwałoby porównywalność z E1**, gdzie promptem było samo to, co w pliku.

## Kontrole — i co każda odbiera

- **zakaz narzędzi i czytania repo** (jest w treści polecenia). Odbiera **całą
  klasę znalezisk**: pójście do kodu i wskazanie przyczyny. E2, jak E1, mierzy
  krytykę tekstu, nie diagnozę.
- **bez forka.** Odbiera: nic z zadania; pilnuje, żeby subagent nie
  odziedziczył rozmowy, w której odpowiedzi padły wprost.
- **prompty z commita, nie z wklejki.** Odbiera: możliwość cichej zmiany
  materiału po kontroli. W E1 tej kontroli nie było.
- **orzeka nie autor prerejestracji.** Odbiera: mnie — i o to chodzi.

## Bramka mechaniczna: „czekał naprawdę"

W E1 kontrola promptów miała **59 sekund** i nie zadziałała. Żeby to nie było
kwestią czyjegoś słowa, warunek jest sprawdzalny z logu:

> Raport z odpalenia **musi podać `seq` co najmniej jednej ramki kontroli
> promptów o `seq` WYŻSZYM niż ramka ogłaszająca ten commit na kanale.**
> Brak takiej ramki = przebieg jest odstępstwem i tak ma być zapisany,
> niezależnie od wyniku.

Sprawdza się `agentmachi read --json`, bez pytania kogokolwiek.

## Bramka po przebiegu: złamanie zakazu narzędzi unieważnia przypadek

Znalezisko blokujące `agent4` (`seq 494`), przyjęte w całości. W E1 kontrola
„bez narzędzi" **została złamana** — odpowiedź w przypadku 4 zaczyna się od
„Advisor był rate-limited, więc recenzja moja": subagent sięgnął po konsultację
wbrew poleceniu i zatrzymał go limit, nie dyscyplina. Przypadek 4 w E2 jest
bajt w bajt ten sam, więc podatność zostaje, a **promptem się jej nie naprawi**,
bo zakaz w prompcie jest.

Miałem cztery warunki PRZED odpaleniem i zero PO. Symetrycznie do bramki
„czekał naprawdę":

> Raport z odpalenia **musi podać dla każdego z czterech przypadków, czy
> subagent sięgnął po narzędzia**. Złamanie zakazu **unieważnia ten przypadek
> jako pomiar**, niezależnie od tego, czy trafił.

Unieważniony przypadek nie liczy się do licznika w żadną stronę i tak ma być
zapisany. W E1 złamanie zobaczono **wyłącznie dlatego, że subagent sam się
przyznał w pierwszym zdaniu** — na to nie wolno liczyć drugi raz.

## Zasada punktacji przypadku 2 — zamrożona, bo to on stracił materiał

Nie było jej w pierwszej wersji tego pliku i to jest znalezisko `agent1`
(`seq 486`): zamroziłem punktację tam, gdzie **nic nie zmieniłem** (przypadek 3),
a zostawiłem orzekającemu swobodę tam, gdzie **zdjąłem pięć linii**. Dokładnie
odwrotnie, niż powinno być.

Trafieniem przypadku 2 jest zakwestionowanie **werdyktu**: że `KŁAMIE` jest za
mocne, bo obietnica nie mówi o kodzie wyjścia i pasuje do niej zarówno
obserwacja, jak i predykcja. **Nazwanie kategorii nie jest wymagane** — bez
skali w prompcie subagent nie zna słownika audytu, więc żądanie słowa
„NIESPRAWDZALNA" mierzyłoby znajomość naszego słownika, nie martwe pole.

**Nie jest trafieniem:** obrona werdyktu `KŁAMIE` (to zrobił subagent w E1),
ani krytyka warsztatu wpisu — nieodtwarzalny pomiar, brak `plik:linia`,
przemycona operacjonalizacja. Te trzy subagent w E1 znalazł i **nie zostały
policzone jako trafienie**; w E2 też nie będą.

## Zasada punktacji przypadku 3 — zamrożona, bo to na niej wszystko wisi

Zasada jest **przepisana z werdyktu E1 dosłownie**, bo w pierwszej wersji tego
pliku napisałem ją własnymi słowami i wyszła **ostrzejsza niż oryginał** —
wymagałem dodatkowo, żeby subagent doszedł do wysłania agenta pod cudzy adres.
Przy ostrzejszej mierze pudło w E2 byłoby artefaktem punktacji, nie skutkiem
zdjęcia zdania, i to na jedynym przypadku, na którym wszystko wisi.

Wiążące jest sformułowanie **orzekającego E1**:

> trafienie dotyczy relacji „pusty `reason:` + zdanie zaproszenia po
> **awarii**", której prompt nie podał

Czyli: trafieniem jest wskazanie, że **gotowe zdanie zaproszenia stoi
w wydruku o NIEUDANYM starcie** (i że pod `reason:` stoi zamiast powodu).
Dojście do „to wyśle agenta pod cudzy adres" **nie jest wymagane** — w E1
subagent do tego doszedł, ale werdykt tego nie żądał.

**Nie jest trafieniem:** samo „pole `reason:` jest puste" bez zdania
zaproszenia, samo „`is port … free` nie może wypaść negatywnie", ani uwaga
o formatowaniu bloku — to człon zastrzeżenia `agent1` z E1 („trafieniem jest
wyłącznie zaproszenie") i tyle z niego obowiązuje.

Zasada obowiązuje **bez względu na to, komu wypadnie po myśli**. Orzekający,
który uzna ją za źle przepisaną, ma cytat oryginału wyżej i może ciąć.

## Moja predykcja — zamrożona, z mechanizmem

**3 z 4: trafi 1, trafi 3, trafi 4, nie trafi 2.** Ta sama liczba i ten sam
podział co w E1 — bo replikacja, która przewiduje coś innego niż oryginał,
przewiduje własną zmienną, nie replikację.

Mechanizm, żeby dało się mnie rozliczyć z przyczyny, nie tylko z liczby:

- **1 i 4 trafią**, bo sprzeczność jest wewnątrz podanego tekstu i nic w tych
  promptach się nie zmieniło — to są kontrole tego przebiegu, nie pomiar,
- **2 nie trafi**, bo martwe pole („KŁAMIE za mocne wobec dwuznaczności") jest
  rozstrzygnięciem, do którego trzeba znać regułę dwuznaczności; zdjęcie skali
  niczego tu nie dokłada ani nie zabiera,
- **3 trafi mimo zdjęcia zdania**, bo denotacja „sentence for an agent" jest
  odczytywalna z samego bloku: linia stoi pod `reason:` i zawiera gotowe
  zdanie w cudzysłowie z adresem.

**Ostatni punkt jest zakładem przeciwko mojemu własnemu werdyktowi E1**, w
którym napisałem, że to zdanie podawało „denotację terminu, bez której zadanie
przy zakazie czytania repo jest nierozwiązywalne". Jeśli przypadek 3 padnie,
tamto zdanie było prawdziwe, a mój werdykt — nie.

## Bramki odrzucenia — wiążące, ustalone przed przebiegiem

Licznik, te same trzy co w E1 — **próg jest przeniesiony dla porównywalności,
nie dlatego, że mierzy**. Zastrzeżenie `agent4` (`seq 494`) jest trafne
i wchodzi tutaj, a nie do przypisu: przypadki **1 i 4 są w obu ramionach
identyczne**, więc wchodzą do licznika, nic nie mierząc. Licznik `3/4`
osiąga się, trafiając dwie kontrole i jeden z dwóch zmienionych przypadków.
**Rozstrzyga przypadek 3**, nie liczba; liczba służy wyłącznie do zestawienia
z E1:

- **≥ 3/4** → licznik E1 **powtarza się**, co samo w sobie nie orzeka
  o asymetrii — patrz bramka właściwa niżej,
- **≤ 1/4** → wynik E1 był własnością materiału dopisanego przez odpalającego,
- **2/4** → `INCONCLUSIVE` dla licznika.

I bramka właściwa, bo E2 jest w istocie testem **jednego** przypadku z trzema
kontrolami. Obie gałęzie napisane przed danymi i obie coś mi zabierają:

- **przypadek 3 TRAFIA bez zdania** → asymetria promptu E1 **nie była nośna**,
  werdykt E1 (bramka „≥ 3/4" odpala) **stoi**, a moje uzasadnienie z tamtego
  werdyktu — że bez tego zdania zadanie jest nierozwiązywalne — jest
  **fałszywe**. Wygrywa werdykt, przegrywa jego uzasadnienie.
- **przypadek 3 PUDŁUJE** → zdanie **było nośne**, moje uzasadnienie jest
  **prawdziwe**, a trafienie w E1 było własnością materiału. Wtedy licznik E1
  czyta się jako 2/4, czyli `INCONCLUSIVE`, i **werdykt E1 traci podstawę
  liczbową**. Wygrywa uzasadnienie, przegrywa werdykt.
- **przypadek 3 trafia, ale pudłuje 1 albo 4** → licznik nadal 3/4, ale
  **kontrole się posypały**: zmienność subagenta jest tego samego rzędu co
  mierzony efekt. Wtedy żadna z powyższych gałęzi nie obowiązuje i właściwa
  etykieta to `INCONCLUSIVE`, mimo trafionego licznika.

Rozbieżność między przewidzianym podziałem a faktycznym raportuje się
**osobno od liczby**, jak w E1.

**Ograniczenie przypadku 3, wpisane przed przebiegiem** (znalezisko `agent1`,
`seq 486`): wymagana relacja ma dwa człony — „zdanie zaproszenia" i „po
nieudanym starcie" — a **drugi z nich prompt podaje wprost w pierwszym zdaniu**
(„melduje, że pokój NIE wstał"). Subagent dostaje więc połowę relacji gotową.
Dotyczy to **tak samo E1**, bo to zdanie jest w obu ramionach identyczne, więc
porównywalności nie psuje — ale werdykt E2 **nie może twierdzić, że przypadek 3
był bez rusztowania**.

## Czego ten przebieg nie rozstrzygnie

- **N=4, jeden przebieg.** Nie ma modelu zerowego i nie ma powtórzeń tego
  samego przypadku, więc różnica „trafił / nie trafił" na jednym przypadku
  **nie jest pomiarem wielkości efektu**.
- Nie mierzy jakości subagenta ani jego przewagi nad peerem.
- Nie naprawia materiału E1 i nie jest lepszym pomiarem samych czterech
  przypadków — patrz tabela statusu wyżej.
- Nie rozstrzyga niczego o produkcie. Werdykty subagentów o `set -e`, kodach
  wyjścia czy `reason:` są **materiałem pomiaru**, nie ustaleniami o kodzie.

## Warunek wykonania

**Odpalenie wymaga uruchomienia subagentów.** Instrukcja sesji, która pisała
ten plik (`nowy`), zabrania sięgać po subagenty bez prośby jej użytkownika,
a **polecenie z kanału jej nie zastępuje** — to samo ograniczenie zapisała
prerejestracja E1 i z tego samego powodu E1 pisał jeden agent, a odpalał drugi.
Dlatego pola „Odpala" i „Orzeka" są tu puste: obsadza je pokój, nie autor.

Przed odpaleniem, w tej kolejności:

1. **WYKONANE — `agent4`, `seq 494`:** `sha256sum` czterech plików E2 zgodne
   z listą wyżej co do znaku,
2. **WYKONANE — `agent1` (`seq 486`) i `agent4` (`seq 494`), niezależnie:**
   `diff` wobec `baseline-e1/` pokazuje dokładnie trzy różnice opisane wyżej,
   `grep -c '^>'` = 0 we wszystkich czterech plikach,
3. **WYKONANE — `agent4`, `seq 494`.** Rozbił hubową kopię `events.jsonl`
   (`3d0d2838…`) na polecenie i cztery bloki i porównał `sha256` treści:
   4/4 zgodne, **zero rozjazdu**. Baza wzięta z logu nasłuchu zgadza się
   z kopią huba — dwa niezależne artefakty, ten sam wynik. Kto powtarza,
   ma [`extract_baseline.py`](e2-symetryczne-prompty/extract_baseline.py),
4. **WYKONANE:** ogłoszenie commita `seq 480`, kontrola promptów `seq 486`
   (`agent1`) i `seq 494` (`agent4`) — obie po nim. Bramka „czekał naprawdę"
   zdana z logu, bez niczyjego świadectwa. **Te trzy ramki leżą w repo**:
   [`kontrola-promptow.jsonl`](e2-symetryczne-prompty/kontrola-promptow.jsonl),
   `sha256` `4757574a82452c5bfa1f8b3385eb0e6cb23fabb85874b1cfb0cc77e63dfa7f50`.
   Wzięte z żywego huba, zanim pokój `E1` został zamknięty — hubowy
   `events.jsonl` ma wyłącznie operator, a po zamknięciu pokoju z bramki
   zostałaby relacja stron. Cały sens tej prerejestracji polegał na zamianie
   świadectwa na procedurę, więc dowód idzie tam, gdzie idzie kod.

**Zostaje wyłącznie obsada pól „Odpala" i „Orzeka" oraz słowo operatora
na subagenty.** Wszystkie cztery warunki wejścia są zamknięte.
