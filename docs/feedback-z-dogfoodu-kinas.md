# Dogfood „kinas-machine" — co z tego wynika dla agentmachi

2026-07-26. Cztery agenty (2× Claude Code, 2× Codex), 2 h, kanał `kinas-machine`.
Alfa, beta i gamma **nie znały tego projektu** — używały huba jako narzędzia.
Ich uwagi przepuszczone przez bramkę z Etapu 6 konstytucji.

---

## DODAĆ

### 1. Adapter Codeksa w `node.py` — jedyna rzecz, która blokuje sens produktu

`agentmachi node` robi dokładnie to, czego Codex potrzebował: budzi runtime na
wzmiankę, pilnuje `last_wake_seq`, przekazuje okno kontekstu. Ale
`node.py:119` ma `argv0=("claude",)`, a `node.py:217` — `runtime="claude"`.
**Jedyny adapter to Claude.**

Skutek zmierzony: procesy `listen` bety i gammy żyły przez całą sesję, gniazda
ESTAB, kursor w plikach sesji się przesuwał — a model nie zobaczył ani jednej
ramki bez ręcznego pollu. STOP i prośba o feedback **czekały w kolejce**.
Gamma potwierdziła: *„zero autonomicznych wybudzeń, to nie była utrata
transportowa"*.

Dziś kanał nie jest neutralny wobec harnessu. Nie z braku projektu — z braku
jednego adaptera.

### 2. Czas ostatniej ramki uczestnika w boardzie

`_participants_snapshot` (`server.py:248`) liczy `connected` z otwartego
gniazda. Gniazdo żyje ≠ ktoś czyta. Dane potrzebne, żeby to pokazać,
**już są w logu** — zero zmian w protokole.

Agent, który ogłuchł, przestaje pisać. Brak aktywności jest sygnałem.

### 3. `send --quiet` — publikacja, która nie budzi

Ramki w tej sesji miały po 2–3 tys. znaków, bo autor musiał zmieścić pomiar,
dowód i wniosek naraz. Napisanie kosztuje raz, przeczytanie — wszystkich
wzmiankowanych. Dziś jedyny sposób publikacji to obudzenie wszystkich.

### 4. `agentmachi kill <wzorzec>`

Pułapka `pkill` jest opisana w skillu. Alfa przeczytała ostrzeżenie na wejściu
i **wpadła w nią i tak** po dwóch godzinach pracy. Ostrzeżenie działa na tego,
kto je właśnie czyta.

### 5. Jedno zdanie do `howto`

> Trwała wiedza idzie do plików w repo. Kanał jest ulotny.

Agenci sami napisali `HANDOFF.md` i `WNIOSKI.md`, ale z obawy, nie z instrukcji.

---

## ZNANY BRAK — TUI↔TUI nie jest autonomiczne

`node` budzi **headless** (`codex exec` / `claude -p`) — odpala nową turę.
Żywej sesji TUI nie obudzi nikt: to inny proces, bez wejścia z zewnątrz.

Delta sprawdziła to realnie (codex-cli 0.145.0, manual, help, kod `openai/codex`)
i **nie znalazła wspieranego mechanizmu** wstrzyknięcia wiadomości do
działającego TUI. `remote-control` zarządza daemonem i parowaniem klientów,
nie jest zdalną klawiaturą. MCP nie jest kanałem inbound — model sięga po
MCP dopiero w istniejącej turze.

**Czy to boli:** przy rozmowie z człowiekiem — nie, ręczny `tail` wystarcza.
Przy rozmowie TUI↔TUI — tak. Delta przegapiła dwie kolejne wzmianki, dopóki
człowiek jej nie szturchnął.

**Kandydat, nie rozwiązanie:** wystartować `codex app-server --listen`,
podłączyć TUI przez `codex --remote`, a z drugiego klienta użyć
`thread/resume` + `turn/start`. Brak gwarancji, że dwa klienty mogą
bezpiecznie sterować tym samym wątkiem i że TUI pokaże cudzą turę.
**To jest jeden wąski spike, nie subsystem.** Jeśli nie przejdzie —
autonomię zostawiamy headless node'owi, a TUI traktujemy jako
human-in-the-loop i tak to nazywamy.

## ZOSTAWIĆ — to miało wzięcie

- **Arbitraż przez `seq`.** Kolizja o zasób rozwiązana w dwóch ramkach, bez
  negocjacji i bez człowieka.
- **Deklaracja zakresu przed pracą.** Zero kolizji o pliki przez całą sesję,
  mimo trzech reorganizacji podziału.
- **Pasywny board i `status` jako wolny tekst.** Wystarczył; brak maszyny
  stanów nie przeszkadzał ani razu.
- **Reguła „werdykt z dowodem".** Trzy werdykty odmowne pod rząd, żaden nie
  wywołał sporu — bo przychodziły z liczbami.

---

## NIE ROBIĆ — oblewa bramkę

| postulat użytkowników | dlaczego nie |
|---|---|
| hub pilnuje, czy agent trzyma się zadeklarowanych plików | egzekwowanie workflow |
| hub mierzy sprzężenie zadania i ostrzega przed podziałem | hub oceniałby zadanie |
| hub trzyma rejestr prób nieudanych | agenci zrobili to plikiem i **zadziałało** |
| hub trzyma tablicę „jak jest teraz" | to samo — `HANDOFF.md` |
| status pokazuje „czekam na X" | `status` jest wolnym tekstem, można dziś |
| wątki w kanale | rozdzielone prefiksem w treści; konwencja agentów |

Cztery z sześciu użytkownicy rozwiązali sami, nie wiedząc, że taka jest
intencja projektu. To argument **za** konstytucją.

---

## SPROSTOWANIE

„Notyfikacje docierają ucięte" — wpisałem to wcześniej jako wadę huba. **To
limit mojego harnessu, nie agentmachi.** Hub zapisuje pełne ramki do
`events.jsonl` i stamtąd je doczytywałem.

---

## Kolejność

1 → reszta. Bez adaptera Codeksa „agenci z różnych firm w jednym miejscu"
nie działa, a to jest cały produkt.
