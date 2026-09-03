# Czy subagent naprawdę tego nie złapie — pomiar 2026-09-02

**HEAD:** `9aa1e7a` — commit zapisujący ten plik, **proxy, nie HEAD
przebiegu**. Przebieg szedł 2026-09-02 na kanale `interwizja`, którego log
skasowano 2026-09-03; zachowana kopia jest pokompaktowa (178 ramek z zakresu
654 numerów) i nie niesie HEAD-a z godzin tego pomiaru.

Zadanie operatora brzmiało: *„macie dzień — uzgodnijcie jeden pomiar, którego
temu projektowi brakuje, i zróbcie go"*, z jawnie postawionym zastrzeżeniem, że
**najciekawszy jest wybór, nie liczba**, i z jawnym ryzykiem: „wybiorą płytko".

Ten plik zapisuje więc dwie rzeczy osobno: **co wybraliśmy i dlaczego**, oraz
**co z tego wyszło**.

## Co wybraliśmy

`zasady-agentyczne.md` ma sekcję „Czego NIE udowodniliśmy" i stawia w niej lukę
wprost: brak pomiaru przewagi kanału nad jednym agentem z subagentami na
problemie spoza tego projektu. Obaj poszliśmy tam pierwsi i obaj uznaliśmy, że
tej luki **nie da się w jeden wieczór domknąć uczciwie** — wymaga problemu
z zewnątrz, dwóch ramion, więcej niż jednego pokoju na warunek i modelu
zerowego, czego wymaga nasz własny `experiments/README.md`.

Zamiast tego wzięliśmy zdanie stojące trzy akapity niżej, w sekcji „Co mamy
naprawdę", postawione jako **fakt**:

> „Subagent tego nie złapie, bo dziedziczy hipotezę razem z pomiarem."

To zdanie nie miało za sobą żadnego pomiaru, a jest nośne: uzasadnia, **po co
komu peer**, skoro subagent jest tańszy, szybszy i nie wymaga huba, protokołu
ani całego tego produktu. Jeśli subagent to jednak łapie, najmocniejszy argument
projektu za sobą samym jest pusty.

**Jak rozstrzygnęliśmy wybór.** Padły dwie propozycje. Druga — klasyfikacja
znalezisk dwóch dni na „żywość konieczna / wymiana wystarczy / jeden agent" —
celowała ostrzej w produkt, bo pytała, czy zarobiła na siebie *żywość* kanału,
a nie sama obecność drugiego agenta. Odpadła na kryterium, które sami
postawiliśmy: **co ją obala, jeśli wyjdzie odwrotnie.** Retrospektywna
klasyfikacja własnego przebiegu przez uczestników jest sądem, nie pomiarem —
przy każdym wyniku dało się powiedzieć „bo akurat".

Po drodze wpadliśmy w pat opisany w konstytucji: **obaj ustąpiliśmy sobie
nawzajem**, każdy uznając propozycję drugiego za lepszą. Stan bez właściciela
przerwał ten, kto miał podstawę przyjąć — nie ten, kto miał niższy `seq`.
`seq` celowo nie został użyty: to nie była kolizja o zasób, tylko decyzja
projektowa, a operator napisał „uzgodnijcie". Sięgnięcie po `seq` zamieniłoby
uzgodnienie na loterię kolejności ramek.

## Metoda

Materiałem są **cztery udokumentowane przypadki** z dwóch dni pracy
(`audyt-szwow-docow-2026-09-02.md`, sekcja o parze), w których każdy z agentów
był ślepy dokładnie na to, co sam napisał, a złapał to drugi.

- **Ramię A** — już się odbyło, obserwowane i zapisane: peer złapał 4/4.
- **Ramię B** — subagent autora, **dziedziczący**: dostaje brief autora tak, jak
  dostałby go realnie w trakcie tamtej pracy, wraz z jego ramką, jego werdyktem
  i jego danymi — plus artefakt. Porównanie jest **wewnątrz artefaktu**: ten sam
  tekst, ten sam autor, dwaj recenzenci.

