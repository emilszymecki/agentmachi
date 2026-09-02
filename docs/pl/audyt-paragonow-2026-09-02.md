# Audyt paragonów — dziesięć najstarszych reguł, 2026-09-02

Zlecenie człowieka: *„weź dziesięć najstarszych reguł z zasad-agentycznych
i daj każdą trzem agentom osobno: odtwórz pomiar, na którym stoi ta reguła.
Które się reprodukują, które zgniły"*. Repo, którego marką są paragony,
dostało audyt paragonów.

**Metoda:** 30 niezależnych przebiegów, po trzy na regułę. Każdy agent dostał
wyłącznie swoją regułę, ten sam brief, zakaz pisania czegokolwiek i zakaz
ruszania żywych hubów. Reguły 1–5 prowadził `agent4`, reguły 6–10 `agent1`.
Ustalenia obu połówek są tu zebrane; przy każdej napisano, czyja jest.

Materiał: [`zasady-agentyczne.md`](zasady-agentyczne.md).

## Wynik

|reguła|werdykt|zgodność trzech przebiegów|
|---|---|---|
|1. Remis rozstrzyga porządek bajtowy|reprodukowana|3/3|
|2. Własność zasobu zamiast rangi|nieodtwarzalna|3/3|
|3. Ustępstwo odwzajemnione|**brak paragonu**|3/3, niezależnie|
|4. Cofnięcie deklaracji to wyścig|nieodtwarzalna|3/3|
|5. Deklaracja nie jest faktem|reprodukowana|3/3|
|6. Weryfikuj w źródle|częściowo|3/3|
|7. Board to `pull`, nie `push`|częściowo|**2:1 — rozbieżność**|
|8. Deklaruj zakres, zanim ruszysz|częściowo|3/3 werdykt, rozbieżnie co do dowodu|
|9. Koszt walidacji|częściowo|3/3|
|10. Zgłaszający sprawdza zapis|częściowo|3/3|

**Żadna reguła nie została obalona.** W trzydziestu przebiegach padło jedno
trafienie w klasę „uzasadnienie przeżyło mechanizm" — i to poza zakresem
pytania (niżej, sekcja o `protocol.py:265`).

Rozbieżności nie uśredniamy. Przy regule 7 dwa przebiegi orzekły
„reprodukowana", jeden „częściowo", **przy identycznych faktach**: spór idzie
o próg, nie o pomiar. Czy „mechanizm trzyma, ale liczby nie da się przeliczyć"
jest reprodukcją, czy tylko potwierdzeniem wniosku z innego źródła. Uśrednienie
skasowałoby jedyną rzecz, którą replikacja wnosi ponad jedno przejście.

## Trzy stopnie paragonu

Oś wypracowana w trakcie (`agent4`, po korekcie zgłoszonej przez `agent1`).
Pierwsza wersja mierzyła obecność etykiety `*Dowód:*` i była błędna: reguła 6
etykiety nie ma, a ma najmocniejsze paragony w dziesiątce, natomiast reguła 2
etykietę ma i nie podaje żadnego wskaźnika. Do tego reguła 5 pisze
`*Dowód —` z myślnikiem, więc **sam pomiar etykiety zależy od wybranego
wzorca**. Etykieta nie jest kryterium.

|stopień|co to znaczy|reguły|
|---|---|---|
|osiągalny|wskaźnik prowadzi dziś tam, gdzie obiecuje|6 (`client_session.py:256`)|
|cytowany, nieosiągalny|`seq NN` z kanału, którego nie ma|1, 4, 5, 6, 7, 10|
|sama relacja|zdarzenie opisane, bez wskaźnika|2, 3, 8, 9|

W całej dziesiątce jest **jeden** paragon weryfikowalny dziś pod podanym
adresem. Przetrwał 39 dni — i w tym czasie zdążył raz zgnić i raz zostać
naprawiony.

## Główny wynik: zgniło doręczanie i archiwum, nie uzasadnienia

Obie połówki doszły do tego osobno, z dwóch różnych stron.

**Archiwum.** Każda z dziesięciu cytuje ramki z kanału `sens` (`seq 28`, `30`,
`61`, `71`, `77`, `94`, `96`, `98`). Żaden z trzydziestu przebiegów nie
dosięgnął ani jednej. Powód nie jest wypadkiem: `.gitignore` wymienia
`events.jsonl`, więc **log huba nigdy nie mógł trafić do repo**. Numery `seq`
w dokumencie nie zgniły — od dnia wpisania nie prowadziły nigdzie, do czego
mógłby dojść ktoś z zewnątrz. Kanał `sens` skasowano; szersze sprzątanie
odnotowuje
[`experiments/board-pull-weryfikacja-escrow.md`](experiments/board-pull-weryfikacja-escrow.md).

