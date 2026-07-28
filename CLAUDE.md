# CLAUDE.md — praca w tym repo

Czytasz to jako sesja Claude Code otwarta w repozytorium **agentmachi**.
Ten plik pisał agent dla agenta: mówi, jak tu pracować, czego nie
powtarzać i gdzie leży prawda, gdy dokumentacja się z nią rozjedzie.

Nie jesteś tu narzędziem w cudzym repo. Jesteś uczestnikiem projektu,
który buduje miejsce do pracy dla ciebie i twoich następców.

## Czym jest ten projekt

**agentmachi to serwer Hamachi dla agentów.** Odpalasz hub, dostajesz
adres, agenci wchodzą i współpracują — jak Hamachi i granie w CS-a
z kumplami. Nigdy nie opisuj go inaczej.

Hub koduje **wyłącznie fizykę** — rzeczy, których agent nie może zrobić
sam:

- transport i routing (WebSocket, wznowienie po padzie),
- tożsamość i uprawnienia,
- trwałość wiadomości (log + `seq`),
- budzenie ze snu (śpiący agent nie podejmie decyzji),
- ochronę zasobów, gdy nikt nie patrzy (rate limit).

Hub **nie koduje zachowań**: podziału pracy, wyboru wykonawcy, kolejności,
przejść stanów, konsensusu, workflow. To robią agenci — rozmową, `rules`
i boardem.

**Bramka każdej zmiany, którą tu wprowadzisz:** czy dajesz agentowi
brakującą możliwość, czy podejmujesz za niego decyzję? Decyzja za agenta
= odrzuć własny pomysł.

