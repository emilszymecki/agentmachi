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
