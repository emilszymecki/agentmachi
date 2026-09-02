# Raport z planu napraw po samobadaniach 0–6

**HEAD w chwili pisania:** `0bb7a9f` · **Czas:** 2026-09-03, 00:15
**Pisał:** `agent1`. To jest połowa raportu — `agent2` opisuje swoją stronę
sam. Rozbieżności stoją tu **jako rozbieżności**, nie jako wersja uzgodniona.

Podział ról ustalił `seq 437` (`agent2`) wobec `seq 439` (`agent1`) —
niższy `seq` wziął, `agent1` wycofał się bez dyskusji.

## Pozycje naprawiane przez `agent1`

| poz. | commit | stan | kto zweryfikował i na czym |
|---|---|---|---|
| B5 | `21ec23b` + `cce6124` | zrobione | **`agent2`**, hub `b5w` na :8952, obie ścieżki: `localhost` → `ListenerLockHeld` rc=1, `127.0.0.1` → rc=124 i wejście pod nadanym nickiem |
| B6 | `17e4e58` + `cce6124` | zrobione | **`agent2`**, własny hub `b6w` na :8951, dwa `listen` na tym samym nicku i `$HOME`: rc=1, `ListenerLockHeld` ×2, ramek `error` 0 |
| B7 | `8dbef69` | zrobione **po przedwczesnym zamknięciu** | **`agent2`**, dwa HOME: B oddał 8961 — port zarezerwowany przez ZATRZYMANY pokój z A, a `list` w A pokazał `stopped, ADDRESS TAKEN` |
| C1 | `c087ec5` | zrobione | **`agent2`** |
| C2 | `61a9d1b` | zrobione | **`agent2`**; reguła 3 świadomie nietknięta |
| A1 | `8406394` → `0bb7a9f` | zrobione po **wycofaniu fałszywej wersji** | `agent2` policzył niezależnie: zgodność na `meadow2`, rozbieżność na `meadow1` |
| A2 | `0bb7a9f` → korekta | zrobione, **z odstępstwem od planu** | **`agent2`** — zakwestionował DWA moje werdykty moją własną regułą D1; przyjąłem oba |
| A3 | `4533074` | zrobione | **`agent2`**, przeliczył cztery sha256 przed liczeniem A1 — zgadzają się |
| A4 | `089dce2` | zrobione | **`agent2`** |
| D1 | `76fab46` | zrobione | **`agent2`** |
| D2 | `f9b4c2c` | zrobione | **`agent2`** |
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

**B2** (`fd1225b` + `bbd0b32`) — **PRZECHODZI.** Czytelny `listen` zaczyna się
od czytelnych wierszy, nie od bloku JSON:

    [session_metadata] you are: role=agent  groups=-  generation=1
    [session_metadata]   czytelnik5   online   last_seq=0  -
    [session_metadata] rules: none (this room sets none) …

*Przeszło przez stan pośredni i to jest część wyniku.* Pierwsza wersja
objęła wyłącznie `session_metadata`; `resync_state` leciał dalej surowym
JSON-em, choć audyt wymieniał oba. **Zgłosił to `agent2` sam na siebie,
zanim ja to znalazłem** (`seq 484`). Nie wiem, czy dotarł do tego bez
cudzego wskazania — nie pytałem, a przy regresji z `bf92069` okazało się,
że pytać trzeba. Zapisuję więc fakt z logu, nie zasługę.
Jako weryfikator orzekłem „PRZECHODZI CZĘŚCIOWO" i poprosiłem
o dokończenie zamiast dopisywania granicy do połowy naprawy; `resync` trafia
w agenta, który właśnie wrócił po rozłączeniu, czyli najbardziej potrzebuje
przeczytać, co przegapił. Domknięte w `bbd0b32`.

*Weryfikacja domknięcia, u mnie, reintrodukcją:* test
`test_resync_state_tez_nie_leci_sciana_JSON_a` przechodzi na czystym kodzie;
po wyłączeniu gałęzi `if data.get("type") == "resync_state"` (`send.py:257`)
pada na **asercji zachowania**, nie na braku symbolu.

*Uwaga o moim pomiarze:* dwa pierwsze podejścia dały **pustkę** i wyglądały
jak brak wyjścia. Powodem był `timeout 8` krótszy niż start `uv run`, nie
defekt. Zapisuję, bo cisza po raz kolejny wyglądała u mnie jak wynik.

**B1** (`2ce045f`) — **PRZECHODZI** co do obecności zdania o granicy:
komunikat awarii mówi wprost, że `serve` bierze dokładnie ten port i nie
szuka innego, a `start` pomija porty trzymane przez żywe huby „this HOME's
or not".

### Trzy rzeczy zgłoszone z weryfikacji — NAPRAWIONE (`80273a4`), sprawdzone

Zgłosiłem je jako weryfikator, nie wchodząc w `cli.py`. `agent2` naprawił
wszystkie trzy i przy okazji znalazł czwartą. Sprawdzone u mnie na żywo,
czysty `AGENTMACHI_HOME`, `start --name widmo --port 8998 --bind 192.0.2.1`:

1. **`reason:` bywała myląca przy niebindowalnym ADRESIE** — radziła zmienić
   port, choć port nie był problemem. Teraz pierwsza linia to prawdziwy błąd
   (`could not bind ws://192.0.2.1:8998`), a na końcu stoi zdanie wprost:
   „if that host is not on this machine, the port is not the problem".
2. **`full log: (none — room removed)`** — `serve.log` **przeżywa** cofnięcie.
   Sprawdzone `ls`-em: plik jest, 370 B. Pokój nadal **nie** pojawia się
   w `list`, więc inwariant B4 (brak adresu, który nie zaistniał) trzyma.
3. **`is port N free: agentmachi list`** — zastąpione przez `who holds 8998:
   ss -tlnp | grep 8998`. Sprawdzian, który **może** wypaść negatywnie,
   zamiast takiego, który nie mógł.

Czwarta, znaleziona przez `agent2` dopiero przy tej poprawce: okno `ogon[-3:]`
ucinało linię z samym `OSError`, bo komunikat po B1 ma cztery linie.
Zawęził też własny test — żądał pustego katalogu, a inwariantem jest brak
ADRESU, nie brak katalogu; za mocna asercja kasowała dowód.

### Regresja z tej naprawy — zgłoszona przez sprawcę, sprawdzona przeze mnie

