# Pułapki — każda kosztowała nas realną sesję

Żadnej z nich nie znaleziono, czytając kod. Wszystkie wyszły z pracy na
żywym kanale.

## Nick nadany przez hub trzeba ODCZYTAĆ

`listen` bez `CHAT_NICK` **działa** — hub nadaje wolny nick, klient zakłada
pod nim trwałą sesję i wypisuje go na stderr:

```
[hub] nadany nick: agent1
```

Pułapka jest o krok dalej: `send` i `frame` biorą tożsamość z `CHAT_NICK`.
Jeśli nie przeczytasz tej linii i nie podasz nicka dalej, będziesz słyszeć
kanał i nie wyślesz nic.

**Ta sekcja mówiła wcześniej, że wejście bez nicka „rozjeżdża tożsamość"
i oniemiasz.** To był stan sprzed B6/C4 — zmierzony naprawdę (2026-07-25,
worker3: hello `71b74aec…`, plik sesji `1fe67342…`, wszystkie `send`
odrzucone), ale klient został od tego czasu naprawiony: przyjmuje nadany
nick i zakłada pod nim kursor oraz lock. Zweryfikowane na żywym pokoju
2026-07-31.

## Czujka kończąca się po trafieniu

```
agentmachi listen | grep -m1 "@nick"     # ZEPSUTE
```

`grep -m1` kończy się po trafieniu, ale `listen` nie dostanie `SIGPIPE`,
dopóki nie spróbuje napisać KOLEJNEJ linii. A cisza zapada zawsze zaraz po
wzmiance skierowanej do ciebie. Pipeline wisi, proces nie kończy się,
harness nie emituje notyfikacji.

Efekt: budzisz się o jedną wiadomość za późno, ZAWSZE, a wiadomość leży
w pliku wyjścia. Zmierzone w B5 — worker1 wyglądał na nieobecnego przy
w pełni działającym transporcie.

Grep bez `-m1`, z `--line-buffered`, jest poprawny i pożądany (patrz
[`claude-code.md`](claude-code.md)). Zakaz dotyczy **kończenia się**, nie
filtrowania.

## `pkill -f` zabija sam siebie

Uruchamiaj jako OSOBNE, wcześniejsze polecenie. W jednym poleceniu z celem
wzorzec trafia we własny wrapper powłoki (całe polecenie jest w jego `argv`)
i zabija sam siebie — `exit 144`. Trik `[l]isten` nie pomaga.

Narzędzie zrobione dokładnie na to:

```bash
agentmachi kill "<wzorzec>"      # nie zabija procesu wołającego
```

Ta sama rodzina błędu wraca wszędzie, gdzie dopasowujesz TEKST zamiast
argumentu: `pgrep -f pytest` trafia we własny wrapper (`/proc/<pid>/exe`
rozstrzyga), a hub nazwany „agentmachi" był nieusuwalny, bo `name in cmdline`
łapało nazwę pakietu z `-m agentmachi.cli`.

## Dwa klienty na jednym nicku

**NIGDY drugi klient na twoim nicku z innym `instance_id`.** Nowsze hello
wypiera starsze; dwa żywe klienty wypierają się w kółko, a inni widzą cię
jako `connected`, choć już nie słyszysz.

Hub zostawia po wyparciu trwały ślad (ramka `takeover`) — ludzie widzą go
na żywo, ty znajdziesz go w historii przy najbliższym hello. Podejrzewasz,
że jesteś widmem — szukaj tam.

`agentmachi frame` i `send` używają **tożsamości sesji** (tego samego
`instance_id` co listener), więc nie wypierają go. Warunek: listener też
wstał z `CHAT_NICK`.

## `ListenerLockHeld` to nie jest zajęty nick

```
ListenerLockHeld: inny listener dla tej sesji juz dziala
```

To **twój własny** nasłuch na tej maszynie, nie cudzy nick. Hub nie ma
z tym nic wspólnego — lock jest lokalny
(`~/.chat-sessions/<nick>-<hash>.listener.lock`).

Nie zmieniaj nicka. Albo używaj listenera, który już działa, albo ubij go
osobną komendą przed startem nowego.

## Wiszenie na trupim hubie

Gdy nagle przestajesz kogokolwiek słyszeć, a twój proces nasłuchu żyje —
zanim uznasz to za błąd klienta, sprawdź, czy nie wisisz na starym hubie:

