# B7: Nick przypięty do adresu — koniec podszywania w trybie open

Data: 2026-07-23. Autor projektu: worker1. Orchestrator: worker2 (zielone).
Zdalne stanowisko e2e: Opusek (VPS Hel). Zlecenie: @Emil — „załatwcie to
kurwa szczelnie i ostatecznie, że można się podszywać pod usera/agenta
kogokolwiek".

## Problem (potwierdzony e2e, nie teoria)

W trybie open (bez tokenu) tożsamość jest słaba: `from` i `instance_id`
podaje klient, więc każdy w tailnecie może się podszyć. B6 blokuje tylko
nick zajęty przez **połączonego** uczestnika — nick **rozłączonego** jest
wolny dla każdego.

Repro na żywym hubie (worker1): `ofiara-test` weszła open i się
rozłączyła; obcy `instance_id` „PODSZYWACZ" wysłał `hello` z
`from=ofiara-test` → hub odpowiedział `resync_required` (wpuścił) i obcy
napisał na kanał w imieniu ofiary.

Human jest już bezpieczny (wejście jako human wymaga tokenu —
`server.py:591`). Dziura dotyczy **agentów** w trybie open.

## Fundament (zweryfikowany w kodzie przed projektem)

- `ChatServer._handler(self, ws)` (`server.py:503`) ma `ws` — obiekt
  połączenia z atrybutem `remote_address` = `(host, port)`. Hub **widzi
  adres źródłowy peera**; klient go nie wpisuje i nie podrobi.
- Wiązanie mieszka w `Registry` (`identity.py`), obok `_instance`
  (nick→instance_id). Dodajemy `_open_addr` (nick→host).
- Sprawdzenie w gałęzi open-hello serwera (`server.py:~584`), tam gdzie
  dziś stoi kontrola „nick zajęty przez połączonego".

## Projekt

### Rdzeń

1. Przy **pierwszym** `hello` nicka w trybie open hub zapamiętuje **host**
   peera (samo IP z `remote_address`, **bez portu** — port źródłowy
   zmienia się co połączenie, więc wiązałby nick do jednego TCP).
2. Kolejne `hello` tego nicka:
   - z **tego samego host** → wpuszczenie (self-resume / reconnect),
   - z **innego host** → odmowa „nick przypięty do innego adresu",
     z propozycją wolnego nicka (jak dziś przy zajętym).
3. Wiązanie **przeżywa rozłączenie** — to cały sens. Rozłączony nick
   zostaje przypięty do swojego host, więc podszywacz z innego adresu
   dostaje odmowę mimo że nick „wolny".

### Zakres

- Dotyczy **wyłącznie trybu open**. W trybie z tokenem token dowodzi
  tożsamości — wiązanie adresu tam nie obowiązuje (bez zmian).
- Human ma token → nie dotyczy.

### Provisional-then-commit (review worker2, MUST)

`_open_addr` **musi iść tą samą ścieżką co tożsamość**: ustawiane na
`trial_registry` (klon), commitowane do live DOPIERO po udanym durable
appendzie `hello`. Dziś generation/instance są prowizoryczne na klonie i
lecą do kosza, gdy append padnie (OSError/dysk) — live zostaje nietknięty.
Gdyby `_open_addr` zapisać wprost na `self.registry`, nieudane hello
zostawiłoby przypięcie do adresu, którego **nigdy nie zalogowano** —
i podszywacz, któremu padł append, i tak przypiąłby sobie nick. To ten sam
niezmiennik „trwałość przed publikacją", który chroniliśmy w całym B1.

### Kolejność reguł w gałęzi open-hello (review worker2, MUST — jawna)

B6 ma dziś dwie reguły, B7 dokłada trzecią. Kolejność jest wiążąca:

1. **nick ŻYWY (connected):**
   - ten sam `instance_id` → **self-resume** (przejdź) — send/frame na
     trzymanym listenerze,
   - inny `instance_id` → **ODMOWA**, NIEZALEŻNIE od host.
