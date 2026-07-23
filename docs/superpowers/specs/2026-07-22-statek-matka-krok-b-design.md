> **SUPERSEDED (2026-07-23):** koncepcję dedykowanego orkiestratora i
> automatycznego schedulera tasków zastępuje plan
> `docs/superpowers/plans/2026-07-23-b3-siec-dla-agentow.md`
> (fizyka w hubie, zachowania w rules.md + rozmowie). Scheduler z B1
> zamrożony pod tagiem `b1-workflow-engine`, cięcie w zadaniu 7.

# agents_chat — krok B: statek matka i rój wyrobnic

Data: 2026-07-22.
**ADNOTACJA 2026-07-23 (po praktyce B1):** koncepcja dedykowanego
orkiestratora ("matka nie koduje") ZASTĄPIONA płynnymi grupami +
rules.md — hierarchia to tekst w rules ("kto jest przed kim"), funkcje
(head/review/worker) zmieniane w locie przez membership_set. Hub jest
infrastrukturą (kolejka/log/lease), nie szefem. Decyzja Emila,
potwierdzona całym przebiegiem B1.
Status: projekt po brainstormingu (kontynuacja PoC A — zaliczony 2026-07-22)

## Wizja

Multiplayer dla ludzi i agentów: jeden komp jest **statkiem matką** (hub,
źródło prawdy, orkiestracja), zewnętrzne sesje Claude Code na osobnych
kontach dołączają jako **wyrobnice** i wykonują taski. Tokeny lecą
równolegle z wielu subskrypcji na jeden projekt. Człowiek uczestniczy
przez czat i TUI.

## Scenariusz nadrzędny (north-star UX — @Emil)

Człowiek uruchamia osobny hub+TUI. Potem na dowolnym komputerze odpala
Claude Code albo Codex i mówi NATURALNIE: „dołącz do serwera xyz jako
@codex z $worker, przedstaw się". Skill agenta ukrywa całą mechanikę:
join/hello, pobranie rules.md do kontekstu, agent card, uzbrojenie
nasłuchu. Operator w TUI od razu widzi: kto dołączył (nick, rola), jakie
rules załadował, status/presence, rozmowę i zdarzenia pokoju.

Publiczny interfejs = polecenie w języku naturalnym + skill. Adresy,
enrollment, token, instance_id, reconnect, ACK — wewnętrzna hydraulika.
**Projekt i plan oceniamy end-to-end względem dokładnie tego scenariusza.**

Domknięcia (beta): agent card w hello niesie `rules_hash` ZAŁADOWANYCH
rules (TUI musi widzieć, na jakiej wersji zasad agent pracuje); bramka
akceptacji B2/B4 to test E2E będący dosłownie powyższym zdaniem —
oceniamy scenariusz, nie checklistę ficzerów.

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

Matka jest **restartowalna bezstratnie**: cały jej stan operacyjny żyje
poza sesją (BRIEF.md, kolejka na serwerze, graf, git) — sesja matki może
paść lub zostać ubita w dowolnym momencie, a świeża sesja po
`/statekmatka:init` wykrywa istniejący hub (działający serwer, BRIEF)
i robi resume zamiast ponownej inicjalizacji. Długowieczna sesja matki
to optymalizacja, nie wymóg — kompaktacja kontekstu nie może niczego
zgubić, bo prawda leży na dysku.

Hub (serwer WS + graphify serve) odpala CZŁOWIEK jako osobny proces
(sekcja "Role i autoryzacja"). `/statekmatka:init` robi resztę:
1. enrolluje sesję jako admin (kod z ukrytego promptu → agent_id + token),
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
usuwa problem echa), `chat`, `task_new`, `task_offer`, `task_claim`,
`task_done`, `task_blocked` (andon), `review_changes` (uwagi z review →
budzi assignee), `status` (idle | working(co) | blocked(na co) |
waiting_review | offline), `fyi` (bez budzenia — tylko do loga),
`backlog` (zaległości przy obudzeniu).

Przydział bez thundering herd: `task_new` NIE jest broadcastem — serwer
wysyła `task_offer` do JEDNEJ idle wyrobnicy (round-robin). Brak
`task_claim` w oknie claim-offer-timeout → oferta idzie do następnej.

### Tożsamość i niezawodność (ustalenia tercetu alfa+beta+codex, do B1)

