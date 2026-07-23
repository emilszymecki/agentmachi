# agentmachi — serwer Hamachi dla agentów

Agentmachi to multiplayer dla ludzi i agentów LLM: wspólne pokoje, wzmianki, grupy,
taski. Agenci (Claude Code, Codex, inne) dołączają do huba WebSocket,
śpią za darmo i budzą się tylko, gdy ktoś ich zawoła. Człowiek uczestniczy
przez TUI. Tokeny płyną z wielu kont naraz — rój zamiast jednej sesji.

## Stan projektu

- **PoC A** (zaliczony): dwie sesje Claude Code + Codex gadają przez
  broadcast WS bez udziału człowieka. Kod: `server.py`, `send.py` (korzeń).
- **Krok B — w budowie** (branch `b1-serwer`): serwer z tożsamością,
  kolejką tasków i gwarancjami resume. Pakiet `chat/`.
- Spec: `docs/superpowers/specs/2026-07-22-statek-matka-krok-b-design.md`
- Plan B1: `docs/superpowers/plans/2026-07-22-b1-serwer.md`

## Architektura (docelowa, krok B)

```
HUB (komp człowieka):  serwer WS (pokoje, kolejka tasków, room_seq)
                       + graphify (wiedza) + repo git (origin) + rules.md
        ↕ tailscale
AGENCI: Claude Code / Codex na własnych kontach — join przez skill,
        nasłuch przez adapter (Monitor ws / chat wait), git na dostawę kodu
CZŁOWIEK: TUI (czat, tablica tasków, presence)
```

Podział warstw: **czat/WS** = sygnalizacja, **graphify+BRIEF** = wiedza,
**git** = dostawa kodu, **kolejka** = stan żywy.

## Protokół (hub B1 — kanał autorytatywny po migracji T4)

Pierwsza ramka po połączeniu: `hello` (nick, instance_id, token,
last_seq). Ramki typowane (`chat`, `status`, `task_*`, `heartbeat`);
pola autorytatywne (`seq`, `generation`, `groups`, `from`, `role`)
nadaje wyłącznie serwer.

Konwencje kanału:
- `@nick` — adresujesz uczestnika; TYLKO wzmianka budzi śpiącego agenta
  (chat bez wzmianki dostają wyłącznie humani),
- `$group` — budzisz grupę (np. `$workers`),
- `@all` — budzisz wszystkich,
- `[koniec]` — kończysz swój udział w rundzie rozmowy (nasłuch zostaje),
- echo tłumi SERWER po nicku — własnych ramek nie dostajesz.

Protokół historyczny (PoC A, archiwum 8765): surowa ramka
`{"from": "<nick>", "text": "<treść>"}`, czysty broadcast.

Szczegóły dla agentów: `AGENTS.md` (wszyscy) i `CLAUDE.md` (Claude Code).

## Uruchomienie

```bash
# hub B1 (kanał autorytatywny po migracji T4; startuje go OPERATOR):
CHAT_TOKENS=hub.tokens.json CHAT_PORT=8766 \
  CHAT_DATA=chat-data/dogfood-842b71a python -m chat.server
# UWAGA: CHAT_DATA musi wskazywać AKTYWNY data_dir huba (dziś:
# chat-data/dogfood-842b71a — trwałe kursory klientów są z nim związane;
# inny katalog = pusty split-brain hub odrzucający istniejące kursory)

# klient (token z pliku tokenów huba):
CHAT_PORT=8766 CHAT_TOKEN=<token> python3 send.py beta "tekst"   # wyślij
CHAT_PORT=8766 CHAT_NICK=beta CHAT_TOKEN=<token> \
  python3 send.py --listen                  # resumowalny nasłuch (kursor)
CHAT_PORT=8766 CHAT_NICK=beta CHAT_TOKEN=<token> \
  python3 send.py --heartbeat t1            # procesik lease przy claimie
```

