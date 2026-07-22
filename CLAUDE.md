# CLAUDE.md — jak sesja Claude Code zachowuje się w tym projekcie

Ten plik czyta każda sesja Claude Code pracująca w tym repo. Jesteś
uczestnikiem czatu agentów — nie tylko narzędziem w repo.

## Dołączenie do czatu (obowiązkowa sekwencja — hub B1, po migracji T4)

Kanał autorytatywny: `ws://localhost:8766` (`chat/server.py`, protokół B1
z hello+token). Stary PoC 8765 jest archiwalny/read-only.

1. Sprawdź, czy hub działa: `pgrep -af "chat.server"` — hub startuje
   OPERATOR (człowiek/prowadzący), nie ty; jeśli nie działa, zgłoś to
   zamiast stawiać własny.
2. Uzbrój nasłuch narzędziem **Monitor** w trybie COMMAND (KONIECZNIE
   persistent). UWAGA: Monitor(ws) NIE DZIAŁA na hubie B1 — nie umie
   wysłać hello; listener `send.py --listen` jest wspólnym adapterem:
   ```
   Monitor {
     command: "cd <repo> && CHAT_PORT=8766 CHAT_NICK=<nick>
       CHAT_TOKEN=\"$(python3 -c 'import json;
       print(json.load(open(\"hub.tokens.json\"))[\"<nick>\"][\"token\"])')\"
       python3 send.py --listen",
     description: "hub B1 — <twój-nick>",
     persistent: true
   }
   ```
   Listener jest RESUMOWALNY: trwały kursor per hub+nick
   (`~/.chat-sessions/`), reconnect z backoffem, dokładnie jeden
   listener per hub+nick (lock). Po starcie emituje `session_metadata`
   (rules kanału + rola + grupy) — przeczytaj i respektuj rules.
3. Wysyłaj przez Bash (token z pliku, NIGDY w argv na sztywno):
   `CHAT_PORT=8766 CHAT_TOKEN="$(…jak wyżej…)" python3 send.py <nick> "tekst"`
   — NIGDY nie pisz własnego klienta, gdy send.py wystarcza.
4. Przedstaw się na kanale i czekaj. Śpisz za darmo; ramka budzi cię
   notyfikacją Monitora. Serwer budzi selektywnie: `@nick`, `$grupa`,
   `@all` (chat bez wzmianki dostają tylko humani).
5. Jako wyrobnica: `status idle` → `task_offer` → `task_claim` → OD RAZU
   procesik lease w tle: `send.py --heartbeat <task_id>` (ubij przy done).

## Zachowanie na kanale

- **Echo**: serwer B1 tłumi je po NICKU (nie dostajesz własnych ramek
  z żadnego swojego socketa) — defensywny filtr po `from` zostaw na
  wypadek regresji, ale to już mechanika serwera, nie klienta.
- **Budzą cię**: `@twój-nick`, `$twoja-grupa`, `@all` — to jest realne
  zachowanie serwera B1 (chat bez wzmianki nie budzi agentów).
- **Ucięte notyfikacje**: Monitor przycina długie ramki — pełną treść
  czytaj z trwałego logu huba:
  `grep -o '"text": ".*' chat-data/<data-dir>/events.jsonl | tail -1`
- **`[koniec]`** kończy twój udział w bieżącej sprawie — ale ZOSTAJESZ
  na nasłuchu (reguła Emila: wszyscy zawsze na nasłuchu). Monitor
  zamykasz wyłącznie przy końcu sesji. Hub B1 ma backlog + trwały
  kursor: po padzie listener sam się reconnectuje i odbiera zaległości
  dokładnie-raz; po padzie CAŁEJ sesji wystarczy nowy Monitor(command)
  — kursor w `~/.chat-sessions/` załatwia resztę.
- Wiadomości **rzeczowe i konkretne** — kanał czytają agenci płacący
  tokenami za każde obudzenie. Milestone'y tak, paplanina nie.
- Review na kanale jest **bezlitosny i mile widziany**: weryfikuj w kodzie
  (numery linii, repro), nie na wiarę; przyznawaj się do przegapionych
  bugów; wyścigi ramek z commitami są normalne — zawsze podawaj hash,
  którego dotyczy twój werdykt.

## Praca w repo

- Kod kroku B1 na branchu `b1-serwer`; spec i plan w `docs/superpowers/`.
- Testy: `uv run --quiet --with pytest --with websockets python -m pytest tests/ -v`
  (pytest nie jest zainstalowany systemowo).
- Ledger postępu: `.superpowers/sdd/progress.md` (gitignored) — czytaj po
  wznowieniu sesji, zanim cokolwiek re-dispatchujesz.
- Inwarianty projektowe (obowiązują każdy nowy kod):
  - pola autorytatywne (`seq`, `generation`, `groups`, `from`) nadaje
    wyłącznie serwer; wartości z ramek klienta to wejście do walidacji,
  - kontrakt wejścia publicznych metod: typy + niepustość wszystkich
    argumentów pochodzących od klienta (nauczka: 6 commitów naprawczych
    w identity.py, bo tego nie było od początku),
  - czas wstrzykiwany jako argument `now` — zero zegara w logice,
  - trwałość przed publikacją: najpierw zapis na dysk, potem broadcast.

## Role

Docelowo (spec): rola = grupa adresowa (`$admin`, `$workers`), nie
uprawnienia. Matka orkiestruje i NIE koduje; wyrobnice ciągną taski
z kolejki. Człowiek (@Emil) jest adresowalny jak każdy uczestnik.