**Inwariant ogólny (beta)**: pola autorytatywne (`seq`, `generation`,
`groups`, `from`) nadaje wyłącznie serwer; wartości z ramek klienta są
wejściem do walidacji, nigdy źródłem prawdy. Generation jest przypinana
do SOCKETU po hello — nigdy czytana z `frame.get()`.

- **Tożsamość logiczna ≠ socket**: `hello` niesie nick + trwałe
  `client_instance_id` (plik sesji obok mechaniki heartbeatu; send.py
  czyta z niego). Wiele socketów tego samego nick+instance współdzieli
  `generation`; reconnect tej samej instancji NIE podbija generation;
  przejęcie nicku przez nowe instance_id podbija ją i unieważnia starą
  sesję (mutacje ze starą generation → reject). Echo tłumione po NICKU
  (wszystkie sockety logicznego nadawcy), nie po sockecie.
- **Mutacje tasków**: każda komenda niesie `command_id` (deduplikacja,
  at-least-once) oraz `expected_task_version` (CAS); serwer po sukcesie
  inkrementuje `task_version`. Sam `(task_id, generation)` jest za gruby
  (done po changes_requested zlałoby się z pierwszym done).
- **Backlog z gwarancją**: monotoniczny `room_seq` per pokój, log zdarzeń
  trwały (przeżywa restart serwera) z retencją — okno/kompakcja po TTL.
  `hello` niesie `last_seq`, serwer odtwarza nowsze. Klient zapisuje
  `last_applied_seq` dopiero PO przetworzeniu ramki, nie po odebraniu.
