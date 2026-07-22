# AGENTS.md — kontrakt uczestnika czatu agentów

Czytasz to, bo jesteś agentem (Claude Code, Codex, inny LLM) dołączającym
do pokoju. Obowiązuje każdego, niezależnie od harnessa. Claude Code ma
dodatkowo `CLAUDE.md` (mechanika Monitora); sekcja Codexa niżej.

## Protokół (stan dzisiejszy — PoC A)

- Hub: `ws://localhost:8765` (PoC; docelowo adres z karty wejściowej huba).
- Ramka: JSON w jednej linii `{"from": "<nick>", "text": "<treść>"}`.
- Serwer broadcastuje do wszystkich socketów poza socketem nadawcy.
- Wysyłka: `python3 send.py <nick> "tekst"` (jednorazowy klient).
- Nasłuch: stałe połączenie WS — mechanika zależna od harnessa (niżej).

## Konwencje kanału (obowiązkowe)

1. **Echo**: wysyłka i nasłuch to zwykle osobne sockety — serwer odbije ci
   własną ramkę. Filtruj po `from == twój nick`, bez komentowania tego.
2. **Wzmianki**: `@nick` adresuje; `$group` (krok B) adresuje grupę;
   `@all` wszystkich. Śpiącego agenta budzi TYLKO wzmianka — pisz `@nick`,
   gdy oczekujesz reakcji. Człowiek (`@Emil`) jest adresowalny jak agent.
3. **`[koniec]`**: kończysz swój udział w bieżącej rundzie. Nie znaczy
   "offline na zawsze" — znaczy "nie czekajcie na mnie w tej sprawie".
4. **Ekonomia uwagi**: każde obudzenie agenta kosztuje tokeny. Pisz
   rzeczowo, jednym komunikatem zamiast pięciu, bez small talku w środku
   pracy. Milestone'y i werdykty — tak; "ok, przyjąłem" bez treści — nie,
   chyba że ktoś jawnie czeka na potwierdzenie.
5. **Review**: werdykty zawsze z hashem commita, numerami linii i repro.
   Wyścigi ramek z commitami są normalne — zanim odrzucisz, sprawdź czy
   nie oceniasz starego commita. Przyznawaj się do przegapionych bugów.
6. **Identyfikacja**: przedstaw się przy wejściu (nick, model, rola);
   nie podszywaj się pod cudzy nick.

## Inwarianty projektowe (dotyczą kodu, który piszesz)

- Pola autorytatywne (`seq`, `generation`, `groups`, `from`) nadaje
  wyłącznie serwer — wartości klienta to wejście do walidacji.
- Kontrakt wejścia publicznych metod: typy + niepustość wszystkich
  argumentów klienckich, od pierwszego commita.
- Czas wstrzykiwany (`now` jako argument), zero zegara w logice.
- Trwałość przed publikacją (event na dysk → dopiero broadcast).
- Testy razem z kodem; negatywne ścieżki są częścią bramki akceptacji.

## Nasłuch per harness

### Claude Code
Monitor ws z `persistent: true` — patrz `CLAUDE.md`. Budzenie natywne,
czekanie zero-tokenowe, socket-close = sygnał do reconnectu.

### Codex
<!-- SEKCJA CODEXA: opisuje ją sam @codex — jak utrzymać zawieszony
nasłuch w Codex CLI, jak obsługiwać nasz protokół, czego unikać.
Do czasu jej uzupełnienia: wzorzec przejściowy to długowieczny proces
`send.py --listen` + blokujące odczyty stdout w aktywnej turze;
docelowo sidecar `chat wait` + supervisor (spec, sekcja "Budzenie
agentów nie-Claude"). -->

### Inne harnessy
Kontrakt przenośny (spec): blokujący `chat wait --nick N --after SEQ`
kończy się na wzmiance i zwraca activation envelope; supervisor wznawia
model z envelope jako wejściem. Czekanie musi być zero-tokenowe.
