# B6: Wejście bez tokenu — tożsamość na sieci, moderacja u człowieka

Data: 2026-07-23. Projekt: worker2. Review: worker1 (orchestrator, 4 zastrzeżenia — wszystkie uwzględnione).
Decyzje operatora (@Emil): **tokeny tylko dla człowieka**; **wpuszczamy
wszystkich, człowiek wyrzuca** (opcja B — poparta też przez worker1 dowodem
z dogfoodu: przez większość dnia człowieka nie było przy komputerze,
a agenci pracowali; poczekalnia zablokowałaby każde wejście po restarcie).

## Problem

Dołączenie agenta ma dziś cztery kroki, z czego **dwa dotyczą tokenu**.
Sekret ląduje w promptach, historii powłoki i wiadomościach na kanale.

## Rozróżnienie, które decyduje o kształcie (worker1)

Token pełni dwie funkcje, a Tailscale zastępuje tylko jedną:

| funkcja | czy tailnet ją załatwia |
|---|---|
| (a) „czy **możesz** wejść" | **tak** — do huba dosięgnie tylko maszyna z tailnetu |
| (b) „**kim** jesteś" | **nie** |

Odpowiedzią na (b) nie jest kryptografia, tylko **człowiek z tokenem**:
wpuszczamy wszystkich, moderator wyrzuca. Tożsamość potwierdza ktoś, kto
wie — zamiast wywodzić ją z adresu albo z sekretu do przepisania.

## Projekt

### 1. Tryb otwarty jest związany z bindem, nie z flagą

- bind na **loopback** albo **adres tailnetowy** (`100.64.0.0/10`,
  `fd7a:115c:a1e0::/48`) → `hello` agenta **bez tokenu** jest przyjmowane,
- bind na **`0.0.0.0`** → hub stoi też na LAN i publicznie; token wraca
  jako wymóg dla wszystkich, bo sieć przestała być bramką.

Kto może dotknąć portu, ten już przeszedł uwierzytelnienie sieci. Gdy port
jest osiągalny dla wszystkich, przesłanka znika i mechanizm wyłącza się sam.

### 2. Człowiek ZAWSZE z tokenem

Rola `human` wymaga tokenu z `tokens.json` **niezależnie od bindu**. To
jedyna rzecz warta ochrony: bez tego dowolny uczestnik tailnetu wszedłby
jako moderator i wyrzucał pozostałych. `tokens.json` przestaje być
obowiązkowy dla agentów, ale nigdy dla ludzi.

### 3. Rola i grupy agenta bez tokenu — jawnie (zastrzeżenie [1])

Wchodząc bez tokenu dostajesz `role="agent"` i `groups=["workers"]`.

Bez tego agent byłby technicznie na kanale i praktycznie głuchy: `$workers`
by go nie obudziło, bo wzmianki grupowe idą po grupach. Domyślna grupa jest
warunkiem tego, żeby wejście w ogóle miało sens.

### 4. Nick: wolny bierzesz, zajętego nie odbierasz (zastrzeżenia [2] i [3])

- nick **wolny** → dostajesz go,
- nick **zajęty przez żywe połączenie** → odmowa + propozycja wolnego
  (`worker3`, `worker4`…); dotychczasowy uczestnik zostaje nietknięty,
- brak propozycji nicka → hub przydziela pierwszy wolny.

**Czym jest „żywe połączenie" — definicja, bez której to nie działa.**
Zastrzeżenie [2] było trafne: rano socket agenta wisiał `ESTAB` na trupim
hubie i z punktu widzenia serwera wyglądał żywo. Rozwiązanie jest już
w bibliotece: `websockets.serve` domyślnie pinguje co 20 s i zamyka
połączenie po 20 s bez odpowiedzi. Martwy socket **wypada sam w ~40 s**,
więc „zajęty" znaczy „zajęty naprawdę". Ustawiamy te wartości jawnie
w wywołaniu `serve`, żeby nikt ich przypadkiem nie zmienił.

**Dlaczego znika `instance_id` z reguły takeoveru (zastrzeżenie [3]).**
Poprzednia wersja projektu pozwalała wyprzeć własny nick, jeśli `instance_id`
się zgadza. Zastrzeżenie było celne: `instance_id` żyje w
`~/.chat-sessions/`, więc świeża sesja, inna maszyna albo czysty kontener
dostają nowy — i **własny powrót zostałby odmówiony**. Dokładnie tak
wyglądał dzisiejszy przypadek worker1. Skoro martwe sockety wypadają same,
reguła jest niepotrzebna: agent po padzie wraca na swój nick, gdy tylko
trup zniknie (≤40 s), bez rozpoznawania „czy to ja".

W trybie z tokenem takeover działa jak dotąd — token dowodzi tożsamości.

### 5. Moderacja: człowiek wyrzuca (zastrzeżenie [4])

Ramka `kick` od uczestnika o roli `human`: hub rozłącza wskazany nick
i zapisuje trwały fakt na kanale (jak `takeover` — inni widzą, co się
stało, zamiast zgadywać, dlaczego ktoś zamilkł).

Hub **nie rozstrzyga sporów o nick** — od tego jest człowiek. Jeśli ktoś
wejdzie jako `worker4` i zachowa się nie tak, moderator go wyrzuca; nie
próbujemy tego wykryć automatycznie.

## Ryzyko — zapisane jawnie, nie przemilczane

W trybie otwartym **tożsamość agenta jest słaba**: nick nie jest niczym
zabezpieczony poza tym, że zajętego nie da się odebrać. Uczestnik tailnetu
może wejść pod dowolnym wolnym nickiem i podawać się za kogo chce. Ten
projekt chroni przed **pomyłką i kolizją**, nie przed złośliwym uczestnikiem.

Przesłanka operatora: **tailnet jest zaufany** — kto w nim jest, został
wpuszczony świadomie, a moderator patrzy. Gdy przestanie być zaufany:
`agentmachi start --bind 0.0.0.0` przywraca tokeny dla wszystkich.

To zdanie trafia do `README` i `howto`.

## Efekt dla człowieka (cel zlecenia)

```
agentmachi start --name pokoj
→ adres + JEDNO zdanie do wklejenia agentowi, bez tokenu

agent:  "dolacz do agentmachi ws://100.x.y.z:8767"
→ wchodzi, sam dostaje nick, od razu pracuje

ty w TUI: widzisz każde wejście, jednym klawiszem wyrzucasz
```

Z czterech kroków zostają dwa, a sekret nie pojawia się nigdzie poza
twoim własnym logowaniem do TUI.

## Podział

- **worker2**: serwer — hello bez tokenu, rola/grupy domyślne, przydział
  nicka, jawny keepalive, ramka `kick`, testy.
- **worker1**: TUI (lista + klawisz wyrzucania + sygnał „nowy wszedł")
  oraz review serwera.

## Stan

- [x] projekt spisany
- [x] review orchestratora — 4 zastrzeżenia, wszystkie uwzględnione
- [x] decyzje operatora: tokeny tylko dla człowieka; wpuszczamy wszystkich
- [ ] implementacja serwera (worker2)
- [ ] TUI z moderacją (worker1)
- [ ] dogfood: trzeci agent wchodzi bez tokenu
