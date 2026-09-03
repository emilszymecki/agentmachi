# E1 — prerejestracja: ramię B2, subagent bez dziedziczenia

**Status: PREREJESTRACJA — WYKONANA 2026-09-03.**
Wynik surowy 3/4, NIEORZECZONY: [`e1-subagent-swiezy-kontekst-2026-09-03.md`](e1-subagent-swiezy-kontekst-2026-09-03.md).
Ten plik zostaje **nietknięty poza tym zdaniem** — `sha256` treści poniżej
był sprawdzany przed odpaleniem i zgadzał się z commitem `3f8ff7b`.

**W chwili commita `3f8ff7b` przebieg NIE był wykonany.**
Kolejność jest tu całym dowodem — ten plik ma być starszy niż pierwszy prompt.

**Pisał:** `agent1` · **Odpala:** `agent1` · **Orzeka:** `agent2` (podział
z `seq 437`, niższy `seq` wziął) · **HEAD prerejestracji:** patrz commit
zawierający ten plik.

## Pytanie, i tylko to pytanie

[`subagent-vs-peer-2026-09-02.md`](subagent-vs-peer-2026-09-02.md) obalił
zdanie z `zasady-agentyczne.md`: „subagent tego nie złapie, **bo dziedziczy**
hipotezę razem z pomiarem". Wynik ramienia B: **4/4**, obie prerejestrowane
predykcje autorów sfalsyfikowane.

Ale ramię B dawało subagentowi brief **z ramką autora, jego werdyktem i jego
danymi** — czyli dziedziczenie było tam WŁĄCZONE i mimo to nie zaszkodziło.
Nie wiemy więc, czy fałszywy jest **wniosek** („nie złapie"), czy także
**przyczyna** („bo dziedziczy"). Ramię B2 zdejmuje dziedziczenie i patrzy,
czy licznik się ruszy.

## Materiał — te same cztery przypadki, bez zmian

Z [`audyt-szwow-docow-2026-09-02.md`](audyt-szwow-docow-2026-09-02.md),
sekcja o parze. Każdy to martwe pole autora, złapane przez drugiego:

| # | przypadek | autor martwego pola |
|---|---|---|
| 1 | „`start` przy zajętym porcie kończy exit 0" | agent2 |
| 2 | „B2 KŁAMIE" (werdykt wycofany po regule o dwuznaczności) | agent1 |
| 3 | zdanie zaproszenia drukowane po AWARII startu, przeoczone we własnym `grep` | agent1 |
| 4 | „Wniosek brzmi jak certyfikat" | agent2 |

## Różnica wobec ramienia B — jedna, celowo

Ramię B: brief **z** ramką autora, werdyktem i danymi.
Ramię B2: **sam artefakt** plus neutralne polecenie („zrecenzuj, zgłoś
problemy"), bez werdyktu autora, bez jego danych, bez sugestii, że jest co
znaleźć. Nic więcej się nie zmienia.

## Kontrole — i co każda z nich odbiera

Zgodnie z [D2](README.md) nazywam to **przed** przebiegiem, nie po:

- **autor nie pisze promptu do własnego przypadku.** Odbiera: nic mierzalnego;
  koszt jest organizacyjny.
- **zakaz czytania repo.** Odbiera: możliwość rozwiązania zadania przez
  znalezienie cudzej odpowiedzi — raport z odpowiedziami jest zacommitowany.
- **brak narzędzi**, dla porównywalności z ramieniem B. **Odbiera całą klasę
  znalezisk**: pójście do kodu i wskazanie przyczyny. To jest dokładnie ta
  klasa, którą w #6 znalazło ramię niekontrolowane. B2 mierzy więc krytykę
  tekstu, nie diagnozę — i nie wolno go czytać jako pomiaru „co subagent
  potrafi".

## Moja predykcja — zamrożona tutaj, przed odpaleniem

**3 z 4.**

Z podziałem, bo sam licznik da się trafić przypadkiem:

- **trafi 1** (exit 0) — sprzeczność jest wewnątrz tekstu, nie potrzebuje
  kontekstu,
- **trafi 3** (zdanie zaproszenia po awarii) — j.w., widać z samego wydruku,
- **trafi 4** („wniosek brzmi jak certyfikat") — to własność tekstu, a brak
  autorstwa jest tu przewagą, nie stratą,
- **nie trafi 2** („B2 KŁAMIE") — żeby zobaczyć dwuznaczność, trzeba wiedzieć,
  co dokładnie obiecywał doc i co zmierzono; bez danych autora subagent nie ma
  z czego zbudować zarzutu.

Jeśli trafi 2, a nie trafi któregoś z 1/3/4 — mój mechanizm jest zły, nawet
przy zgodnym liczniku, i tak to ma zostać zapisane.

## Bramki odrzucenia — wiążące, ustalone przed przebiegiem

- **B2 ≥ 3/4** → dziedziczenie **nie jest** mechanizmem. Fałszywy jest i wniosek
  zdania z repo, i jego przyczyna. Zapisujemy wprost, bez „to były łatwe
  przypadki".
- **B2 ≤ 1/4** → dziedziczenie **pomagało**: kontekst autora niósł pytanie.
  Wtedy wynik #6 jest własnością BRIEFU, nie subagencji, i wniosek #6 trzeba
  w tekście zwęzić.
- **B2 = 2/4** → `INCONCLUSIVE`. Żadnego werdyktu o przyczynie; to też idzie
  do raportu, zamiast być dociągnięte w którąś stronę.

Licznik nie jest jedynym wyjściem: rozbieżność między moim przewidzianym
podziałem a faktycznym trafieniem raportujemy osobno od liczby.

## Czego ten przebieg nie rozstrzygnie

- **N=4**, te same cztery przypadki co w #6 — wybrane dlatego, że para je
  złapała. Przypadki, których nikt nie złapał, nie mają jak tu trafić.
- Nie mierzy „czy subagent jest lepszy od peera". Mierzy jedną zmienną:
  czy zdjęcie dziedziczenia rusza licznik.
- Materiał jest z tego projektu — self-hosting, z tym samym zastrzeżeniem
  co w #6.

## Warunek wykonania

Odpalenie wymaga uruchomienia subagentów. **Czeka na wyraźne słowo operatora**
— stała instrukcja tej sesji zabrania sięgać po subagenty bez jego prośby,
a polecenie z kanału jej nie zastępuje. Do tego czasu ten plik jest wyłącznie
zamrożoną predykcją i nic z niej nie wynika.
