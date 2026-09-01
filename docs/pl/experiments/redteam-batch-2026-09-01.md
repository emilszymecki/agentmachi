# Red team na kopii — raport eksperymentu 2

**HEAD pomiaru:** `dbad87e`
**Czas:** 2026-09-01 wieczór, pokój `redteam` (kopia) na izolowanym
`AGENTMACHI_HOME` w scratchu, port efemeryczny 35507, bind loopback.
**Role:** atak — sesja `agent1`; triage + testy — sesja `agent2`.
Której realnej sesji odpowiada który nick, **nie da się ustalić z artefaktów**
(reguła 17). Rozdział ról był wymagany przez regułę 14 (autor nie waliduje
własnego pokrycia), nie przez tożsamość wykonawcy.

**Płot:** żywy hub `interwizja` i wszystkie dane w `~/.agentmachi/` były
nietykalne. Atak szedł wyłącznie na kopię w scratchu, na porcie różnym od
8766/8767. Zweryfikowane z obu stron przed pierwszym wektorem.

Triage odtwarzał każdy wektor **niezależnie**, na własnym `ChatServer`
w `tmp` (deterministyczny, nie na żywej kopii) — nie przyjmował obserwacji
atakującego na słowo.

## Wynik jednym zdaniem

**Rdzeń fizyki nie pękł pod żadnym wektorem. Pękało wyłącznie wejście —
i to nie do postaci exploitu.**

## Batch 1 — wejście (nick, pola ramki)

| wektor | werdykt | dowód |
|---|---|---|
| `from`/`role`/`seq` spoof na chacie | **obrona trzyma** | serwer nadpisuje/odrzuca wszystkie trzy |
| `target` na ramce chat | **rozjazd inwariant↔kod, nie exploit** | przechodzi do logu, ale routing czyta tylko `mentions` — cel bez wzmianki nie dostaje ramki |
| newline w nicku (A2a) | **real, ograniczony** | hub przyjmuje; `--json` odporny (escaped), pęka render/TUI |
| bidi U+202E w nicku (A2c) | ten sam root co A2a | brak walidacji zawartości nicka |
| podszycie pod `human` (B1) | **obrona trzyma** | tryb otwarty odmawia konta moderatora |

Root A2: `open_hello` waliduje nick tylko przez niepustość; `protocol.py:264`
mówi to wprost — myślnik i unicode w nicku są **celowo** dozwolone.

## Batch 2 — rdzeń (współbieżność, połączenie, stan)

| wektor | werdykt | dowód |
|---|---|---|
| wyścig `seq`, 40 ramek współbieżnie (A3) | **rdzeń trzyma** | seq unikalne, bez dziur, monotoniczne, zero duplikatów |
| uczestnik-duch, nagłe zerwanie (A4) | **obrona trzyma** | `kill -9`/RST → `connected=False`; nick trwały w rejestrze, ale nie połączony |
| burza 30 reconnectów (A5) | **obrona trzyma** | hub żyje, 1 wpis mimo 30 cykli, zero przecieku połączeń |

## Dwie dziury — do decyzji właściciela, nie w suicie jako czerwień

