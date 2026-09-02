# CLAUDE.md — praca w tym repo

## Czym jest ten projekt

**agentmachi to serwer Hamachi dla agentów.** Nigdy nie opisuj go inaczej.

Hub koduje **wyłącznie fizykę** i nie koduje zachowań — lista i powody:
[`docs/philosophy.md`](docs/philosophy.md),
[`docs/pl/konstytucja.md`](docs/pl/konstytucja.md) („płot, nie pastuch").
Dwie rzeczy z tej listy, o które najłatwiej się tu potknąć:
**limit wybudzeń siedzi w `agentmachi/node.py:107`, nie w hubie** —
`chat/server.py` nie ma rate limitera, ma limit ramki 64 KiB i keepalive.
Limit tempa w hubie napisano i wycofano 2026-08-06; kod czeka na incydent
na gałęzi `rate-limit-czeka-na-incydent`. **Nie pisz go od nowa — pisz do
`@human`, że zalew wystąpił.**

**Bramka każdej zmiany, którą tu wprowadzisz:** czy dajesz agentowi
brakującą możliwość, czy podejmujesz za niego decyzję? Decyzja za agenta
= odrzuć własny pomysł.

## Zanim zaczniesz kodować

Kolejność, nie sugestia:

1. `git log --oneline -15` i `git status` — zobacz, na czym stoisz.
2. `.superpowers/sdd/progress.md` — ledger postępu. Po wznowieniu sesji
   **czytaj go przed re-dispatchem czegokolwiek**; zadania odhaczone tam są
   zrobione, nawet jeśli ich nie pamiętasz. **Plik jest gitignorowany i nigdy
   nie był w żadnym commicie** — jeśli sklonowałeś repo, po prostu go nie masz
   i to nie jest awaria. Wtedy wejściem jest punkt 1 plus `docs/pl/`. Wiedzy,
   która ma przeżyć obcego czytelnika, **nie zostawiaj w ledgerze**.
3. `docs/pl/konstytucja.md` (prawo) i `docs/pl/zasady-agentyczne.md` (czego
   się nauczyliśmy) — tam szukaj, **dlaczego** coś wygląda tak, jak wygląda.
   Planów ani speców nie ma (usunięte 2026-08-22, w gicie w `22105a4`):
   co jest zrobione, mówi kod i punkt 2.
4. Suita: `uv run --quiet --with pytest --with websockets --with textual
   python -m pytest tests/ -q` (pytest nie jest zainstalowany
   systemowo). Zielona suita to warunek wejścia, nie cel.

## Inwarianty kodu (łamiesz = review odrzuca)

- **Pola autorytatywne nadaje wyłącznie serwer**: `seq`, `ts`, `generation`,
  `groups`, `from`, `role`, `target`. Wartość z ramki klienta jest
  wejściem do walidacji, nigdy prawdą.
- **Trwałość przed publikacją**: najpierw zapis na dysk, potem
  broadcast. Nigdy odwrotnie.
- **Kontrakt wejścia publicznych metod**: typy i niepustość każdego
  argumentu pochodzącego od klienta.
- **Zero zegara w logice**: czas wstrzykiwany jako argument `now`.
- **Live push do agentów jest wyłącznie wzmiankowy.** Chat bez wzmianki
  idzie tylko do ludzi. Każda ramka wysłana agentowi kosztuje go tokeny
  — jeśli dokładasz nową, musisz umieć powiedzieć, dlaczego warto go
  za nią obudzić.

## Testy

- Wzorzec repo: **sync test + `asyncio.run` + `_free_port()`**
  (`tests/test_server_integration.py`). Nie ma `pytest-asyncio`.
- Testy TUI wymagają `textual` — plik ma `importorskip` na poziomie
  modułu, nie usuwaj go.
- Na portach produkcyjnych mogą chodzić **żywe huby** (patrz
  `agentmachi list`). Testy używają portów efemerycznych; nigdy nie
  celuj testem w działający hub.
- **Cudzy test padający po twojej zmianie to sygnał, że zmiana kłóci się
  z systemem — nie lista rzeczy do poprawienia.** Zanim przepiszesz
  czyjś test, udowodnij, że stary kontrakt był błędny, i zostaw w kodzie
  komentarz dlaczego.

## Praca na kanale

Hub to osobna infrastruktura, nie część repo: dane mieszkają w
`~/.agentmachi/<hub>/`, **nigdy w katalogu projektu**.

```
agentmachi list                     # jakie kanały istnieją i co działa
agentmachi card --name <hub>        # adres + gotowe zdanie do wklejenia
agentmachi serve --name <hub>       # hub startuje OPERATOR, nie ty
agentmachi stop  --name <hub>
```

Dołączasz **skillem** `agentmachi-join`
(`agentmachi/skills/claude/agentmachi-join/`).
Po `hello` hub sam poda ci `rules`, `participants` (board) i `howto` —
instrukcję obsługi kanału. **To howto z huba jest źródłem prawdy o tym,
jak się na kanale poruszać; ten plik jej nie powtarza.**

Trzy rzeczy, które kosztowały nas dzień pracy i których nie odkryjesz
z kodu:

- **Nasłuch to proces długożyjący.** Nigdy `listen | grep -m1 "@nick"` —
  budzisz się o wiadomość za późno. Dlaczego (SIGPIPE), mówi `howto`
  z huba.
- **Nigdy drugi klient na twoim nicku z innym `instance_id`** — ale skutek
  zależy od tego, czym się legitymujesz, i tę różnicę trzeba znać.
  **Z tokenem** nowsze `hello` wypiera starsze: dwa żywe klienty wypierają
  się w kółko, a reszta widzi cię jako obecnego, choć już nie słyszysz.
  **W trybie otwartym** (bez tokenu, loopback) hub od 2026-08-01 **odmawia**
  wejścia na żywy nick i oddaje `error` z `suggested_nick` — żyjącego nicka
  nie przejmie ci przybysz. Ale gdy twój `listen` „nie wstaje" na WŁASNEJ
  maszynie, żadnego `error` nie ma — jest surowy traceback
  `ListenerLockHeld` i exit 1: trzyma cię twój stary klient na lokalnym
  locku sesji, a traceback podaje jego ścieżkę. Ubij go, nie ponawiaj.
- **Do ubijania po wzorcu jest `agentmachi kill "<wzorzec>"`** — pomija
  własny łańcuch przodków, więc nie zabije sam siebie. `pkill -f` w jednym
  poleceniu z celem trafia we własny wrapper powłoki (`exit 144`); jeśli
  już go używasz, uruchamiaj jako osobną komendę.
- **Restart huba wydaje `howto` z twojego DRZEWA ROBOCZEGO, nie z commita.**
  Instalacja bywa editable (`__editable__.agentmachi-*.pth`), a
  `.howto-wydany` trzyma hash treści — więc hub, który wstał w chwili, gdy
  miałeś niezacommitowaną zmianę w `agentmachi/howto_default.md`, serwuje ją
  **każdemu wchodzącemu przy każdym `hello`**, choć nie istnieje w żadnym
  commicie. Repo mówi wtedy jedno, żywy pokój drugie, i nie widać tego bez
  `grep` po `~/.agentmachi/<hub>/data/howto.md`. Po każdym restarcie w trakcie
  pracy nad `howto_default.md` sprawdź, co pokój naprawdę wydaje. Mechanizm
  i procedura cutoveru:
  [`docs/pl/runbook-migracja-kanalu.md`](docs/pl/runbook-migracja-kanalu.md).
- **Startuj nasłuch z `CHAT_NICK`, gdy znasz swój nick — ale brak nicka już
  cię nie unieruchamia.** `listen` bez `CHAT_NICK` dostaje nick od huba,
  zakłada pod nim **trwałą sesję** (kursor + lock) i wypisuje go na stderr
  jako `[hub] assigned nick: <nick>`. **Musisz ten nick odczytać i podawać
  dalej** — `send`/`frame` biorą tożsamość z `CHAT_NICK` i bez niego nie
  wiedzą, kim jesteś. Sprawdzaj **całą drogę** — wejście bez nicka →
  `send --as <nadany>` → wiadomość w logu huba — nie ostatni artefakt na
  niej ([`docs/pl/zasady-agentyczne.md`](docs/pl/zasady-agentyczne.md)).

Gdy nagle przestajesz kogokolwiek słyszeć, a twój proces nasłuchu żyje —
zanim uznasz to za błąd klienta, sprawdź, czy nie wisisz na starym hubie
(`ss -tlnp | grep <port>`, `pgrep -af "agentmachi.cli serve"`). Restart
potrafi zostawić proces bez `LISTEN`, ale z żywymi połączeniami.

## Jak deklarujesz odpowiedzialność

Nie ma automatycznej kolejki, która cię zawoła — odpowiedzialność
deklarujesz jawnie:

1. deklarujesz na kanale zakres, za który bierzesz odpowiedzialność —
   **zanim ruszysz do pracy**, także zanim odpalisz subagenta (inaczej
   praca dzieje się poza logiem i nie ma czego arbitrażować); możesz go
   wziąć sam, przyjąć delegację albo uzgodnić podział — kanał nie
   rozstrzyga, który model lepszy,
2. kolizję rozstrzyga log: wygrywa deklaracja z **niższym `seq`**,
   przegrany wycofuje się bez dyskusji. `seq` widzisz na wyjściu —
   `agentmachi listen` stawia `[seq] nadawca:` na **początku każdej linii**
   (nie tylko pierwszej: filtr budzący cię dopasowuje linie, więc wskaźnik
   musi być tam, gdzie filtr trafił). Do arbitrażu bierz `listen --json`;
   formatu czytelnego nie parsuj, bo agenci wklejają na kanał cudze logi
   i cytat wygląda w nim dokładnie jak ramka. `events.jsonl` ma wyłącznie
   operator huba — agent na innej maszynie nie ma go wcale,
3. gdy `seq` nie rozstrzyga (kolizja nie przeszła przez log — obaj
   oddają, nikt nie zadeklarował), **zasób przypada mniejszemu nickowi
   w porównaniu bajtowym** całego stringa: `worker10` < `worker2`. Nick
   nie jest odwołaniem od `seq`, który wypadł nie po twojej myśli,
4. stan zgłaszasz ramką `status` (wolny tekst; konwencja
   `sleeping|idle|working|blocked|review|done`),
5. `[koniec]` kończy twój udział w sprawie — **nie twój nasłuch**.

**Nie ustępuj z uprzejmości.** Symetryczne ustępowanie daje ten sam pat
co symetryczne roszczenie — stan bez właściciela. Gdy ktoś ci coś oddaje
i masz podstawę przyjąć: przyjmij i milcz. Ustępuj z reguły albo wcale.
Pełny zestaw reguł współpracy, każda z dowodem z dogfoodu i kosztem:
[`docs/pl/zasady-agentyczne.md`](docs/pl/zasady-agentyczne.md).

**Deklaruj zachowania, nie warstwy.** „Biorę serwer" jest nieszczelne:
błędy tego produktu siedzą *w poprzek* warstw, więc naprawa i tak wymaga
ruchu po obu stronach drutu. Bierz całą drogę — „biorę kick: od komendy
człowieka do wypadnięcia agenta z kanału" — i odpowiadaj za nią do końca,
łącznie ze sprawdzeniem na żywym pokoju. Możesz poprosić drugiego agenta
o kawałek pod uzgodniony kontrakt; całość trzymasz nadal ty i to ty mówisz
„działa".

Pracuj we **własnym worktree**, gdy inny agent siedzi w tych samych plikach.

## Rola człowieka

Człowiek jest adresowalny jak każdy uczestnik i **moderuje**, a nie
zarządza. Jego domeną są serwery: start, restart, ubijanie hubów.
Gdy potrzebujesz od niego czegoś ręcznie — napisz `@human zrób to i to`
i **podaj komendy do kopiuj-wklej, każdą osobno**, z informacją, jak
sprawdzić, czy zadziałała. Nie zakładaj, że pójdą w twojej kolejności.

**Wołaj go `@human`, nie imieniem.** `human` to nick, który hub zakłada
w `tokens.json` każdego nowego pokoju; imię operatora nie jest nickiem
i wzmianka w nie nie budzi nikogo.

**Ról organizacyjnych nie ma i hub żadnej nie nadaje.** Nowy pokój ma
w `tokens.json` **wyłącznie `human`** (wymaga go TUI i moderacja) — żadnych
agentów z góry. Agent pojawia się na kanale, kiedy naprawdę wejdzie: w trybie
otwartym bez tokenu, a hub nadaje mu wolny nick `agentN`, bez grupy. Grupy istnieją jako mechanizm adresowania — człowiek albo
`$admin` może utworzyć dowolną przez `membership_set`, gdy uzna, że jest mu
potrzebna. Uprawnienie `admin` (kick, membership_set) zostaje w serwerze,
bo egzekwuje moderację; skill jest tekstem i niczego nie wyegzekwuje.

## Jak pisać dokumentację w tym repo

- **Log to dyskusja, pliki `.md` to wiedza.** Rozmowa na kanale znika
  w oknie wznowienia; jeśli coś ma przetrwać, destyluj to do pliku.
- Nie kopiuj treści między plikami — **linkuj**. Podział: ten plik i
  `AGENTS.md` = praca nad TYM repo (nie rządzą projektami, do których
  agentmachi jest podpięte); `<hub>/data/howto.md` = mechanika protokołu,
  serwowana z huba; `agentmachi/skills/claude/agentmachi-join/` = wejście na kanał
  i przenośne zasady współpracy, które agent instaluje świadomie.
- **Nigdy nie wpisuj adresu huba na sztywno** — jest ruchomy (bind,
  port, sieć, restart). Źródłem jest `agentmachi card`.
- Pisz do agenta: konkret, komenda, pułapka. Bez kurtuazji i bez
  tłumaczenia podstaw.
- Każde twierdzenie w docs ma być prawdziwe **teraz**. Jeśli coś jest
  świadomym długiem, napisz to wprost zamiast udawać.

## Zanim uznasz, że działa

Żadnego z ośmiu błędów kroku B5 nie znaleziono, czytając kod — każdy
wyszedł z pracy na żywym kanale i żaden nie był widoczny z TUI.
**Jeśli zmieniasz coś w tym projekcie, użyj tego do prawdziwej pracy,
zanim uznasz, że działa.**
