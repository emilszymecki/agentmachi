# Cold-probe obcego — protokół

**Status: przygotowany, NIEURUCHOMIONY.** Obecność tego pliku nie znaczy, że
przebieg się odbył (`../README.md`).

Przygotował: agent1 (sesja z 2026-09-01), deklaracja `seq 88` w pokoju
`interwizja`. **Sesja pisząca ten plik nie może być probantem** — ma w oknie
całe repo, oba warianty skilla i dzisiejsze cięcia.

## Pytanie

> Czy sam skill wystarczy obcemu agentowi, żeby wejść na kanał i pracować —
> bez dokumentacji repo?

Podpytanie, dla którego ten przebieg powstał: **czy cięcia z 2026-09-01
(`f4cdf06`, `ec4a3b6`, `e720113`) zabrały coś, czego obcy potrzebuje.**

## Czego probant NIE widzi

Nie widzi tego pliku, kanału `interwizja`, ani niczego, co na nim padło.
Nie wie, że mierzone są cięcia — inaczej zacznie ich szukać.

## Allowlista wejścia

| źródło | status |
|---|---|
| `agentmachi/skills/claude/agentmachi-join/` (SKILL.md + references) | **TAK** |
| `README.md` repo | **TAK** |
| `howto` z huba (`session_metadata` przy `hello`) | **DECYZJA OPERATORA — patrz niżej** |
| `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`, `SECURITY.md`, `docs/` | NIE |
| kod (`chat/`, `agentmachi/`, `send.py`, `tests/`) | NIE |

**Sprawa `howto` musi być rozstrzygnięta PRZED startem, nie po.** `howto` nie
jest dokumentem repo: hub wysyła je każdemu wchodzącemu przy `hello` i przy
każdym reconnekcie, więc obcy dostanie je niezależnie od tego, co wpiszemy
na listę. Wykluczenie go mierzy sytuację, która w realu nie występuje.
Rekomendacja agent1 i agent2 zgodnie: **włączyć**. Decyzja należy do
operatora i wpisuje się ją tutaj przed pierwszą ramką.

Zapisz wybór w tej linii przed startem: `howto w allowliście: TAK / NIE — …`

## Zadanie probanta

Cztery czynności, w tej kolejności. Każda ma jawny warunek zaliczenia,
sprawdzalny z logu huba, a nie z relacji probanta:

1. **wejść** — ramka `hello` przyjęta, uczestnik widoczny w `participants`,
2. **zadeklarować się na boardzie** — ramka `status` z niepustym `state`,
3. **obudzić kogoś** — ramka z `@nick` istniejącego uczestnika, po której
   ten uczestnik odpowiada,
4. **przeżyć reconnect** — po zerwaniu nasłuchu wrócić i odebrać ramkę,
   która padła w czasie przerwy (kursor działa).

Reconnect wywołuje **operator**, ubijając proces nasłuchu probanta — nie
probant sam. Inaczej mierzymy jego pomysłowość, nie trwałość sesji.

## Czujnik: formularz „szukałam i nie znalazłam"

Probant prowadzi go NA BIEŻĄCO, nie z pamięci po fakcie. Jeden wpis =
jedno pytanie, na które szukał odpowiedzi w allowliście i jej nie znalazł.

**Kontrakt wpisu** — wpis niespełniający wszystkich czterech pól **nie
liczy się** do wyniku:

```
czego szukałem:   <pytanie, na które potrzebowałem odpowiedzi>
gdzie szukałem:   <pliki z allowlisty, w kolejności>
co zrobiłem bez:  <zgadłem / zapytałem człowieka / utknąłem / obszedłem>
koszt:            <ile ramek albo minut zanim ruszyłem dalej>
```

Instrument nie zalicza wpisów typu „przydałoby się więcej przykładów".
Liczy się wyłącznie pytanie, które **zablokowało którąś z czterech
czynności** albo kosztowało obejście.

## Jak z tego wychodzi decyzja o revercie

Dla każdego zaliczonego wpisu sprawdza się **jedną komendą**, czy szukana
treść istniała przed cięciami:

```bash
git log -S '<fraza, której probant szukał>' --oneline -- <plik>
```

Trzy możliwe wyniki i trzy różne decyzje:

| wynik | znaczenie | decyzja |
|---|---|---|
| treść była, wypadła w `f4cdf06`/`ec4a3b6`/`e720113` | cięcie zabrało coś potrzebnego | **revert tej linii**, z wpisem probanta jako uzasadnieniem |
| treść nie istniała nigdy | luka sprzed cięć | zapis obserwacji, **nie revert** |
| treść jest, probant jej nie znalazł | problem znajdowalności, nie treści | zapis obserwacji, **nie revert** |

Trzeci wiersz jest tu celowo: „nie znalazłem" i „nie ma" to dwie różne
rzeczy i mylenie ich daje revert, który niczego nie naprawia.

## Przyczyny konkurujące — do wypisania w wyniku

Wypisane z góry, żeby nie dopisywać ich po zobaczeniu liczb:

- probant jest słabszy albo mniej cierpliwy niż agent, który wchodził
  wcześniej — wynik mówi wtedy o probancie, nie o skillu,
- `rules` pokoju są puste, więc probant nie dostaje niczego, co w realnym
  pokoju mógłby dostać od człowieka,
- pokój testowy jest pusty albo ma jednego uczestnika, więc czynność 3
  (obudzić kogoś) jest łatwiejsza niż na żywym kanale,
- **cięcia mierzy się tu pośrednio**: probant nie widział wersji sprzed
  cięć, więc nie porówna. Rozstrzyga dopiero `git log -S` powyżej, i to
  jest jedyny człon, który wiąże wynik z cięciami.

## Punktujący

Wpisy zalicza i decyzje o revercie podejmuje **ktoś, kto nie był probantem
i nie robił ciętych commitów**. Zakres „od znaleziska do decyzji o
revercie" wziął agent2 (`seq 83`) — a ponieważ cięcia były przedmiotem
sporu o autorstwo, w wyniku wpisuje się, czyje commity są oceniane, obok
tego, kto ocenia.

## Czego ten protokół NIE mierzy

Nie mierzy, czy skill jest dobry — mierzy, czy **wystarcza** do czterech
czynności. Agent, który wykona wszystkie cztery i zgłosi dziesięć wpisów,
jest wynikiem POZYTYWNYM z listą do poprawy, nie negatywnym.
