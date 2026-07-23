# B6: Wejście bez tokenu — tożsamość oparta na sieci

Data: 2026-07-23. Autor projektu: worker2. Review: worker1 (orchestrator).
Zlecenie: @Emil — „każdy może połączyć się do serwera, otwarty dostęp, bo
i tak musisz dodać kompa przez tailscale.com, więc to na niego zrzucam
bezpieczeństwo".

## Problem

Dołączenie agenta ma dziś cztery kroki, z czego **dwa dotyczą tokenu**:
wypisz go na maszynie huba, przenieś, wklej do promptu. Sekret ląduje
w promptach, historii powłoki i wiadomościach na kanale. To najgorszy
fragment naszej własnej instrukcji — dyktowaliśmy go człowiekowi ręcznie.

## Rozróżnienie, które decyduje o kształcie (worker1)

Token pełni dziś **dwie różne funkcje**, a Tailscale zastępuje tylko jedną:

| funkcja | czy tailnet ją załatwia |
|---|---|
| (a) „czy **możesz** wejść" | **tak** — do huba dosięgnie tylko maszyna w tailnecie |
| (b) „**kim** jesteś" | **nie** — tailnet nie wie, że jesteś `worker1` |

Otwarty dostęp bez rozwiązania (b) zamienia pomyłkę w cichą kradzież
tożsamości: każdy wchodzi jako `worker1` i wypiera prawdziwego, który
staje się widmem — czyli awaria, którą tępiliśmy dziś pół dnia (F3).

## Projekt

### 1. Tryb otwarty jest związany z bindem, nie z flagą

- bind na **loopback** albo **adres tailnetowy** (`100.64.0.0/10`,
  `fd7a:115c:a1e0::/48`) → `hello` bez tokenu jest przyjmowane,
- bind na **`0.0.0.0`** → hub stoi też na LAN i interfejsie publicznym;
  token pozostaje **jedyną** ochroną, więc tryb otwarty jest **odmawiany**
  z wyjaśnieniem, a nie po cichu wyłączany.

Uzasadnienie (fizyka, nie polityka): kto może dotknąć portu, ten już
przeszedł uwierzytelnienie sieci. Gdy port jest osiągalny dla wszystkich,
przesłanka znika i mechanizm musi się wyłączyć sam.

### 2. Nick przydziela hub, nie człowiek

`hello` bez tokenu z polem `nick` (propozycja agenta, opcjonalna):

- nick **wolny** → dostajesz go,
- nick **zajęty przez żywe połączenie** → **odmowa**, hub proponuje wolny,
- brak propozycji → hub przydziela pierwszy wolny `worker<N>`.

Przydzielony nick wraca w odpowiedzi `hello` (pole `from`) — agent
dowiaduje się, kim jest, zamiast to deklarować.

### 3. Takeover tylko dla własnego `instance_id`

To jest odpowiedź na zastrzeżenie (b) i jedyne miejsce, gdzie ten projekt
dotyka istniejącej mechaniki:

- `hello` na zajęty nick z **tym samym `instance_id`** → takeover jak
  dotąd (to twój własny reconnect po padzie sieci; bez tego agent nie
  wróciłby na swój nick, dopóki stary socket nie umrze na timeoucie TCP),
- `hello` na zajęty nick z **innym `instance_id`** → **odmowa** z
  propozycją wolnego nicka; dotychczasowy uczestnik zostaje nietknięty.

W trybie z tokenem zachowanie **bez zmian** (token dowodzi tożsamości, więc
takeover jest legalny).

### 4. `tokens.json` zostaje

Nie kasujemy mechanizmu — przestaje być obowiązkowy. Hub publiczny
(`0.0.0.0`, tunel) działa jak dotąd.

## Ryzyko — zapisane jawnie, nie przemilczane

W trybie otwartym **tożsamość jest słaba**: `instance_id` podaje klient,
więc uczestnik tailnetu może je podrobić i przejąć cudzy nick. Ten projekt
chroni przed **pomyłką i kolizją**, nie przed złośliwym uczestnikiem.

Przesłanka, na którą godzi się operator: **tailnet jest zaufany** — kto
w nim jest, został tam wpuszczony świadomie. Gdy przestanie być zaufany,
wracasz do tokenów: `agentmachi start --bind 0.0.0.0` je wymusza.

To zdanie musi trafić do `README` i `howto`, żeby nikt nie uznał, że hub
w trybie otwartym daje gwarancje, których nie daje.

## Efekt dla człowieka (cel zlecenia)

```
agentmachi start --name pokoj
→ adres + JEDNO zdanie do wklejenia agentowi, bez tokenu

w Claude Code / Codex:  "dolacz do agentmachi ws://100.x.y.z:8767"
→ agent wchodzi i SAM dostaje nick
```

Z czterech kroków zostają dwa, a sekret nie pojawia się nigdzie.

## Podział

- **worker2**: serwer — walidacja hello bez tokenu, przydział nicka,
  zmiana reguły takeoveru, testy.
- **worker1**: review projektu (przed kodem) + skill/komenda po stronie
  CC i Codeksa, gdy serwer będzie gotowy.

## Stan

- [x] projekt spisany (ten plik)
- [ ] review orchestratora — **przed** implementacją
- [ ] implementacja serwera
- [ ] skill + komenda dla człowieka
- [ ] dogfood: trzeci agent wchodzi bez tokenu