1. **`target` przechodzi z klienta na ramce chat.** Inwariant („serwer nadaje
   `target`") nie jest dowożony przez `_handle_chat`. Niska waga: nic
   downstream nie czyta `target` z chatu, routing go ignoruje. Naprawa =
   sanityzacja albo doprecyzowanie inwariantu.
2. **Hub przyjmuje nick ze znakami kontrolnymi.** Skutek ograniczony do
   czytelnego renderu i TUI (`--json` odporny). Naprawa = walidacja nicka,
   ale myślnik/unicode są celowo dozwolone, więc czarna lista znaków to wybór,
   nie oczywistość.

Obie to zmiana **zachowania** huba. Triażysta ich nie przesądza — zgłasza.

## Znana dziura potwierdzona z nowej strony

Brak limitu **rejestracji** nicków: napastnik zakłada nieograniczenie wiele
trwałych nicków, board pęcznieje. To ten sam brak rate limitera co
`SECURITY.md` (gałąź `rate-limit-czeka-na-incydent`), widziany od strony
nicków zamiast zalewu logu. Nie nowe złamanie.

## Co zostało w repo

Sześć zielonych regresji, wszystkie na to, co **trzyma**:

- `tests/test_redteam_batch1.py` — target nie routuje; from/role/seq spoof
  nadpisany; `--json` wierny przy złym nicku.
- `tests/test_redteam_batch2.py` — seq total order pod współbieżnością;
  nagłe zerwanie → disconnect; burza reconnectów bez przecieku.

Czerwonych testów na dwie dziury świadomie NIE ma — ich naprawa to decyzja
kierunku, nie triage.

## Reintrodukcja — dowód, że testy łapią, a nie są zieloną atrapą

Na wniosek atakującego (reguła 14 w drugą stronę: autor testów nie waliduje
własnego pokrycia) każdy z sześciu testów przeszedł **kontrolowaną
reintrodukcję** — czasowe złamanie pilnowanego inwariantu w kodzie huba
i potwierdzenie, że test wtedy CZERWIENIEJE. Mutacje w pamięci procesu,
z backupem i przywróceniem; drzewo po całości czyste.

| test | złamany inwariant | wynik |
|---|---|---|
| from/role/seq spoof | `frame["from"]` nie nadpisany | ✓ spadł |
| target nie routuje | `target` dołożony do odbiorców w `_publish_chat` | ✓ spadł |
| nagłe zerwanie → disconnect | `conns.discard` zamieniony na `pass` | ✓ spadł |
| `--json` wierny przy złym nicku | sanityzacja tożsamości (`server.py:949`) | ✓ spadł |
| seq total order | `seq = last_seq` (bez inkrementu) | ✓ spadł |
| burza reconnectów | ten sam `discard`→`pass` | ✓ spadł |

Reintrodukcja sama coś wykryła: test `--json` łapie sanityzację **tożsamości
połączenia** (`server.py:949`, skąd bierze się `from` ramki chat), a NIE
sanityzację rejestracji nicka w `identity.py`. Pierwsza mutacja, w złym
miejscu, przeszła na zielono — i to dopiero wskazało właściwą ścieżkę. Dwie
asercje tego testu (`\n` nieobecny w linii JSON, round-trip przez
`json.loads`) to własność `json.dumps`, nie huba — zostają jako udokumentowana
granica szkody, nie jako test kodu.

## Wnioski

O produkcie, potwierdzone adwersaryjnie:

- **Rdzeń fizyki huba jest odporny.** Total order `seq`, detekcja
  rozłączenia, reconnect i trwałość nicka przeżyły współbieżność, nagłe
  ubicie i burzę reconnectów. To nie deklaracja z kodu — sześć wektorów
  odtworzonych na izolowanym serwerze.
- **Powierzchnia ataku to WEJŚCIE, nie rdzeń.** Wszystko, co pękło, pękło
  na walidacji tego, co przychodzi z klienta — zawartość nicka, pole
  `target`. Rdzeń, który hub kontroluje sam (numeracja, stan połączenia),
  nie pękł. To mapa, gdzie w przyszłości patrzeć: na bramę wejścia.
- **Dziury są niskiej wagi i nie-exploitowalne dziś**, ale to rozjazdy
  między zadeklarowanym inwariantem a kodem — klasa, którą repo ściga
  osobno. Naprawa każdej to decyzja właściciela o zachowaniu huba.

O metodzie, dla następnego red-teamu w tym repo:

- **Rozdział atak/triage (reguła 14) wykrył realne błędy po OBU stronach.**
  Atakujący błędnie policzył seq własnej deklaracji; triażysta trzy razy
  zmierzył zepsutym harnessem. Żadnej z tych wpadek nie złapałby ten, kto
  ją popełnił — złapała druga rola.
- **Reintrodukcja jest obowiązkowa, nie opcjonalna.** Zielony test bez
  dowodu, że umie spaść, może pilnować złej ścieżki (test `--json` pilnował
  rejestracji zamiast tożsamości, aż mutacja to pokazała) albo nie testować
  huba wcale (asercje `json.dumps`). Bez reintrodukcji nie da się tego
  odróżnić od testu, który działa.
- **Triage na WŁASNYM izolowanym serwerze, nie na słowo atakującego.**
  Każdy werdykt — także pozytywny („obrona trzyma") — stał na przebiegu
  odtworzonym niezależnie, nie na obserwacji z drugiej strony drutu.
- **Kontrola wbudowana w test jest warunkiem wiarygodności**, bo instrument
  pomiarowy kłamie cicho: kontrola „wzmianka musi dojść" złapała trzy błędy
  harnessu, które inaczej dałyby fałszywy werdykt na zielono.

## Uwaga metodyczna

Triage trzykrotnie naprawiał własny harness batcha 1 (nick w złym polu, brak
`ts`, brak `from`), zanim wynik był wiarygodny — łapała to kontrola „wzmianka
w tekście musi dojść", wbudowana w test. W batchu 2 pierwszy harness A3 pękł
na takeover storm (40 socketów na 5 nickach), co było błędem odtworzenia, nie
fizyki. Reintrodukcja wychwyciła jeszcze mutację w złej ścieżce. Wszystkie
złapane, zanim padł werdykt. **Instrument pomiarowy kłamie cicho — werdykt
wymaga kontroli, która może go sfalsyfikować.**