**Doręczanie.** `agentmachi/cli.py` ma `DEFAULT_RULES = ""` (od `6a42c68`,
2026-07-29, „hub jest mechaniką, nie ustrojem"), a `rules.md` świeżego pokoju
ma zero bajtów. Komentarz obok obiecuje, że zasady współpracy „należą do
skilla" — sprawdzone w obu wariantach skilla: nie przeszły tam. Skutek
zmierzony: reguła 1 dociera do obcego agenta w połowie (sam `seq`, bez
porządku bajtowego nicków — czyli bez tej części, której całe uzasadnienie
brzmi „musi być przesądzone, bo inaczej obaj uznają, że wygrali"). Reguły 2,
3 i 4 nie docierają wcale.

Reguły żyją wyłącznie w plikach o pracy nad TYM repo. Agent na innej maszynie
dostaje pusty `rules.md` i połowę jednej reguły.

## Co mechanizmy robią naprawdę

Wszędzie, gdzie mechanizm dało się wykonać, wykonał się zgodnie z regułą.
Przebiegi wywoływały kod wprost, bez startowania hubów:

- **7** — `status` nie idzie do agenta, chat bez wzmianki też nie
  (`chat/server.py`, gałąź `role == "human"`). Filtr jest nietknięty od
  `e29a11d` (2026-07-26), więc ciągłość jest **zmierzona**, nie założona.
- **9** — hub waliduje wyłącznie kształt ramki. `protocol.validate` przyjmuje
  bez słowa „X5 na polu które już zajęte" i „plansza pełna po 1 ruchu".
  Identycznie w `a2f6c85` i w HEAD: twierdzenie trzyma na obu końcach okna.
- **10** — ucinanie powiadomień żyje (`protocol.TRUNCATION_MARK`), `seq`
  przeżywa cięcie, a `send.py` niesie pomiar z pokoju `meadow2`: 7 z 8 ramek
  budziło odbiorcę bez własnego numeru, zanim `seq` przesunięto na początek.
- **6** — obrona przed przejęciem własnego listenera działa i ma zielony test.

Jeden wyjątek prawdziwy: **reguła 8**. Jej wniosek brzmi „mechanizm, który
mieliśmy". Pole `subject` na boardzie faktycznie istniało dobę przed sesją
(`2ff9a92`, 2026-07-24) i działa dziś — ale nośnik normy zniknął. Zdanie jest
więc prawdziwe o polu i fałszywe o tym, co agent dostaje przy wejściu.

## Trzy paragony, które mówią o sobie nieprawdę

**Reguła 6.** Cytat `client_session.py:256` trafia dziś, ale tylko dlatego, że
go naprawiono. Oryginał wskazywał `:203` i **był wtedy poprawny**; zgnił przez
rozrost pliku. Naprawił to `9d7fd6e` (2026-08-22) — i uzasadnił się fałszywie:
twierdzi, że „cytat nigdy nie był w źródle sprawdzony", a sprawdził `883f7f9`
(commit przeprowadzki `docs/` → `docs/pl/`) zamiast `a2f6c85` (commit
wpisujący). Naprawa dobra, opis naprawy nieprawdziwy.

**Reguła 10.** „W pierwszej wersji tego dokumentu zabrakło dwóch rzeczy" —
trzy przebiegi sprawdziły to samo: najstarszy commit zawiera już obie, a
`git log -S` nie pokazuje żadnego późniejszego dopisania. „Pierwsza wersja"
była szkicem na kanale, który nigdy nie wszedł do gita. Git trzyma stan **po**
naprawie, więc pominięcia nie da się dziś ani potwierdzić, ani przypisać.

**Reguła 8.** Zdarzenie ma niezależnego, **wcześniejszego** świadka: `f4efbf5`
(2026-07-23) opisuje je tymi samymi słowami, ale podaje inną sesję (dogfood
B5, nie `sens` z 25 lipca), inny wyzwalacz (pilne zgłoszenie operatora, nie
„lepszy PoC niż talk") i inny zasób: dwie równoległe implementacje `restart`,
nie „dwie równoległe pamięci". Ocalały bliźniak żyje (`2966cd3`, pięć minut
przed commitem reguły). Rdzeń zdarzenia jest więc potwierdzony **mocniej** niż
relacją autorów, a wszystkie szczegóły paragonu są przeniesione z innego dnia.

## Po co były trzy agenty na regułę

To jest ta część, której jedno przejście nie daje, i to ona płaci za
trzydzieści przebiegów.

**Reguła 8: dwóch z trzech agentów znalazło `f4efbf5`. Trzeci nie i napisał,
że zdarzenie „nie ma ŻADNEGO niezależnego artefaktu".** Ten sam brief, to samo
repo, przeciwne wnioski o *istnieniu* dowodu. Przy jednym przejściu raport
twierdziłby jedno albo drugie i brzmiałby tak samo pewnie.

Ten trzeci nie był gorszy — miał inne pokrycie: jako jedyny znalazł `2ff9a92`
i twardo potwierdził przesłankę o mechanizmie. Uśrednienie trzech głosów
skasowałoby oba znaleziska naraz.

Dwie poprawki do treści reguł wyszły od pojedynczych agentów i nie powtórzyły
się u pozostałych dwóch (czyli przy jednym przejściu: 1/3 szansy na każdą):

- **reguła 1** — „łamacz symetrii był dostępny od pierwszej sekundy i ani razu
  nieużyty" jest dowodem na *istnienie problemu*, nie na skuteczność
  lekarstwa. Krok drugi reguły (porządek bajtowy) nie ma paragonu od
  pierwszego dnia: nikt nigdy nie zmierzył, że działa, bo w sesji źródłowej
  ani razu go nie użyto.
- **reguła 2** — „przekazywalny jedną ramką" trzyma się *warunkowo*: bez
  wzmianki przekazanie ląduje w logu i nikogo nie budzi. Reguła tego warunku
  nie zawiera.

## Znalezione po drodze, poza zakresem pytania

**`chat/protocol.py:265`** uzasadnia poprawne zachowanie odwołaniem do „rules
kanału pkt 15" — listy skasowanej `6a42c68` w 2026-07-29. To jedyne trafienie
w „uzasadnienie przeżyło mechanizm" w całym badaniu i jedyne, które siedzi
w kodzie, a nie w dokumentacji.

**Ostrzeżenie huba o nieznanym nicku mówi więcej, niż zrobił mechanizm.**
Dwie sąsiednie gałęzie w `chat/server.py` odpowiadają inaczej na to samo
pytanie: gałąź grupowa mówi „NO AGENT wakes up **through it**" i wymienia
trzeciego adresata („mentions of participants who do exist"), nickowa mówi
„NO AGENT woke up" i trzeciego adresata pomija. Złapane na żywym pokoju:
hub powiedział „żaden agent się nie obudził" w chwili, gdy budził `agent1`
dwiema poprawnymi wzmiankami w tej samej ramce.

Komentarz nad tą gałęzią zapisuje, że ten sam błąd złapano tu już raz
i naprawiono **węziej, niż występował** — poprawka objęła ludzi, bo scenariusz,
na którym błąd znaleziono, miał tylko człowieka. Test na to istnieje
(`tests/test_server_integration.py`,
`test_ostrzezenia_mowia_co_sie_stalo_z_ramka_a_nie_tylko_co_jest_nie_tak`),
**nosi kontrprzykład we własnym scenariuszu** — wysyła `"@beta @nikt-taki hej
$upiory"` i dowodzi, że `beta` ramkę dostał — i przechodzi, bo o treści obu
ostrzeżeń sprawdza tylko `"log" in t.lower()`. Zielone przechodziło obok
kontrprzykładu, który samo wygenerowało.

**Granica wzmianki nie dociera do nikogo spoza tego repo.** `parse_mentions`
wymaga spacji przed `@`, więc `` `@nick` ``, `(@nick)` i `**@nick**` nie budzą
nikogo. Zachowanie jest **zamierzone** i opisane w `AGENTS.md` — ale wyłącznie
tam. Zmierzone na trzech poziomach: `agentmachi/howto_default.md` o granicy
milczy, żywy pokój wydaje bajtowo ten sam plik i też milczy, drzewo robocze
zgadza się z commitem. Wchodzący dostaje howto bez tej informacji, a przy
nieznanym nicku hub przynajmniej ostrzega — tu nie ostrzega nic, bo wzmianka
nigdy nie powstaje.

Defektu z tego **nie zrobiliśmy**: pomiar na logu pokoju dał 123 ramki i zero
przypadków, w których ktoś naprawdę przegrał na tej granicy. Konstytucja każe
wtedy zapisać obserwację zamiast budować — ta sama bramka, która wycofała
limit tempa w hubie 2026-08-06.

## Błąd w briefie, do protokołu

Brief nie podawał komendy do suity, więc wszystkie trzydzieści przebiegów
uderzyło w `No module named pytest` (pytest nie jest zainstalowany w `.venv`;
`CLAUDE.md` podaje `uv run --with pytest`). Większość obeszła to, wykonując
kod wprost; dwa przebiegi same znalazły drogę. **Powtarzając to badanie,
podaj komendę do suity w briefie** — inaczej mierzy się pomysłowość agentów
w omijaniu środowiska.

## Czego ten audyt NIE sprawdził

Nie sprawdzaliśmy, czy opisane zdarzenia naprawdę zaszły — tego nie da się
sprawdzić i żaden przebieg tego nie obejdzie. Log kanału `sens` nie istnieje
i nie mógł istnieć w repo. Sprawdzaliśmy wyłącznie, **czy fizyka, na którą
reguły się powołują, nadal działa**. Działa.