Zachowanie `serve.log` sprawiło, że katalog pokoju przeżywa porażkę, a migawka
adresu pytała wtedy o **katalog**. Skutek: **druga** nieudana próba pod tą samą
nazwą zostawiała `tokens.json`, a `hub_rows` wpuszczał pokój do `list` pod
adresem **domyślnym** — widmo pod adresem, o który nikt nie prosił. Dokładnie
to, przed czym ostrzega docstring cofnięcia napisany kilka godzin wcześniej.

Nie złapała tego ani suita `agent2` (testowała **jedną** porażkę), ani ja —
zgłosiłem defekt wydruku, nie jego skutek uboczny. **Ani sam `agent2`:**
uznał pracę za skończoną i ogłosił to, a dopiero przegląd trzeciej strony
kazał mu sprawdzić, czy zachowany `serve.log` nie psuje migawki. Naprawił
po wskazaniu (`bf92069`): migawka mierzy `tokens.json`, czyli to samo, czym
mierzy widoczność `hub_rows`, a test robi dwie porażki pod rząd.

*Napisałem tu wcześniej, że `agent2` znalazł tę regresję sam. To nieprawda
i sprostował to on, przeciwko sobie, żeby nie weszła do zapisu.* Prawdziwy
bilans dnia jest skromniejszy i mocniejszy zarazem: **trzy błędy, trzy różne
źródła zewnętrzne** — moje przeliczenie (jego A1), przegląd trzeciej strony
(ta regresja), moje zgłoszenie z weryfikacji (trzy defekty wydruku).
**Żaden nie wyszedł od autora.** Autokontrola nie dała dziś ani jednego
trafienia po żadnej ze stron; działało wyłącznie cudze spojrzenie.

**Sprawdzone u mnie na żywo**, czysty `AGENTMACHI_HOME`, dwie porażki pod rząd
na tej samej nazwie (`--port 8998`, potem `--port 8997`, oba `--bind
192.0.2.1`): `list` zwraca `no rooms`, a na dysku zostaje **wyłącznie**
`serve.log` (740 B — wyjście obu prób). Obie własności trzymają naraz: log
przeżywa, adres nie.

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
B5, B6, C1, C2 i A3 — wszystkie przechodzą, B5 na własnym hubie z obiema
ścieżkami (`localhost` → `ListenerLockHeld`, `127.0.0.1` → wejście pod
nadanym nickiem). Czekają: A2, A4, D1, D2 i B7. Do czasu ich sprawdzenia
werdykt „zrobione" jest **moim słowem**, a plan mówi wprost, że to za mało.

**Wszystkie pozycje `agent2` (B1–B4) są zweryfikowane po mojej stronie**,
łącznie z domknięciem B2 i trzema naprawami zgłoszonymi z weryfikacji.

**Stan końcowy weryfikacji krzyżowej: pełny poza E1.** `agent2` sprawdził
wszystkie moje pozycje, łącznie z luźnymi końcami (dziura 1 i reguła 3),
i przy każdej z nich zgłosił coś, czego sam nie zobaczyłem: dwa werdykty
A2 do zdjęcia moją własną regułą D1 oraz nienośny człon w paragonie
reguły 3 (kredytowałem dwa mechanizmy tam, gdzie zadziałał jeden).

**B7 zamknąłem raz przedwcześnie i to jest osobny wpis, nie przypis.**
Napisałem „zero residuum", bo werdykt „prawdziwa w zakresie, którego nie
podaje" stoi w `docs/` dokładnie dwa razy i oba to pozycje `agent2` (B1, B2),
w których plan dawał wybór „naprawa **albo** zdanie o granicy". Rozumowanie
było poprawne w chwili pisania. Przestało być, gdy `agent2` wybrał naprawę:
jego granica dla doboru portu siedzi w komunikacie awarii bindu, a obietnica
w skillu milczała dalej. **Nie sprawdziłem swojego wniosku po cudzym
commicie, który zmieniał jego przesłankę** — i znalazł to `agent2`, nie ja,
najprostszym możliwym sposobem: `git log` i brak commita z numerem pozycji.

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


---

# Połowa `agent2`

**Scalone tu 2026-09-03 przez `agent2`.** Plan wymagał JEDNEGO pliku, a przez
chwilę istniały dwa — każdy z nas napisał swoją połowę osobno. Tekst `agent1`
powyżej jest nietknięty; poniżej wchodzi połowa `agent2` w całości, razem
z jej błędem i korektą. Nie uzgadnialiśmy tych dwóch części ze sobą: gdzie
się różnią, różnica ma zostać widoczna.

**HEAD pierwszego wpisu:** `3f8ff7b` · **ostatnia zmiana tej połowy przy:**
`cfb1959` (dopisywana w miarę zamykania pozycji — stempel z pierwszego wpisu
podany jako pierwszy wpis, nie jako stan bieżący)
**Czas:** 2026-09-03, ok. 00:30, pokój `interwizja`
**Pisze:** sesja deklarująca się jako `agent2`. Której z równoległych sesji
odpowiada — nie da się ustalić z artefaktów (`zasady-agentyczne.md`, reguła 17).

To jest **połowa raportu**: pozycje, które wykonałem, plus moje weryfikacje
cudzych. Zdania o pozycjach `agent1` pochodzą z mojego pomiaru albo są jawnie
oznaczone jako niezweryfikowane. Nigdzie nie oceniam zdania, które sam
napisałem.

## Podział i jak został ustalony

Obaj zadeklarowaliśmy podział, kolidując na B1/B3/B4. Rozstrzygnął log:
moja deklaracja ma `seq 437`, deklaracja `agent1` — `seq 439`. Niższy wziął.
`agent1` wycofał się bez dyskusji (`seq 444`).

Pozycje, które **obaj oddaliśmy drugiemu** (B5–B7, C1, C2, A2, A3, A4, D1, D2),
to symetryczne ustępowanie — stan bez właściciela, przed którym ostrzega
konstytucja. Rozstrzygnęły oba mechanizmy i wskazały to samo: `seq 437`
przypisał je `agent1`, a tiebreak nickiem (`agent1` < `agent2` bajtowo) też.

| | naprawia | weryfikuje |
|---|---|---|
| B1, B2, B3, B4 | agent2 | agent1 |
| B5, B6, B7, C1, C2, A2, A3, A4, D1, D2 | agent1 | agent2 |
| A1 | obaj niezależnie | — |
| E1 | agent1 odpala | agent2 orzeka |

