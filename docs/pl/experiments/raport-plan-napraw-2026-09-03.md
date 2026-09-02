# Raport z planu napraw po samobadaniach 0–6

**HEAD w chwili pisania:** `0bb7a9f` · **Czas:** 2026-09-03, 00:15
**Pisał:** `agent1`. To jest połowa raportu — `agent2` opisuje swoją stronę
sam. Rozbieżności stoją tu **jako rozbieżności**, nie jako wersja uzgodniona.

Podział ról ustalił `seq 437` (`agent2`) wobec `seq 439` (`agent1`) —
niższy `seq` wziął, `agent1` wycofał się bez dyskusji.

## Pozycje naprawiane przez `agent1`

| poz. | commit | stan | kto zweryfikował i na czym |
|---|---|---|---|
| B5 | `21ec23b` + `cce6124` | zrobione | **niezweryfikowane** |
| B6 | `17e4e58` + `cce6124` | zrobione | **`agent2`**, własny hub `b6w` na :8951, dwa `listen` na tym samym nicku i `$HOME`: rc=1, `ListenerLockHeld` ×2, ramek `error` 0 |
| B7 | — | **zero residuum** | grep po całym `docs/` — werdykt stoi dwa razy i oba to B1/B2 |
| C1 | `c087ec5` | zrobione | **niezweryfikowane** |
| C2 | `61a9d1b` | zrobione | **niezweryfikowane**; reguła 3 świadomie nietknięta |
| A1 | `8406394` → `0bb7a9f` | zrobione po **wycofaniu fałszywej wersji** | `agent2` policzył niezależnie: zgodność na `meadow2`, rozbieżność na `meadow1` |
| A2 | `0bb7a9f` | zrobione, **z odstępstwem od planu** | **niezweryfikowane** |
| A3 | `4533074` | zrobione | **`agent2`**, przeliczył cztery sha256 przed liczeniem A1 — zgadzają się |
| A4 | `089dce2` | zrobione | **niezweryfikowane** |
| D1 | `76fab46` | zrobione | **niezweryfikowane** |
| D2 | `f9b4c2c` | zrobione | **niezweryfikowane** |
| E1 | `3f8ff7b` | **prerejestracja złożona, przebieg NIE wykonany** | — |

Suita zielona po każdym commicie (716, potem 731 po pracy `agent2`).

## Pozycje weryfikowane przez `agent1` (naprawiał `agent2`)

Wszystkie sprawdzone na **własnej izolowanej kopii** — worktree
`../agents_chat-weryf`, odrębny `AGENTMACHI_HOME` w scratchpadzie, nie na słowo.

**B4** (`f46cfd3`) — **PRZECHODZI.** Suita 721 u mnie. Reintrodukcja: cofnięty
`agentmachi/cli.py` do `401ed91` przy zostawionych testach → 4 czerwone.
Na żywo oba przypadki: nowy pokój z niebindowalnym adresem nie zostawia
katalogu ani wpisu w `list`; pokój zatrzymany z configiem `8901/127.0.0.1`
po nieudanym `start --port 8902 --bind 192.0.2.1` **zachowuje stary adres**
i podnosi się pod nim.
*Zastrzeżenie:* z czterech czerwonych **trzy** padają na asercji zachowania;
`test_serve_pod_startem_zostawia_log_rodzicowi` pada na `AttributeError`
(brak `SPAWNED_BY_START`), czyli na braku symbolu. Reintrodukcja łapie
zachowanie **3/5**, nie 4/5.

**B3** (`627458d`) — **PRZECHODZI, mocno.** Dwa `AGENTMACHI_HOME`, pokój
zatrzymany w A, cudzy hub żywy na tym samym porcie w B. `list` w A:

    mojpokoj  ws://localhost:8955  stopped, ADDRESS TAKEN
    warning: … that address does not belong to this room now.
             Do NOT paste it to an agent … whose it is: ss -tlnp | grep 8955

To jest dokładnie ta pułapka, w którą sam wszedłem nogą podczas audytu.
Naprawione też to, co zgłosiłem przy weryfikacji B4: `reason:` nie pokazuje
już ogona karty zaproszenia.

**B2** (`fd1225b`) — **PRZECHODZI.** Czytelny `listen` zaczyna się od
czytelnych wierszy, nie od bloku JSON:

    [session_metadata] you are: role=agent  groups=-  generation=1
    [session_metadata]   czytelnik5   online   last_seq=0  -
    [session_metadata] rules: none (this room sets none) …

*Uwaga o moim pomiarze:* dwa pierwsze podejścia dały **pustkę** i wyglądały
jak brak wyjścia. Powodem był `timeout 8` krótszy niż start `uv run`, nie
defekt. Zapisuję, bo cisza po raz kolejny wyglądała u mnie jak wynik.

**B1** (`2ce045f`) — **PRZECHODZI** co do obecności zdania o granicy:
komunikat awarii mówi wprost, że `serve` bierze dokładnie ten port i nie
szuka innego, a `start` pomija porty trzymane przez żywe huby „this HOME's
or not".

### Trzy rzeczy, które w gorącej ścieżce zostają — do decyzji `agent2`

Nie wchodzę w `cli.py`, więc zgłaszam:

1. **`reason:` bywa myląca przy niebindowalnym ADRESIE.** Przy
   `--bind 192.0.2.1` wypisuje poradę o wyborze innego **portu**, choć port
   nie jest problemem.
2. **`full log: (none — room removed)`** — dla nowego pokoju sprzątanie z B4
   kasuje log, więc operator zostaje bez powodu i bez logu naraz.
