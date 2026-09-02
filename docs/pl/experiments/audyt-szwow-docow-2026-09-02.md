# Audyt szwów dokumentacji — 2026-09-02

Zadanie operatora: każda obietnica z **gorącej ścieżki** („ta komenda robi X",
„po reconnekcie Y") sprawdzona **zachowaniem**, nie lekturą. Cold-probe
(`cold-probe/spec.md`) mówi, czego brakuje; ten audyt mówi, **co kłamie**.

Wykonali: `agent1` i `agent2` na pokoju `interwizja`, w parze — operator
poprosił wprost o pracę parami, nie o podział na silosy.

## Metoda: ślepe wykonanie krzyżowe

Rdzeń, i to on odróżnia ten przebieg od czytania doców ze zrozumieniem:

> **Kto wykonuje komendę, nie zna obietnicy, którą ona ma spełnić.**

Inaczej wykonawca widzi to, czego się spodziewa — ta klasa błędu zjadła nam
poprzedniego dnia kilka godzin (`zasady-agentyczne.md`, reguła 17 i sąsiednie).

1. A wyciąga obietnicę z pliku, cytuje ją dosłownie z `plik:linia` i
   **zamraża predykcję na dysku** wraz z warunkiem falsyfikacji.
2. A publikuje `sha256` pliku predykcji na kanale — **przed** wysłaniem poleceń.
3. B dostaje GOŁE polecenia („uruchom to, opisz co się stało"), bez cytatu
   i bez oczekiwanego wyniku, wykonuje na izolowanej kopii i raportuje
   **surową** obserwację.
4. Dopiero wtedy A odmraża predykcje i orzeka. Hash sprawdzany publicznie.

Role zamieniają się między zestawami: każdy jest raz przewidującym, raz
ślepym wykonawcą. Nikt nie certyfikuje własnego wykonania.

**Reguła rozstrzygania dwuznaczności**, ustalona przed fazą 4: jeśli obietnica
jest napisana tak, że i predykcja, i obserwacja do niej pasują — werdykt brzmi
NIESPRAWDZALNA, nie PRAWDA. Dwuznaczność w gorącej ścieżce jest znaleziskiem,
nie remisem.

## Kategorie werdyktu

| kategoria | znaczenie |
|---|---|
| PRAWDA | obietnica sprawdzona zachowaniem i trafiona |
| KŁAMIE | zachowanie sprzeczne z obietnicą |
| PRAWDZIWA W ZAKRESIE, KTÓREGO NIE PODAJE | obietnica trafna w swoim zakresie, ale milcząca o granicy, poza którą przestaje obowiązywać — a czytelnik na tę granicę trafia |
| NIESPRAWDZALNA Z DOKUMENTOWANEJ ŚCIEŻKI | obietnica opisuje zachowanie, do którego dokumentowanym klientem nie da się dojść |
| NIESPRAWDZALNA Z TEJ STRONY | wymaga środowiska, którego nie mamy (np. żywa sesja Codeksa) — to stan NASZEGO stanowiska, nie wada obietnicy |

Trzecia kategoria nie była przewidziana na starcie. Dopisaliśmy ją, gdy padły
**dwa niezależne** przypadki tego samego kształtu — patrz Znaleziska 1 i 2.
To nie jest złagodzenie „KŁAMIE": obietnica z tej kategorii jest prawdziwa,
a mimo to wprowadza czytelnika w błąd, bo jej zakres jest niewypowiedziany.

**Ale skala ruszyła się w trakcie przebiegu i czytelnik musi to wiedzieć,
zanim uwierzy w liczbę zero.** Trzecia kategoria powstała, gdy wyniki leżały
już na stole; reguła o dwuznaczności („pasuje predykcja i obserwacja →
NIESPRAWDZALNA") też weszła w trakcie. Oba ruchy mogą kategorię KŁAMIE
wyłącznie **opróżniać**, nigdy zapełniać. To nie zarzut złej wiary — to
stopień swobody, który przy nagłówku „zero KŁAMIE" waży więcej niż dobór
próbki. Wskazał to dopiero recenzent bez autorstwa; obaj audytorzy pisali
i recenzowali ten plik, nie widząc tego ani razu.

## Zestaw A — `howto_default.md` (wyciągał agent2, wykonywał ślepo agent1)

Predykcje zamrożone 20:55:16, `sha256` 656010a6ac0d9b0b… ogłoszony na kanale
przed pierwszym poleceniem, zweryfikowany przed odmrożeniem.

| # | obietnica (`howto_default.md`) | werdykt |
|---|---|---|
| A1 | :13 hub ostrzega i **mimo to loguje** ramkę z nieistniejącą grupą | PRAWDA |
| A2 | :14 chat bez wzmianki dociera **tylko do ludzi** | PRAWDA (obie połowy) |
| A3 | :34 `read` bez locka, bez ruchu kursora, obok żywego `listen` | PRAWDA |
| A4 | :36 hub nigdy nie odbija ramki nadawcy | PRAWDA |
| A5 | :43 `[hub] assigned nick: <nick>` na **stderr** | PRAWDA |
| A6 | :46 wejście bez nicka to **nowy uczestnik za każdym razem** | PRAWDA |
| A7 | :76 drugi klient bez tokenu dostaje `error` z `suggested_nick` | NIESPRAWDZALNA Z DOKUMENTOWANEJ ŚCIEŻKI |
| A8 | :78 `send`/`frame` nie wypierają własnego listenera | PRAWDA |
| A9 | :84 `board` bez locka, bez kursora, nikogo nie budzi | PRAWDA |
| A10 | :89 `state` maks. 32 znaki | PRAWDA |

**A2 — obie połowy, ale nie tym samym dowodem.** Połowa agentowa: 0 trafień
u nasłuchującego agenta, ramka w logu — zmierzona ślepo. Połowa ludzka:
klient `human` z tokenem DOSTAŁ chat bez wzmianki (`[16] ktos: A2h chat bez
zadnej wzmianki`) — dobita osobno, już **bez ślepoty**, bo obietnica była
wtedy znana obu stronom. Werdykt pełny, dowód drugiej połowy słabszy i tak
oznaczony. Przez jeden etap raportu pozycja stała jako „PRAWDA w połowie
sprawdzonej": zaliczenie całości na podstawie połowy byłoby tym samym
instrumentem, który nie może sfalsyfikować.

**A10 — słabość po naszej stronie, nie po stronie doca.** Predykcja była
dysjunkcją („odrzuci albo utnie"), czyli trudniejsza do sfalsyfikowania niż
powinna. Rozstrzygnęło się na odrzucenie i obietnica jest trafna, ale
predykcję postawiono zbyt luźno — zapisane, żeby następny nie powtórzył.

## Zestaw B — skille zarządzania pokojem (wyciągał agent1, wykonywał ślepo agent2)

Predykcje zamrożone, `sha256` e852dddf… ogłoszony na kanale przed pierwszym
poleceniem, zweryfikowany przed odmrożeniem. Werdykty wystawił agent1;
przepisane tu wiernie, bo pióro trzyma drugi.

| # | obietnica | werdykt |
|---|---|---|
| B2 | `start` o działającym pokoju: „that is NOT an error, that is an answer" | **PRAWDA** (skorygowane 2026-09-02 po pomiarze — patrz niżej) |
| B3 | `stop` zachowuje historię; restart utrzymuje zapisany adres | PRAWDA |
| B4 | `del` bez `--yes-delete` odmawia | PRAWDA (powtórka bez ślepoty) |
| B5 | `--all` + `--name` — odmowa | PRAWDA |
| B6 | `--all` + `--port` — odmowa | PRAWDA |
| B7 | `del --all` wymaga zbioru zgodnego z dyskiem | PRAWDA |
| B8 | `agentmachi kill` pomija własny łańcuch przodków | PRAWDA |
| B9 | odmowa `read` poza końcem logu nazywa ostatni `seq` huba | PRAWDA |
| B10 | odmowa `read --seq` nazywa zakres, który wrócił | PRAWDA (dowód uboczny + powtórka bez ślepoty) |
| B11 | `read` bez locka, bez ruchu kursora, obok żywego `listen` | PRAWDA |
| B12 | hub nie odbija ramki jej nadawcy | PRAWDA |
| B14 | `send` reużywa tożsamości listenera i go nie wypiera | PRAWDA |

B1 (auto-dobór portu) i B13 (mieszany stdout `listen`) nie są tu tabelką —
rozrosły się w Znaleziska 1 i 2.

**B2 — werdykt zdegradowany przez jego własnego autora.** W fazie 4 stał jako
KŁAMIE: doc mówi „to nie błąd, to odpowiedź", a komenda kończy się kodem 1.
Przy review autor zastosował do siebie regułę o dwuznaczności i wycofał się:
doc mówi o **interpretacji komunikatu**, nie o kodzie wyjścia, i nigdzie nie
obiecuje zera. Obserwacja pasuje do obietnicy tak samo dobrze jak predykcja,
więc KŁAMIE było za mocne. Hazard zostaje realny — kod wyjścia czyta automat,
a dla automatu stan docelowy wygląda na awarię — ale to milczenie o granicy,
nie fałsz.

**B2 — KOREKTA PO POMIARZE, werdykt padł DRUGI RAZ.** Pozycja przeszła trzy
etapy i warto, żeby było widać wszystkie, bo pouczający jest dopiero trzeci:

1. `KŁAMIE` — doc mówi „to nie błąd", komenda kończy się kodem 1.
2. `PRAWDZIWA W ZAKRESIE, KTÓREGO NIE PODAJE` — autor sam się wycofał: doc mówi
   o interpretacji komunikatu, nie o kodzie wyjścia, i nigdzie nie obiecuje zera.
3. **`PRAWDA`** — po pomiarze wykonanym dopiero w eksperymencie meta (zadanie 6),
   na wniosek subagenta, który wytknął, że cały ten werdykt stoi na szkodzie
   NIEZMIERZONEJ: „»agent skryptujący po exit code« nie został zaobserwowany;
   to hipoteza o hipotetycznym konsumencie, podana w rubryce ustaleń audytu
   behawioralnego".

Pomiar, którego zabrakło, i który zajął jedno wywołanie:

    agentmachi start --name interwizja      (pokój działa)
    → harness: <error> Exit code 1
      agentmachi: room 'interwizja' is already running (PID 22731).

Szkoda okazała się realna: agent wywołujący komendę bezpośrednio dostaje od
harnessu awarię. Ale ten sam pomiar **obala interpretację**, na której stał
werdykt. Skoro agent naprawdę zobaczy błąd, to zdanie w docu robi dokładnie to,
po co istnieje — uprzedza przed sygnałem, który wystąpi. Doc nie milczy o tej
granicy; doc **jest** o tej granicy. Formułując to za subagentem: „po co
ostrzegać »to nie jest błąd«, jeśli nic nie wygląda na błąd" — obaj audytorzy
czytali niezerowy kod jako dowód PRZECIW obietnicy, a jest on dowodem NA JEJ
RZECZ.

Uwaga wykonawcza z tego samego pomiaru: szkoda zależy od tego, JAK agent wywoła
komendę. Wpięta w większy skrypt — powłoka wychodzi zerem i harness nie zgłasza
nic. Dopiero wywołanie gołe przepuszcza kod wyjścia dalej.

Ta pozycja jest w całym audycie jedyną, której werdykt padł DWA RAZY, i obie
korekty przyszły z zewnątrz autora: pierwsza od peera, druga od subagenta.

**B4 i B10 — dwie pozycje wymagały powtórki z winy konstrukcji polecenia.**
W B4 wcześniej zadziałał strażnik działającego pokoju i gałąź `--yes-delete`
nie została dotknięta; w B10 podana wartość wypadła poza koniec logu i trafiła
w inną gałąź komunikatu. Powtórki wykonano po tym, jak obietnice były już obu
stronom znane — **ślepota była stracona i dowód jest słabszy**, co odnotowano
zamiast przemilczeć.

## Znalezisko 1 — kolizja portu między katalogami HOME

Obietnica (skille zarządzania pokojem): nowy pokój bez `--port` sam dobiera
wolny port i mówi o tym w wyniku.

Zmierzone:

    ~/.agentmachi/ats_create/config.json          {"port": 8766, "bind": "127.0.0.1"}
    <scratch>/audyt-home-13155/t1/config.json     {"port": 8766, "bind": "127.0.0.1"}

Dwa niezależne `AGENTMACHI_HOME` przydzieliły **ten sam port**, bo dobór jest
HOME-lokalny, a porty są globalne dla maszyny. Świeży HOME nie widzi pokoi
z `~/.agentmachi`, więc bierze domyślne 8766 — port produkcyjnego pokoju.
Zaobserwowane dwa razy, w dwóch osobnych katalogach.

Werdykt: **PRAWDZIWA W ZAKRESIE, KTÓREGO NIE PODAJE.** Obietnica nie kłamie —
milczy, że „wolny" znaczy „wolny w TYM `AGENTMACHI_HOME` i niezbindowany w tej
sekundzie". Zatrzymany pokój ma port zarezerwowany we własnym configu i nikt
tego nie respektuje.

Ostrzejsze repro, wykonane niezależnie przez drugiego agenta: `start` bez
`--port` **zapisał do configu port trzymany przez cudzy żywy hub**
(`{"port": 8767}`, gdy 8767 należał do działającej `interwizji`).

**Reguła, ustalona dwoma przebiegami kontrolnymi na czystych HOME** — decyduje,
czy pierwszy kandydat (8766) jest REALNIE ZBINDOWANY, czy tylko zarezerwowany
przez pokój w tym HOME:

- 8766 tylko **zarezerwowany** (pokój istnieje, zatrzymany, nic nie nasłuchuje)
  → „port 8766 is taken — hub gets 8767", config `{"port": 8767}` — a 8767
  trzyma cudzy żywy hub. **Cudzy port nie jest sprawdzany.**
- 8766 **realnie zbindowany** przez obcy proces → „room gets 8768", 8767
  poprawnie ominięte, pokój wstaje.

Czyli krok „port zajęty, biorę następny" przeskakuje porty zarezerwowane
w tym HOME, ale **przy przeskakiwaniu nie sprawdza, czy następny port trzyma
ktoś obcy**. Obie obserwacje z tego audytu (dwa niezależne HOME, oba trafiły
w 8767) pochodzą z pierwszego przypadku.

Kolizja została udowodniona **porównaniem configów, bez uruchamiania**
`ats_create`. Sprawdzenie przez wykonanie skutku byłoby złamaniem własnej
reguły o probach (`AGENTS.md`: probe testuje ZDOLNOŚĆ, nie wykonuje skutku).

## Znalezisko 2 — czytelny `listen` zaczyna się od ściany JSON-a

`howto_default.md:26` obiecuje, że wiadomość drukuje się jako `[seq] nick: line`,
i nazywa ten format „a LOSSY rendering **for humans**".

Zmierzone niezależnie w dwóch pozycjach (A5 i B13): zwykły `listen` wypisuje na
STDOUT najpierw **surowy JSON `session_metadata` z całym howto w jednym
wierszu**, potem surowy `resync_state`, i dopiero potem czytelne linie.

Obietnica o formacie WIADOMOŚCI jest prawdziwa. Milczy o tym, że ten sam
strumień niesie nierenderowane bloki JSON — a to dotyczy dokładnie tego
czytelnika, dla którego format powstał.

Werdykt: **PRAWDZIWA W ZAKRESIE, KTÓREGO NIE PODAJE.**

## Znalezisko 3 — obietnica o kolizji nicka jest lokalnie nieosiągalna

`howto_default.md:76` obiecuje: drugi klient bez tokenu dostaje `error`
z `suggested_nick` i wchodzi pod nim.

Zmierzone: drugi `listen` na tym samym nicku, na tej samej maszynie, **nie
dochodzi do huba**. Pada wcześniej na LOKALNYM locku sesji
(`~/.chat-sessions/<nick>-*.json`), surowym `BlockingIOError` z tracebackiem
Pythona. Ścieżka huba nie zostaje wywołana. Pierwszy nasłuch żyje dalej.

Nie orzekamy, że hub kłamie — z innej maszyny (osobny katalog sesji) zapewne
robi dokładnie to, co obiecuje. Orzekamy, że **obietnica stoi tam, gdzie
czytelnik naturalnie ją sprawdzi, a sprawdzenie da mu co innego**.

Drugie kłamstwo w tym samym miejscu, tym razem twarde: `CLAUDE.md` radzi
„jeśli twój `listen` nie wstaje, przeczytaj `error` zamiast ponawiać".
W tym scenariuszu **nie ma żadnego `error`** — jest traceback. Rada kieruje
czytelnika do artefaktu, który w tej sytuacji nie powstaje.

## Znalezisko 4 — `list` podaje adres cudzego huba, a audytor w to wszedł

Najmocniejsze znalezisko przebiegu, bo powstało przez uderzenie w nie nogą,
a nie przez lekturę.

**Co się stało.** Pokój testowy `t9` dostał w scratch-HOME port 8767 — port
ŻYWEJ `interwizji`. Start się nie powiódł. Mimo to:

    agentmachi list  →  t9   ws://localhost:8767   stopped

`list` podał **adres pokoju, który nie działa**, a pod tym adresem stał cudzy,
żywy hub. Klient wziął ten adres i wysłał — ramki trafiły do produkcji.
W logu `interwizja` stoją do dziś jako ślad: `seq 295-298`, nick `ktos`.
Nie skasowano ich: log jest append-only, a sprzątanie w cudzym logu byłoby
gorsze niż ślad z wyjaśnieniem.

**Co z tego jest wadą produktu.** Adres z `list`/`card` jest w dokumentacji
**źródłem prawdy o pokoju**. Dla pokoju, który nie wstał z powodu kolizji
portu, to źródło wskazuje obcy hub i niczego nie sygnalizuje. Odtworzone
niezależnie przez obu agentów, na dwóch osobnych katalogach HOME.

**Czego wadą produktu NIE jest — odwołanie własnego zarzutu.** Pierwsza wersja
tego raportu twierdziła, że `start` przy zajętym porcie kończy się kodem 0.
**To nieprawda i zostało odwołane.** `start` zachowuje się poprawnie: wypisuje
„port N is already taken by another process — room 'X' has nothing to start on"
i kończy się kodem **1**. Zarzut wziął się z wadliwego pomiaru — patrz M5.

Produkt ostrzegł **dwukrotnie**, komunikatem i kodem wyjścia. Audytor zdusił
komunikat (`>/dev/null 2>&1`) i nie sprawdził kodu. Ciężar tego kroku spada
w całości na wykonawcę, nie na dokumentację.

### Dwa dodatkowe defekty w tym samym wydruku

Blok, którym `start` melduje nieudane wstanie pokoju, zawiera jeszcze dwie
rzeczy — obie zobaczone dopiero przy odtwarzaniu cudzego repro:

**(1) Na NIEUDANYM starcie drukowane jest gotowe zdanie zaproszenia:**

    room 'r2' did NOT come up.
      reason:
              sentence for an agent (join skill):
                "join agentmachi 'r2' (ws://localhost:8767) as agent1"
      is port 8767 free:  agentmachi list

Zdanie w tej postaci ma w całym obiegu **jedno** zastosowanie: wkleić je
agentowi. Tu opisuje pokój, który nie wstał, pod adresem cudzego żywego huba.
Człowiek, który wykona dokładnie to, co produkt podsunął mu po awarii, wyśle
agenta do obcego pokoju. Podpowiedź „is port 8767 free: `agentmachi list`"
domyka pętlę: odsyła po weryfikację do narzędzia, które ten sam błędny adres
potwierdzi.

**(2) Pole `reason:` pokazuje zaproszenie zamiast powodu.**

**KOREKTA DIAGNOZY (2026-09-02, po zadaniu 6).** Pierwsza wersja tej sekcji
mówiła „pole `reason:` jest puste" i liczyła to jako **drugi defekt wydruku**.
Obie rzeczy są nieprawdziwe. Diagnozę postawił subagent z dostępem do kodu,
sprawdzona i potwierdzona w źródle:

- `serve` drukuje kartę pokoju (`cli.py:1091`) **zanim** zawoła `server_main()`
  (`cli.py:1097`), czyli zanim jakikolwiek bind się wydarzy,
- proces dziecka kieruje stdout i stderr do JEDNEGO pliku; stderr leci od razu,
  stdout wypada z bufora dopiero przy wyjściu interpretera — więc w `serve.log`
  traceback stoi WYŻEJ, a karta NIŻEJ,
- `cli.py:1429` bierze `ogon[-3:]`, czyli ostatnie trzy linie — ogon KARTY.
  Pierwsza z nich to pusta linia z `print_card`, stąd „reason:" i nic po
  dwukropku.

Czyli: `reason:` **nie jest puste** — jest wypełnione ogonem karty. Zdania
zaproszenia **nie drukuje `start` po awarii** — drukuje je dziecko, zanim wie,
czy zbinduje, a `start` cytuje je z powrotem **jako powód**. To jest **JEDEN
defekt kodu o trzech objawach**, nie dwa defekty wydruku, i wystąpi przy
**każdej** nieudanej próbie bindu, nie tylko przy kolizji portu.

Konsekwencja dla planu poprawek: to jest **naprawa w kodzie**, a nie
„usunięcie sprzeczności w wydruku". Pierwsza wersja tego raportu skierowała
defekt produktu do backlogu dokumentacji.

**M5 — potok zjada kod wyjścia, a `$?` mierzy nie to, co się myśli.**

    agentmachi start --name t9 > plik 2>&1 ; echo $?      → 1
    agentmachi start --name t9 2>&1 | head -8 ; echo $?   → 0

`$?` po potoku zwraca kod OSTATNIEGO ogniwa. Zero należało do `head`/`sed`,
nie do mierzonego programu. Fałszywy zarzut przeżył jedną publikację i został
obalony dopiero przez **drugiego agenta**, który nie odtworzył wyniku i kazał
zmierzyć bez potoku — mimo że pióro trzymał ten, kto pisze raport o tym, jak
dokumentacja kłamie. Trzeci przypadek tego samego kształtu w jednym dniu:
instrument, który nie mógł sfalsyfikować własnej tezy.

**Ta sama pułapka wystąpiła u OBU agentów, niezależnie, w tym samym audycie** —
u jednego potok zjadł kod wyjścia przy `del`, `tail -3` uciął zakres przy
`read`; u drugiego potok przy `start`. Dwóch wykonawców, jedna klasa błędu,
jeden dzień. To nie jest anegdota o którymkolwiek z nich, tylko właściwość
narzędzia, którym oboje mierzyli, i obowiązuje każdy następny przebieg:
**kod wyjścia mierzy się bez potoku, zakres bez `head`/`tail`.**

### Znalezisko 5 — adres zapisuje się przed potwierdzeniem bindu

Dopisane 2026-09-02 po zadaniu 6; ogniwo **niezależne** od doboru portu
ze Znaleziska 1.

Pokój, który **nigdy nie wstał**, ma już zapisany adres w `config.json`,
a `agentmachi list` podaje ten adres jako adres pokoju. Zmierzone w tym
audycie (`t9`: `{"port": 8767}` w configu, `list` drukuje
`ws://localhost:8767`, pokój nie działa) i odtworzone niezależnie na innej
przyczynie awarii — nieroutowalny bind zamiast kolizji portu — gdzie dobór
portu był **poprawny**, a `list` i tak kłamał.

Znaczenie: naprawa doboru portu (Z1) **nie usuwa** tego ogniwa. Adres trafia
do configu przed potwierdzeniem, że cokolwiek się zbindowało, więc `list`
i `card` mogą wskazywać port, którego ten pokój nigdy nie dostał.

## Znaleziska z samej metody

Trzy rzeczy wyszły nie z doców, tylko z prowadzenia audytu. Zapisane, bo
następny przebieg wejdzie w nie tak samo.

**M1 — „osobne kopie" nie były osobne.** Ścieżka katalogu roboczego wyprowadza
się z identyfikatora sesji, a ten jest u obu równoległych sesji **wspólny**
(`zasady-agentyczne.md`, reguła 17 — wczoraj biła w atrybucję, dziś w płot).
Obaj agenci trafili do jednego katalogu. `rm -rf` jednego z nich skasował
katalogi **działających** hubów drugiego.

Skutek: **osierocone huby** — procesy żywe i nasłuchujące, katalogi danych
skasowane, `agentmachi list` ich nie widzi. Jeden z nich okupował port
produkcyjnego pokoju.

Poprawka, zastosowana w trakcie: katalog kopii dostaje suffiks **unikalny dla
sesji**, a identyfikator sesji nim nie jest — jedyne, co rozróżnia równoległe
sesje, to PID procesu harnessu z łańcucha przodków (`audyt-home-<pid>`).

**M2 — jedna obserwacja poszła do kosza i to jest wynik pozytywny.** Pierwsze
przejście `del --name t1` dało „room 't1' does not exist" — co wyglądało jak
defekt produktu. Było skutkiem cudzego `rm -rf` we wspólnym katalogu.
Powtórzone na rozłącznym HOME dało zachowanie **poprawne**: „room 't1' is
RUNNING — first: agentmachi stop". Raport bez tej kontroli obciążyłby produkt
za wypadek stanowiska.

**M3 — własny skan procesów dał fałszywy alarm.** Pętla szukająca osieroconych
hubów zgłosiła pokój o nazwie `$r` w katalogu produkcyjnym. Nie istniał:
`pgrep` trafił we **własny wrapper powłoki**, którego `argv` zawierało
literalne `--name $r` z pętli akurat uruchamianej. Dokładnie pułapka opisana
w `AGENTS.md` („Argv kłamie") — rozstrzyga plik wykonywalny procesu, nie tekst.

Wystąpiła **ponownie, tego samego dnia, minuty po zacommitowaniu tego raportu**:
skan sprzątający po audycie zgłosił trzy „moje żywe huby", z których wszystkie
były wrapperami powłoki — `pgrep -f` trafił we własne polecenie, a `environ`
wrappera niósł ścieżkę scratcha, po której skan filtrował. Rozstrzygnięcie po
`/proc/<pid>/exe` dało zero. Autor sekcji o tej pułapce wpadł w nią, sprzątając
po jej opisaniu — co jest najmocniejszym dostępnym argumentem, że nie chroni
przed nią wiedza, tylko **wybór dyskryminatora**.

## Co ta para naprawdę dała — cztery razy ten sam mechanizm

Obserwacja `agent1`, zapisana tu, bo znika razem z logiem, a jest mocniejszym
argumentem za pracą w parze niż cokolwiek w sekcji o metodzie:

> **Żaden z nas nie znalazł najważniejszych rzeczy sam.**

Cztery przypadki z tego jednego przebiegu, za każdym razem złapane przez
DRUGIEGO:

| co | kto postawił | kto obalił / zobaczył |
|---|---|---|
| „`start` przy zajętym porcie kończy exit 0" | agent2 | agent1 — nie odtworzył i kazał mierzyć bez potoku |
| „B2 KŁAMIE" | agent1 | wycofane po regule o dwuznaczności, którą postawił agent2 |
| zdanie zaproszenia drukowane po AWARII startu | przeoczone przez agent1 (własny `grep`) | agent2, odtwarzając cudze repro |
| „Wniosek brzmi jak certyfikat" | agent2 (autor akapitu) | agent1 — zobaczył, bo nie on go pisał |

Wzorzec jest jeden i symetryczny: **każdy z nas był ślepy dokładnie na to,
co sam napisał.** Nie z niekompetencji — obaj znali regułę, obaj cytowali ją
sobie nawzajem tego samego dnia. Wiedza o pułapce nie chroniła; chroniło
wyłącznie to, że patrzył ktoś, kto nie miał w danym zdaniu autorstwa.

To jest ta sama rzecz, którą `zasady-agentyczne.md` ma jako **regułę 14**
(„autor nie zwaliduje własnego pokrycia") — tutaj z czterema wystąpieniami
w jednym przebiegu i, co istotne, **po obu stronach pary**. Poprzednie
sformułowanie reguły brzmiało jak ostrzeżenie dla autora. Ten przebieg
pokazuje je jako właściwość układu: para znajduje rzeczy, których żadna
z połówek nie znajdzie, i to działa w obie strony jednocześnie.

### Wniosek operacyjny: parowanie ma być STRUKTURALNE, nie postawą

Skoro chroniło wyłącznie cudze autorstwo, to apel „uważaj na własne
założenia" jest w tym przebiegu **udowodniony jako nieskuteczny** —
czterokrotnie, na dwóch wykonawcach, którzy regułę 14 znali i cytowali ją
sobie nawzajem tego samego dnia.

Zadziałały wyłącznie mechanizmy, które **odbierały autorstwo**:

- ślepe wykonanie krzyżowe — wykonawca nie zna obietnicy, więc nie ma czego
  potwierdzić,
- predykcje zamrożone z `sha256` ogłoszonym przed poleceniami — nie da się
  ich dopisać po zobaczeniu wyniku,
- review sekcji przez tego, kto jej nie pisał — łącznie z pytaniem wprost
  „czy to brzmi jak rozgrzeszenie", na które autor nie mógł odpowiedzieć sam.

Przy planowaniu następnego przebiegu to jest różnica między **„poproście się
nawzajem o sprawdzenie"** a **„zaprojektujcie przebieg tak, żeby nikt nie
oceniał zdania, które sam napisał"**. Pierwsze nie zadziałało ani razu;
drugie zadziałało cztery razy. Formułowanie tego jako apelu do staranności
jest zamianą mechanizmu na dobre chęci.

## Wniosek: ani jedno KŁAMIE — i dlaczego to nie jest certyfikat

Po obu wycofaniach — „`start` kończy exit 0" i „B2 KŁAMIE", **każde
wycofane przez autora dopiero po tym, jak wymusił to drugi** — w kategorii
KŁAMIE nie została ani jedna pozycja **z zakresu `howto` i skille**.
Sprawdzono **24** obietnice (10 zestawu A, 12 w tabeli B, plus B1 i B13, które
nie są w tabeli, bo rozrosły się w Znaleziska 1 i 2). Żadna **z tych, które
sami wybraliśmy**, nie okazała się fałszem.

**Zakres nagłówka jest zawężony świadomie.** Poza `howto` i skillami audyt
uderzył nogą w jedno **twarde kłamstwo** — rada z `CLAUDE.md`, żeby przy
niewstającym `listen` przeczytać `error`, którego w tej sytuacji nie ma
(Znalezisko 3). Nie należy do audytowanego zakresu, ale należy do gorącej
ścieżki, więc nagłówek „ani jedno KŁAMIE" NIE obejmuje całej dokumentacji
i nie wolno go tak cytować.

To zastrzeżenie nie jest kurtuazją, tylko głównym ograniczeniem wyniku —
patrz „Czego ten wynik nie znaczy" niżej.

Znaleziska mieszczą się w dwóch kształtach:

- **prawdziwa w zakresie, którego nie podaje** — dobór portu (prawdziwy
  w obrębie jednego `AGENTMACHI_HOME`), czytelny `listen` (prawdziwy
  o wiadomościach, milczący o blokach JSON przed nimi), `start` o działającym
  pokoju (prawdziwy wobec człowieka, milczący wobec kodu wyjścia, który czyta
  automat),
- **niesprawdzalna z dokumentowanej ścieżki** — kolizja nicka: obietnica
  opisuje hub, a lokalny lock sesji uprzedza go tracebackiem.

Do tego jedna rzecz, która nie jest obietnicą, tylko **wewnętrzną
sprzecznością wydruku**: blok o nieudanym starcie melduje „room did NOT come
up", a dwie linijki niżej podaje gotowe zdanie zaproszenia do tego pokoju,
pod adresem cudzego huba. Żadne zdanie nie jest tam fałszywe z osobna;
niebezpieczne jest ich zestawienie — i to jest **najgroźniejszy pojedynczy
przypadek całego audytu**, mimo że nie zasłużył na etykietę KŁAMIE.

### Co z tym zrobić

Do **dopisania zakres** w trzech miejscach i do **usunięcia sprzeczności**
w jednym wydruku. Dopiero potem uwaga o naturze tej roboty: nie jest to
prostowanie nieprawdy, więc planuje się ją inaczej — nie ma zdania do
skreślenia, jest granica do wypowiedzenia.

I nie jest to robota *łatwiejsza* niż naprawa kłamstw. **Milczenie o granicy
jest trudniejsze do znalezienia i do naprawienia niż fałsz.** Kłamstwo widać
przy pierwszym uruchomieniu i da się je zgrepować. Niewypowiedziany zakres
działa poprawnie aż do dnia, w którym ktoś z niego wyjdzie — a wtedy nie ma
czego szukać, bo żadne pojedyncze zdanie nie jest fałszywe. Dwa z czterech
znalezisk tego przebiegu wyszły dopiero wtedy, gdy audytor własną nogą wszedł
poza granicę, o której doc milczał.

### Czego ten wynik nie znaczy

„Ani jedno KŁAMIE" jest **po części własnością tego, co wybraliśmy do
audytu** — a wybieraliśmy my, nie los. Dwa mechanizmy, oba pchają wynik
w tę samą stronę:

- **Protokół premiuje obietnice ostre.** Obaj wyciągaliśmy wyłącznie te,
  którym da się postawić warunek falsyfikacji. Obietnica mglista — napisana
  tak, że nie sposób powiedzieć, co by ją obaliło — miała mniejszą szansę
  trafić na listę. A mglistość jest dokładnie tym miejscem, w którym
  kłamstwo się chowa. Metoda ma **systematyczne niedopróbkowanie tam, gdzie
  ryzyko jest największe.**
- **Gorąca ścieżka to najczęściej poprawiany fragment doców w tym repo.**
  `howto` był prostowany wielokrotnie, skille przechodziły review. Brak
  kłamstw w części najlepiej pilnowanej **nie uogólnia się na resztę.**

Ten wynik jest więc przejściem po **wąskim, najlepiej utrzymanym wycinku,
metodą, która premiuje obietnice ostre** — nie orzeczeniem o dokumentacji
produktu jako całości. Cytowany bez tego akapitu staje się certyfikatem,
którym nie jest.

## Czego ten audyt NIE objął

(ograniczenia WYNIKU są wyżej, w „Czego ten wynik nie znaczy"; tu — zakres)


- Nie objął `CLAUDE.md` ani `AGENTS.md` jako całości — to ścieżka nasza, nie
  obcego, i rozdęłaby listę. Jedno zdanie z `CLAUDE.md` weszło tylko dlatego,
  że wypadło w tym samym miejscu co Znalezisko 3.
- Nie objął obietnic wymagających żywej sesji Codeksa (Goal mode, `codex-wait.sh`,
  „koniec polecenia nie budzi modelu"). Kategoria NIESPRAWDZALNA Z TEJ STRONY —
  lista gotowa do dobicia, gdy Codex wejdzie na kanał.
- Nie jest pomiarem porównawczym i nie ma modelu zerowego. To przejście po
  liście obietnic, nie eksperyment z ramionami.
