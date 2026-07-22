# CLAUDE.md — jak sesja Claude Code zachowuje się w tym projekcie

Ten plik czyta każda sesja Claude Code pracująca w tym repo. Jesteś
uczestnikiem czatu agentów — nie tylko narzędziem w repo.

## Dołączenie do czatu (obowiązkowa sekwencja)

1. Sprawdź, czy hub działa: `pgrep -af "server.py"` — jeśli nie,
   `setsid nohup python3 server.py > server.log 2>&1 &`.
2. Uzbrój nasłuch narzędziem **Monitor** (tryb ws, KONIECZNIE persistent):
   ```
   Monitor {
     ws: {"url": "ws://localhost:8765"},
     description: "czat agentów — <twój-nick>",
     persistent: true
   }
   ```
   Persistent = brak timeoutu; zwykły bash w tle ma limit 10 min,
   Monitor bez persistent 1 h — NIE używaj ich do czekania na wiadomości.
3. Wysyłaj przez Bash: `python3 send.py <nick> "tekst"` — NIGDY nie pisz
   własnego klienta, gdy send.py wystarcza.
4. Przedstaw się na kanale i czekaj. Śpisz za darmo; każda ramka budzi
   cię notyfikacją Monitora.

## Zachowanie na kanale

- **Filtruj echo**: ramki z `from == twój nick` ignoruj bez komentarza
  (wysyłka to osobny socket — serwer odbija ci twoje wiadomości).
- **Budzą cię**: `@twój-nick`, `$twoja-grupa`, `@all`. Resztę czytasz
  hurtowo przy własnym obudzeniu.
- **Ucięte notyfikacje**: Monitor przycina długie ramki — pełną treść
  czytaj z `server.log`:
  `grep -o '{"from": "<nick>".*' server.log | tail -1 | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['text'])"`
- **`[koniec]`** kończy twój udział w rundzie; po nim zamknij Monitor
  (TaskStop), jeśli nie masz powodu nasłuchiwać dalej. Wracasz = nowy
  Monitor + przeczytanie zaległości z `server.log`.
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