2. **nick ROZŁĄCZONY, ale przypięty** (był już w trybie open):
   - ten sam host → **wpuszczenie** (reconnect / lokalny „swój"),
   - inny host → **ODMOWA** (podszycie, B7).
3. **nick WOLNY** (nigdy nie przypięty) → **wpuszczenie**, zapamiętaj host
   na `trial`.

### Rozstrzygnięcie pytania worker2: żywy nick + ten sam host + inny instance

**Decyzja: ODMOWA** (reguła 1, host nieistotny dla żywego nicka).

To wygląda na sprzeczne z decyzją (a) „lokalny = zaufany", ale nie jest —
i rozróżnienie jest sednem: zaufanie lokalne odblokowuje **rozłączony**
nick (nie traktujemy lokalnego procesu jako podszywacza), ale **żywy** nick
jest chroniony przed wypieraniem ZAWSZE. Powód nie jest teoretyczny:
**dziś przeżyliśmy wojnę generacji** dokładnie z tego, że dwa żywe procesy
tego samego nicku (`worker1`) wypierały się w kółko, 40+ takeoverów w kilka
sekund. Gdyby B7 wpuszczał „ten sam host, inny instance" jako takeover,
odtworzyłby tę wojnę dla lokalnych. Host liczy się **tylko** dla
rozłączonego nicku; żywy + inny instance = odmowa, kropka.

## Trzy rozstrzygnięcia (decyzje do review, nie sztywne)

### (a) Loopback — lokalni agenci dzielą adres

Agenci na maszynie huba łączą się z tego samego host (loopback albo
self-tailnet IP huba, np. `100.84.163.11`). Adres ich **nie rozróżnia** —
wiązanie po IP nic nie daje w obrębie jednej maszyny.

**Decyzja: lokalny host = zaufany-z-definicji.** Wiązanie chroni MIĘDZY
maszynami — to jest realny model zagrożeń („obcy z innego VPS"). Kto ma
dostęp lokalny do maszyny operatora, ma i tak dostęp do wszystkiego
(tokeny, pliki, procesy) — podszycie lokalne jest poza modelem.

**Świadome ograniczenie, zapisane jawnie** (jak ograniczenia B6): dwaj
agenci na TEJ SAMEJ maszynie mogą się nawzajem podszyć. Nie chronimy
przed tym, bo nie ma czego chronić — lokalny dostęp to już pełne zaufanie.
Adres loopback/self huba jest traktowany jako „ten sam podmiot".

### (b) Wygasanie — nick nie może wisieć na martwym adresie wiecznie

**Decyzja: wiązanie żyje w pamięci `Registry`, ginie z restartem huba.**
Registry ładuje się przy starcie z `tokens.json` (nie z wiązań), więc
restart huba czyści wszystkie przypięcia — to naturalne, zerokosztowe
wygasanie. Bez osobnego TTL na start (prostota — „less is more"): TTL to
timer, stan i kolejny przypadek brzegowy; dokładamy go dopiero, jeśli
praktyka pokaże, że restart to za rzadko.

Człowiek może zwolnić wiązanie ręcznie — patrz (c).

### (c) Ręczne odpięcie — rozkaz roota bije wiązanie

**Decyzja: `kick` zwalnia wiązanie.** Kick i tak odłącza uczestnika;
naturalnie powinien też odpiąć jego nick, żeby ktoś inny (albo ten sam
agent z nowego adresu) mógł wejść. Człowiek wyrzucający agenta świadomie
zwalnia jego tożsamość. Zero nowej komendy — rozszerzamy istniejący
`_on_kick`: po zamknięciu socketów usuń `_open_addr[nick]`.

To pokrywa też przypadek „agent zmienił adres" (restart VPS → nowy tailnet
IP): jego stary nick jest przypięty do starego host i odmawia z nowego;
człowiek robi `/kick <nick>` i agent wchodzi z nowego adresu. Rozkaz roota
bije wiązanie — spójne z regułą 1 (człowiek > agent).

## Ograniczenia — jawne, nie przemilczane

- Chroni MIĘDZY maszynami, NIE w obrębie jednej (patrz (a)).
- Zakłada, że adres tailnetu jest wiarygodny — w trybie open jest, bo hub
  stoi na loopbacku/tailnecie; przy bindzie `0.0.0.0` tryb open jest i tak
  wyłączony (B6 wymaga tam tokenu), więc adres zza tunelu/proxy nas nie
  dotyczy.
- Wiązanie ginie z restartem huba — świadomie (b).

## Kryterium zaliczenia (worker2)

1. **repro worker1 MUSI dać odmowę:** obcy instance na rozłączony nick
   z innego adresu → error, nie wejście.
2. **self-reconnect MUSI przejść:** ten sam nick z tego samego adresu →
   wpuszczenie.
3. **e2e Opusek (VPS):** po fixie Opusek próbuje podszyć się pod cudzy
   rozłączony nick z Helsinek → musi paść; wraca na własny nick z tego
   samego adresu → musi przejść.
4. Regresja: wszystkie dotychczasowe testów zielone; tryb tokenowy i
   kontrola „zajęty przez połączonego" nietknięte.

## Podział

- **worker1**: trzyma całość end-to-end (projekt, integracja, weryfikacja
  na żywym hubie + koordynacja Opuska). Kod mogę napisać sam albo poprosić
  worker2 o kawałek pod ten kontrakt — całość i „działa" zostaje u mnie.
- **worker2** (orchestrator): dostarcza, o co poproszę; nie dubluje.
- **Opusek**: zdalne stanowisko e2e z VPS.

## Stan

- [x] problem potwierdzony e2e (repro worker1)
- [x] fundament zweryfikowany (`ws.remote_address` istnieje)
- [x] projekt spisany (ten plik)
- [ ] review orchestratora + Opuska — **przed** kodem
- [ ] implementacja (Registry `_open_addr` + gałąź open-hello + kick zwalnia)
- [ ] weryfikacja: repro→odmowa, self-reconnect→przejście, Opusek e2e
