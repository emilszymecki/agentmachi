# Wsad projektowy: resumowalny klient B1/B2 (precondition-cutover)

Status: BLOCKER-CUTOVER (nie luźne TODO). Zebrane PRZED implementacją, żeby
nie powtarzać 7 rund serwera. Autor wsadu: codex (na kanale, 2026-07-22).
To wsad do briefu — nie plan implementacji. Sekwencja: najpierw domknięcie
B1 (serwer, finalny whole-branch review), potem to.

## Cel

`send.py` (i listener) muszą utrwalać kursor i wznawiać bez utraty ani
duplikacji — dziś hello zawsze `last_seq=0`, brak kursora, brak reconnectu.
Runbook migracji (`docs/runbook-migracja-kanalu.md`, gate "BLOCKED-B2")
zależy od tego.

## Kontrakt (codex, do review po dispatchu)

1. **Plik sesji per hub+nick**, nie jeden globalny JSON. Namespace: hub URI
   + nick (env `CHAT_SESSION_DIR`). Pola: `instance_id`, `last_applied_seq`.
   Zapis: atomic replace, 0600, z lockiem — listener i `send_once` tego
   samego nicka działają RÓWNOLEGLE.
2. **Tylko listener aktualizuje kursor.** `send_once` używa TEGO SAMEGO
   `instance_id` (żeby nie takeover'ować listenera), ale NIE przesuwa
   kursora (inaczej zjadłby listenerowi backlog).
3. **Po hello**: przetwarzaj backlog po `seq`, zapisuj kursor PO każdej
   zastosowanej ramce. Resync: zastosuj `state`, potem zapisz
   `snapshot_seq`. NIE ustawiaj ślepo `reply.last_seq` jako kursora —
   przy takeover między policzeniem backlogu a reply mogą wejść
   współbieżne eventy, których klient nie zastosował.
4. **Live**: `seq <= cursor` → skip (duplikat); ramka bez `seq` → wypisz,
   ale NIE przesuwaj kursora.
5. **Reconnect loop** z ograniczonym backoffem. Uszkodzony plik sesji →
   fail-closed z JAWNĄ instrukcją naprawy w komunikacie (np. "skasuj plik
   X = świadomy pełny resync"), nie samo "odmawiam startu". NIGDY cichy
   reset do 0.
6. **Pojedynczy aktywny listener per hub+nick** przez lock.

## Granica gwarancji (ważne — nie obiecywać za dużo)

`cursor-after-apply` daje **at-least-once**. „Dokładnie raz" dla
arbitralnego side-effectu jest NIEMOŻLIWE bez transakcyjnego sinka.
`activation_id` musi być TRWAŁYM kluczem idempotencji adaptera
(stan claimed→done), nie samą listą w pamięci.

## Znalezisko architektoniczne (beta): listener = wspólny adapter harnessów

`Monitor(ws)` (obecny nasłuch Claude) NIE UMIE wysłać hello — tylko
otwiera socket i streamuje ramki. Na `chat/server.py` (wymaga hello jako
pierwszej ramki) dostanie `"pierwsza ramka musi być hello"` + close.
**Wniosek: nasłuch Claude na hubie B1 przez `Monitor(ws)` NIE ZADZIAŁA.**

Rozwiązanie bez nowego kodu: Claude przechodzi z `Monitor(ws)` na
`Monitor(command: CHAT_PORT=… CHAT_NICK=… CHAT_TOKEN=… python3 send.py --listen)`.
Każda linia stdout listenera to event budzący sesję; hello + cursor +
reconnect + lock załatwia TEN SAM kod co dla Codexa.

**Konsekwencja projektowa: listener `send.py --listen` z tego zadania jest
WSPÓLNYM ADAPTEREM WSZYSTKICH harnessów** (Claude przez Monitor(command),
Codex przez /goal polling, inne przez `chat wait`) — jeden kod, trzej
konsumenci. To wchodzi do runbooka (sekcja "nasłuch per harness") i do
CLAUDE.md/AGENTS.md przy migracji docsów (po T4).

## Smoke gate (z runbooka + codex)

- listener → msg1 → kill → msg2 (offline) → restart → msg2 zastosowane
  DOKŁADNIE raz, kursor monotoniczny.
- osobno: duplikat tego samego `seq`/`activation_id` → suppress.

## Delta z review klienta send.py (beta, f7ffb91)

- **D2**: `do_hello` bez timeoutu na recv — zamrożony hub wiesza klienta
  na zawsze (tryb awarii z incydentu 5f6fed9, wciąż otwarty). Fix:
  `asyncio.wait_for` + czytelny błąd.
- **D3**: `listen()` hardcoduje `role="human"`, `send_once` — `"agent"`;
  ten sam nick przedstawia się różnie zależnie od trybu. Klient bierze
  `CHAT_ROLE` (serwer i tak autorytatywnie nadaje z configu).
- **D4 (motywacja-repro kontraktu sesji)**: wspólny `instance_id` dla
  RÓŻNYCH nicków z jednego klona repo — to było dokładnie źródło
  "tajemniczych hello" (wszystkie trzy miały ten sam instance_id).
  Namespace sesji per hub+nick zamyka tę klasę.
- **D5 (decyzja)**: po R7 każdy `send_once` appenduje trwały hello-event —
  1 wiadomość = 2 eventy w logu. Hello-lite dla znanych (nick, instance)
  albo świadoma akceptacja kosztu pod kompakcję.
- **D6**: `CHAT_TOKEN` default `""` — czytelny lokalny błąd "brak
  CHAT_TOKEN" przed połączeniem zamiast wysyłania pustego tokenu.
- (D1 — listener ginie na malformed frame — wszedł do fix-packa B1.)

## Delta z whole-branch review Opusa (do zrobienia W TYM zadaniu)

- **ROZJAZD FORMATU `activation_id`**: `protocol.make_envelope` generuje
  `nick:from-to` (nieużywane przez serwer), a `server._offer_event`
  generuje `nick:seq` — DWA formaty. Ujednolicić na `nick:seq` (format
  serwera, kotwiczony w trwałym evencie) ZANIM adapter podepnie envelope;
  `make_envelope` przepisać albo usunąć.
- **Dead code do sprzątnięcia przy okazji**: `identity.is_current` (:89)
  i `protocol.make_envelope` — nieużywane; usunąć albo podpiąć świadomie.
