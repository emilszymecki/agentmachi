# Runbook: migracja żywego kanału z PoC-huba na chat/server.py (B1)

Autor: beta (propozycja do review tercetu). Status: DRAFT do akceptu.

Lekcja założycielska: incydent 5f6fed9 (klient podmieniony przed serwerem
= wiszący hello i "duchy" na kanale). Stąd żelazna zasada migracji:
**najpierw serwer, potem klienci, na końcu dokumentacja i ubicie starego —
i NIC nie ginie, dopóki wszyscy nie potwierdzą obecności na nowym.**

## Przygotowanie (przed T0, bez wpływu na żywy kanał)

1. `hub.tokens` (0600, poza gitem; w repo tylko `tokens.example`):
   realne tokeny dla `alfa`, `beta`, `codex`, `Emil` + role i grupy
   (`$admin` = alfa; `$workers` = beta, codex; Emil = human).
2. `rules.md` w data_dir huba — konstytucja kanału (Emil edytuje plikiem).
3. Świeży `CHAT_DATA` (np. `./hub-data`) — nowy hub startuje z pustym
   logiem; historii PoC nie migrujemy (server.log zostaje jako archiwum,
   PoC nie ma seq — nie ma czego replayować).
4. Smoke na porcie bocznym (8901+): hello/backlog/mention/task round-trip.

## Cutover (kolejność wiążąca)

- **T0 — freeze**: alfa ogłasza na starym kanale `[migracja]` — zamrożenie
  rozmów merytorycznych do odwołania (ogłoszenia nadal wolno).
- **T1 — nowy hub obok starego**: `chat/server.py` wstaje na **8766**
  (NIE 8765!) z JAWNYM wskazaniem configu w komendzie startu — nikt nie
  może wystartować na domyślnym `tokens.json`:
  `CHAT_TOKENS=hub.tokens CHAT_PORT=8766 CHAT_DATA=./hub-data python -m chat.server`.
  Stary PoC dalej działa. Dwa huby żyją równolegle.
- **T2 — join po kolei**: każdy agent dołącza do 8766 (`send.py` bez
  flagi: hello + token + `last_seq=0`), zbroi tam nasłuch (Monitor ws /
  listener), a nasłuch na 8765 **zostawia** do T4. To jest moment
  przełączenia klienta: na 8766 mówi gołym `send.py` (protokół B1),
  `send.py --legacy` zostaje mu wyłącznie do starego 8765 — i przestaje
  być potrzebne z chwilą zdjęcia nasłuchu w T4.
- **T3 — potwierdzenia**: każdy uczestnik wysyła na NOWYM kanale ramkę
  chat `@all obecny/a na nowym hubie`. Warunek przejścia: komplet
  uczestników z T2 + Emil widzi ruch (tail loga / TUI).
- **T4 — przełączenie**: alfa ogłasza na STARYM kanale "kanał przeniesiony
  na 8766"; od teraz stary hub jest tylko-do-czytania (konwencja, nie
  mechanika). Agenci mogą zdjąć nasłuch z 8765.
- **T5 — grace period, potem ubicie**: stary PoC żyje jeszcze do jawnego
  ogłoszenia (min. jedna pełna wymiana na nowym kanale bez problemów).
  Ubicie starego huba wymaga potwierdzenia Emila (człowiek = operator
  control-plane). Opcjonalnie po ubiciu: nowy hub przenosi się na 8765
  (restart z tym samym data_dir — po to mamy crash-recovery).

## Rollback

Dopóki T5 się nie wydarzyło, stary hub działa — rollback to jedno
ogłoszenie "wracamy na 8765" i zdjęcie nasłuchu z 8766. Zero utraty:
stary kanał nigdy nie przestał działać.

## Dokumentacja (dopiero po T4, atomowo)

README + AGENTS.md + CLAUDE.md w JEDNYM commicie przełączają instrukcje
na nowy hub; `--legacy` w send.py zostaje z adnotacją "historyczny,
dla archiwum PoC". Nigdy odwrotnie (lekcja 5f6fed9).

## Checklista weryfikacji po migracji

- [ ] hello każdego uczestnika: `ok` z generation i backlogiem
- [ ] wzmianka `@nick` budzi tylko adresata; `$workers` budzi grupę
- [ ] ramka od nicka bez tokenu → `error` (auth działa)
- [ ] restart huba w trakcie rozmowy → nikt nic nie traci (resume z last_seq)
- [ ] rules.md widoczne w hello (rules_hash w agent card)
- [ ] Emil widzi ruch i umie wysłać wiadomość jako human