- **Resume poza oknem retencji — jawny, nigdy cichy**: serwer trzyma
  `earliest_seq` i `snapshot_seq`; gdy `last_seq < earliest_seq`,
  odpowiada `resync_required` (nigdy partial replay wyglądający jak pusty
  backlog). Klient pobiera wtedy spójny snapshot żywego stanu huba
  (kolejka, lease'y, statusy) oznaczony `snapshot_seq`, stosuje atomowo,
  zapisuje `last_applied_seq = snapshot_seq`, potem odtwarza eventy
  nowsze. BRIEF+git to kontekst wiedzy — nie zastępują snapshotu żywego
  stanu. Kolejność trwałości: przy kompakcji najpierw zapis/rename
  snapshotu, potem usunięcie przykrytych eventów; przy mutacji najpierw
  trwały event/stan, potem publikacja i odpowiedź.
- **Retencja `command_id`** ≥ maksymalny czas retry/życia taska (stara
  komenda nie może stać się "nowa" po wygaśnięciu dedupu);
  `expected_task_version` stanowi drugą barierę.
- **Auth agenta**: token per agent (tailscale ogranicza sieć, ale nie
  chroni nicku przed innym peerem w tailnecie). Szczegóły wydawania —
  sekcja "Role i autoryzacja".

### Grupy adresowe — config-first (korekta @Emil: LESS IS MORE)

**"Slack dla agentów"** — to jest kalibracja całości: pokoje, wzmianki,
grupy, presence, człowiek przez TUI. Warstwa adresowa prosta jak drut;
taski/lease/resume to "aplikacje w Slacku", nie fundament.

**Hub jest osobnym bytem odpalanym przez człowieka** (`cowork_agents_4_all
<sesja> --continue`), nie przez sesję matki. Matka = zwykły restartowalny
klient. Człowiek/TUI to operator huba: tylko on zmienia config.

**Role = ALIASY GRUPOWE w mechanice wzmianek, nie uprawnienia.**
`$admin == @alfa`, `$workers == @codex + @beta`; wzmianka `$workers`
budzi całą grupę jednym słowem. Kontrakt: agent card niesie `groups`;
parser wzmianek rozpoznaje `@nick`, `$group`, `@all`; `$group` rozwija
się do AKTUALNYCH członków; membership przeżywa reconnect; nieznana
grupa → jawny błąd, nigdy cichy broadcast. Serwer pilnuje wyłącznie
poprawności maszyny stanów tasków — legalność komend NIE zależy od
grupy. Miękkie ograniczenia zachowania żyją w rules.md i skillach.
(Permission matrix/RBAC: future consideration, jedno zdanie, wraca
tylko jeśli realnie zaboli.)

**Config huba (`hub.toml`)** — źródło prawdy, pisane ręcznie przez usera:
kody grup (enrollment; przypisują do grupy adresowej), definicje grup,
wskazanie rules.md. Plik: chmod 600, w .gitignore; w repo tylko
`hub.toml.example`. Sekret enrollment przez stdin/env — NIGDY argv
(historia shella) i nigdy do room-logu. Token per agent zostaje dla
tożsamości/reconnect (instance_id/generation bez zmian) — nie daje
żadnych uprawnień.

**Rules — finalna prostota (korekta @Emil)**: miękkie zasady żyją w
osobnym pliku `rules.md` przy hubie. Hello/karta wejściowa wskazuje plik
albo zwraca jego treść; skill agenta czyta aktualną wersję przy
join/resume, wprowadza do kontekstu i respektuje. Serwer NIE
interpretuje rules, NIE wiąże ich z permission matrix, żadnego
`rules_stale` w protokole. Opcjonalny hash służy wyłącznie wykrywaniu
zmiany/cache. Rules zmienia wyłącznie lokalny człowiek (plik); czat ani
agent-admin nie mogą ich nadpisać; adapter podaje je modelowi zawsze
PONIŻEJ hierarchii system/safety harnessa. BRIEF co najwyżej linkuje do
rules.md — nie kopiuje.

**Granice (codex)**: hub.toml NIE przechowuje wydanych tokenów ani żywego
stanu kolejki (osobny trwały registry/state). Reload configu atomowy,
last-known-good: błąd TOML nie zeruje uprawnień, tylko odrzuca reload
i alarmuje TUI.
- Świadomie przesunięte: jeden trwały socket na klienta (B2), pełne
  fencing tokeny i per-frame ACK (dopiero gdy skala/bugi zażądają — YAGNI).

### Budzenie agentów nie-Claude (wkład codexa; envelope w B1, adapter w B2)

Monitor(ws) to prywatna funkcja Claude Code — protokół nie może od niej
zależeć. Przenośny kontrakt budzenia:

- `chat wait --nick N --instance ID --after SEQ` — blokujący, zero-tokenowy
  proces: robi reconnect/resume sam, kończy się dopiero na wzmiankę
  (`@nick`/`@all`/task_offer) i zwraca **activation envelope** (JSON):
  `activation_id`, zakres `room_seq`, backlog, wyzwalająca wzmianka.
- Supervisor (sidecar poza modelem) po zakończeniu `wait` wznawia model
  (Codex: app-server/SDK/exec), podaje envelope jako input, streamuje
  odpowiedź na czat, zapisuje `last_applied_seq` dopiero PO zakończeniu
  tury, po czym znów odpala `wait`.
- Inwarianty adaptera: jedno aktywne wybudzenie na `client_instance_id`;
  wzmianki nadchodzące w trakcie pracy trafiają do kolejki (steer), nie
  odpalają drugiej instancji; `activation_id` idempotentne; rozłączenie WS
  nie gubi kursora.

B1 definiuje envelope i semantykę ACK/resume (protokół); implementacja
adaptera Codex — B2. Claude'owy Monitor staje się wtedy tylko jednym
z możliwych adapterów.

### Konwencja wzmianek

`@nick` adresuje uczestnika (tylko wzmianka budzi śpiącego agenta),
`$group` budzi wszystkich AKTUALNYCH członków grupy (jedno słowo — cała
grupa), `@all` budzi wszystkich, `@Emil`/`@<human>` — człowiek jest
adresowalny tak samo jak agenci. Nieznana grupa → jawny błąd do nadawcy.

Zasady uwagi (ekonomia tokenów): serwer budzi agenta wyłącznie ramkami
zaadresowanymi do niego (`to` lub `@nick` w treści chatu) oraz taskami
z kolejki (gdy idle). Chat bez wzmianki i `fyi` nie budzą nikogo — lądują
w logu pokoju, agent czyta zaległości hurtowo przy najbliższym własnym
obudzeniu (serwer wysyła wtedy `backlog` z pominiętymi ramkami).
Wyrobnice nie mają DM między sobą (obserwowalność); DM tylko człowiek→agent.

Odporność połączenia: Monitor zgłasza zamknięcie socketa — klient MA
OBOWIĄZEK wejść wtedy w pętlę reconnect (backoff), ponowić hello i pobrać
backlog. Śpiący klient bez uzbrojonego Monitora to stan zabroniony.

## Kolejka tasków

Na serwerze, w pamięci + zrzut do JSON (restart nie gubi kolejki).

Stany taska: open → claimed → review → done, z odnogami:
- review → **changes_requested** → claimed (u TEGO SAMEGO assignee,
  lease zachowany — kontekst taska jest już w jego głowie; ramka
  `review_changes` budzi go z uwagami),
- claimed → **blocked** (andon): TTL lease ZAMROŻONY, task zaparkowany
  poza WIP limitem; po max czasie parkowania andon eskaluje do człowieka
  ponownie zamiast wisieć w ciszy.

**Karta taska** (minimum, żeby nie prowokować andon-spamu): cel, kryteria
akceptacji, komenda weryfikacji (test), pliki best-effort, hash HEAD
i hash BRIEF.md z chwili przydziału (wyrobnica wie, czy robić pull).

**Lease z TTL**: heartbeat odnawia proces w tle odpalany przy claim
(background bash u wyrobnicy), ubijany przy done. Proces co tick sprawdza,
czy sesja-rodzic żyje (PPID) — rodzic martwy → self-kill → lease wygasa
naturalnie (brak zombie-claimów). Sesja pada → task wraca do open.
Claim przeżywa reconnect z tym samym nickiem w oknie TTL.
Zamrożenie/rozmrożenie TTL egzekwuje SERWER (klient tylko raportuje stan);
w waiting_review i parked heartbeat klienta również się ubija —
rodzic-check pokrywa oba przypadki.

**WIP limit**: kolejka nie wydaje więcej tasków naraz, niż wynosi
przepustowość review (konfigurowalne, default = 2× liczba wyrobnic
w review + 1). Matka może delegować review wyrobnicy (peer review);
bramka merge zawsze u matki.

Semafor plikowy: best-effort — task może deklarować pliki i serwer nie
wyda dwóch tasków z przecięciem, ale pliki często znane są dopiero
w trakcie; ostatecznym rozjemcą konfliktów jest git na merge'u.

### Prawo edycji kodu — dwa rozdzielne kanały (pytanie @Emil, konsensus)

**INWARIANT: credential czatu (WS-token) NIGDY nie nadaje prawa zapisu
repo. Osobny credential Git zatwierdza wyłącznie operator huba.**

- Czat/taski/presence: WS + token z enrollment (jak wyżej).
- Dostawa kodu: git push przez SSH na maszynę huba. Default: tailscale
  ogranicza TYLKO sieć; na hubie zwykły OpenSSH + dedykowany user git.
  Skill wyrobnicy generuje klucz ed25519 per hub (prywatny nie opuszcza
  maszyny), pubkey+fingerprint idzie uwierzytelnionym WS w agent card;
  operator akceptuje w TUI → wpis do authorized_keys z `restrict` +
  forced-command do git-gate (tylko upload-pack/receive-pack, pre-receive
  blokuje main, opcjonalnie namespace per worker). Audyt: który agent
  wypchnął co; zero shell access.
- Tailscale SSH — wariant opcjonalny dla zaufanych maszyn jednoosobowych
  (omija authorized_keys, więc traci forced-command; sprawdzone w docs).
- Zakres: B2 (klucz w skillu) / B3 (sieć) / B4 (approve/revoke w TUI);
  B1 tylko ten inwariant.

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

1. **B1 — serwer**: pokoje, hello z instance_id/generation, typowane
   ramki, zasady budzenia i wzmianek, tłumienie echa po nicku, kolejka
   tasków z lease + CAS (command_id, task_version) + zrzut JSON, room_seq
   z trwałym logiem i retencją, resume z last_seq, tokeny agentów.
   Testy pytest (rozbudowa test_chat.py) pisane RAZEM z kodem (warunek
   bety i codexa). **Bramka akceptacji B1** (testy inwariantów, nie tylko
   happy-path): stare generation odrzucone; command_id deduplikowane;
   błędny expected_task_version → konflikt bez mutacji; reconnect
   odtwarza od last_applied_seq; zbyt stary kursor → resync_required
   ze spójnym snapshotem; duplikat activation_id nie uruchamia drugiej
   pracy; task_offer timeout przechodzi do następnej wyrobnicy;
   wygaśnięcie lease przywraca task dokładnie raz.
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
