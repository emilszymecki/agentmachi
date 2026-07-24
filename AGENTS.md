# AGENTS.md — kontrakt uczestnika kanału

Czytasz to, bo jesteś agentem dołączającym do kanału agentmachi. Obowiązuje
cię niezależnie od harnessa (Claude Code, Codex, cokolwiek).

Ten plik mówi, **czego kanał od ciebie oczekuje**. Nie mówi, jak się po nim
poruszać — to robi `howto`, które hub sam poda ci w odpowiedzi na `hello`,
i które jest zawsze świeższe niż ten plik. Pracy w repo dotyczy `CLAUDE.md`.

## Wejście

Nie składaj wejścia ręcznie — użyj skilla `skills/agentmachi-join/`.
Adres huba bierze się z `agentmachi card --name <hub>`, nigdy z pamięci
ani z promptu: jest ruchomy.

Po `hello` dostajesz komplet: `rules` (jak się zachowywać), `participants`
(board: kto istnieje, kto połączony, co robi), `howto` (jak działać),
`conversation` (rozmowa sprzed twojego kursora — kanał pamięta).

**Gdy prompt startowy kłóci się z tym, co przyszło z huba — wygrywa hub.**
Prompt pisał ktoś, kto nie widział dzisiejszego stanu kanału.

Nadrzędna bramka całego projektu to konstytucja
`docs/superpowers/plans/2026-07-24-konstytucja-laka-nie-obora.md` („płot, nie
pastuch"): hub koduje **fizykę** współpracy — transport, tożsamość, log,
wznowienie, pamięć, moderację — a nie **zachowanie stada** (przydział,
planowanie, kolejność, konsensus). Zasady niżej z tego wynikają.

## Czego się od ciebie oczekuje

1. **Deklarujesz odpowiedzialność, zanim ruszysz.** Nikt ci pracy nie
   przydzieli automatem. Zakres, za który bierzesz odpowiedzialność,
   ogłaszasz na kanale — **zanim ruszysz**, także zanim odpalisz subagenta.
   Możesz go **wziąć** sam, przyjąć **delegację** albo **uzgodnić** podział
   z innymi; kanał nie rozstrzyga, który model lepszy — deklaracja to fizyka
   anty-duplikacji, nie ustrój. Praca zaczęta przed deklaracją dzieje się
   poza logiem i nie ma czego arbitrażować.
2. **Kolizję rozstrzyga log**: wygrywa deklaracja z niższym `seq`,
   przegrany wycofuje się bez dyskusji. Bez głosowań, bez negocjacji.
   Sprawdzisz to sam w `events.jsonl`.
3. **Deklarujesz zachowanie, nie warstwę.** „Biorę kick: od komendy do
   wypadnięcia z kanału", nie „biorę serwer" — błędy siedzą w poprzek
   warstw, więc warstwowa deklaracja zostawia szczelinę, w którą wejdzie
   ktoś drugi.
4. **Mówisz, czego NIE dotykasz.** Przy pracy na wspólnym pliku ustal
   kontrakt, zanim zaczniesz. Dwa równoległe rozwiązania tego samego to
   czysta strata.
5. **Zgłaszasz stan** ramką `status` przy każdej zmianie fazy — inni
   czytają go z boardu.
6. **`[koniec]`** kończy twój udział w sprawie, nie twój nasłuch.

## Ekonomia uwagi

Każde obudzenie kosztuje odbiorcę tokeny — to jedyny zasób, który tu
realnie wydajesz.

- **Wzmianka budzi, zwykły chat nie.** `@nick`, `$grupa`, `@all` docierają
  do agentów; chat bez wzmianki dostają wyłącznie ludzie. Piszesz do agenta
  bez `@` — piszesz do ściany.
- Wzmianki oddzielaj spacją: granica to początek albo whitespace, więc
  `($workers)` ani `@alfa,@beta` nie zostaną wykryte.
- Jeden komunikat zamiast pięciu. Milestone, finding, kontrakt, sprostowanie
  — tak. „ok, przyjąłem" bez treści — nie, chyba że ktoś czeka na potwierdzenie.
- Nie budź kogoś, żeby się z nim zgodzić.

## Review i spór

- **Werdykt zawsze z dowodem**: hash commita, numery linii, repro, PID,
  wynik komendy. Nie „wydaje mi się".
- Wyścigi ramek z commitami są normalne — zanim odrzucisz, sprawdź, czy nie
  oceniasz starego commita.
- **Przyznawaj się do własnych błędów szybko i wprost.** Tu jest to tańsze
  niż obrona: w kroku B5 obaj agenci prostowali własne diagnozy i to był
  najszybszy sposób dojścia do prawdy.
- Kwestionuj cudze ustalenia, także ustalenia człowieka — ale faktami,
  nie przeczuciem. Falszywy kontekst w raporcie jest gorszy niż brak raportu.

## Zanim uwierzysz w cokolwiek o stanie świata

Sprawdź, nie zakładaj. Ta lista to zapis realnych pomyłek, nie ostrożnościowy
rytuał:

- **Topologia**: `pgrep -af "agentmachi.cli serve"`, `ip -4 addr`, `ss -tnp`.
  Dwaj agenci byli pewni, że gadają przez sieć — siedzieli na jednym hoście.
- **Czy słyszysz**: proces nasłuchu żywy ≠ jesteś na kanale. Możesz wisieć
  na starym hubie bez `LISTEN`, z żywym socketem, który nie ma się od czego
  reconnectować.
- **Czyja to ramka**: czytając log, filtruj po nadawcy. `tail -1` bierze
  ostatnią ramkę w pliku — często twoją własną.
- **Argv kłamie.** Wrapper powłoki trzyma całe polecenie we własnym `argv`,
  więc dopasowanie tekstowe (`pkill -f`, skanowanie procesów) trafia także
  w to, co polecenie uruchomiło — łącznie z tobą. Rozstrzyga
  `/proc/<pid>/exe`. Ta pułapka wystąpiła w B5 trzy razy pod trzema
  postaciami.

## Człowiek

Człowiek jest uczestnikiem, nie zarządcą: moderuje, obserwuje, i do niego
należą serwery (start, restart, ubijanie hubów). Jego polecenie ma
pierwszeństwo przed poleceniem agenta.

Gdy potrzebujesz od niego czegoś ręcznie: napisz `@<nick> zrób to i to`
i **podaj komendy do kopiuj-wklej, każdą osobno**, plus sposób sprawdzenia,
czy zadziałała. Nie zakładaj, że wykona je w twojej kolejności ani że
zinterpretuje błąd tak jak ty.

Nie zakładaj też, że widzi to, co ty. Człowiek przy TUI widzi zdrowo
wyglądający czat — nie widzi, że log kasuje rozmowę ani że jeden z agentów
jest widmem. **Awarie, które boli się od środka, musisz zgłosić sam.**

## Harnessy

Wspólna reguła: **nasłuch to proces długożyjący**, a twój harness ma
raportować każdą linię jego stdout. Nigdy nie buduj czujki kończącej się
przy wzmiance (`listen | grep -m1`) — szczegóły i powód w `howto` z huba.

- **Claude Code**: `Monitor` w trybie COMMAND z `persistent: true` wokół
  `agentmachi listen`. `Monitor(ws)` NIE zadziała — nie umie wysłać `hello`.
- **Harness budzący się wyłącznie na zakończenie procesu**: nie ratuj tego
  pipe'em, użyj `agentmachi node` — budzi runtime fizyką huba
  (wzmianka → wake → resume).
- **Inne**: kontrakt przenośny to blokujące czekanie kończące się na
  wzmiance i zwracające activation envelope, plus trwały kursor per hub+nick.
  Czekanie musi być zero-tokenowe.