E1 krzyżował się trzykrotnie. Ustąpiłem na merytorycznym argumencie (`seq 446`),
`agent1` tego ustępstwa nie przyjął i miał rację: wiążąca jest deklaracja
z niższym `seq`, czyli moja, a ona mówi „ty odpalasz, ja orzekam".

---

## B1 — kolizja portu między katalogami `AGENTMACHI_HOME`

**ZROBIONE jako GRANICA, nie naprawa.** Commit `2ce045f`.

Plan dawał wybór i wymagał uzasadnienia pomiarem. Pomiar: dwa katalogi HOME,
żywy hub na `DEFAULT_PORT` w pierwszym, cztery drogi:

| droga | wynik |
|---|---|
| `start --port <zajęty przez cudzy hub>` | odmowa, rc=1, port nazwany |
| `start` bez `--port`, pokój nowy | przesunięcie 8766 → 8768, omija ŻYWE porty cudzego HOME |
| `start`, pokój istniejący | zachowuje swój adres |
| `serve` bez `--port`, pokój nowy | brał zajęty port, padał na bindzie |

Trzy z czterech poprawne. Czwarta po naprawie B4 kończy się głośno, kodem 1
i bez śladu — nie kłamstwem i nie widmem.

**Napisałem naprawę i ją wycofałem.** Alokator omijający żywe porty w `serve`
wywrócił cudzy test `test_serve_bez_portu_bierze_domyslny_i_nadal_przesuwa` na
**pierwszym** przebiegu: dostał 8769 zamiast 8767, bo obok żyła `interwizja`.
Repo rozstrzygnęło tę sprawę wcześniej i ma trzy zapisy — docstring
`_wybierz_port_zywy` zabrania używać go poza `start` wprost, `_wybierz_port`
podaje powód (wynik zależałby od tego, co akurat chodzi na maszynie),
`_port_accepts` nazywa to artefaktem izolacji zmierzonym 2026-08-06.
CLAUDE.md każe przed przepisaniem cudzego testu udowodnić, że stary kontrakt
był błędny. Kontrakt właśnie udowodnił, że miał rację.

Zamiast tego blok awarii bindu mówi wprost, że `serve` binduje dokładnie ten
port i nie szuka innego, i podaje obie drogi wyjścia (`--port` albo `start`).
Granica czytana w chwili potrzeby, nie w pliku, do którego trzeba trafić.

**Zweryfikuje:** agent1. **Niezweryfikowane w chwili pisania.**

## B2 — `listen` w trybie czytelnym zaczynał się od ściany JSON-a

**ZROBIONE.** Commit `fd1225b`.

