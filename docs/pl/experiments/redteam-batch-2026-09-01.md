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

## Uwaga metodyczna

Triage trzykrotnie naprawiał własny harness batcha 1 (nick w złym polu, brak
`ts`, brak `from`), zanim wynik był wiarygodny — łapała to kontrola „wzmianka
w tekście musi dojść", wbudowana w test. W batchu 2 pierwszy harness A3 pękł
na takeover storm (40 socketów na 5 nickach), co było błędem odtworzenia, nie
fizyki. Oba złapane, zanim padł werdykt. **Instrument pomiarowy kłamie cicho —
werdykt wymaga kontroli, która może go sfalsyfikować.**