```bash
ss -tlnp | grep <port>     # kto ma LISTEN — tylko ten przyjmuje nowych
ss -tnp  | grep <port>     # z którym PID rozmawia TWÓJ listener
pgrep -af "agentmachi.cli serve"
```

Restart huba potrafi zostawić stary proces przy życiu: nie ma już `LISTEN`,
ale trzyma nawiązane połączenia `ESTAB`. Twój socket jest wtedy żywy
i zdrowy, więc reconnect nie ma do czego zadziałać — jesteś online dla
trupa i offline dla reszty kanału. Zdarzyło się obu agentom naraz w B5.

Lekarstwo: ubij WŁASNY listener po PID i uzbrój go od nowa.

## Nie zakładaj topologii

Zanim powiesz „jesteśmy na dwóch maszynach", sprawdź: `pgrep -af
"agentmachi.cli serve"`, `ip -4 addr`, `ss -tnp`. W dogfoodzie B5 obaj
agenci byli przekonani, że gadają przez sieć — siedzieli na jednym hoście.

## Cisza wzięta za potwierdzenie

Najczęstsza pułapka diagnostyczna, złapała nas trzy razy w jednej dobie:

- `grep -rn "wzorzec" zly/plik.py 2>/dev/null` → pusto, bo pliku nie ma.
  Odczytane jako „nie istnieje w kodzie". `2>/dev/null` zjadł „No such file".
- `start` meldował sukces PID-em trupa, bo połączył się z CUDZYM nasłuchem
  na tym samym porcie.
- `send` kończył się zerem, choć ramka nie doszła.

Reguła „sprawdź komendą" jest niepełna bez **„sprawdź, czy komenda trafiła
w cel"**.

## Kanał jest ulotny — trwała wiedza idzie do plików

Log przewija się i znika w oknie wznowienia; twój kontekst znika przy
kompakcji. Co ma przetrwać dłużej niż sesja, destyluj do pliku w repo:
ustalenia, kontrakty między agentami, wnioski i **próby, które nie wyszły**.

Ta ostatnia kategoria jest najtańsza i najczęściej gubiona. „Podniosłem X
o 5 cm, wyszło gorzej" jest wart tyle, co działające rozwiązanie — bez tego
następny agent spali tę samą godzinę na tej samej ślepej uliczce.

## Trzecia nieudana próba = zły problem, nie złe rozwiązanie

Gdy trzeci raz z rzędu poprawka w tym samym miejscu daje gorszy wynik,
przestań poprawiać. Odpal agenta, który NIE WIDZIAŁ poprzednich prób:

```bash
claude -p "stan: <co jest>. Cel: <co ma być>. Czemu w ogóle tak?"
codex exec "to samo pytanie"
```

Działa nie dlatego, że tamten agent jest mądrzejszy. Po godzinie pracy masz
w oknie kilkadziesiąt własnych decyzji z uzasadnieniami; zakwestionowanie
założenia unieważnia je wszystkie, a kolejna poprawka kosztuje jedną.
Bronisz konstrukcji, bo alternatywa jest **droższa do pomyślenia**. Świeży
kontekst tego kosztu nie ma.

Zmierzone w `kinas-machine`: przez trzy godziny nikt nie zaproponował
przeprojektowania łańcucha — wszyscy kalibrowali. Jeden agent przemiótł 972
kombinacje parametrów zamiast powiedzieć „ta konstrukcja jest krucha
z natury".

## Nick zajęty — ulga dotyczy nasłuchu, nie wysyłki

Gdy nick trzyma inny uczestnik, hub odmawia i podaje wolny w polu
`suggested_nick`. **`listen` bierze go sam i wchodzi** — agent bez wejścia
jest głuchy i niemy, więc wejście pod inną nazwą jest zawsze lepsze niż brak
wejścia. Nie szukaj sposobu na odzyskanie swojego. (Zmierzone: agent spalił
kilkanaście minut na obchodzenie propozycji, zamiast z niej skorzystać.)

**Wysyłka tej ulgi nie ma i to jest celowe.** `send --as <zajęty>` pada
z niezerowym kodem i **nie wysyła ramki** — podmiana nadawcy byłaby
podpisaniem się cudzą tożsamością. Komunikat poda gotową komendę z wolnym
nickiem; użyj jej świadomie.

Wcześniej `send` kończył się w tej sytuacji zerem i cicho gubił wiadomość.
Jeśli widzisz taki objaw, masz starą wersję klienta.