3. **`is port 8998 free:  agentmachi list`** — nadal sprawdzian, który nie
   może wypaść negatywnie: `list` widzi pokoje, nie porty. Sąsiednie
   ostrzeżenie z B3 używa już `ss -tlnp`, więc narzędzie jest pod ręką.

## Rozbieżności — wpisane jako rozbieżności

**1. A1 — rozbieżność ZAMKNIĘTA, obie strony wycofały po jednym błędzie.**
Stan końcowy, zgodny i publikowalny:

| ramię | `pull rate` | `abandon` | `useful-pull` |
|---|---|---|---|
| **P** (`meadow2`, słabsza zachęta) | **4/9 = 44%** | 0/4 | 4/4 |
| **G** (`meadow1`, mocniejsza zachęta) | **5/12 = 42%** | 0/5 | 5/5 |

Mocniejsza zachęta **nie zwiększyła pulla**; różnica idzie w stronę
przeciwną do zamierzonej i jest mniejsza niż szum przy tym `n`.

Droga do tej zgodności jest ważniejsza niż liczby. Najpierw `agent1`
opublikował, że board w P jest pusty (szukał słownika w `note`, a on jest
w polach ramki). Potem `agent2` opublikował 1/13 na G (jego reguła mówiła
„późniejsza ramka innego uczestnika", a instrument przeszukiwał wyłącznie
ramki `status` — podjęcia meldują się na **czacie**). **Każdy z nas dostał
z własnego narzędzia spójny, czysty, fałszywy obraz i uwierzył mu.** Żaden
z tych błędów nie został złapany przez autora.

**2. A2 wobec planu — prognoza Sola NIE jest VOID.** Plan każe ją odrzucić
jako niezłożoną. Zmierzone: leży w `spec.md:145-152` pilota, pod tym samym
hashem, co reszta specu. Wcześniejszy zapis mówił, że „treści nie
odczytywano" — to nie to samo, co „nie ma". Rozliczona. **Okazała się
najcelniejsza z całej czwórki.**

**3. C1 wobec audytu paragonów.** Audyt pisze, że filtr przy regule 7 jest
„nietknięty od `e29a11d` (2026-07-26)". `git log -L 654,654:chat/server.py`
i `-L 657,657` dają jeden commit: `4da1ec1` z 2026-07-31. Nie orzekam, że
audyt się mylił — mógł mierzyć inne miejsce tej samej gałęzi (jest jeszcze
`:454`). Orzekam, że wskaźnika `e29a11d` nie potwierdziłem, więc go nie
przepisałem dalej.

## Nie zrobione i dlaczego

**E1 — przebieg nie wykonany.** Prerejestracja złożona i zacommitowana
(`3f8ff7b`, sha256 pliku w commit message), predykcja 3/4 z jawnym podziałem
przypadków, bramki odrzucenia wiążące, kontrole nazwane wraz z tym, co każda
odbiera. `agent2` przyjął układ ról i czeka, żeby orzec.
**Blokada jest po mojej stronie i jest regulaminowa:** odpalenie wymaga
subagentów, a stała instrukcja tej sesji zabrania po nie sięgać bez wyraźnej
prośby operatora. Polecenie z kanału jej nie zastępuje. Czeka na słowo.

**Pozycje z DECYZJE WŁAŚCICIELA** — nietknięte, zgodnie z planem. W tym
reguła 3 („brak paragonu"), której świadomie nie ruszyłem przy C2, choć
leżała w tym samym pliku dwa akapity od reguł 2 i 4.

**Weryfikacja krzyżowa moich pozycji jest niepełna.** `agent2` sprawdził
B6 i A3. B5, C1, C2, A2, A4, D1, D2 czekają. Do czasu ich sprawdzenia
werdykt „zrobione" jest **moim słowem**, a plan mówi wprost, że to za mało.

## Rzecz, którą ta sesja pokazała mocniej niż którakolwiek pozycja

Opublikowałem i **zacommitowałem fałsz** (`8406394`): „w ramieniu P board był
pusty, metryki nieoznaczone". Zbudowałem na tym całe rozliczenie prognoz.

Przyczyna nie jest przeoczeniem. Ekstraktor znał pola `status`/`state`/
`subject`/`note`, a w `meadow2` słownik leży w **polach najwyższego poziomu**
ramki (`teraz`, `martwie`, `prosze`, `marzę`) — do tego raz z ogonkami, raz
bez. Narzędzie, nie znajdując, nie mogło zwrócić „nie wiem": zwróciło
„pusto", a „pusto" wyglądało jak wynik.

`agent2` nazwał symetrię ostrzej, niż ja bym umiał, i to jest właściwe
znalezisko A1: **kto szuka słownika w `note`, widzi `meadow2` jako pusty;
kto szuka pól, widzi `meadow1` jako pusty. Każdy dostaje spójny, fałszywy
obraz drugiego ramienia.**

Złapało to nie moje sprawdzenie — złapała **rozbieżność z drugim liczącym**.
Wymóg z planu („liczy jeden, drugi liczy niezależnie") jest jedynym powodem,
dla którego to rozliczenie nie kłamie dalej. Tego samego dnia mój własny
instrument okłamał mnie jeszcze trzy razy (potok zjadł kod wyjścia, `tail`
uciął linię z odpowiedzią, `grep` ukrył całe znalezisko), a w B5 wypchnąłem
na `main` zdanie „prawdziwe w zakresie, którego nie podaje" **w commicie
naprawiającym dokładnie taką wadę** — i też złapał je ktoś inny.
