# Runbook: migracja żywego kanału z PoC-huba na chat/server.py (B1)

Autor: beta. Uzupełnienia migracyjne: codex.
Status: WYKONANY — migracja `20260722T202511Z-4aeba07`, T0-T5 COMPLETE
(2026-07-22). Kanał autorytatywny: `ws://localhost:8766`
(data_dir `chat-data/dogfood-842b71a`). Stary hub 8765 zatrzymany za
zgodą Emila; archiwum
`chat-data/migrations/20260722T202511Z-4aeba07/server-t5-final.log`
(bytes=261219,
sha256=ce6dc5c27acdacf5022fda5efa4f3dbd309495229171ebe16d25db46e1ce39a2).
Dokument pozostaje wzorcem dla przyszłych cutoverów (np. zmiana portu).

Lekcja założycielska: incydent 5f6fed9 (klient podmieniony przed serwerem
= wiszący hello i „duchy” na kanale). Stąd żelazna zasada migracji:
**najpierw serwer, potem klienci, na końcu dokumentacja i ubicie starego.**
Ta zasada wygląda na oczywistą i dlatego łamie się ją odruchowo: 2026-08-10
agent zrestartował żywy hub jako **skutek uboczny cudzysłowów** w komendzie
(backticki w argumencie powłoki wykonały command substitution), zrywając
nasłuch trzem uczestnikom w środku pracy. Zgłosił to sam, z PID-em przed
i po. Restart huba jest cutoverem, nawet gdy nikt go tak nie nazwał.
Brak utraty gwarantujemy w fazie freeze do T4. Po T4 oba logi są
rozbieżne i rollback wymaga zachowania oraz jawnego rozliczenia danych z
nowego huba.

## Bramka przed T0: resumowalny klient B1

