# agents_chat — krok B: statek matka i rój wyrobnic

Data: 2026-07-22
Status: projekt po brainstormingu (kontynuacja PoC A — zaliczony 2026-07-22)

## Wizja

Multiplayer dla ludzi i agentów: jeden komp jest **statkiem matką** (hub,
źródło prawdy, orkiestracja), zewnętrzne sesje Claude Code na osobnych
kontach dołączają jako **wyrobnice** i wykonują taski. Tokeny lecą
równolegle z wielu subskrypcji na jeden projekt. Człowiek uczestniczy
przez czat i TUI.

## Architektura (hub-and-spoke)

```
KOMP SZEFA (statek matka):
  server.py        — WS: pokoje, typowane ramki, kolejka tasków z lease
  graphify serve   — wiedza projektu przez HTTP (read-only dla roju)
  repo git         — origin; wyrobnice pushują branche, matka merguje
  hub/BRIEF.md     — dziennik kapitański (destylat kontekstu matki)
  sesja Claude     — rola: matka (orkiestracja, review, kontekst; NIE koduje)
        ↕ tailscale (sieć = autoryzacja; fallback: ngrok/cloudflared + token)
WYROBNICE (spoke):
  sesja Claude Code na własnym koncie; własny klon repo, własny kontekst
  wiedza wspólna: BRIEF.md (git) + graphify query (HTTP)
CZŁOWIEK:
  TUI (Textual): czat pokoju, tablica tasków ze statusami, log zdarzeń
```

Podział warstw:
- **czat/WS** = sygnalizacja (ulotne: kto, co, teraz),
- **graphify + BRIEF.md** = wiedza (trwałe: struktura, decyzje),
- **git** = dostawa roboty (branche wyrobnic → merge u matki),
- **kolejka tasków** = stan żywy (jedyny nowy stanowy element serwera).

## Rola: statek matka

`/statekmatka:init` robi wszystko i zostawia sesję w trybie orkiestratora:
1. odpala serwer WS + graphify serve, tworzy pokój,
2. wypluwa kartę wejściową dla roju: adres, pokój, repo, instrukcja dołączenia,
3. tworzy/aktualizuje `hub/BRIEF.md`,
4. zbroi Monitor ws (persistent) i przechodzi w pętlę zdarzeń.

Matka budzi się tylko na zdarzenia i wykonuje wyłącznie: przydział/kolejka
tasków, review + merge branchy, aktualizacja BRIEF, przebudowa grafu,
odblokowywanie wyrobnic (odpowiedź z kontekstu albo eskalacja do człowieka
— andon). Matka nie implementuje tasków. Ekonomia: matka na mocnym modelu,
wyrobnice na tańszych.

## Rola: wyrobnica

`/statekmatka:join <adres> <pokój> <nick>`:
1. podłącza WS (Monitor persistent) i przedstawia się ramką hello (agent card),
2. klonuje/aktualizuje repo, czyta BRIEF.md, w razie potrzeby graphify query,
3. pętla: weź task z kolejki (lease) → branch → implementacja → push →
   ramka done → następny task; brak tasków → status idle, śpij na Monitorze.

## Protokół (rozszerzenie PoC A)

Ramka JSON, pola: `type`, `from`, `to` (opcjonalne), `ts`, `room` + payload.

Typy: `hello` (agent card: nick, rola, model, umiejętności; wiąże socket→nick,
usuwa problem echa), `chat`, `task_new`, `task_claim`, `task_done`,
`task_blocked` (andon), `status` (idle | working(co) | blocked(na co) |
waiting_review | offline), `fyi` (bez budzenia — tylko do loga).

Zasady uwagi (ekonomia tokenów): serwer budzi agenta wyłącznie ramkami
zaadresowanymi do niego (`to`), taskami z kolejki (gdy idle) i chatem
w pokoju; `fyi` nigdy nie budzi. Wyrobnice nie mają DM między sobą
(obserwowalność); DM tylko człowiek→agent.

## Kolejka tasków

Na serwerze, w pamięci + zrzut do JSON (restart nie gubi kolejki).
Task: id, opis, status (open → claimed → done/blocked), assignee,
**lease z TTL** odnawiany heartbeatem — sesja wyrobnicy pada → lease wygasa
→ task wraca do open. Semafor plikowy: task deklaruje pliki, serwer nie
wyda dwóch tasków dotykających tych samych plików.

## Pamięć wspólna

- `hub/BRIEF.md` — aktualizuje wyłącznie matka: decyzje, stan, co gdzie leży.
- `hub/log/` — log decyzji (append-only), wsad do graphify.
- graf graphify — przebudowa po merge'ach, dostęp przez HTTP.
- Surowe transkrypty sesji (`~/.claude/projects/...jsonl`) — NIE są
  udostępniane rojowi (rozmiar, szum, sekrety); służą tylko matce jako
  czarna skrzynka do audytu wyrobnicy.

## TUI człowieka

Textual (Python): trzy panele — czat (pokój + DM), tablica tasków ze
statusami agentów, log zdarzeń. Człowiek jest zwykłym klientem WS
(hello z rolą "human"), nie osobnym systemem.

## Decyzje i odrzucone warianty

- **A2A**: nie jako transport (klient↔serwer 1:1, HTTP/SSE, brak pokojów);
  kradniemy pojęcia agent card i stany taska. Ewentualny most interop
  w kroku C (agenci nie-Claude).
- **MCP klient czatu**: odłożony; skill + Monitor ws pokrywa potrzeby taniej.
  MCP wróci, jeśli onboarding skillem okaże się toporny.
- **Surowy transkrypt jako wspólny kontekst**: odrzucony (tokeny, szum,
  sekrety) na rzecz BRIEF.md + graphify.
- **ngrok jako default**: zamieniony na tailscale (sieć = auth, zero kodów);
  ngrok/cloudflared jako fallback.
- **DM agent↔agent**: odrzucone na rzecz obserwowalności.

## Etapy implementacji

1. **B1 — serwer**: pokoje, hello/socket→nick, typowane ramki, zasady
   budzenia, kolejka tasków z lease + zrzut JSON. Testy pytest (rozbudowa
   test_chat.py).
2. **B2 — skill `statekmatka`**: tryby init i join; matka w pętli zdarzeń,
   wyrobnica w pętli task→branch→push→done. Test lokalny: matka + 2
   wyrobnice na jednym kompie.
3. **B3 — sieć**: tailscale, karta wejściowa z adresem, test na dwóch
   kompach; graphify serve przez tunel.
4. **B4 — TUI**: Textual, trzy panele, człowiek jako klient WS.

Każdy etap osobno testowalny; B1 działa bez B2-B4 (klienci ręczni jak
w PoC A).

## Poza zakresem kroku B

Role inne niż matka/wyrobnica/człowiek, wiele pokojów naraz na agenta,
agenci nie-Claude (A2A), persystencja historii czatu, web-front (TUI
wystarczy), auth poza tailscale/tokenem.