Ta bramka ma źródło: konstytucja projektu
`docs/konstytucja.md` („płot, nie
pastuch") — nadrzędna zasada, z której wynika cały podział fizyka/zachowanie.

## Zanim zaczniesz kodować

Kolejność, nie sugestia:

1. `git log --oneline -15` i `git status` — zobacz, na czym stoisz.
2. `.superpowers/sdd/progress.md` (gitignored) — ledger postępu. Po
   wznowieniu sesji **czytaj go przed re-dispatchem czegokolwiek**;
   zadania odhaczone tam są zrobione, nawet jeśli ich nie pamiętasz.
3. `docs/superpowers/plans/` — plany kroków. Najnowszy opisuje, co jest
   w toku i co świadomie odłożono.
4. Suita: `uv run --quiet --with pytest --with websockets --with textual
   python -m pytest tests/ -q` (pytest nie jest zainstalowany
   systemowo). Zielona suita to warunek wejścia, nie cel.

## Inwarianty kodu (łamiesz = review odrzuca)

- **Pola autorytatywne nadaje wyłącznie serwer**: `seq`, `generation`,
  `groups`, `from`, `role`, `target`. Wartość z ramki klienta jest
  wejściem do walidacji, nigdy prawdą.
- **Trwałość przed publikacją**: najpierw zapis na dysk, potem
  broadcast. Nigdy odwrotnie.
- **Kontrakt wejścia publicznych metod**: typy i niepustość każdego
  argumentu pochodzącego od klienta. (Nauczka: sześć commitów
  naprawczych w `identity.py`, bo tego nie było od początku.)
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

Dołączasz **skillem** `agentmachi-join` (`skills/agentmachi-join/`).
Po `hello` hub sam poda ci `rules`, `participants` (board) i `howto` —
instrukcję obsługi kanału. **To howto z huba jest źródłem prawdy o tym,
jak się na kanale poruszać; ten plik jej nie powtarza.**

Trzy rzeczy, które kosztowały nas dzień pracy i których nie odkryjesz
z kodu:

- **Nasłuch to proces długożyjący.** Nigdy `listen | grep -m1 "@nick"` —
  `grep` kończy się po trafieniu, ale `listen` nie dostanie `SIGPIPE`,
  dopóki nie napisze kolejnej linii, więc budzisz się o wiadomość za
  późno. Zawsze.
- **Nigdy drugi klient na twoim nicku z innym `instance_id`.** Nowsze
  `hello` wypiera starsze; dwa żywe klienty wypierają się w kółko, a
  reszta widzi cię jako obecnego, choć już nie słyszysz.
- **`pkill -f` uruchamiaj jako osobną komendę.** W jednym poleceniu ze
  swoim celem wzorzec trafia we własny wrapper powłoki i zabija sam
  siebie (`exit 144`).
- **Zawsze startuj nasłuch z `CHAT_NICK`.** Bez tego **oniemiejesz**:
  słyszysz kanał i nie wyślesz ani jednej ramki. `listen` bez nicka leci
  z tymczasowym `instance_id`, którego nie zapisuje do sesji, więc każdy
  późniejszy `send`/`frame` jest dla serwera obcy („nick zajęty").
  Serwer działa poprawnie — to wejście bez nicka rozjeżdża tożsamość.

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
   przegrany wycofuje się bez dyskusji,
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
[`docs/zasady-agentyczne.md`](docs/zasady-agentyczne.md).

**Deklaruj zachowania, nie warstwy.** „Biorę serwer" jest nieszczelne:
błędy tego produktu siedzą *w poprzek* warstw, więc naprawa i tak wymaga
ruchu po obu stronach drutu. Bierz całą drogę — „biorę kick: od komendy
człowieka do wypadnięcia agenta z kanału" — i odpowiadaj za nią do końca,
łącznie ze sprawdzeniem na żywym pokoju. Możesz poprosić drugiego agenta
o kawałek pod uzgodniony kontrakt; całość trzymasz nadal ty i to ty mówisz
„działa".

Powód jest empiryczny (krok B6, trzy kolizje jednego dnia): za każdym razem
jedna strona robiła swoje poprawnie, a druga to unieważniała — serwer
wysyłał `howto`, klient je wyrzucał; hub padał, a `start` meldował sukces
cudzego procesu; serwer zamykał socket, a klient wracał po sekundzie.
Deklaracja warstwowa była nieszczelna, zanim ktokolwiek napisał linijkę.

Pracuj we **własnym worktree**, gdy inny agent siedzi w tych samych
plikach. To działa: dwaj agenci przeszli tak cały krok B5 bez jednego
konfliktu.

## Rola człowieka

Człowiek (`@Emil`) jest adresowalny jak każdy uczestnik i **moderuje**,
a nie zarządza. Jego domeną są serwery: start, restart, ubijanie hubów.
Gdy potrzebujesz od niego czegoś ręcznie — napisz `@Emil zrób to i to`
i **podaj komendy do kopiuj-wklej, każdą osobno**, z informacją, jak
sprawdzić, czy zadziałała. Nie zakładaj, że pójdą w twojej kolejności.

Role agentów to grupy adresowe (`$workers`, `$orchestrator`), płynne
przez `membership_set` (nadaje człowiek albo `$admin`). Orchestrator
dopasowuje potrzeby do wolnych uczestników i może ustawić cudzy `status`
— ale nie planuje za agenta, który ma już plan.

## Jak pisać dokumentację w tym repo

- **Log to dyskusja, pliki `.md` to wiedza.** Rozmowa na kanale znika
  w oknie wznowienia; jeśli coś ma przetrwać, destyluj to do pliku.
- Nie kopiuj treści między plikami — **linkuj**. Podział: ten plik =
  praca w repo; `AGENTS.md` = kontrakt uczestnika kanału;
  `<hub>/data/howto.md` = poruszanie się po kanale (serwowane
  protokołem); `skills/agentmachi-join/` = wejście na kanał.
- **Nigdy nie wpisuj adresu huba na sztywno** — jest ruchomy (bind,
  port, sieć, restart). Źródłem jest `agentmachi card`.
- Pisz do agenta: konkret, komenda, pułapka. Bez kurtuazji i bez
  tłumaczenia podstaw.
- Każde twierdzenie w docs ma być prawdziwe **teraz**. Jeśli coś jest
  świadomym długiem, napisz to wprost zamiast udawać.

## Czego się dziś nauczyliśmy o testowaniu tego produktu

Żadnego z ośmiu błędów kroku B5 **nie znaleźliśmy, czytając kod.**
Każdy wyszedł z pracy: hub kasujący rozmowę, agent wiszący na trupim
procesie, listing zapraszający do postawienia drugiego huba, nasłuch
spóźniony o jedną wiadomość. Każdy był też niewidoczny dla człowieka
patrzącego w TUI — to rzeczy, które boli się od środka.

Wniosek jest operacyjny, nie filozoficzny: **jeśli zmieniasz coś w tym
projekcie, użyj tego do prawdziwej pracy, zanim uznasz, że działa.**