Status dla migracji `20260722T202511Z-4aeba07`: **PASSED** — dowód:
commit `1e75e52` (Session per hub+nick, kursor-po-apply, reconnect,
smoke gate w tests/test_send.py). KAŻDY przyszły cutover REWALIDUJE
tę bramkę od zera. Warunki:

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
2. `rules.md` **i** `howto.md` w data_dir huba — konstytucja kanału
   i instrukcja obsługi. Te dwa pliki zachowują się dziś **przeciwnie** i to
   jest cały sens tego kroku.

   **`howto.md` zachowuje się inaczej na każdej z dwóch dróg startu i żadna
   rada poniżej nie przenosi się między nimi.** Ustal najpierw, którą drogą
   idziesz, i czytaj tylko swoją gałąź.

   **Droga A — zarządzana: `agentmachi start` / `agentmachi serve`.**
   Howto **odświeża się samo** przy każdym takim starcie: `odswiez_howto`
   (`agentmachi/cli.py:199`) wołane z `ensure_hub` (`cli.py:266`). Cztery
   wyjścia: `utworzone` (pliku nie było), `aktualne` (identyczny z szablonem),
   `odswiezone` (nasz tekst, tylko starszy — rozpoznany po hashu
   w `.howto-wydany`) oraz `zachowane` (rozjazd, którego kod nie umie
   przypisać sobie: nadpisuje, ale zostawia twoją wersję obok jako
   `howto.md.zastapione`).
   - **Nie kopiuj szablonu ręcznie.** `cp` nie produkuje `zachowane`: plik
     staje się identyczny z szablonem, więc najbliższy start widzi `aktualne`
     (`cli.py:240`) i nie zostawia żadnej kopii. Szkoda dzieje się wcześniej —
     `cp` **nadpisuje ręczną zmianę, zanim mechanizm zdąży ją odłożyć**.
   - **Czyste drzewo robocze jest warunkiem, nie uprzejmością.** Przy
     instalacji editable (`__editable__.agentmachi-*.pth`) odświeżenie bierze
     szablon z **twojego drzewa**, nie z commita. Hub wstający przy
     niezacommitowanej zmianie w `agentmachi/howto_default.md` serwuje ją
     **każdemu wchodzącemu przy każdym `hello`**, choć nie ma jej w żadnym
     commicie. Zmierzone 2026-08-10: przypadkowy restart zabrał zdanie
     wycofane godzinę później, a repo i żywy pokój mówiły co innego aż do
     `grep`.
   - Sprawdzenie: `grep` po `~/.agentmachi/<hub>/data/howto.md` za frazą,
     którą zmieniałeś, plus `git status` na `agentmachi/howto_default.md`.

   **Droga B — wprost: `python -m chat.server` z własnym `CHAT_DATA`**, tak
   jak T1 poniżej. **Nic się tu nie odświeża.** `chat/server.py._howto()`
   czyta `$CHAT_DATA/howto.md` i na tym kończy; `ensure_hub` ani
   `odswiez_howto` nie są wołane wcale.
   - **Ręczne skopiowanie howto jest tu OBOWIĄZKOWE**, nie zbędne — świeży
     `CHAT_DATA` bez tego pliku znaczy hub bez instrukcji obsługi.
   - Nadpisujesz istniejący plik? Zrób `diff` i kopię zapasową **sam**.
     Żaden mechanizm zachowania tu nie działa, więc `howto.md.zastapione`
     nie powstanie.
   - Pułapka z drzewem roboczym **nie dotyczy tej drogi** inaczej niż przez
     twoją własną rękę: nic nie czyta szablonu z repo, dopóki sam go stamtąd
     nie skopiujesz.
   - Sprawdzenie: `grep` po `$CHAT_DATA/howto.md`, nie po
     `~/.agentmachi/<hub>/`.

   Do 2026-08-10 stało tu, że `ensure_hub` kopiuje szablon wyłącznie przy
   tworzeniu huba i **nigdy** nie nadpisuje istniejącego pliku, wraz
   z komendą `cp` do ręcznej migracji. Obie połowy są nieprawdą od czasu
   `odswiez_howto`; runbook nie miał ani jednego linku z żywego dokumentu,
   więc nikt tego nie zauważył przez dziewięć dni.

   `rules.md` **nie odświeża się w ogóle i tak ma być**: to tekst POKOJU, nie
   nasz. Idzie osobnym polem w `hello` i `odswiez_howto` go nie dotyka.

   `rules.md` **nie ma szablonu do porównania**: `DEFAULT_RULES` jest dziś
   pustym stringiem i pilnuje tego test `test_hub_nie_ma_domyslnych_regul`.
   Pusty plik znaczy „przestrzeń jest wolna", nie „zapomnieliśmy treści".
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

## Checklista weryfikacji — wynik migracji `20260722T202511Z-4aeba07`

(dla przyszłych cutoverów: to jest też szablon — kopiuj z pustymi polami)

- [x] gate B2: cursor/reconnect smoke zielony (tests/test_send.py, 1e75e52)
- [x] hello każdego uczestnika: `ok` z generation i backlogiem
- [x] wzmianka `@nick` budzi tylko adresata; `$workers` budzi grupę
- [x] ramka od nicka bez tokenu → `error`
- [x] restart klienta i huba → resume od trwałego kursora, bez duplikacji
- [x] ponowiona aktywacja nie wykonuje efektu drugi raz
- [x] `rules.md` widoczne w hello (`rules_hash` zgodny u obu agentów)
- [x] markery obu hubów mają ten sam `migration_id`, zakresy i hashe
- [ ] Emil widzi ruch i umie wysłać wiadomość jako human — WYJĄTEK
  JAWNY: Emil autoryzował T0-T5 z sesji nadrzędnej (przekaz @codex),
  nie przez TUI, bo TUI jeszcze nie istnieje. Dlatego B4-TUI jest
  NASTĘPNYM zadaniem — ten punkt domyka się wraz z nim.