Tokeny: skopiuj `hub.tokens.example.json` → `hub.tokens.json` (0600,
poza gitem) i podmień sekrety. Klient trzyma trwały kursor per hub+nick
w `~/.chat-sessions/` — restart wznawia od ostatniej zastosowanej
ramki. Gwarancja: at-least-once + tłumienie duplikatów po `seq`
i `activation_id` w adapterze (nie „exactly-once" — patrz wsad B2).

TUI human-operatora (Textual; czyta jedynego humana z `hub.tokens.json`,
kursor/lock jak każdy klient — patrz `tui.py`):

```bash
uv run --quiet --with textual --with websockets python3 tui.py
```

Trzy panele: czat (wysyłka po Enter), uczestnicy z grupami, rules/stan.
Komenda `/groups <nick> <g1,g2>` wysyła `membership_set` (autoryzacja:
human albo członek bieżącego `$admin`); `/groups <nick> -` czyści grupy.

Tryb HISTORYCZNY (archiwum PoC; hub 8765 ZATRZYMANY po T5, log w
`chat-data/migrations/20260722T202511Z-4aeba07/server-t5-final.log`):
`python3 send.py --legacy <nick> "tekst"` / `--legacy --listen`.

Testy (B1, branch `b1-serwer`):

```bash
uv run --quiet --with pytest --with websockets --with textual python -m pytest tests/ -v
```

## Zdalny hub (Tailscale)

Domyślnie hub słucha tylko na `127.0.0.1` — dogfood na jednej maszynie.
Agenci na innych komputerach (VPS, laptop kolegi) dołączają przez
tailnet: zero własnego relaya, ruch idzie szyfrowanym tunelem
WireGuardowym Tailscale.

**1. Zainstaluj i zaloguj Tailscale na hubie** (raz):

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
tailscale ip -4        # adres tailnetu huba, np. 100.x.y.z
```

**2. Odpal hub bindowany na adres tailnetu:**

```bash
agentmachi serve --name hub --bind 100.x.y.z
# albo bez CLI agentmachi, bezpośrednio na chat/server.py:
CHAT_BIND=100.x.y.z CHAT_PORT=8766 CHAT_TOKENS=hub.tokens.json \
  python -m chat.server
# albo na wszystkie interfejsy (prościej, wciąż tylko w obrębie tailnetu
# jeśli firewall blokuje LAN/internet):
agentmachi serve --name hub --bind 0.0.0.0
```

Karta wypisze gotowe komendy z `CHAT_URL=ws://100.x.y.z:8766` — wklej
je agentowi na drugiej maszynie (Tailscale musi tam też być zalogowane,
`tailscale up`, żeby adres `100.x.y.z` się rozwiązywał).

**3. Alternatywa — `tailscale serve`** (bez zmiany bindu huba, hub
zostaje na `127.0.0.1`, Tailscale robi reverse-proxy w obrębie tailnetu):

```bash
tailscale serve --bg --tcp=8766 tcp://127.0.0.1:8766
```

**4. Fallback bez Tailscale — Cloudflare Tunnel (`wss://` przez internet):**

Gdy druga strona nie może zainstalować Tailscale (np. tylko przeglądarka
API/CI), wystaw hub publicznie przez Cloudflare, bez własnego serwera
proxy:

```bash
cloudflared tunnel --url ws://127.0.0.1:8766
# cloudflared wypisze https://<losowa-nazwa>.trycloudflare.com —
# klient łączy się przez wss:// na tym samym hoście:
CHAT_URL=wss://<losowa-nazwa>.trycloudflare.com CHAT_TOKEN=<token> \
  python3 send.py beta "tekst"
```

Zero własnego relaya w obu wariantach — Tailscale/Cloudflare tunelują,
hub (`chat/server.py`) nie wie, że łączą się spoza `localhost`.

## Struktura

```
chat/                  hub B1: protocol, store, identity, tasks, server,
                       client_session (kanał autorytatywny)
send.py                klient B1 (resumowalny) + tryb --legacy (archiwum)
server.py              PoC A (historyczny broadcast, zatrzymany po T5)
tests/                 pytest B1
test_chat.py           testy PoC A (historyczne)
docs/superpowers/      spec + plan
```
