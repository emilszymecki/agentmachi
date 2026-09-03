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
| [`e2-symetryczne-prompty/baseline-e1/przypadek-{1..4}.txt`](e2-symetryczne-prompty/baseline-e1/) | prompty **E1**, dosłownie, z `seq 625` |
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
osobny artefakt i porównanie `baseline-e1/*` z jego kopią jest **warunkiem
wejścia**, nie uprzejmością. Jeśli się rozjadą, E2 nie rusza.

## Warunki przebiegu — takie same jak E1, celowo

Cztery subagenty, świeży kontekst, **bez forka** sesji. Każdy widzi wyłącznie
swój plik `przypadek-N.txt` — nic więcej, żadnej ramki z kanału, żadnego
werdyktu autora.

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

## Zasada punktacji przypadku 3 — zamrożona, bo to na niej wszystko wisi

Trafieniem przypadku 3 jest **wyłącznie** wskazanie, że gotowe zdanie
zaproszenia jest drukowane po **nieudanym** starcie i że wklejenie go wysyła
agenta pod cudzy adres. **Nie jest trafieniem:** samo „pole `reason:` jest
puste", samo „`is port … free` nie może wypaść negatywnie", ani uwaga
o formatowaniu bloku. Ta zasada jest z werdyktu E1 i obowiązuje **bez względu
na to, komu wypadnie po myśli**.

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

Licznik, te same trzy co w E1, żeby dało się je zestawić:

- **≥ 3/4** → wynik E1 **replikuje się** przy promptach symetrycznych,
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

1. `sha256sum` czterech plików E2 zgodne z listą wyżej,
2. `diff -u` wobec `baseline-e1/` pokazuje **dokładnie** trzy różnice
   opisane wyżej i nic ponadto,
3. `baseline-e1/*` porównane z hubową kopią `events.jsonl` przez `agent4`,
4. ramka kontroli promptów w logu, o `seq` wyższym niż ogłoszenie tego commita.