**Dlaczego brief, a nie fork sesji.** Fork odziedziczyłby całą rozmowę z tego
dnia, w której odpowiedzi padły wprost — mierzyłby podanie rozwiązania, nie
dziedziczenie hipotezy. Zdanie z repo mówi o dziedziczeniu hipotezy *razem
z pomiarem*; brief zawierający ramkę, werdykt i dane autora jest dokładnie tym.

**Zabezpieczenia, ustalone przed startem:**

- **autor nie pisze promptu do własnego przypadku** — zna odpowiedź, więc
  przeciekłaby mu do promptu i zmierzylibyśmy prompt, nie subagenta. Prompty
  krzyżowe, neutralne („zrecenzuj, zgłoś problemy"), bez sugestii, że jest co
  znaleźć,
- **predykcje zamrożone na dysku i ogłoszone `sha256` na kanale przed
  odpaleniem czegokolwiek**; hashe zweryfikowane publicznie przed odmrożeniem,
- **kryteria trafienia spisane z góry**, osobno na każdy przypadek, z jawnym
  wskazaniem, co trafieniem NIE jest („ogólne uwagi stylistyczne" nie liczą się,
  nawet gdy trafne),
- **zakaz czytania repo** w promptach: raport z odpowiedziami do wszystkich
  czterech przypadków jest zacommitowany, więc subagent z dostępem do plików
  rozwiązałby zadanie przez znalezienie cudzej odpowiedzi. Kontrola dodana po
  starcie jednego z ramion — pierwszy, niekontrolowany przebieg został z wyniku
  głównego wyłączony i oznaczony osobno,
- **bramka odrzucenia, wiążąca:** ≥3 trafienia na 4 → zdanie z repo jest
  fałszywe i tak zostaje zapisane, bez „to były łatwe przypadki".

## Wynik: 4/4. Bramka odpalona

Subagenty złapały **wszystkie cztery** martwe pola, w przebiegach
kontrolowanych, bez użycia narzędzi.

**Obie predykcje sfalsyfikowane własnymi, prerejestrowanymi warunkami:**

| | predykcja | wynik |
|---|---|---|
| agent1 (`sha256 8be6a102…`) | 1 z 4 | 4 z 4 — sfalsyfikowana |
| agent2 (`sha256 d57769ad…`) | 1–2 z 4, z podziałem na martwe pola „mechaniczne" (złapie) i „osądu" (nie złapie) | 4 z 4 — sfalsyfikowana liczbowo **i** w mechanizmie: oba przypadki „osądu" trafione |

Mechanizm z tezy — „nie złapie, **bo dziedziczy** hipotezę" — nie zadziałał ani
razu. Subagenty dostawały brief z gotowym werdyktem autora jako punkt wyjścia
i **rozmontowywały go**, zamiast go dziedziczyć.

## Czego subagenty nie tylko złapały, ale znalazły więcej niż para

To jest ostrzejsza część wyniku niż licznik. Przykłady, których **żaden
z dwóch agentów nie zobaczył przez dwa dni**:

- *Niezerowy kod wyjścia jest prawdopodobnie POWODEM, dla którego to zdanie
  w docu w ogóle napisano — po co ostrzegać „to nie jest błąd", jeśli nic nie
  wygląda na błąd.* Obaj czytali ten kod jako dowód **przeciw** obietnicy;
  jest dowodem **na jej rzecz**. Doprowadziło to do korekty werdyktu
  w wypchniętym już raporcie (`ea5dfc8`).
- *„Agent skryptujący po exit code" nie został zaobserwowany — to hipoteza
  o hipotetycznym konsumencie, podana w rubryce ustaleń audytu behawioralnego.*
  Audyt, którego cała teza brzmi „sprawdzone zachowaniem", miał w środku
  twierdzenie o szkodzie opartej na niczym. Zmierzone dopiero po tym zarzucie.
- *Sprawdzian `is port 8767 free: agentmachi list` nie może wypaść negatywnie* —
  etykieta pyta o port, komenda odpowiada listą pokoi; dla procesu spoza
  agentmachi potwierdzi fałszywą tezę „port wolny". Ostrzejsze niż ustalenie
  pary, która nazwała to „domknięciem pętli".
- *Zerowy wynik z próby 22 jest dowodem SŁABSZYM, nie mocniejszym* — i pytanie,
  które z tego wynika: **czy którykolwiek z tych testów mógł wyprodukować wynik
  KŁAMIE?** Po obu wycofaniach odpowiedź brzmi: nie. To pytanie o **moc
  instrumentu** całego audytu, i nie postawił go żaden z audytorów.
  (Liczba „22" pochodzi z cytowanego subagenta, który liczył za naszym błędnym
  licznikiem — sprawdzonych obietnic było **24**, patrz `f313c7e`. Subagent
  odziedziczył tu nasz błąd i to jest jedyne miejsce, w którym dziedziczenie
  zadziałało tak, jak przewidywała obalona teza.)
- *Brak kontroli negatywnej: nikt nie pokazał, że aparatura pomiarowa w ogóle
  UMIE wypisać wynik negatywny.* Przez dwa dni sprawdzaliśmy, czy **produkt**
  umie zawieść, i ani razu, czy **nasz instrument** umie pokazać porażkę.

## Ramię bez kontroli — i dlaczego znalazło więcej

Pisze `agent2`, bo to jego przebieg, jego błąd wykonawczy i jego artefakt.
Autor pliku recenzuje.

**`agent2` nie zastosował kontroli od początku.** Pierwsze dwa subagenty odpalił
BEZ zakazu czytania repozytorium — a zacommitowany raport audytu zawierał
gotowe odpowiedzi do wszystkich czterech przypadków. Kontrolę dołożył
`agent1`; powtórki poszły z nią i to one weszły do pomiaru. Bez tego zdania
plik sugerowałby, że ramiona były równe od startu. Nie były.

**Niekontrolowany subagent, mając narzędzia, znalazł rzeczy, których nie ma
żaden przebieg kontrolowany ani żaden z dwóch agentów.** 21 i 25 wywołań
narzędzi, praca w izolowanym `AGENTMACHI_HOME`, produkcja nietknięta
(sprawdzone po fakcie: jeden żywy hub, zero nowych ramek w logu):

- **przyczyna „pustego `reason:`" w kodzie** — `serve` drukuje kartę pokoju
  (`cli.py:1091`) zanim zawoła `server_main()` (`:1097`); dziecko pisze stdout
  i stderr do jednego pliku, stderr od razu, stdout dopiero przy wyjściu, więc
  traceback ląduje wyżej niż karta; `:1429` bierze `ogon[-3:]` — ogon karty.
  Audyt opisywał trzy objawy jako dwa defekty wydruku. To **jeden defekt kodu**,
  występujący przy każdej nieudanej próbie bindu.
- **mechanizm Znaleziska 1** — `_wybierz_port` świadomie nie odpytuje systemu
  (żeby testy nie były flaky), więc przy przeskoku ląduje na porcie żywego huba.
  Para nazwała objaw; subagent znalazł przyczynę i miejsce w kodzie.
- **pięć błędów w zacommitowanym audycie**: zły licznik (22 zamiast 24),
  nagłówek „ani jedno KŁAMIE" sprzeczny ze zdaniem „drugie kłamstwo, tym razem
  twarde" 170 linii wyżej, nieprawdziwa atrybucja wycofań, błędna diagnoza
  najgroźniejszego defektu i niezgłoszone przesunięcie skali werdyktów
  w trakcie przebiegu. Wszystkie potwierdzone w źródle przez obu agentów;
  poprawione w `f313c7e`.
- **wada artefaktu `agent2`** — do przypadku 1 wkleił jedną linię
  z czterolinijkowego komunikatu i port, który bez jawnego `--port` nie mógł
  się pojawić. Jego „rekonstrukcja stanu z tamtej chwili" była edytowana,
  czego nie zauważył, wysyłając ją drugiemu do promptu.

### Co z tego wynika i jest niewygodne

Sformułowanie „ramię bez kontroli znalazło więcej" jest za słabe i trzeba je
postawić ostrzej, bo prawdziwa wersja obciąża projekt pomiaru, a nie wykonawcę:

> **Ramię kontrolowane było STRUKTURALNIE NIEZDOLNE do znalezienia większości
> tych rzeczy.**

Kontrola brzmiała „nie czytaj plików, nie przeszukuj repozytorium". Pięć błędów
audytu leży **w pliku audytu**, a przyczyny defektów **w plikach kodu**.
Subagent kontrolowany nie znalazł ich nie dlatego, że był gorszy — tylko
dlatego, że zabroniliśmy mu tam zajrzeć.

Czyli nie jest tak, że jedno ramię wypadło lepiej. Jest tak, że **kontrola
wycięła całą KLASĘ znalezisk** — przyczyny w kodzie i sprzeczności między
dokumentami — zostawiając wyłącznie krytykę rozumowania z podanego tekstu.
Nasza „kontrola porównywalności" była **jednocześnie ograniczeniem zakresu**,
i żaden z nas tego nie zauważył, wprowadzając ją; najmniej ten, kto ją dołożył.
Przebieg metodologicznie gorszy dał wynik konsekwentniejszy nie przez brak
kontroli, tylko przez dostęp, który kontrola odbierała.

Wniosek praktyczny, osobny od licznika: **narzędzia zmieniają nie to, CZY
subagent złapie, tylko CO znajdzie.** Z narzędziami idzie do kodu i wskazuje
przyczyny. Bez narzędzi kwestionuje rozumowanie. Oba są potrzebne i mierzą co
innego — kto odpala subagenta do recenzji, powinien wiedzieć, który tryb
zamawia.

Ten przebieg miał trafić do raportu jako „obserwacja uboczna". Trafia jako
osobny wynik, bo znalazł więcej niż ramię główne.

## Wniosek

**Zdanie „Subagent tego nie złapie, bo dziedziczy hipotezę razem z pomiarem"
jest w świetle tego pomiaru FAŁSZYWE.** Zapisane zgodnie z bramką ustaloną
przed startem, bez łagodzenia.

Co z tego NIE wynika: że subagent zastępuje peera. Ramiona nie są dopasowane —
peer działał w toku pracy, z pełnym kontekstem dnia i bez zaproszenia do
recenzji; subagent dostał zimny artefakt i **jawne polecenie „zgłoś problemy"**.
Możliwe, że zmierzyliśmy nie „subagent vs peer", tylko **„czy ktokolwiek
poproszony wprost o krytykę ją znajdzie"** — a wtedy prawdziwym wnioskiem jest,
że w pracy nikt nas o tę krytykę nie prosi, i to jest rola, którą peer pełnił
przypadkiem. Tego ten pomiar nie rozstrzyga i nie udaje, że rozstrzyga.

## Czego ten pomiar nie obejmuje

- **N=4**, cztery przypadki z jednego dnia, wybrane dlatego, że były
  udokumentowane — czyli dlatego, że peer je złapał. Przypadki, których nie
  złapał nikt, nie mają jak trafić do tej próby. Selekcja działa na korzyść
  ramienia A i mimo to ramię B wyszło na remis.
- **Self-hosting**: materiał pochodzi z tego projektu, o czym `zasady-agentyczne.md`
  ostrzega osobnym zdaniem („użycie produktu do naprawiania produktu zawsze
  wygląda jak sukces produktu").
- **Ramię B2 nie zostało wykonane.** Subagent ze świeżym kontekstem, bez
  dziedziczenia, miał odróżnić, czy „dziedziczenie" jest naprawdę mechanizmem.
  Zabrakło wieczoru. Bez niego wiemy, że teza jest fałszywa, ale nie wiemy,
  czy fałszywa jest jej *przyczyna*, czy tylko *wniosek*.
- Wielka luka — przewaga kanału nad jednym agentem z subagentami na problemie
  spoza repo — **zostaje otwarta**. Ten pomiar dotyka jednego mechanizmu
  wewnątrz niej.
