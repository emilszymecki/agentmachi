# Spike TUI — czy żywą sesję da się obudzić z zewnątrz (2026-09-02)

**HEAD:** `a58ffc2` — commit zapisujący ten plik, **proxy, nie HEAD
przebiegu**. Ten sam powód co wyżej: przebieg szedł na kanale `interwizja`, a
jego log skasowano 2026-09-03.

Zlecenie człowieka: *„ZNANY BRAK — żywej sesji nikt nie obudzi. Trzech agentów,
trzy niezależne drogi (hooki harnessu, wstrzyknięcie do terminala, kanał
notyfikacji), każdy w swoim workspace, bez podglądania; spotkanie dopiero
z wynikami. Wynik: mechanizm albo udokumentowana niemożliwość z trzech stron."*

Badane twierdzenie stoi w [`../zasady-agentyczne.md`](../zasady-agentyczne.md):
**„żywej sesji TUI nie obudzi nikt z zewnątrz"**.

**Wynik: twierdzenie jest FAŁSZYWE na wersjach zmierzonych dzisiaj.** Droga C
osiągnęła to, co dokument uznaje za niemożliwe, i zostało to zreplikowane
niezależnie. Dokument opisuje codex 0.145.0; pomiar robiono na Claude 2.1.258
i codex 0.149.1.

## Metoda

Trzy drogi, każda badana przez osobnego agenta we własnym worktree, bez
dostępu do pozostałych. **Dispatch i weryfikację prowadziły różne osoby** —
`agent4` odpalał, `agent1` weryfikował i pisze ten zapis. Powód jest z reguły
14 tego repo („autor nie zwaliduje własnego pokrycia"): kto odpala trzy drogi,
nie powinien też orzekać, że niemożliwość jest udokumentowana z trzech stron.

### Odstępstwo od standardu tego katalogu — do protokołu

[`README.md`](README.md) wymaga prerejestracji **w commicie wcześniejszym niż
pierwsza ramka przebiegu**; timestamp gita jest całym dowodem. Nasza
prerejestracja była opublikowana na kanale przed wynikami, ale **nie w
commicie** — a log huba nie jest trwały (`events.jsonl` nie wchodzi do repo,
patrz [audyt paragonów](../audyt-paragonow-2026-09-02.md)). Czyli nasz dowód
uprzedniości jest słabszy niż standard, który ten katalog sam stawia, i za
kilka dni zniknie. Zapisane tutaj jako wada przebiegu, nie jako szczegół.

## Stan kontrolny (opublikowany przed wynikami)

`node.py` budzi agenta **odpalając nowy proces**, który wznawia historię po
`session_id` (`_handle_wake` → `runtime.run` → `claude -p [--resume]`). Hub
sięga transkryptu, nigdy procesu. Stąd trzy stany, nie dwa — oś, na której
mierzone są wszystkie trzy drogi:

|stopień|kto uzbraja|przykład|
|---|---|---|
|I|operator, przed startem sesji|hook w `settings.json`, `agentmachi node`|
|II|sesja sama, o sobie, w trakcie|`agentmachi listen` uzbrojony przez agenta|
|III|nikt — sesja po prostu żyje|**badany brak**|

Weryfikator jest przypadkiem II i powiedział to przed pomiarem, żeby jego
własna reaktywność nie została wzięta za dowód, że żywa sesja jest osiągalna.

## Prerejestracja i jej jawna korekta

Kryteria „mechanizmu" ustalono przed wynikami: cel istniał wcześniej (ten sam
PID); bez wcześniejszej zgody ze środka; odbiorca cytuje losowy string
wygenerowany po jego starcie; powtarzalne komendą.

**Warunek drugi był źle postawiony i został zakwestionowany publicznie, nie
naciągnięty.** „Nic wcześniej uzbrojonego" jest niespełnialne z konstrukcji —
cokolwiek dosięgnie procesu, musi mieć po jego stronie coś, co słucha; nawet
`node` wymaga, żeby ktoś wcześniej uruchomił `agentmachi node`. Zastąpiony osią
I/II/III powyżej. **Obie wersje zostają widoczne**, żeby czytelnik wiedział, że
próg zmienił się po zobaczeniu wyniku.

Symetria progu jest jedynym powodem, dla którego cokolwiek tu znaczy: ten sam
punkt 3 **odebrał** drodze A zaliczenie przy stringu ustalonym w promptcie
i **przyznał** je po rerunie z losowym.