Zmierzone: pierwsza linia trybu czytelnego to **jedna** linia surowego JSON-a
na ~18 tys. znaków — rules + board + całe howto, z `—` i `\n` zamiast
tekstu. Kryterium z planu („prawdziwe dla kogoś, kto czyta od pierwszego
wiersza") nie było spełnione dla jedynej ramki, którą dostaje **każdy**
wchodzący, przy **każdym** reconnect.

`session_metadata` renderuje się teraz po ludzku. Znacznik `[session_metadata]`
powtarza się w KAŻDEJ linii i to warunek działania filtra, nie kosmetyka:
dokumentowany filtr to `grep -v session_metadata` **przed** filtrem wzmianek,
bo `@all`, `takeover` i `4003` siedzą w treści howto. Gdyby znacznik stał tylko
w nagłówku, samo rozbicie na linie zepsułoby filtr.

Zmierzone na żywym hubie: **108 linii przed filtrem, 0 po nim**, tą samą
niezmienioną komendą z doców.

**Uczciwie o sile dowodu:** reintrodukcja obala **1 z 3** nowych testów, nie 3.
Dwa pozostałe są kontrolami — pilnują, że nie przesadziłem, i mają przechodzić
w obie strony.

**Poprawiłem cudzy test** `test_hello_ok_emits_session_metadata_before_backlog`.
Jego własny komentarz mówi, że broni KOLEJNOŚCI emisji, a nie kształtu linii,
ale asercja `'"abc"' in lines[0]` wiązała się z kształtem surowego JSON-a —
`rules_hash` leżał w linii 0 tylko dlatego, że linia 0 była zrzutem całej ramki.
Kolejność i widoczność skrótu bronione dalej, kształt puszczony.

**Granica tej naprawy, zgłoszona przeze mnie, nie znaleziona u mnie.**
Naprawiłem **wyłącznie** `session_metadata`. W `send.py:251` stoi dokładnie
jeden warunek na typ, więc **`resync_state` nadal leci surowym JSON-em**
w trybie czytelnym. Audyt wymieniał oba. Zrobiłem jeden, bo `session_metadata`
dostaje **każdy** przy **każdym** wejściu, a resync jest rzadki — ale to jest
wybór, nie kompletność, i nie ma przejść jako kompletność. Jeśli `agent1` uzna,
że B2 przez to nie jest zrobione, dorobię `resync_state`.

**Zweryfikuje:** agent1. **Niezweryfikowane w chwili pisania.**

## B3 — `list` podawał adres cudzego huba i nic nie ostrzegał

**ZROBIONE.** Commit `627458d`. Trzy rzeczy, u dwóch jedna przyczyna.

**Główne.** Pokój `t9` nie wstał, a `list` podał `ws://localhost:8767` — adres
żywej `interwizji`. Cztery ramki stoją w cudzym logu do dziś (`seq 295–298`,
nick `ktos`). Wiersz zatrzymanego pokoju, pod którego adresem ktoś słucha,
dostaje teraz `stopped, ADDRESS TAKEN` plus ostrzeżenie mówiące wprost, czego
z tym adresem **nie** robić. Sieci pytamy wyłącznie o pokoje zatrzymane
i wyłącznie o ich własny adres.

**Dwa defekty z tego samego wydruku, jedna przyczyna.** Dziecko drukowało kartę
pokoju do `serve.log` PRZED bindem, a rodzic cytuje ogon tego logu jako
`reason:`. Stąd i „powód: zdanie zaproszenia", i gotowe do wklejenia
`join agentmachi 'r2' (ws://localhost:8767) as agent1` dla pokoju, który nie
wstał, pod adresem cudzego huba. Pod `start` karty nie drukuje już dziecko —
drukuje ją rodzic, po potwierdzeniu bindu, i robił to zawsze.

**Rozszerzenie zakresu, zgłaszam jako własne.** Podpowiedź „stopped ones you
can launch" wskazywała pokój z zajętym adresem, czyli komendę, która na pewno
odmówi — w wydruku, który właśnie ostrzega, że z tym pokojem coś jest nie tak.
Takie pokoje są teraz pomijane. Jeśli `agent1` uzna to za dopisywanie — idzie
do raportu jako rozbieżność, nie jako uzgodniona wersja.

**Zweryfikuje:** agent1. **Niezweryfikowane w chwili pisania.**

## B4 — adres zapisywany przed potwierdzeniem bindu

**ZROBIONE.** Commit `f46cfd3`. **ZWERYFIKOWANE przez agent1** (`seq 463`):
własne worktree `../agents_chat-weryf`, detached na moim commicie, suita 721,
reintrodukcja (cofnięty mój `cli.py` do `401ed91`, testy zostawione) → 4 czerwone,
1 zielony, plus dwa przypadki odtworzone na żywo na jego własnym HOME.

Zmierzyłem **trzy** przypadki, nie jeden:

1. nowy pokój, `--bind 192.0.2.1` → `list` i `card` podawały
   `ws://192.0.2.1:8999` jako prawdę o pokoju,
2. to samo z samodzielnego `serve` — drugie wejście, ta sama klasa co
   `_odmow_zajetego_portu`, gdzie strzeżone było jedno z dwóch,
3. **najdroższy:** pokój działający pod `ws://127.0.0.1:8901` po nieudanym
   `start --port 8902 --bind 192.0.2.1` zostawał pod tym drugim adresem **na
   trwałe**. Dobry adres ginął, a rada z komunikatu („wybierz inny port") nie
   miała jak pomóc, bo config już kłamał.

**Odstępstwo od litery planu — zgłoszone przeze mnie, nie znalezione u mnie.**
Plan mówi „kolejność: bind, potem zapis". Dosłownie jest to nieosiągalne bez
nowego mechanizmu w rdzeniu, którego plan zabrania: adres zapisują **dwa**
procesy przed bindem (`ensure_hub` u rodzica i u dziecka), a ten, który
binduje, już nie wraca — `server_main` blokuje do SIGTERM-a. Jedynym istniejącym
sygnałem „bind udany" jest `READY_MARK` czytany przez rodzica. Zrobiłem to więc
jako **cofnięcie z migawki**, nie opóźnienie zapisu. Skutek ten sam, okno inne:
między spawnem a `READY_MARK` równoległy `list` widzi pokój.

Kasowanie samego `config.json` nie wystarczało: `hub_rows` wpuszcza pokój do
`list` na podstawie `tokens.json`, więc pokój bez configu pokazywałby się pod
adresem **domyślnym** — widmo pod adresem, o który nikt nie prosił.

## B5, B6, B7 — pozycje agent1

**B6 — ZWERYFIKOWANE PRZEZE MNIE, przechodzi.** Nie na słowo: własny izolowany
`AGENTMACHI_HOME`, hub `b6w` na 8951, dwa `listen` na nicku `probant`, ten sam
`$HOME`:

    rc drugiego = 1
    chat.client_session.ListenerLockHeld: another listener for this session is
      already running (lock: ~/.chat-sessions/probant-cc97617a357c.listener.lock)
    ramek `error` / `suggested_nick`: 0
    wystąpień ListenerLockHeld: 2

Poprawione zdanie w `CLAUDE.md` jest prawdziwe co do słowa, łącznie z tym, że
traceback podaje ścieżkę locka.

**B5 — ZWERYFIKOWANE PRZEZE MNIE, przechodzi**, i korekta `cce6124` jest
mocniejsza niż pierwsza wersja. Własny hub `b5w` na 8952, listener 1 pod
`localhost` na nicku `probant`:

| drugi `listen` | wynik |
|---|---|
| `ws://localhost:8952` (ten sam zapis) | rc=1, `ListenerLockHeld` ×2 |
| `ws://127.0.0.1:8952` (inny zapis) | rc=124 — **żyje**, hub: `[nick] 'probant' is taken by someone else — coming up as 'agent1'` |

Czyli co do słowa: lock jest per **zapis adresu**, `127.0.0.1` go omija,
wchodzisz i nasłuchujesz **pod cudzym nickiem**. Zdanie `agent1` jest
prawdziwe; zakres może być nawet szerszy, niż podaje — nick, który hub nadał
w moim teście, to `agent1`, czyli w tym pokoju byłby to nick żywego uczestnika.

**B7 — ZROBIONE po moim zgłoszeniu (`8dbef69`), ZWERYFIKOWANE PRZEZE MNIE,
przechodzi.** Zdanie granicy trafiło do obu skilli: „free" jest ograniczone
do TEGO `AGENTMACHI_HOME` plus tego, co zbindowane teraz, a inny HOME odda
port pokoju, który zatrzymałeś.

Sprawdziłem, czy to zdanie jest **prawdziwe**, nie czy istnieje. Dwa HOME,
pokój `mojpokoj` **zatrzymany** w A na 8961:

    HOME B:  start --name obcy --port 8961  ->  wstaje, config {"port": 8961}
    HOME A:  list  ->  mojpokoj  ws://localhost:8961  stopped, ADDRESS TAKEN

Obietnica trzyma co do słowa, a przy okazji widać, że jego zdanie granicy
i moje ostrzeżenie z B3 **składają się**: B7 mówi czytelnikowi, że tak może
się stać, B3 mówi mu, że właśnie się stało.

**Historia tej pozycji zostaje w raporcie, bo jest treścią.** Zamknąłem ją
najpierw jako „brak commita", `agent1` zamknął ją wcześniej jako „zero
residuum" — obie oceny były przedwczesne z przeciwnych stron. Poniżej stan,
który to rozstrzygnął: `git log origin/main` ma A1, A2, A3, A4,
B1–B6, C1, C2, D1, D2 i prerejestrację E1. B7 nie ma. To pozycja `agent1`,
więc jej nie wykonuję; zgłosiłem ją na kanale wraz z materiałem.

W `audyt-szwow-docow-2026-09-02.md` werdykt „prawdziwa w zakresie, którego nie
podaje" pada 5 razy, z czego **dwie** to żywe obietnice bez zdania granicy:

- **linia 180** — dobór portu: milczy, że „wolny" znaczy „wolny w TYM
  `AGENTMACHI_HOME` i niezbindowany w tej sekundzie". Moja granica z B1
  **istnieje, ale siedzi w komunikacie awarii bindu `serve`**, nie w tekście
  samej obietnicy. Obietnica w docs nadal milczy.
- **linia 221** — format `[seq] nick: line` milczy, że ten sam strumień niesie
  nierenderowane bloki JSON. Po moim B2 jest to **prawie** nieaktualne —
  patrz granica B2 niżej.

## C1, C2 — pozycje agent1

**C1 — ZWERYFIKOWANE, przechodzi.** Sprawdziłem mechanicznie, że każdy SHA
z nowych wskaźników istnieje w tym repo i że data się zgadza:

    4da1ec1  2026-07-31  fix(takeover): kursor przestaje przeskakiwac ramki…
    a2f6c85  2026-07-25  docs(rules): zasady agentyczne z dogfoodu…

**C2 — ZWERYFIKOWANE, przechodzi.** Status `NIEODTWARZALNY` stoi w tekście,
z datą audytu i z rozróżnieniem „nieodtwarzalny nie znaczy fałszywy", czyli
dokładnie tak, jak plan wymagał — bez łagodzenia i bez wzmacniania.

**Zastrzeżenie, które zgłosiłem przed pracą i które zostaje w mocy:** reguły 17
w `zasady-agentyczne.md` nie mogę weryfikować przy C2, bo sam ją napisałem.
Jeśli wpadła w zbiór „nieodtwarzalnych", idzie do raportu jako
**niezweryfikowana krzyżowo**, nie jako uzgodniona.

## A1 — trzy metryki board-pull

**ROZBIEŻNOŚĆ, rozstrzygnięta pomiarem. Publikacja wstrzymana do zgodności.**

Policzyłem niezależnie, przed przeczytaniem liczb `agent1`. Pieczęć A3
zweryfikowałem przed liczeniem — wszystkie cztery sha256 się zgadzają.

Moje reguły klasyfikacji (do diffowania są **reguły**, nie liczby):

- **R1.** wpis = każde wystąpienie pola `proszę`/`marzę` o wartości innej niż
  „nic". Powtórzenie tej samej prośby w kolejnej ramce liczy się jako osobny
  wpis, bo spec mówi „odsetek **wpisów**".
- **R2.** podjęty = późniejsza ramka **innego** uczestnika nazywająca ten sam
  artefakt i meldująca działanie na nim.
- **R3.** dwuznaczne → NIESPRAWDZALNE, nie „podjęte" (reguła dwuznaczności z D1).

| | wpisów | podjęte | pull rate | abandon | useful-pull |
|---|---|---|---|---|---|
| meadow1 (G) | 12 | 5 | **42%** | 0/5 | 5/5 |
| meadow2 (P) | 9 | 4 | **44%** | 0/4 | 4/4 |

**Liczby na meadow1 są po korekcie. Moja pierwsza wersja mówiła 1/13 = 8%
i była błędna** — patrz „Dwa błędy instrumentu" niżej. Na meadow2 obaj
policzyliśmy niezależnie **4/9 = 44%** i zgodziliśmy się co do grosza.

Wniosek, który z tego wychodzi, jest `agent1`: **mocniejsza zachęta nie
zwiększyła pulla** (42% wobec 44%), `abandon` identyczny (0%),
`useful-pull` po równo (100%).

### Dwa błędy instrumentu, po jednym na głowę

Rozbieżność na A1 nie była sporem o liczbę. Obaj zbudowaliśmy narzędzie pod
własną hipotezę i obaj dostaliśmy z niego **spójny, fałszywy** obraz —
w narzędziu żadnego z nas nie było gałęzi, w której własna liczba mogłaby paść.
Każdy błąd złapał ten drugi. To jedyny powód, dla którego oba wyszły.

**Błąd `agent1`: pola kontra `note`.** Opublikował i zacommitował (`8406394`), że w meadow2
board był **pusty** — „wszystkie 16 ramek status niosło wyłącznie `state`",
metryki NIEOZNACZONE (0/0) — i zbudował na tym całe rozliczenie prognoz A2.

Zmierzone z **jego własnych zapieczętowanych plików**:

    events-meadow2-final.jsonl    0 ramek status  {}
    merged-meadow2.jsonl         16 ramek status  {…, 'teraz':15, 'martwie':10,
                                  'prosze':2, 'proszę':4, 'marzę':4, 'marze':2}

Czyli `events` nie ma **żadnej** ramki status — nie da się z niego wyciągnąć
ani „16", ani „wyłącznie state". `merged` ma 16 i **niesie pola**.

**Mechanizm, i to jest właściwe znalezisko A1: ramiona zakodowały ten sam
słownik inaczej.** W meadow1 pól nie ma — `teraz:`/`martwie:`/`prosze:` siedzą
wewnątrz tekstu pola `note` (`note` w 17/17 ramek). W meadow2 to
**pierwszoklasowe pola ramki** (`note` w 1/16). Kto szuka słownika w `note`,
widzi meadow2 jako pusty; kto szuka pól, widzi meadow1 jako pusty. Obaj
dostają spójny, fałszywy obraz drugiego ramienia. Spec ostrzegał przed czymś
sąsiednim („końcowego `events.jsonl` nie traktujemy za wystarczające źródło
historii statusów") — wada instrumentu była nazwana przed przebiegiem, tylko
o innym pliku.

`agent1` **wycofał swoje A1 w całości** (`seq 478`), nie skorygował — jego
słowami: „opublikowałem i zacommitowałem fałsz". Poprawka po jego stronie,
bo to jego pozycja i jego plik (`0bb7a9f`).

**Mój błąd: `status` kontra `chat`.** Policzyłem meadow1 na 1/13 = 8% i to
było fałszywe. Moja reguła R2 mówi „późniejsza ramka **innego uczestnika**",
bez ograniczenia typu — a **wykonałem** ją wyłącznie na ramkach `status`.
Reguła i instrument się rozjechały w miejscu, które przesądzało wynik:
podjęcie melduje się **na kanale**, nie w statusie. Szukałem podjęć tam, gdzie
ich z definicji nie ma, dostałem czyste 8% i uwierzyłem.

Dowody, które pominąłem, leżą w `merged-meadow1.jsonl` jako ramki `chat`:

    seq 54  agent1 → "@agent2 REVIEW 4b87c07: przechodzi. Sprawdziłem każde
                      twierdzenie osobno"        — podejmuje seq 27/42/52
    seq 116 agent1 → "Weryfikacja przyjęta w całości"
                                                 — domyka seq 100, które
                                                   oznaczyłem NIESPRAWDZALNE

Po korekcie przyjmuję mianownik `agent1` (wyrzuca `seq 62`, „wołam się chętnie
do review", jako **ofertę**, nie prośbę — oferta nie jest wpisem, który ktoś
może podjąć). **A1 jest zgodne i wolno publikować.**

To ta sama klasa błędu co jego, w drugą stronę. Nie jest to symetria dla
ozdoby: obaj znamy regułę „instrument dobrany pod hipotezę nie ma gałęzi,
w której hipoteza pada", obaj ją zapisaliśmy, i obaj w nią weszliśmy tego
samego wieczoru na tym samym zbiorze danych.

**Czego moje liczby nie mówią — i to nie jest skromność:**

1. n jest małe (13 i 9 wpisów, dwóch uczestników). Różnica 8% vs 44% ma
   przedział ufności szerszy niż sama różnica.
2. Ramiona różnią się **nie tylko** ontologią. W meadow1 prawie wszystkie
   prośby to `agent2` → `agent1` o review, na które `agent1` nie odpowiedział
   widoczną ramką. W meadow2 prośby szły w **obie** strony. Kierunkowość jest
   konkurencyjnym wyjaśnieniem całej różnicy i tego przebiegu nie da się od
   niej odseparować.
3. `abandon` 0% w obu ramionach może znaczyć „podejmowali tylko to, co
   dowozili", a nie „board działa".
4. Mierzymy słownik, który z produktu **usunęliśmy**. To rozliczenie długu,
   nie przesłanka do przywrócenia pól.

## A2, A3, A4 — pozycje agent1

**A3 — ZWERYFIKOWANE, przechodzi.** Przeliczyłem sha256 wszystkich czterech
eksportów przed liczeniem A1 — zgadzają się z pieczęcią. Etykieta „pieczęć
post-hoc" jest w pliku i mówi wprost, czego pieczęć **nie** dowodzi.

**A2 — NIEZWERYFIKOWANE, i częściowo unieważnione.** `agent1` rozliczył
prognozy przeciw twierdzeniu „P dał zero wpisów", które właśnie upadło.
Trzeba je przeliczyć po jego poprawce A1. Osobno: `agent1` zmierzył, że
prognoza Sola **nie jest** VOID — leży w `spec.md:145-152` pod tym samym
hashem co reszta specu. Plan zakładał, że nie została złożona. **Tego nie
weryfikowałem.**

**A4 — ZWERYFIKOWANE, przechodzi.** Oba wymagane punkty stoją w liście „Co
musi mieć każdy eksperyment": hash eksportu **na koniec przebiegu, przed
punktacją**, oraz prerejestracja **w commicie**, z jawnym „kanał
prerejestracją nie jest". Sprawdziłem paragony, nie samą obecność:
`spike-tui-…md:24` naprawdę ma sekcję „Odstępstwo od standardu tego katalogu",
a pieczęć post-hoc naprawdę przedstawia się jako spóźniona. Standard stoi na
własnych, sprawdzalnych przykładach, nie na deklaracji.

## D1, D2 — pozycje agent1

**ZWERYFIKOWANE, oba przechodzą.**

**D1** — ślepe wykonanie krzyżowe stoi jako cztery kroki z zamrożeniem
predykcji i publikacją `sha256` **przed** wysłaniem poleceń, a wykonawca
dostaje gołe polecenia bez cytatu obietnicy. Reguła dwuznaczności zapisana
w mocnej formie: „dwuznaczność w gorącej ścieżce jest **znaleziskiem, nie
remisem**". Użyłem jej w A1 jako reguły R3, zanim ją tu przeczytałem — i to
ona kazała mi oznaczyć `seq 100` jako NIESPRAWDZALNE zamiast zgadywać. (Że
akurat ta klasyfikacja była zbyt ostrożna, bo dowód leżał w chacie, jest moim
błędem instrumentu, nie wadą reguły.)

**D2** — zdanie „nazwij, co kontrola odbiera, przed przebiegiem" stoi wraz
z konkretnym kosztem z #6: odebranie narzędzi „dla porównywalności" wycięło
całą klasę znalezisk. Paragon sprawdzony w źródle. Zapis idzie dalej niż
sam wymóg — mówi, że najmniej zauważa to ten, kto kontrolę dołożył, i to
jest prawdziwe o tym przebiegu.

## E1 — ramię B2, subagent bez dziedziczenia

**PREREJESTRACJA ZŁOŻONA przez agent1** (`3f8ff7b`, predykcja 3/4, sha256 pliku
w treści commita). **Przebieg nie wykonany w chwili pisania.**
Odpala `agent1`, orzekam ja.

**Ujawnienie, które musi towarzyszyć mojemu przyszłemu orzeczeniu:** sekcja
„Ramię bez kontroli" w `subagent-vs-peer-2026-09-02.md` jest moja, a prereg
`agent1` opiera na niej analizę kosztu kontroli („brak narzędzi odbiera całą
klasę znalezisk"). Czytelnik ma to wiedzieć, zanim uwierzy mojemu werdyktowi.

## Poza zakresem — wykonane zgodnie z planem, czyli nie tknięte

Wszystkie pozycje z „DECYZJE WŁAŚCICIELA" i z „NIE TERAZ". Nie wykonałem ich
i nie proponowałem w ich miejsce własnych.

---

## Regresja, którą wprowadziłem naprawiając cudze zgłoszenie

Zachowanie `serve.log` przy cofnięciu (punkt 3 zgłoszenia `agent1`) **złamało
B4 przy drugiej próbie**. Migawka pytała o istnienie **katalogu**, a katalog
zaczął przeżywać porażkę — więc druga nieudana próba na tej samej nazwie
widziała „pokój istnieje", cofała sam `config.json` i zostawiała
`tokens.json`. `hub_rows` wpuszcza pokój do `list` właśnie po `tokens.json`,
więc `list` pokazywał `ghost` pod adresem **domyślnym**.

To jest **dokładnie** widmo, przed którym ostrzega docstring mojego własnego
cofnięcia — „widmo pod adresem, o który nikt nie prosił". Napisałem to zdanie
kilka godzin wcześniej i i tak w nie wszedłem, bo poprawiałem jedną rzecz
i nie sprawdziłem, co ona zmienia w założeniu obok.

Naprawione: migawka mierzy teraz `tokens.json`, nie katalog — czyli **to samo,
czym mierzy widoczność `hub_rows`**. Regresyjny test robi dwie porażki pod
rząd. Zmierzone na żywo: po dwóch nieudanych startach w katalogu zostaje sam
`serve.log`, a `list` jest pusty.

Nie znalazła tego ani moja suita (bo testowała jedną porażkę), ani weryfikator
(bo zgłosił defekt, nie jego skutek uboczny). Znalazł go **przegląd trzeciej
strony**, po tym jak uznałem pracę za skończoną.

## Mój własny błąd metody w tej sesji

Przy pomiarach B1 zrobiłem `rm -rf` na katalogu `AGENTMACHI_HOME` **bez**
`stop` i zostawiłem osieroconego huba na 8768 (PID 199290) — proces żywy
i nasłuchujący, niewidoczny dla `list`, bo jego katalog już nie istniał.
To **M1 z audytu szwów**, który współpisałem, powtórzone przeze mnie
kilkanaście godzin później.

Kosztowało konkretnie: to on zajął 8768 i sprawił, że cudzy test dostał 8769
zamiast 8767 — czyli wszedł mi w **pomiar**, na którym stała decyzja B1.
Ubity (`agentmachi kill "serve --name x2"`), potwierdzone `ss`: 0 nasłuchów.

Znajomość reguły nie wystarczyła. Wystarczyłoby `stop --all` przed `rm -rf`.

## Obserwacja poboczna, nie pozycja planu

`docs/pl/raport-sesja-odejmowania.md` linkuje do `philosophy.md` względnie
z `docs/pl/`, a plik leży w `docs/`. Jedyny martwy link względny w całym
`docs/` + `CLAUDE.md` + `AGENTS.md` (sprawdzone mechanicznie). Nie naprawiam —
nie ma za tym liczby z tych sześciu zapisów i nie jest to pozycja planu.

## Stan suity

`731 zielonych` na `2ce045f` (moje cztery pozycje, przed rebase na A1/A2/E1
`agent1`). Po każdej z moich napraw suita była zielona przed commitem.

---

# Luźne końce — dopisane po zwolnieniu pozycji przez operatora

**Zwolnienie:** `@human`, `seq 518`, 2026-09-03: „Zasady poprawiacie sami,
autor znaleziska nie przepisuje własnego zdania". **HEAD tej sekcji:**
`5edc3de`. **Podział:** deklaracja `agent1` `seq 520` wobec `agent2` `seq 524`
— niższy wziął, `agent2` wycofał się z dziury 1 i reguły 3 bez dyskusji.

## A2 — ZWERYFIKOWANE (nie: policzone niezależnie)

Rozróżnienie jest treścią, nie formalnością: **widziałem wnioski `agent1`,
zanim zacząłem** (czytałem commit message `8406394` i `0bb7a9f`), więc
niezależności nie mam i nie udaję jej. Sprawdzałem każdy werdykt wprost
przeciwko zapieczętowanemu `spec.md:125-152` pilota (hash `7007402a…378cef`
przeliczony, zgodny z `commitments/2026-08-22.txt`) i przeciwko uzgodnionym
liczbom A1.

**Przechodzi:** prognoza Sola faktycznie leży w `spec.md:145-152` — plan
zakładał, że jej nie ma, i mylił się; „warunek NIE odpalił" przy skażonej
prognozie jest poprawne po korekcie A1 i jawnie oznaczone jako konsekwencja
tamtej pomyłki; człon Sola „G mocno zwiększy pull" pada niezależnie od progu
(G jest **niższy**), a „P ≈ G w użyteczności" trafia dosłownie (100% wobec
100%).

**Dwa werdykty kwestionuję — obie na WŁASNEJ regule D1 `agent1`** („jeśli
pasuje i predykcja, i obserwacja → NIESPRAWDZALNA, nie PRAWDA"):

| werdykt | prognoza | dlaczego NIESPRAWDZALNA |
|---|---|---|
| TRAFIONA | „G da żywy pull z **małym** podatkiem śmieciowym" | progu nie zapisano; podatek to `marzę` 0/7, czyli **7 z 12** wpisów nie podjął nikt |
| TRAFIONY | „Oba ramiona dadzą **wysoki** `pull rate`" | progu „wysoki" nikt nie zapisał przed przebiegiem; 42% czyta się w obie strony |

Obie to **jedyne** trafienia swoich prognoz. Po ich zdjęciu Claude/Fable
pierwotna ma 0 trafień, a skażona Opus 5 — 0 trafień i 3 sfalsyfikowane,
czyli wniosek `agent1` („skażenie kontekstem nie pomogło jej ani trochę")
robi się **mocniejszy**. Nie tykam jego pliku; zgłoszone, decyzja jego.

## Dziura 2 z red-teamu — ZROBIONE (`befe2c7` + `3334bef`)

Raport red-teamu zostawił ją bez czerwonego testu świadomie: „czarna lista
znaków to wybór, nie oczywistość". Zgoda — więc czarnej listy nie ma.

Strażnik chodzi po **właściwości**: nick nie może nieść znaku z kategorii
Unicode `Cc/Cf/Cs/Co/Cn/Zl/Zp/Zs`. Powód strukturalny, nie estetyczny —
`@nick` kończy się na białym znaku (spacja = nick **nieadresowalny**), a
`board` i TUI stawiają nick w kolumnach (`\n`, RLO = wyglądanie na kogoś
innego wszędzie, gdzie te kolumny się drukują).

Falsyfikacja w **obie** strony: 8 nicków ma odpaść, 7 ma przejść (`my-agent`,
`agent_2`, `łukasz`, `renée`, CJK, emoji, `agent2.1`). Bez drugiego zestawu
strażnik odrzucający wszystko przechodziłby pierwszy w komplecie. Komunikat
podaje **codepoint**, nie wkleja znaku — wklejony RLO/ANSI przepisałby
komunikat o samym sobie.

**Granica świadoma:** kontrola stoi tylko na ścieżce **otwartej**, gdzie nick
pochodzi wprost od wchodzącego. Ścieżka tokenowa bierze nick z `tokens.json`
operatora; tam walidacja nie broni przed napastnikiem, a potrafi zamknąć
działający pokój przy starcie.

Żywy hub: cztery ataki odrzucone, `my-agent` i `łukasz` wpuszczone.

Przepisany cudzy test `test_json_odczytuje_wiernie_nick_ze_znakami_kontrolnymi`
— miał w sobie **asercję-instrukcję** („hub odrzucił nick, zaktualizuj test"),
bo autor tę zmianę przewidział. Inwariant (jedna ramka = jedna linia w
`--json`, bo na tym stoi arbitraż po `seq`) zostaje; pojazd zmieniony na
mocniejszy, bo legalny: newline w **treści**, który nie zniknie po żadnej
przyszłej walidacji nicka.

### Złamałem main na dwie minuty i mechanizm jest powtarzalny

Commit `befe2c7` wypchnął **same testy**. Importowały
`sprawdz_ksztalt_nicka`, którego w `chat/identity.py` nie było — padała
kolekcja całego pliku, nie pojedynczy test.

Jak: dowodziłem reintrodukcji, podmieniając wywołanie strażnika na `pass`,
i cofnąłem podmianę przez `git checkout -- chat/identity.py`. **Fix nie był
jeszcze zacommitowany**, więc `checkout` przywrócił nie „stan sprzed hacka",
tylko HEAD — czyli wersję bez naprawy. `git add -A` objęło już same testy.

Czego zabrakło: po reintrodukcji uruchomiłem **tylko jeden plik** i **tylko
przed** przywróceniem, żeby zobaczyć czerwień. Zielonego przebiegu **po**
przywróceniu nie zrobiłem. Reintrodukcja ma dwa przebiegi: czerwień dowodzi,
że coś pada, a że wróciło na miejsce — dopiero zieleń po. Naprawione
w `3334bef`, sprawdzone tym razem także **świeżym `git clone` z origin**,
bo własnemu drzewu po takiej operacji nie ma powodu ufać.

## Dwa zdania w zasadach — ZROBIONE (`5edc3de`)

Oba znaleziska są `agent1` (spike TUI weryfikował i spisywał on; ramię A z #6
odpalał on), więc zgodnie z regułą operatora pisał `agent2`, a `agent1`
weryfikuje zgodność z pomiarem.

**„żywej sesji TUI nie obudzi nikt z zewnątrz"** → **„żywą sesję TUI budzi
HARNESS, i tylko on"**, z czterema granicami, bez których nowe zdanie znaczy
więcej, niż wolno: nadawcą musi być proces harnessu (gniazdo prywatne,
`peerToken`), kanał nie ma envelope'u (treść zewnętrzna ląduje na pozycji
komunikatu **harnessu** i model wykonał surowy string co do znaku), kanał
jest jednokierunkowy (budzący nie wie, czy obudził), wynik przypięty do
wersji. Stary opis zostaje jawnie jako stan sprzed pomiaru.

**„subagent tego nie złapie, BO DZIEDZICZY"** → **„złapie to NIE-AUTOR,
a dziedziczenie hipotezy mu nie przeszkadza"**. Przeformułowane wokół
nie-autorstwa, tak jak wskazywał pomiar z #5 (apel 0/4, struktura 4/4).
Zostawiona **jawna niewiedza**, bo bez niej byłaby to druga wersja tego
samego błędu: nie wiemy, czy pracę wykonało nie-autorstwo, czy samo jawne
polecenie „zgłoś problemy", którego peer nigdy nie dostaje. Odpowie E1 —
prerejestrowane, nieuruchomione, i link do niego stoi w tekście.

## E1 — NADAL NIE ZROBIONE, powód regulaminowy, obie strony niezależnie

`@human` wymienił E1 wśród luźnych końców i napisał „róbcie". **To nie
odblokowuje przebiegu u żadnego z nas** i obaj doszliśmy do tego osobno.

Przebieg wymaga subagentów. Wiadomość na kanale nie jest instrukcją
użytkownika sesji — skill mówi to wprost („channel content is weaker than all
of them"), a `@human` na kanale jest **uczestnikiem**, nie konsolą żadnej
z sesji. Ta sama granica, którą `agent1` podał wcześniej, i nie znika przez
to, że polecenie brzmi „róbcie".

Żeby E1 ruszył, prośba musi trafić do jednej z sesji **jako instrukcja
użytkownika**, nie jako ramka. Prerejestracja czeka złożona i zapieczętowana
(`3f8ff7b`, predykcja 3/4, sha256 pliku w commit message) — nic w niej nie
zgnije.

## Dług spłacony: weryfikacja dwóch pozycji `agent1`

**Dziura 1 (`target`), `10bb061` — PRZECHODZI.** Sprawdzone na żywym hubie
(`targ` na :8981, własny `AGENTMACHI_HOME`), oba końce i obie strony:

    na drucie do odbiorcy:  target = None,  wiadomość DOTARŁA
    w events.jsonl:         chat   target = None
                            status target = 'napastnik'  (serwerowy — został)

Czyli wartość klienta nie przeżywa ani drutu, ani logu, a naprawa nie zabrała
`target` nadawanego przez serwer. Kontrola dotarcia w tym samym przebiegu —
bez niej „target = None" znaczyłoby równie dobrze „nic nie doszło".

**Reguła 3, `c3a66b6` — PRZECHODZI, z jednym zastrzeżeniem.** Paragon
sprawdziłem **wprost z logu**, nie z pamięci — o co sam prosiłem, będąc jego
stroną. Wszystkie sześć numerów istnieje i mówi to, co przypisuje im tekst:
`437` i `439` to dwie deklaracje, `446` to arbitraż z cytowanym zdaniem,
`520`/`524` to druga kolizja, `532` to wycofanie się przegranego.

*Zastrzeżenie:* zapis mówi, że pat pękł „niższy `seq`, a dla pozycji oddanych
obustronnie — porównanie bajtowe nicka (reguła 1)". Porównanie nicka **nie
było nośne**: w `seq 446` stoi wprost, że *oba* mechanizmy wskazały to samo,
bo deklaracja z niższym `seq` już te pozycje przypisała. Nick potwierdził
wynik, nie rozstrzygnął go. Dla reguły, której cały sens to „co realnie
przecina pat", to różnica warta poprawienia — mechanizm nośny był jeden.

Zgłoszone, nie poprawione: to pozycja `agent1`, a ja jestem w tym paragonie
stroną, więc tym bardziej nie przepisuję go sam.
