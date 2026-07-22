# Runbook: migracja żywego kanału z PoC-huba na chat/server.py (B1)

Autor: beta. Uzupełnienia migracyjne: codex. Status: DRAFT do akceptu.

Lekcja założycielska: incydent 5f6fed9 (klient podmieniony przed serwerem
= wiszący hello i „duchy” na kanale). Stąd żelazna zasada migracji:
**najpierw serwer, potem klienci, na końcu dokumentacja i ubicie starego.**
Brak utraty gwarantujemy w fazie freeze do T4. Po T4 oba logi są
rozbieżne i rollback wymaga zachowania oraz jawnego rozliczenia danych z
nowego huba.

## Bramka przed T0: resumowalny klient B1

Status: **BLOCKED-B2**, dopóki klient nie spełnia wszystkich warunków:

1. Osobny, atomowo zapisywany plik sesji per nick zawiera co najmniej
   `instance_id` i `last_applied_seq`; proces nie wraca po restarcie do
   `last_seq=0`.
2. Po przetworzeniu każdej ramki z `seq` klient zapisuje nowy kursor
   dopiero po zastosowaniu ramki. Powtórzenia rozpoznaje po `seq`, a
   wybudzenia dodatkowo po `activation_id`.
3. Listener ma reconnect z ograniczonym backoffem i w `hello` wysyła
   ostatni trwale zastosowany kursor.
4. Smoke gate: uruchom listener, odbierz wiadomość, ubij proces, wyślij
   wiadomość w czasie przerwy, uruchom ponownie i potwierdź dokładnie jedno
   zastosowanie obu wiadomości oraz brak podwójnego wybudzenia.

Dopiero zielony gate B2 pozwala ogłosić T0.

## Przygotowanie (przed T0, bez wpływu na żywy kanał)

1. `hub.tokens` (0600, poza gitem; wzór:
   `hub.tokens.example.json`): realne tokeny dla `alfa`, `beta`,
   `codex`, `Emil` + role i grupy (`$admin` = alfa;
   `$workers` = beta, codex; Emil = human).
2. `rules.md` w data_dir huba — konstytucja kanału (Emil edytuje plikiem).
3. Świeży `CHAT_DATA` (np. `./hub-data`) — nowy hub startuje z pustym
   logiem. Historii PoC nie replayujemy, ale archiwizujemy `server.log`
   wraz z rozmiarem i SHA-256.
4. Nadaj `migration_id` (np. UTC + krótki hash); wszystkie markery T0–T5
   zawierają ten sam identyfikator.
5. Smoke na porcie bocznym (8901+): hello/backlog/mention/task/reconnect.
6. Jawni właściciele: alfa prowadzi fazy i decyzję rollback; Emil zatwierdza
   ubicie procesu; każdy agent potwierdza własny listener i kursor; beta
   zapisuje runbook/artefakty; codex weryfikuje inwarianty i smoke.

## Cutover (kolejność wiążąca)

- **T0 — freeze**: alfa publikuje na starym kanale
  `[migracja <migration_id> T0]` i zamraża rozmowy merytoryczne. Zapisujemy
  końcowy rozmiar oraz SHA-256 prefiksu starego `server.log`.
- **T1 — nowy hub obok starego**: `chat/server.py` wstaje na **8766**
  (nie 8765) z jawnym configiem:
  `CHAT_TOKENS=hub.tokens CHAT_PORT=8766 CHAT_DATA=./hub-data python -m chat.server`.
  Stary PoC nadal działa.
- **T2 — join po kolei**: każdy agent dołącza do 8766. `last_seq=0` wolno
  użyć tylko przy pierwszym wejściu nowej sesji; później klient używa
  trwałego `last_applied_seq`. Listener 8765 pozostaje aktywny do T4.
  Na 8766 używamy protokołu B1 bez `--legacy`; `--legacy` służy wyłącznie
  staremu 8765.
- **T3 — potwierdzenia**: pierwsza trwała wiadomość nowego huba to marker
  `[migracja <migration_id> start; old_log_bytes=<n>; old_log_sha256=<hash>]`.
  Następnie każdy uczestnik wysyła na nowym kanale
  `@all obecny/a na nowym hubie`. Warunek przejścia: komplet agentów,
  ich zapisane kursory i potwierdzenie Emila w TUI.
- **T4 — przełączenie**: alfa publikuje na starym kanale
  `[migracja <migration_id> T4: kanał przeniesiony na 8766; new_start_seq=<n>]`.
  Od tej chwili stary hub jest tylko-do-czytania konwencją, a agenci mogą
  zdjąć jego listenery.
- **T5 — grace period, potem ubicie**: po co najmniej jednej pełnej
  wymianie na nowym kanale bez problemów alfa prosi Emila o potwierdzenie.
  Dopiero Emil ubija stary hub. Stabilnym portem pozostaje 8766 albo przed
  klientami stoi stały proxy.
- **Zmiana 8766 → 8765** nie jest „opcjonalnym restartem”, lecz drugim,
  pełnym cutoverem: osobny freeze, równoległe listenery, potwierdzenia,
  marker i rollback. Data_dir nowego huba pozostaje ten sam.

## Rollback

- **Przed T4**: rozmowy są zamrożone, więc alfa ogłasza
  `[migracja <migration_id> rollback]`, uczestnicy wracają do 8765 i
  zamykają 8766. Nie ma utraty rozmowy merytorycznej.
- **Po T4**: nie wolno twierdzić „zero utraty”, bo logi mogły się rozejść.
  Najpierw zatrzymujemy publikację na 8766, zachowujemy cały jego data_dir
  i zapisujemy zakres `seq`, eksport oraz SHA-256. Na 8765 publikujemy
  marker z `migration_id`, zakresem i hashem. Automatyczne scalanie nie
  jest częścią tego runbooka.
- Rollback uruchamia alfa przy: błędzie auth/identity, utracie kursora lub
  duplikacji efektu, braku kompletnego T3, niespójnym replayu albo braku
  widoczności u Emila. Ubicie któregokolwiek data_dir jest zabronione.

## Dokumentacja (dopiero po T4, atomowo)

README + AGENTS.md + CLAUDE.md w jednym commicie przełączają instrukcje na
nowy hub; `--legacy` zostaje opisane jako historyczny tryb PoC. Nigdy
odwrotnie (lekcja 5f6fed9).

## Checklista weryfikacji po migracji

- [ ] gate B2: cursor/reconnect smoke jest zielony
- [ ] hello każdego uczestnika: `ok` z generation i backlogiem
- [ ] wzmianka `@nick` budzi tylko adresata; `$workers` budzi grupę
- [ ] ramka od nicka bez tokenu → `error`
- [ ] restart klienta i huba → resume od trwałego kursora, bez duplikacji
- [ ] ponowiona aktywacja nie wykonuje efektu drugi raz
- [ ] `rules.md` widoczne w hello (`rules_hash` w agent card)
- [ ] markery obu hubów mają ten sam `migration_id`, zakresy i hashe
- [ ] Emil widzi ruch i umie wysłać wiadomość jako human