## Droga B — wstrzyknięcie do terminala: NIEMOŻLIWOŚĆ

Odmowa zapada w jądrze, z komunikatem:

```
TIOCSTI                  -> EIO    (dev.tty.legacy_tiocsti = 0)
ptrace                   -> EPERM  (kernel.yama.ptrace_scope = 1)
zapis do /dev/pts/N      -> idzie na WYJŚCIE, nie do kolejki wejścia
/proc/<pid>/fd/N mastera -> klonuje ptmx, wejście puste
```

Zweryfikowane niezależnie na tej maszynie (jądro 7.1.5). TIOCSTI nie jest tu
wyłączony lokalną decyzją — od 6.2 stoi za przełącznikiem domyślnie wyłączonym,
czyli to kierunek upstreamu, nie polityka do zmiany.

`tmux send-keys` działa **wyłącznie gdy TUI odpalono wewnątrz tmuxa** — to
stopień I/II, nie dosięgnięcie z zewnątrz. Ocenione z dokumentacji: tmuxa ani
screena nie ma na maszynie (potwierdzone), więc bez instalowania czegoś u
człowieka nie dało się inaczej. **Luka pomiaru, zapisana jako luka.**

Rozstrzygnięcie metodologiczne, które zostaje jako reguła: cel był atrapą
czytającą `read()` z tty, nie żywym `claude`, i **to wystarcza dla wyniku
negatywnego**, bo odmowa zapada poniżej warstwy aplikacji — jądro nie patrzy,
kto czyta. Gdyby odmowa była aplikacyjna, atrapa byłaby niewystarczająca.

Osobno: sesja weryfikatora ma `/proc/self/fd/0` → `/dev/null`. Dla takiego
harnessu droga B jest bezprzedmiotowa z innego powodu niż jądro — **nie ma tam
terminala do wstrzyknięcia.** Odkręcenie `legacy_tiocsti` niczego by nie zmieniło.

## Droga A — hooki harnessu: MECHANIZM, ale na sąsiednie pytanie

Most przez hook `Stop` (timeout 600, wisi na pliku, zwraca `decision: block`):
zapis do pliku z zewnątrz, bez klawiatury → model podejmuje nową turę w żywym
TUI. Zmierzone we własnym pty, `~/.claude/settings.json` nietknięty.

Rerun z losowym tokenem — zweryfikowany przez weryfikatora z artefaktów:

```
session_start.stamp   15:14:16.815
bridge start          15:16:29.723
token_generated_at    15:16:54.315      -> 2 min 37,5 s po starcie sesji
                                           i 24,6 s po uzbrojeniu mostu
bridge deliver        15:16:54.932      -> 25,2 s po uzbrojeniu mostu
tui.out               2 wystąpienia tokena: "Stop hook error:" i "●"
```

Punkt 3 spełniony. Droga A to **czysty stopień I** (prompt startowy jest
warunkiem stanu — `Stop` musi mieć od czego się odbić — nie aktem uzbrojenia
doręczania).

**Ale most działa wyłącznie w chwili, gdy sesja kończy turę; po zaśnięciu nie
rusza** (dowód negatywny: `FileChanged` dwa razy, zero tury). Czyli to „nie
daj zasnąć", a nie „obudź". Sam w sobie nie zamyka badanego braku.

Codex: droga zamknięta, zero zdarzeń zewnętrznych.

## Droga C — kanał notyfikacji: STOPIEŃ III OSIĄGNIĘTY

Dwa kanały inbound do żywej, **bezczynnej** sesji:

- **Claude 2.1.258** — każda sesja rejestruje `/run/user/1000/cc-socks/<pid>.sock`;
  proces zewnętrzny adresuje po nazwie, cel podejmuje pełną nową turę.
- **codex 0.149.1** — `codex queue --thread <UUID> --message`, żywy TUI ≤ 4 s.

Substrat zweryfikowany niezależnie: katalog istnieje, jedno gniazdo na sesję,
prawa 0600.

### Replikacja niezależna — to ona rozstrzyga

Weryfikator, z sesji niezwiązanej ze spike'em i bez dostępu do jego worktree,
wygenerował u siebie `openssl rand -hex 12`, **opublikował token na kanale
przed wysłaniem** i zaadresował cel po nazwie. Transkrypt celu:

```
[28] user       <cross-session-message from="uds:/run/user/1000/cc-socks/40672.sock"
                  from-name="agentmachi-86" from-mode="prompting">
                ...odpowiedz samym tokenem...: 8574166b5b88d95a5f2f4b5b
[31] assistant  8574166b5b88d95a5f2f4b5b
```

Żywa bezczynna sesja podjęła turę od zdarzenia zewnętrznego i odesłała string,
którego nie mogła znać z własnego promptu, przysłany przez nadawcę spoza
eksperymentu. **Stopień III, zreplikowany.**

### Granica, która zostaje otwarta

Nadawcą był proces harnessu (`claude -p`, a przy replikacji — druga sesja
Claude Code). Budzika w czystym Pythonie nie napisano: gniazdo jest prywatne
i wymaga `peerToken`. Czyli zmierzono **„harness dosięga żywej sesji"**, nie
„dowolny skrypt dosięga żywej sesji". To zmienia odpowiedź na pytanie *kto może
obudzić*, nie na pytanie *czy da się*.

## Koszty i ryzyka, gdyby to weszło do produktu

**Brak envelope'u — zmierzone wykonanie, nie hipoteza.** W drodze A treść
zewnętrzna ląduje jako `Stop hook error: ...`, czyli na pozycji komunikatu
**harnessu**, nie peera, i model wykonał surowy string co do znaku. `node.py`
rozwiązał ten sam problem `WAKE_PREAMBLE` + `envelope`, z komentarzem, że gołe
ramki obok envelope'u czynią oznaczenie dekoracją. Każdy most zbudowany na
tych kanałach potrzebuje envelope'u **od pierwszej linijki**, nie jako
polerowania.

**Kanał jest jednokierunkowy.** Cel odpowiedział zwykłym tekstem, a tekst nie
jest widoczny dla innych sesji — echo zobaczono wyłącznie czytając transkrypt
z dysku. Budzący nie ma jak się dowiedzieć, czy obudził.

**Skutki uboczne przebiegu** (zgłoszone przez wykonawcę na siebie i
potwierdzone): dotknięty `mtime` prawdziwego `~/.codex/queue_1.sqlite`,
transkrypt celu pozostawiony w `~/.claude/projects/`. Oba benign, oba poza
scratchpadem.

## Obserwacje o metodzie

**`grep -c` kłamie na przechwytach terminala.** `tui.out` ma 69 775 bajtów
i **zero** znaków nowej linii, więc „liczba pasujących linii" to 1 przy dwóch
wystąpieniach. To nie ciekawostka: jedno wystąpienie znaczy „treść weszła",
dwa — „treść weszła i model ją wykonał". Najprostsza komenda sprawdzająca
skasowałaby drugi fakt. Licz `grep -o | wc -l` albo `re.finditer`.

**Dwie korekty złapane przez weryfikatora, zanim weszły do zapisu.** Obie tej
samej klasy — artefakt pokazuje stan *po* zdarzeniu i wygląda na dowód zdarzenia:

- twierdzenie o cross-talku („token trafił do cudzej sesji") **nie potwierdziło
  się**: pomylono katalog roboczy sesji z jej tożsamością. Sesja nazywa się
  `spikec-echo-claude`, a `spikec-target` to jej cwd. Adresowanie po nazwie
  zadziałało poprawnie;
- jako dowód „mój cel ma mój token" wskazano transkrypt, który był **własną
  sesją nadawcy** — tam token jest z definicji.

**Inwentarz gniazd był o jedną sesję przesunięty**: `40672.sock`, przypisane
człowiekowi, należało do agenta — koperta wiadomości podaje je wprost jako
nadawcę.

**Trzy drogi były ślepe na worktree, ale dzieliły substrat.** Replikacja
weryfikatora i rerun drogi C nadawały na te same `cc-socks` do tego samego celu.
Izolacja workspace'ów nie jest izolacją kanału systemowego — i nikt tego
założenia wcześniej nie zmierzył.

## Co z tego wynika dla `zasady-agentyczne.md`

Zdanie „żywej sesji TUI nie obudzi nikt z zewnątrz" **przestało być prawdziwe**
i wymaga poprawki: droga istnieje, jest zależna od harnessu i wersji, wymaga
nadawcy będącego harnessem, nie niesie provenance i nie potwierdza doręczenia.
Zgodnie z [`README.md`](README.md) tego katalogu wynik wraca do zasad **jako
obserwacja**, nie jako nowy paragraf — poprawka zdania należy do człowieka.
