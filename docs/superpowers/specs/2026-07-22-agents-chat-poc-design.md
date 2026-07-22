# agents_chat — PoC A: dwie sesje Claude Code gadają przez WebSocket

Data: 2026-07-22
Status: zatwierdzony kierunek (krok A z planu A → B → C)

## Cel

Dowieść mechaniki multiplayer dla agentów: dwie niezależne sesje Claude Code
(osobne konteksty, docelowo osobne konta rozliczeniowe) komunikują się przez
wspólny hub bez udziału człowieka. Człowiek ogląda biernie.

Sukces: alfa i beta wymieniają ~5 rund ping-ponga (przedstawienie się, small
talk), kończą `[koniec]`, żadna sesja nie wisi w ciszy i żadna nie mieli
tokenów w pętli.

Poza zakresem (krok B/C): sieć/VPS, autoryzacja, role szef/worker, przydzielanie
tasków, wymiana plików kontekstu, persystencja historii.

## Architektura

Trzy elementy:

1. **`server.py`** — serwer WebSocket na `localhost:8765` (biblioteka
   `websockets`, ~50 linii). Głupia rura: każdą ramkę od klienta broadcastuje
   do wszystkich pozostałych klientów. Zero persystencji, zero logiki.
2. **Dwie sesje Claude Code** (alfa, beta) — każda:
   - nasłuchuje przez `Monitor {ws: "ws://localhost:8765"}` (persistent) —
     każda ramka budzi agenta,
   - wysyła przez `python3 send.py <nick> "tekst"` odpalane Bashem.
3. **Obserwator (człowiek)** — `python3 send.py --listen` podpina się jako
   trzeci klient i tylko wypisuje ruch; alternatywnie patrzy na oba terminale.

Przepływ: alfa wysyła → serwer broadcastuje → Monitor bety dostaje ramkę →
beta budzi się, odpisuje przez send.py → Monitor alfy dostaje ramkę → pętla.

## Protokół

Ramka = JSON w jednej linii: `{"from": "alfa", "text": "..."}`.

- Tożsamość deklaruje nadawca; serwer niczego nie dokleja ani nie weryfikuje
  (auth to problem kroku B).
- Agent ignoruje ramki, w których `from` == własny nick (broadcast może wrócić
  do nadawcy — zależnie od implementacji serwera nadawca jest wykluczony, ale
  klient i tak filtruje po swojej stronie).
- Koniec rozmowy: ramka z `text` == `[koniec]` po ~5 rundach. Obaj agenci
  zamykają wtedy Monitory (TaskStop) i kończą turę.
- Serwer nie kończy się sam — ubijany Ctrl+C.

## Pliki

```
server.py   — serwer broadcast (websockets)
send.py     — klient: wyślij jedną wiadomość i wyjdź; tryb --listen: wypisuj ruch
```

Prompt startowy dla sesji agentów podaje człowiek ręcznie (dwa terminale,
`claude "jesteś alfa…"`). Treść przykładowego promptu trafi do planu
implementacji.

## Obsługa błędów

- **Serwer pada** → Monitor zgłasza zamknięcie socketa z kodem; agent
  raportuje to człowiekowi zamiast wisieć w ciszy.
- **Drugi agent milczy** → po jednej ramce przypominajki agent kończy
  `[koniec]`.
- **send.py nie może się połączyć** → niezerowy exit code i czytelny błąd na
  stderr; agent widzi to w wyniku Basha.

## Testowanie

Wyłącznie ręczne — to jest cały sens PoC:

1. `python3 server.py` w tle,
2. dwie sesje Claude Code z promptami startowymi (alfa zaczyna),
3. obserwacja: ping-pong leci, po ~5 rundach `[koniec]`, Monitory zamknięte.

Bez testów automatycznych na tym etapie.

## Decyzje i odrzucone warianty

- **Transport**: WebSocket (wybór użytkownika). Odrzucone: wspólny plik JSONL
  (najprostszy, ale nie prowadzi do kroku B), tmux send-keys (hack).
- **Język serwera**: Python (wybór użytkownika). Rozważane Go (statyczny
  binarek pod VPS) — do ewentualnej podmiany w kroku B; Rust odrzucony jako
  overkill dla głupiej rury.
