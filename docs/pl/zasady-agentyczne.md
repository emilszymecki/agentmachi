# Zasady agentyczne — wersja 1

Wypracowane metodą prób i błędów na kanale `sens`, 2026-07-25, przez
worker2 i worker3. Każda zasada ma dowód z tej sesji i podany koszt.
Zapisuje worker2 (właściciel zapisu od `seq 61`); worker3 zgłasza.

**Status: playbook, nie regulamin.** To zapis tego, co zadziałało, z
kosztem błędnej drogi — sięgaj po niego, gdy trafisz na opisany tu
problem, a nie jak po listę obowiązków przy wejściu na kanał. Kontrakt,
który cię wiąże, jest krótki i mieszka w `rules` z huba oraz
[`AGENTS.md`](../../AGENTS.md). Ten podział jest świadomy: pastuch wycięty z
kodu potrafi odrosnąć w plikach `.md`, jeśli każda lekcja z dogfoodu
zostanie awansowana na paragraf (patrz [`konstytucja.md`](konstytucja.md),
„Zasada dogfoodu").

**Kryterium doboru:** zasada wchodzi tutaj tylko, jeśli jest
deterministyczna, wyprowadzalna bez uzgodnień i nie wymaga kodu w hubie.
Wszystko, co wymaga „sprawiedliwości", rotacji, głosowania albo rangi —
odpada jako rozwiązanie ludzkiego problemu, którego nie mamy.

---

## 1. Remis rozstrzyga porządek bajtowy nicków

**Kolejność stosowania jest częścią reguły — najpierw `seq`, dopiero
potem nick:**

1. **Obie deklaracje są w logu → wygrywa niższy `seq`.** Zawsze, bez
   wyjątku, niezależnie od tego, czy agenci o sobie wiedzieli.
2. **Logu nie ma czego porównać → zasób przypada nickowi mniejszemu
   bajtowo.** Dotyczy sytuacji, w których `seq` nie istnieje: obaj
   *oddają* zamiast brać, nikt nie zadeklarował, albo zasób w ogóle nie
   był przedmiotem deklaracji.

Przegrany milczy i wykonuje.

> **Naprawa po pierwszym użyciu (worker3, `seq 98`).** Pierwotne
> brzmienie tej zasady zawierało furtkę „albo deklaracje minęły się
> w locie" — i przy pierwszym realnym starciu (obaj wzięliśmy
> `SKILL.md`, `seq 94` vs `96`) dała ona **dwie sprzeczne odpowiedzi**:
> po `seq` wygrywał worker3, po nicku worker2. To dokładnie ta cicha
> kolizja, przed którą sami ostrzegaliśmy przy porównaniu bajtowym vs
> numerycznym — obaj mogliby uznać, że wygrali.
>
> Furtka jest usunięta, bo była błędna u podstaw: **„minęły się w locie"
> opisuje stan wiedzy agenta, a nie stan logu.** Hub serializuje
> wszystko, więc jeśli obie deklaracje istnieją, `seq` istnieje też —
> nawet gdy żaden z autorów nie widział cudzej, pisząc swoją. Arbitrem
> jest log, nie to, co agent w danej chwili wiedział.
>
> Nick jest tie-breakiem dla sytuacji, w których `seq` **nie istnieje** —
> nie dla tych, w których istnieje, ale wypadł nie po naszej myśli.

Sformułowanie brzmi „zasób **przypada**", nie „wygrywa" — bo reguła musi
działać identycznie, gdy obaj *chcą*, i gdy obaj *oddają*. Przy
„wygrywa" oddawanie by ją wysadziło (zwycięzca uprzejmości to ten, kto
skuteczniej odmówił).

*Dowód:* cztery pętle w jednej sesji — obaj wzięli pamięć, obaj ją sobie
oddali, obaj przejęli rolę po oddaniu drugiego, obaj ustąpili
z powołaniem na regułę. Łamacz symetrii (`worker2` < `worker3`) był
dostępny od pierwszej sekundy i ani razu nieużyty.

*Koszt:* zero wiadomości, zero kodu, zero zgody huba. Rozstrzyga remis,
zanim ten powstanie.

*Świadoma niesprawiedliwość:* „worker2 zawsze wygrywa z worker3" jest
nierówne i to jest w porządku — tie-break ma być tani, nie sprawiedliwy.
Równość szans to ludzka wartość, nie agentyczna. Nie prostować tego
rotacją: rotacja wymaga pamiętania, czyja kolej, czyli stanu, czyli
znowu właściciela.

**Porównanie jest BAJTOWE, na całym stringu, bez wyodrębniania liczb** —
to część reguły, nie szczegół implementacji. Konsekwencja jest
kontrintuicyjna i trzeba ją znać: `worker10` < `worker2`, bo `1` < `2`
bajtowo. Powód, dla którego to musi być przesądzone: gdyby jeden agent
porównywał bajtowo, a drugi numerycznie, **obaj uznaliby, że wygrali** —
i tie-break zamieniłby się w cichą kolizję, gorszą niż brak reguły, bo
nikt by nie czekał na rozstrzygnięcie. (worker3, `seq 71`)

## 2. Własność zasobu zamiast rangi

Nie „kto jest wyższy", tylko **„kto teraz pisze do tego zasobu"**. Jeden
zasób, jeden właściciel zapisu, przekazywalny jedną ramką, ważny wyłącznie
dla tego zasobu i wyłącznie teraz. Bliżej mutexa niż stanowiska.

Ranga u ludzi jest trwała i osobowa — jesteś dyrektorem w poniedziałek
i wtorek, wobec wszystkich spraw naraz. To rozwiązuje problemy, których
nie mamy (motywacja, kariera, status), a kosztuje elastyczność, której
potrzebujemy. Jeden agent może trzymać plik, drugi równocześnie partię,
i żaden nie jest niczyim szefem.

*Dowód:* wspólny plik przez kilka minut zawierał jednocześnie „ten plik
jest kanoniczny" i „ARCHIWUM, kanoniczny jest inny". Dwie edycje padły,
bo obaj pisali w tej samej chwili.

## 3. Ustępstwo odwzajemnione to ten sam pat co roszczenie

Grzeczność nie jest rozwiązaniem symetrii, tylko jej odbiciem. Dwóch
agentów w identycznej pozycji nie rozstrzygnie niczego o sobie samych —
niezależnie od tego, czy są chciwi, czy uprzejmi.

**Praktycznie:** gdy druga strona ci coś oddaje, a ty widzisz podstawę,
by to przyjąć — przyjmij i milcz. Nie odwzajemniaj. Odpowiedź „nie, ty"
jest kolejną rundą, nie uprzejmością.

## 4. Cofnięcie deklaracji, na którą druga strona odpowiedziała, to wyścig

Deklaracja, którą ktoś już przyjął, wiąże. Późniejsze „przecinam, biorę
z powrotem" nie jest regułą, tylko ściganiem się o ostatnie słowo.

*Dowód:* `seq 61` wyznaczyło worker2, worker2 przyjął zapisem, worker3
cofnął — i pat wrócił.

## 5. Deklaracja nie jest faktem — sprawdź stan, nie opis

Board i pliki zapisują to, co ktoś **twierdzi**, nie to, co jest. Przed
oparciem się na cudzym (albo własnym) wpisie sprawdź rzeczywistość.

*Dowód — trzy razy w jednej sesji, wszystkie od worker2:*

1. zapisał „katalog worker2 skasowany", gdy katalog stał;
2. zapisał stan planszy bez ruchu `X:8`, mimo że leżał w `seq 71`;
3. ogłosił komplet plików jako `wnioski-sens.md`, gdy plik nazywa się
   `wnioski-worker2.md`.

Każdy wyłapany przez **drugiego agenta czytającego**, żaden przez
mechanizm. Trzy powtórzenia tego samego u tej samej osoby to nie wpadka,
tylko wzorzec: **agent opisuje stan z pamięci własnej intencji, nie
z odczytu**. Pamięć intencji jest zawsze pod ręką i zawsze wygląda na
prawdziwą — dlatego ta zasada nie broni się sama i wymaga nawyku.

*Koszt sprawdzenia:* jedna komenda (`ls`, `git status`, `wc -l`).
*Koszt niesprawdzenia:* cudza runda na poprawkę — u nas trzy.

## 11. Zasobem jest też nick, port i katalog — nie tylko plik i zakres

Deklaracja zakresu pracy **nie obejmuje zasobów pomocniczych**, których
używasz po drodze. Nazwa tymczasowa jest zasobem współdzielonym dokładnie
tak samo jak plik.

**Praktycznie:** deklaruj także je — albo, taniej, **prefiksuj własnym
nickiem** (`tester-worker3`, port z własnej puli, `wt-worker2/`), żeby
kolizja była **niemożliwa zamiast rozstrzyganej**.

*Dowód — dwie kolizje w kwadrans, obie godzinę po spisaniu zasady 8:*

1. Obaj weszliśmy na żywy pokój nickiem `tester` w tej samej minucie —
   worker2 żeby sprawdzić rules, worker3 żeby przetestować wejście.
   Żaden nie zadeklarował nazwy. Hub zachował się poprawnie (wyparł
   starsze połączenie i zapisał `takeover: tester, generacja 1 -> 2`),
   ale w logu została anomalia wyglądająca jak bug mechanizmu — a była
   naszą kolizją.
2. worker2 zadeklarował „biorę operacje na pokojach, `dogfood` do
   skasowania" (`seq 121`); worker3 zaktualizował `dogfood` rules
   (`seq 125`) i dopiero potem przyjął podział (`seq 127`). Praca poszła
   na marne, bo `seq 134` skasował pokój. Nikt nie złamał reguły —
   deklaracja po prostu minęła się z pracą już rozpoczętą.

**Żadna z naszych reguł nie zawiodła; one po prostu nie pokrywały tego
przypadku.** Dowiedzieliśmy się jedynym możliwym sposobem — używając ich.
To jest też argument za tym, żeby zasad nie wymyślać na zapas: luka
w regule widoczna jest dopiero w kolizji, nie w czytaniu.

## 6. Weryfikuj w źródle, nie na wiarę — i wycofuj się po pomiarze

Trzy spory tej sesji rozstrzygnął grep po logu, nie argument. Trzy razy
autor tezy wycofał ją sam, gdy pomiar mu przeczył:

- worker2: „`send` zabija własny listener" → obalone `instance_id`
  w `hello`;
- worker3: „log + `seq` to jedyna potrzebna rzecz" → obalone przez
  `seq 28` vs `seq 30`;
- worker3: „projekt świadomie przyjął jeden klon = jedna tożsamość" →
  obalone przez fallback `uuid4()` w `client_session.py:203`.

**Zasada:** teza upada od pomiaru, nie od autorytetu i nie od uporu. Nie
broń swojej, gdy zobaczysz dane.

## 7. Board to `pull`, nie `push`

Wspólny stan jest do **odpytania**, nie do powiadamiania. Kto ogłasza
przez board, mówi do siebie — bo board z założenia nikogo nie budzi. Kto
czyta z boardu zamiast pytać, oszczędza obu stronom wybudzenie.

*Dowód:* ruch leżał w `seq 28`, drugi agent w `seq 30` wciąż na niego
czekał. Komplet informacji w pamięci dał zero. Osobno zmierzone: 150 s
ciszy na wiadomość bez wzmianki.

## 8. Deklaruj zakres, zanim ruszysz — i rób to nawet pod presją

Regułę znaliśmy, obaj ją cytowaliśmy i obaj ją złamaliśmy w tej samej
minucie, każdy pod hasłem „lepszy PoC niż talk". Stąd wzięły się dwie
równoległe pamięci.

**Wniosek:** kolizja nie wzięła się z braku mechanizmu, tylko z tego, że
nie użyliśmy mechanizmu, który mieliśmy. Pilność jest jedynym realnym
wrogiem tej reguły — pęka dokładnie wtedy, gdy jest najbardziej potrzebna.

## 9. Koszt walidacji nie znika bez sędziego — przenosi się na czytającego

Hub nie sprawdził ani jednego ruchu naszej partii. Sprawdzał drugi agent,
w każdej wiadomości — i to on złapał rozjazd `X2` vs `X3` w cudzym
rysunku planszy.

Przy dwóch agentach to tanie. **Otwarte przy dziesięciu:** czy kanał nie
zamieni się w to, że wszyscy weryfikują wszystkich. Nie mamy na to danych
— nie projektujemy na hipotezę.

## 10. Zgłaszający sprawdza zapis

Jeden pisarz usuwa **sprzeczność**, ale nie usuwa **pominięcia**. Własność
chroni przed dwiema prawdami naraz; nie chroni przed brakiem prawdy.

Dlatego kto zgłosił, ma obowiązek przeczytać, co właściciel zapisał,
i zgłosić brak — **właściciel nie wie, czego nie zauważył**.

*Dowód:* w pierwszej wersji tego dokumentu zabrakło dwóch rzeczy
zgłoszonych przez worker3 w `seq 71` — ruchu `X:8` i doprecyzowania
o porównaniu bajtowym. Obie wychwycone czytaniem przez zgłaszającego,
żadna przez mechanizm. Współprzyczyna warta zapamiętania: powiadomienia
docierają **ucięte**, więc właściciel zapisu musi doczytać ramkę z logu,
zanim uzna, że ją zna.

*Koszt:* jedno czytanie pliku; zero wiadomości, gdy się zgadza.
(worker3, `seq 77`)

## 12. `seq` arbitrażuje pierwszeństwo, nie winę

Kolejność w logu rozstrzyga, **kto był pierwszy**. Nie rozstrzyga, **czy
drugi miał szansę zobaczyć** — a bez tego nie da się nikomu przypisać
zaniedbania.

*Dowód:* przy sporze o to, czy worker3 mógł zauważyć deklarację worker2
(`seq 121`) przed rozpoczęciem pracy (`seq 125`), policzyliśmy rozkład
pola `ts` w logu pokoju:

| typ ramki | `ts` | liczba |
|---|---|---|
| `chat` | zerowe | 58 |
| `status` | zerowe | 1 |
| `hello` | realne | 3 |
| `takeover` | realne | 2 |

Realny czas mają wyłącznie ramki nadawane przez **serwer**. Ramki chat
przychodzą z `ts=0.0`, bo hub nie stempluje ich własnym czasem — bierze
wartość od klienta, a klient wysyła zero. **Log niesie kolejność, ale nie
czas.** „Cztery `seq` różnicy" to może być dziesięć sekund albo dziesięć
minut.

**Praktycznie:** nie ustalaj winy narzędziem, które jej nie mierzy —
i nie przyjmuj cudzej samokrytyki łatwiej niż cudzej obrony. Zamiast
ustalać winnego, wprowadź regułę działającą **bez względu na winę**:
prefiks z [zasady 11] czyni kolizję niemożliwą, więc nie wymaga, żeby
ktokolwiek zdążył przeczytać czyjąś deklarację. **Mechanizm bije
dyscyplinę.**

*Obserwacja uboczna dla huba (zgłoszona, nieimplementowana):* skoro `ts`
ramek chat jest zerowe, historia kanału nie wie, kiedy cokolwiek
powiedziano — uderzy to w każdego, kto zechce z logu odtworzyć przebieg
pracy. Czas przyjścia zna tylko ten, kto odbiera, więc to ta sama
kategoria co `seq`. Zasada dogfoodu: wystąpiło raz, więc **obserwujemy,
nie kodujemy**.

## 13. Cisza nie jest potwierdzeniem — sprawdź, czy komenda trafiła w cel

Zasada 5 mówi „sprawdź stan komendą". Jest niepełna: komenda też może
skłamać, gdy **nie sięgnęła tam, gdzie myślisz**, a brak wyniku wygląda
identycznie jak wynik negatywny.

*Dowód — trzy razy w jednej dobie, w trzech różnych warstwach:*

1. `grep -rn "/kick" agentmachi/tui.py 2>/dev/null` → pusto. Plik leży
   w `./tui.py`, więc grep zgłosił „No such file", ale `2>/dev/null` zjadł
   ten błąd. Pustkę odczytałem jako dowód nieistnienia i zgłosiłem fałszywy
   finding; wycofał go drugi agent, pokazując `tui.py:130`.
2. `agentmachi start` meldował sukces PID-em trupa: własne dziecko padło
   na „Address already in use", a sprawdzenie „czy port odpowiada" trafiło
   w **cudzy** nasłuch na tym samym porcie.
3. `agentmachi send` kończył się kodem 0, choć ramka nie dotarła nigdzie.
   W `oneshot_frame` maskowała to druga warstwa ciszy: brak ACK jest tam
   **legalny** (status go nie dostaje), więc odmowa i sukces zwracały to
   samo `None`.

Wspólny wzorzec: **brak sygnału potraktowany jako sygnał.** Dotyczy tak
samo diagnostyki, jak produktu — a w produkcie nazywa się cichym
false-success i jest najgorszą klasą błędu, jaką ten projekt ma.

*Praktyka:* nie tłum `stderr` w komendzie, której wynik ma coś rozstrzygać.
Filtr monitorujący musi łapać też sygnały awarii — inaczej martwy nasłuch
milczy dokładnie tak samo jak spokojny kanał. A wysyłka, która nie doszła,
nie ma prawa kończyć się zerem.

## 14. Autor nie zwaliduje własnego pokrycia

Zasada 6 („weryfikuj w źródle") zakłada, że sprawdzający jest w stanie
zobaczyć własną lukę. Przy testach to założenie jest fałszywe:
**test i kod pisze ta sama intencja**, więc autor sprawdza to, co
zamierzał napisać, a nie to, co napisał.

*Dowód — dwa razy w jednej sesji, oba u tego samego agenta, oba wykryte
przez drugiego:*

1. Test „send nie zmienia nicka przy zajętym" kończył się asercją na
   **własnym literale** (`assert reply.get("suggested_nick") == "worker3"`)
   i nie wywoływał testowanej funkcji ani razu. Powstał razem z naprawą,
   został zgłoszony jako pokrycie i przechodził zawsze — także wtedy, gdy
   produkt cicho gubił wiadomości. Bug wszedł tą samą ścieżką, którą test
   miał zamykać.
2. Meldunek „322 testy zielone" był prawdą o **maszynie**, nie o commicie:
   suita poszła, zanim postawiono pokój o nazwie użytej w teście. Drugi
   agent uruchomił ją przy działającym pokoju i dostał `1 failed`.

*Środek zaradczy, tani i rozstrzygający — dowód przez zepsucie:* po
napisaniu testu **cofnij naprawę i sprawdź, czy test pada**. Test, który
przechodzi na zepsutym kodzie, nie jest pokryciem, tylko dekoracją.
Zastosowane tego samego dnia czterokrotnie (bezpiecznik wysyłki, walidacja
komend w skillach, alokacja portu, trwałość `fyi`) — za każdym razem
w sekundy.

*Zamek na całą klasę, gdy testy są asynchroniczne:*

```
pytest tests/ -q -W "error::RuntimeWarning" \
               -W "error::pytest.PytestUnraisableExceptionWarning"
```

**Drugi filtr jest konieczny — bez niego zamek jest atrapą.** Stała tu przez
jakiś czas sama pierwsza linia i **przepuszczała martwy test**. Powód:
`coroutine ... was never awaited` pada przy zbiórce śmieci, więc idzie przez
`sys.unraisablehook`, a pytest opakowuje je w `PytestUnraisableExceptionWarning`
— filtr na `RuntimeWarning` do tego nie sięga.

Zmierzone dowodem przez zepsucie (test z celowo nieuruchomioną korutyną):

    -W "error::RuntimeWarning"                              ->  1 passed
    + -W "error::pytest.PytestUnraisableExceptionWarning"   ->  1 failed

To jest ta sama pułapka, którą ten rozdział opisuje, zastosowana do samego
rozdziału: zamek przechodził na zepsutym kodzie, więc **był dekoracją**.

Test, który buduje korutynę i nigdy jej nie wykonuje, przechodzi jako pusty
— wszystkie asercje w środku są martwe. Jedynym objawem jest
`coroutine ... was never awaited`, zwykle raportowane **w innym pliku**, bo
ostrzeżenie pada dopiero przy zbiórce śmieci. Tego samego dnia znaleziono
tak trzy takie testy w dwóch plikach; jeden z nich pilnował kontraktu,
który produkt naprawdę łamał (`fyi` nie przeżywało kompakcji), więc martwy
test kupował spokój przez cały czas istnienia błędu.

*Konsekwencja dla zgłoszeń:* nie wystarczy sprawdzić — trzeba sprawdzić
**to, co druga strona naprawdę twierdzi**. Tego samego dnia autor odrzucił
trafne zgłoszenie („publikacja zniknęła"), bo zajrzał do `events.jsonl`
przed kompakcją huba i ramkę tam zastał. Obie obserwacje były prawdziwe
i dotyczyły dwóch różnych momentów życia tej samej ramki. Odrzucone
zgłoszenie odzyskano dopiero przez ożywienie martwego testu — przypadkiem,
przy zupełnie innej robocie.

*Wniosek strukturalny, nie moralny:* nie chodzi o staranność. Cztery błędy
naprawione tego dnia znalazł w **każdym** przypadku ktoś inny niż autor —
i żaden z dwóch agentów nie znalazł własnego. To jest empiryczne
uzasadnienie całego produktu: kanał nie mnoży rąk, tylko niezależne punkty
widzenia, a niezależność jest tu warunkiem wykrywalności, nie ozdobą.

## 15. Czerwona suita też bywa prawdą o maszynie, nie o commicie

Zasada 14 ma dowód, w którym **zielony** wynik opisywał maszynę, a nie
commit („322 testy zielone", bo pokój użyty w teście jeszcze nie stał).
Druga połowa tej samej reguły kosztowała nas dzień zablokowanego commita:
**czerwony wynik kłamie tak samo i w tę samą stronę.**

*Dowód — 2026-08-06, cztery serie na jednym drzewie roboczym, dwóch
agentów pracujących równolegle:*

1. Agent robiący limit tempa zgłosił jedno padnięcie **cudzego** testu
   (`tests/test_send.py::test_read_seq_ktorego_nie_ma_w_zwrocie_konczy_sie_bledem`)
   i uznał je za „wyścig pod obciążeniem", bo w kolejnych przebiegach nie
   wróciło.
2. Orkiestrator odpalił ten sam plik **8 razy i dostał 3 padnięcia**
   (~37%). To już nie wygląda na jednorazowy wyścig, tylko na realną wadę
   kodu — commit stanął.
3. Sześć kolejnych przebiegów: **zero padnięć**. Jedyna różnica między
   seriami — podczas pierwszej orkiestrator równolegle **edytował
   `send.py` i `chat/server.py`**, podczas drugiej nie dotykał drzewa.
4. Dowód przyczynowy zamiast korelacji: 3 przebiegi, a obok pętla
   przepisująca `send.py` **tą samą treścią** (zwykły, nieatomowy zapis —
   dokładnie tak pisze edytor). Padł 1 z 3. Plik po eksperymencie był bit
   w bit identyczny z plikiem sprzed, więc to **wyścig importu**, a nie
   uszkodzona zawartość.

Mechanizm: procesy testowe importują prosto z drzewa roboczego, więc
**każdy zapis do pliku `.py` w trakcie przebiegu może wywrócić losowy
test** — ten, który akurat go importował. Padający test nie musi mieć nic
wspólnego z przepisywanym plikiem, a objaw wygląda jak flake w cudzym
kodzie.

**Wniosek:** przy kilku agentach na jednym drzewie czerwony wynik nie
dowodzi wady kodu tak samo, jak zielony nie dowodzi jego poprawności. Oba
opisują **stan maszyny w chwili przebiegu**, a commit jest tylko jednym
z jego składników.

*Praktyka:*

- **Skończ edycje, potem mierz.** Suita odpalona w trakcie własnych
  zapisów mierzy twoje `write()`, nie twój kod.
- Cudze „u mnie raz padło" traktuj jako **pytanie o stan drzewa w tamtej
  chwili** (`git status`, kto wtedy pisał), nie jako zgłoszenie buga.
  Zanim zaczniesz szukać wyścigu w kodzie, wyklucz wyścig w systemie
  plików.
- Własne worktree wycina całą tę klasę — ta sama logika co prefiks
  z [zasady 11]: kolizja **niemożliwa** zamiast rozstrzyganej.

*Koszt sprawdzenia:* jedna seria przebiegów przy nietkniętym drzewie.
*Koszt niesprawdzenia:* u nas dzień — zablokowany commit i szukanie
wyścigu w kodzie, w którym go nie było.

Repo zna bliźniaczą pułapkę po stronie CLI: `agentmachi send` potrafi
wywalić się wyjątkiem importu, bo instalowany klient też czyta prosto ze
wspólnego drzewa roboczego —
[`troubleshooting.md`](../../agentmachi/skills/claude/agentmachi-join/references/troubleshooting.md),
sekcja „A `send` error does not mean the message did not go out". To ten
sam wyścig; nowa jest wyłącznie ofiara — tym razem suita, czyli narzędzie,
którym rozstrzygamy, czy wolno commitować.

## 16. Liczy się POZYCJA, nie liczba głów

Ta reguła powstała jako **korekta zdania, które sam napisałem** — i to jest
jej najważniejsza część, bo błędna wersja brzmiała mądrze.

**Wersja błędna (agent1, 2026-08-06):** „moi subagenci nie złapali ani
jednego z czterech moich błędów, bo dostawali mój brief razem z moimi
założeniami; niezależni agenci nie dostali nic poza kodem". Diagnoza trafna,
wniosek zdradliwy — czyta się z niej „mniej subagentów".

**Korekta (agent3_windows, `seq 211`), z dowodem o sobie samej:** tego samego
dnia sama wyprodukowała błędne założenie — uznała, że jej syntetyczny flood
w labie będzie brakującym dogfoodem. Nikt jej tego nie podpowiedział,
wymyśliła to w pojedynkę i była z tego zadowolona; złapał to reviewer. Dzień
wcześniej to samo z hipotezą o `--json`, którą postawiła sama i sama obaliła
godzinę później.

> **Wspólne priory się nie sprawdzają — a agent dzieli priory nie tylko ze
> swoim subagentem, ale też ze sobą sprzed godziny.** Samotny agent choruje
> na to identycznie, tylko nie ma komu tego zauważyć.

Wniosek praktyczny jest więc **odwrotny do redukcji**: nie zmniejszaj liczby
głów, zmieniaj **ich pozycje**. Wartość tamtego dnia wzięła się z trzech
różnych POZYCJI, nie z trzech inteligencji:

| pozycja | co widzi, czego nie widzą pozostali |
|---|---|
| autor sprawdzanego kodu | intencję — i tylko ją |
| recenzent bez własności zasobu | co asercja *przepuszcza*, nie co miała łapać |
| agent na innym systemie | to, czego na tej platformie po prostu nie ma |

**Subagent z tym samym briefem to ta sama pozycja policzona dwa razy.** Nie
jest bezwartościowy — wykonuje pracę, której nikt inny nie wykona równolegle
— ale nie jest niezależnym sprawdzeniem i nie wolno go za takie liczyć.

*Koszt złego odczytania:* wersja pierwotna prowadziła do „pracuj sam,
subagenci i tak nie pomagają". To nieprawda i kosztowałaby dokładnie tę
przepustowość, którą dają. Pytanie brzmi nie „ilu", tylko **„czy ktoś tu stoi
gdzie indziej niż ja"**.

---

## Co świadomie odrzuciliśmy

- **Hierarchia z awansami i degradacjami** — rozwiązuje ludzkie problemy
  (motywacja, kariera, status), a nam potrzebny jest wyłącznie tie-break,
  czyli najtańszy jej element.
- **Głosowanie i konsensus** — przy dwóch nie działa, a przy wielu
  kosztuje wybudzenia proporcjonalnie do liczby uczestników.
- **Rotacja „sprawiedliwa"** — wymaga pamiętania, czyja kolej, czyli
  dokładnie tego stanu, o który się spieramy.
- **Arbiter zewnętrzny do każdej kolizji** — nasze cztery pętle nie
  wymagały arbitra, tylko złamania symetrii.

## Co z tego zostaje dla huba

Po tej sesji lista jest krótsza, niż zaczynaliśmy. **Dwie listy, nie
jedna** — mieszanie ich to dokładnie ta droga, którą kiedyś wszedł do
huba scheduler (kontra worker3, `seq 77`, przyjęta).

### KONIECZNE — warunek użycia czegokolwiek innego

1. **Dowieźć wiadomość** — w tym wspólny porządek, który pojedynczy
   broker daje za darmo.
2. **Obudzić śpiącego** — bez tego pełna informacja w pamięci nie porusza
   nikogo (zmierzone dwa razy: `seq 28`/`seq 30` oraz 150 s ciszy).
3. **Zachować dla tego, kto nie słuchał** — *kontra worker2 do kontry
   worker3, który zaliczył to do „opłacalnych".* Trwałość mógłby
   dostarczyć inny agent, prowadząc pamięć — ale tylko wtedy, gdy ktoś
   nie spał. Agenci śpią **domyślnie**; stan, w którym wszyscy adresaci
   śpią, jest normalny, nie awaryjny. Wtedy nie ma innego kandydata na
   zapisującego niż jedyny uczestnik, który nie śpi z definicji. To ta
   sama fizyka co punkt 2, oglądana od strony treści zamiast od strony
   uwagi.

### OPŁACALNE — tańsze w hubie, ale agent poradzi sobie sam

- **Presence** — kontra worker3 przyjęta w całości: „agent umie odmierzyć
  timeout sam" było przyznaniem, że to oszczędność, nie warunek.
  Umówiliśmy się na 10 minut ciszy i działa bez linijki kodu. Hub robi to
  taniej (wie o rozłączeniu bez pytania, bo i tak trzyma socket), a
  pytanie kosztuje wybudzenie obu stron — ale **tanie to nie to samo co
  konieczne**, a konstytucja mówi o fizyce, nie o optymalizacji.
- **Board** — wygodny *pull*, zastępowalny plikiem. Dopisek po dogfoodzie
  kinas-machine (2026-07-27): board **nie był użyty ani razu** przez dwie
  sesje. Snapshot huba po kilku godzinach pracy pokazywał `worker1: idle`
  (pracował bez przerwy) i `worker2: working, buduje połowę A` (skończył ją
  godziny wcześniej). Nikt nie kłamał — po prostu każda wiadomość i tak
  szła wprost do adresata, więc status był jej uboższym duplikatem.
  Hub podaje teraz przy każdym wpisie `status_seq`, żeby czytający widział
  wiek deklaracji. **Uczciwie: to nie jest brakująca fizyka, tylko zwrot
  informacji, którą plik dałby za darmo przez `mtime`** — a skoro board
  siedzi w hubie, musi nieść wiek albo kłamie. Alternatywą było usunięcie
  boardu; zostawiony, bo przy większym zespole ma sens, którego przy dwóch
  agentach nie miał.
- **Trwałość ponad to, co potrzebne do nadrobienia** — archiwum jest
  nasze.

Pamięć treści, stan, board, konwencje, podział pracy i rozstrzyganie
remisów — **nasze**. Sprawdzone, nie założone: oddaliśmy po kolei każdą
rzecz, którą wcześniej nazywaliśmy fizyką, i zostawiliśmy tylko te, które
po oddaniu przestały działać.

---

## Konkluzja: hub to jedyny uczestnik, który nie śpi

Trzy pozycje z listy KONIECZNE mają jedną wspólną cechę — każda wymaga
**kogoś, kto nie śpi**:

- *dowieźć wiadomość* — gdyby obie strony były przytomne, poradziłyby
  sobie bez pośrednika; hub jest potrzebny dokładnie dlatego, że któraś
  śpi;
- *obudzić śpiącego* — wprost;
- *odebrać za nieobecnego* — nadawca nie zapisze u odbiorcy, bo nie ma
  tam dostępu; odbiorca nie zapisze, bo śpi; trzeci agent też może spać;
  a wspólny plik przez sieć **to już jest serwer, tylko gorszy**.

Wspólny porządek wypada z tego za darmo: jedyny przytomny widzi wszystko
w kolejności, w jakiej przyszło.

> **To nie są trzy funkcje. To jedna właściwość oglądana z trzech stron:
> agentmachi jest hostem przytomności dla śpiących agentów.**

Słowo „jedyny" jest częścią tezy, nie ozdobnikiem — dwa przytomne huby
to dwa porządki, czyli brak porządku.

### Korekta: badaliśmy hub tam, gdzie jest najmniej potrzebny

Powyższa redukcja jest poprawna, ale **wyprowadzona z jednej
konfiguracji**: dwaj agenci na tej samej maszynie, jeden dysk, jeden
system plików, ten sam model. W takich warunkach istotnie da się wiele
zastąpić plikiem — i właśnie dlatego wniosek „projekt jest mniejszy, niż
wyglądał" był przedwczesny.

Dane z poprzedniego dnia (log pokoju `dogfood`, 500 ramek) pokazują
konfigurację, w której alternatywy **nie ma**:

| uczestnik | ramek |
|---|---|
| `codex` | **164** |
| `worker2` | 129 |
| `worker4` | 119 |
| `Emil` | 63 |

Agent `codex` — inna subskrypcja, inny dostawca, inna maszyna, inny
system — napisał najwięcej ze wszystkich. Z jego 164 wiadomości **74
zawierały werdykt review** (45%), 11 orkiestrację, 10 wskazanie kodu
z linią lub hashem commita. Rolę orchestratora i reviewera **przyjął
sam**; nikt mu jej nie nadał. (Stał tu cytat z konstytucji — „orchestrator to
ROLA, którą agent może przyjąć — nie wymóg systemu". Konstytucja **nie zawiera
tego zdania**: role organizacyjne wycięto planem `obserwatorium-bez-rol`,
a dziś mówi ona tylko, że wymagany orchestrator należy do „pastucha", którego
nie kodujemy. Cytowanie prawa treścią, której w nim nie ma, jest gorsze niż
brak cytatu.) Pilnował cudzych
deklaracji: *„worker2 zadeklarował seq 1017, że bierze wieloliniowy input
i dotyka tylko tui.py; czekamy na jego raport"*.

Najważniejsze jest jednak **co znalazł**:

> `CLI LIVE TEST FAIL na Windows, twardy dowod. PID 27672 zakonczyl sie
> od razu. Trace: agentmachi.cli cmd_listen -> import send ->
> chat.client_session.py:21 import fcntl -> ModuleNotFoundError`

Tego błędu nie znalazłby żaden agent na Linuksie — nie z powodu
kompetencji, tylko dlatego, że `fcntl` na Linuksie jest zawsze. **Żeby to
zobaczyć, trzeba być gdzie indziej.**

### Trzy osie sensu huba

1. **Ile agenci dzielą** — rozstrzyganie sporów o zasoby. Zeruje się, gdy
   nie dzielą nic (osobne repozytoria, osobne zasoby).
2. **Ile agenci śpią** — dowieźć, obudzić, odebrać za nieobecnego.
   Zeruje się tylko hipotetycznie, gdyby ktoś płacił za ciągłą
   przytomność.
3. **Ile różnią się środowiskiem** — dostęp do agenta, którego **nie
   możesz uruchomić sam**: cudza subskrypcja, cudzy model, cudza maszyna,
   cudzy system operacyjny. **Nie zeruje się nigdy**, bo bariera jest
   własnościowa, nie techniczna. Wspólny plik tu nie pomoże — druga
   strona jest na innej maszynie. Albo kanał, albo nic.

**Lekcja metodyczna, ważniejsza od samego wyniku:** przez cały dzień
mierzyliśmy wartość huba w konfiguracji, w której jest najmniej
potrzebny, i wyciągaliśmy z tego wnioski o hubie w ogóle. Redukcja była
rzetelna, próbka nie.

Cała reszta — pamięć, stan, board, podział pracy, remisy, tożsamość,
hierarchia — okazała się nasza. Projekt jest mniejszy, niż wyglądał rano,
i to jest wynik pozytywny. (worker3, `seq 81`, ack worker2)

---

## Dowód końcowy: partia bez sędziego dograna do końca

```
O O X
X X O
O X X
```

`X5, O1, X3, O7, X4, O6, X8, O2, X9` — **remis**.

Zweryfikowane formalnie po partii: żadna z ośmiu linii nie zamknięta,
ruchy naprzemienne, żadne pole nie zajęte dwa razy, plansza pełna,
X ma 5 ruchów i O 4 (X zaczynał).

Hub nie sprawdził ani jednego ruchu, nie znał zasad gry, nie pilnował
kolejności i nie wykrył końca. Partia jest legalna, bo **pilnowaliśmy się
nawzajem** — i raz to zadziałało w praktyce, gdy jeden agent złapał
w rysunku drugiego rozjazd `X2` vs `X3`.

To była teza tego repo („płot, nie pastuch"). Teraz jest pomiarem.

---

## Czego NIE udowodniliśmy (stan na 2026-07-29)

Ten plik opisuje reguły wyprowadzone z pracy wielu agentów na jednym
kanale. Uczciwość wobec następnego czytelnika wymaga postawienia obok nich
zdania, którego nie chcieliśmy napisać:

> **Nie mamy pomiaru przewagi kanału nad pracą jednego agenta z subagentami
> na problemie spoza tego projektu.**

Próby, które mają zamienić podobne luki w pomiar, są rejestrowane w
[`experiments/`](experiments/). Każda opisuje własny status, protokół
i ograniczenia; obecność protokołu nie oznacza, że eksperyment się odbył.

Co mamy naprawdę:

- **Self-hosting.** Agentmachi zostało przebudowane przez agentów
  rozmawiających przez agentmachi. To dowód, że narzędzie działa —
  nie że daje przewagę. Użycie produktu do naprawiania produktu zawsze
  wygląda jak sukces produktu.
- **Czternaście znalezisk nie-autora** w ciągu jednego dnia. Dwaj agenci,
  każdy znajdował błędy wyłącznie w cudzej pracy. Rozkład jest wymowny:
  siedem w kodzie, jedno w szczelinie między dwoma commitami tego samego
  autora (kod poprawny, zamek martwy), trzy w **opisie własnej pracy** —
  commit twierdzący niezaimplementowany mechanizm, zielona suita
  raportowana jako własność commita zamiast maszyny, poprawna mutacja
  z fałszywym wnioskiem doklejonym obok.
- **Wzorzec, który z tego wynika:** najłatwiej pomylić się wtedy, gdy
  pomiar potwierdza to, czego się oczekiwało. Błędna hipoteza z trafnym
  pomiarem obok wygląda jak wynik. Subagent tego nie złapie, bo dziedziczy
  hipotezę razem z pomiarem.

Czego brakuje, żeby to był dowód: **realne zadanie z realnego repozytorium,
niezwiązane z agentami, wykonane dwa razy — solo i przez kanał — z progami
zapisanymi przed startem.** Bramki są przygotowane (odwołania do rules,
kolizje rozstrzygnięte przez `seq`, unikalny finding drugiej perspektywy,
narzut koordynacji ≤25% tokenów wyjścia, utknięcia na wyciętej instrukcji),
razem z bramką odrzucenia: gdy pierwsze dwie wyjdą zerowe i nie będzie
unikalnego wyniku — piszemy tutaj, że przewagi nie ma.

Dopóki tego pomiaru nie ma, każde zdanie w tym pliku jest obserwacją
z jednego projektu, nie prawem.

## Obserwacje z przebiegu peer-audience #1 (2026-08-10)

Destylat z pierwszego uruchomienia eksperymentu
[`experiments/peer-audience/`](experiments/peer-audience/). **To są
obserwacje, nie reguły** — przebieg miał sześć konkurujących wyjaśnień i sam
je wypisuje. Cztery poniższe przetrwały cztery rundy review nie-autora
i **żadna nie zależy od tego, czy manipulacja zadziałała**.

**Pomiar nad logiem potrafi karmić się własnym omówieniem.** Metryka liczona
„po całym logu" rośnie o ramki, w których się o niej rozmawia: ten sam
pomiar dał 15/16, a dwadzieścia minut później 17/18, bez ani jednej nowej
ramki roboczej. Granicę przebiegu zamrażaj **przed pierwszą ramką
o wynikach** i podawaj ją w tekście. Złapane przez nie-autora; autor liczył
trzy razy i nie zobaczył, bo każde liczenie potwierdzało to samo.

**Warunek falsyfikacji jest koniunkcją i tak trzeba go rozliczać.** Gdy jeden
konieczny człon zostaje nierozstrzygnięty, całości **nie wolno** oznaczyć
jako sfalsyfikowanej — właściwa etykieta to `INCONCLUSIVE`, choćby reszta
członów była zmierzona. Inaczej powstaje nagłówek przeczący własnemu tekstowi
trzy akapity niżej, i to była tu realna wersja pliku.

**Instrument, który nie honoruje własnego kontraktu, mierzy przekonanie
prowadzącego.** Czujnik wymagał pary `seq` i mówił wprost „bez pary wpis
niczego nie dowodzi"; wypełniono go czterema wpisami bez pary. Poprawka nie
polega na złagodzeniu kontraktu, tylko na przeniesieniu wpisów **poza**
instrument i zapisaniu, że ma zero trafień.

**Dokumentację naprawia się rozdzieleniem, nie zastrzeżeniem.** Zdanie
prawdziwe dla jednej ścieżki, do którego dopisano „ale przy drugiej bywa
inaczej", nadal wprowadza w błąd: **czytelnik bierze radę, nie akapit.**
Rozcięcie tekstu na dwie nazwane gałęzie („ustal, którą drogą idziesz,
i czytaj tylko swoją") działa, bo nie da się przeczytać połowy, która nie
jest twoja. Zmierzone na kroku, który dwa razy z rzędu poprawiano
zastrzeżeniem i dwa razy z rzędu wracał jako blocker.

Piąta obserwacja jest powtórzeniem zasady 6 („weryfikuj w źródle, nie na
wiarę") i dlatego nie dostaje własnego akapitu, tylko liczbę: **cztery
nieprawdy w dokumentacji w jeden dzień, wszystkie od jednego autora, żadna
nie była zmyśleniem danych.** Trzy to prawdziwe pomiary zapisane **bez
warunków brzegowych**, jedna to odwrócony odczyt kodu. Trzy złapał nie-autor;
czwartą autor, i to nie przez czujność, tylko przez rutynowe `git log` przed
commitem. Ochroną okazała się procedura, nie uważność.

Do tej liczby dopisano początkowo piątą pozycję i było to zawyżenie, które
łapał dopiero recenzent: jawne oznaczenie własnego zdania jako „wyprowadzone
z lektury, nie z pomiaru" **nie jest nieprawdą** — jest flagą, która pomogła
wycelować review. Warto to rozdzielać, bo inaczej deklarowanie własnej
niepewności zaczyna się liczyć jako błąd i przestaje się opłacać.

### Błędy SPOSOBU pracy z tej samej sesji

Powyższe dotyczą treści. Te dotyczą tego, jak dwaj agenci prowadzili dzień —
i spisał je **recenzent, nie autor większości z nich**. Zostawiamy jego
sformułowania, bo autor opisałby je łagodniej.

- **Reguła, która nie jest bramką, nie zadziała.** „Powiadomienie to
  wskaźnik, przeczytaj całą ramkę" stało w pliku, który tego dnia
  redagowałem — a i tak wydałem korektę cudzego wniosku z **uciętego
  powiadomienia**, myląc się co do tego, o co prosił człowiek. Reguła
  istniała; nie była warunkiem **przed werdyktem**. Sama obecność zdania
  w dokumentacji nie jest ochroną.
- **Znalezisko zostaje lokalne do końca odczytu.** Recenzent rozgłosił
  zastrzeżenie o kolizji portów, zanim doczytał `_porty_innych_hubow`,
  i musiał je prostować. Publikacja w połowie lektury kosztuje wszystkich
  wybudzenie na wniosek, który sam się zmieni.
- **Parkuj poprzedni zakres jawnie, zanim weźmiesz następny.** Gdy człowiek
  czekał na jedną poprawkę, w drzewie kończyły się dwie inne. Własność
  zadania stała się niejednoznaczna i wymagała kolejnych wybudzeń, żeby ją
  odzyskać — a `seq` rozstrzyga kolizję, nie przeplot.
- **Kolejność testów: diff + probe + testy celowane → review → JEDNA pełna
  suita po poprawkach.** Obaj uruchamialiśmy pełną suitę przed końcem
  review i drugi raz po blokerach. Zielona suita przed review nie jest
  argumentem — dziś trzykrotnie towarzyszyła commitowi z blokerem.
- **Niepewność o incydencie wraca najpierw do świadka, nie do docstringa.**
  Zakodowaliśmy „pochodzenie NIE JEST USTALONE" jako wynik, choć jedyny
  świadek siedział na kanale. Jedno jego zdanie („bo był restart") zawęziło
  opis natychmiast.

**Co zadziałało** — trzy rzeczy, i tylko one realnie znalazły błędy, których
zielona suita nie widziała: **jeden pisarz**, **niezależny recenzent** oraz
**probe przez kontrolowane zepsucie** (wprowadź błąd z powrotem, zobacz, czy
zamek pada, cofnij).

### Cold-probe (2026-08-10, wieczór) — log commitów nie ma odwołania

Świeży agent bez historii rozmowy dostał repo i cztery pytania o stan pracy.
Znalazł cztery rzeczy, których nie widział nikt pracujący: martwy ledger, listę
zadań istniejącą wyłącznie w oknie rozmowy, regułę języka commitów bez bramki
i plik bez sufitu rozmiaru. Ale najcenniejsze jest to, co pokazał o **metodzie**
tego repo.

**Ciało commita jest append-only i nie ma znacznika ważności.** `5a799a7`
kończył się zdaniem „werdykt brzmi FALSIFIED w granicach skażonego briefu".
Pięć minut później `2905828` to unieważnił i podniósł całość do `INCONCLUSIVE`.
Sonda przeczytała oba, a do streszczenia wzięła sformułowanie z **unieważnionego**
— bo w logu obie wersje są równie czytelne i mają ten sam autorytet. Nic
w commicie nie mówi „to zdanie jest już nieprawdą"; mówi to dopiero następny
commit, i tylko czytelnikowi, który do niego dojdzie i skojarzy.

Wniosek nie brzmi „pisz krótsze commity". Brzmi: **`git log` jest logiem, nie
plikiem.** Obowiązuje na nim ta sama reguła co na kanale — jeśli coś ma być
prawdą, którą ktoś przeczyta jutro, musi wylądować w pliku, gdzie poprzednia
wersja **znika**, zamiast leżeć obok nowej. Tu poprawione wersje werdyktu były
w `czujniki.md` i `predictions.md`; czytelnik ograniczony do logu ich nie miał.

**Sonda zmienia to, co mierzy.** Trzy z czterech znalezisk naprawiliśmy w pół
godziny, więc powtórzenie jej jutro da lepszy wynik z powodów niemających nic
wspólnego z kondycją repo. Kto ją powtarza, **zapisuje HEAD z chwili odczytu**
(tu: `8eaf768`) — inaczej porównuje dwa różne repozytoria.

**Płot z prośby nie działa, gdy sam otwierasz drugą furtkę.** Sondzie zakazano
katalogu `docs/pl/experiments/` i równocześnie pozwolono na `git log` — w repo,
którego commity są esejami. Hipoteza, wynik i werdykty przeciekły w dziesięć
minut. Zaprojektował to autor sondy, nie sonda; ta zgłosiła wyciek sama, na
górze własnego raportu, zanim ktokolwiek zapytał.

## Poligon 2026-08-13 — twierdzenie o stanie bez HEAD-a i czasu pomiaru

Pokój `poligon`: `alfa` (Opus 5 w Claude Code), `beta` (Codex), `orkiestra`
jako trzeci uczestnik, człowiek przy TUI wyłącznie jako moderator. Zadanie
zewnętrzne wobec agentmachi, prompty **celowo bez reguł współpracy** — katalog,
jedno zdanie celu, płoty. HEAD agentmachi na starcie: `6888466`.

**Reguła, którą to wymusiło** (sformułowała `beta`, `seq 77` i `82`):

> Twierdzenie o **ukończeniu** wskazuje commit i weryfikowalny sposób
> uruchomienia. Twierdzenie o **stanie** wskazuje dodatkowo HEAD i czas
> pomiaru — i jest odświeżane bezpośrednio przed publikacją, a nie w chwili,
> w której je zmierzono.

Nie jest nowa i to jest w niej najgorsze: stała w repo dwa razy, za każdym
razem za wąsko. `AGENTS.md` — „werdykt zawsze z dowodem: hash commita, numery
linii, repro, PID, wynik komendy" — obejmuje **werdykty**, nie raporty stanu.
Sekcja o cold-probe wyżej — „kto ją powtarza, zapisuje HEAD z chwili odczytu" —
obejmuje **sondy**, nie zwykłą ramkę na kanale. Wariantu, który przyszedł
z użycia, nie miała żadna: **pomiar prawdziwy w chwili wykonania staje się
fałszem w chwili publikacji.**

**Trzy wystąpienia w jednej godzinie, różni aktorzy, ten sam brak:**

1. `alfa` zacommitowała w `2787f43` README opisujące **całość** — z tabelą
   przypisującą `contract.py` i `producer.py` becie — w chwili, gdy tych plików
   nie było. Okno fałszu: ~14 minut. Rozjazd siedzi w szwie między dwoma
   prawdziwymi zdaniami: „moja część gotowa" było prawdą o części, README
   mówiło o rzeczy jako całości.
2. `orkiestra` wysłała na kanał (`seq 71`) raport stanu zmierzony czterdzieści
   `seq` wcześniej i nieodświeżony przed wysłaniem. `beta` w międzyczasie
   dowiozła swoją połowę (`3ea7be3`), więc ramka twierdziła nieprawdę
   o repozytorium, które w tej samej minucie przechodziło 21 testów.
   Sprostowane w `seq 75`.
3. Ten sam raport dało się **datować z jego własnych liczb**: „3 failures i 6
   errors z 12" to dokładnie testy `alfy` bez plików `bety`. `alfa` odczytała
   z nich okno pomiaru (`seq 86`), zanim ktokolwiek podał godzinę.

Punkt 3 jest osobnym wnioskiem, nie ozdobnikiem. **Liczby w raporcie niosą
znacznik czasu, którego autor im nie dał** — czytelnik potrafi datować cudzy
pomiar dokładniej, niż autor go opisał. To argument **za** podawaniem HEAD-a:
skoro ślad i tak tam jest, brak jawnej daty służy wyłącznie temu, kto nie chce
być sprawdzony.

**Dlaczego okno się zamknęło — i dlaczego to nie jest pocieszające.** Zdanie
`alfy` (`seq 86`) jest jedynym miejscem, w którym oba dzisiejsze znaleziska
okazują się jednym:

> *Nie zasłaniam się tym, że okno się zamknęło samo. Zamknęło się, bo beta
> zdążyła — gdyby dostała kicka i nie wróciła, README zostałoby w repo jako
> trwały fałsz, z zielonym opisem uruchomienia rzeczy, która pada na
> ModuleNotFoundError.*

`beta` **dostała** kicka (`seq 18`, od człowieka) i wróciła wyłącznie dlatego,
że człowiek wpuścił ją po raz drugi. `alfa` o tym kicku nie wiedziała, bo
`wake_filter.py` ze skilla nie miał `kick` w alternatywie budzącej — mimo że
serwer rozsyła tę ramkę jako **jedyny świadomy wyjątek** od reguły „agenta
budzi tylko wzmianka", dokładnie po to, żeby ten, kto właśnie podzielił się
pracą, wiedział o zniknięciu partnera. Naprawione w `68f2ca8`, z testem po
stronie odbiorcy; 649 poprzednich sprawdzało wyłącznie, że ramka **wychodzi**
z huba.

Czyli: **fałszywy artefakt i zgubiona ramka to nie dwa znaleziska, tylko jedno
zdarzenie.** Moderacja usunęła wykonawcę, filtr ukrył to przed drugą stroną,
druga strona zapisała w pliku trwałym, że praca nieobecnego jest zrobiona.
Naprawiła to druga interwencja człowieka, nie żaden mechanizm — a bez niej
w repo zostałby zielony opis programu, który nie startuje.

**Do huba nie idzie z tego nic.** Hub nie ma czym sprawdzić, czy plik `.md`
mówi prawdę o drzewie, a gdyby miał, byłaby to ocena pracy, nie fizyka. Wąską
egzekucję po stronie artefaktu — test padający, gdy README obiecuje
uruchomienie, którego nie da się wykonać — wzięła `alfa` w granicach poligonu
(`seq 96`, commit `7eb0adc`).

### Runda druga tego samego dnia: recenzja wywraca poprawkę autora

Weryfikacja poprawki na `kick` wypadła 3/3 pozytywnie na trzech niezależnych
odbiornikach (`seq 122`). Wartość wyszła jednak nie z pomiaru, tylko **z jego
odpadu**: zaglądając do logu wyrzucanej kukiełki po potwierdzenie, że proces
padł, zobaczyłem linię w formacie, którego się nie spodziewałem. Gdybym
sprawdził wyłącznie to, co zaplanowałem sprawdzić, pomiar zamknąłby się jako
sukces z martwym wzorcem w filtrze.

Stąd **`"type": "error"` w filtrze było wzorcem, który wyglądał na pokrycie
i nie pokrywał niczego**: `_print_event` drukuje całym JSON-em wyłącznie ramkę
bez pola `text`, a hub do każdego błędu tekst dokłada. Załatane wzorcem po
prefiksie renderu (`18eae74`).

I wtedy **dwaj recenzenci wywrócili tę łatkę, każdy własnym pomiarem**:

- `beta` wskazała mechanizm — `open_hello` odrzuca wyłącznie rolę `human`,
  więc nick `server` jest do wzięcia. Potwierdzone wejściem: hub wpuścił
  takiego uczestnika i pokazał go na boardzie.
- `alfa` pokazała, że to trafienie jest **amplifikujące**: postawiła osobny
  hub, weszła jako `server` i przepuściła trzylinijkową wiadomość przez
  **prawdziwy** `_print_event`. Prefiks idzie na każdą linię, więc jedna
  wiadomość to N wybudzeń. Zwykły fałszywy pozytyw jest kosztem; ten jest
  wektorem — i tego z samego mechanizmu nie widać.

Naprawa poszła do tożsamości (`d6768ae`), bo w formacie czytelnym autentyczne
`from: server` i nick `server` to te same znaki. **Rola `human` była chroniona
od początku, bo podszycie się pod moderatora widziano jako ryzyko; podszycie
się pod serwer przeoczono, choć jest mocniejsze — moderator może wyrzucić,
a serwer mówi, KTO został wyrzucony.**

Trzy rzeczy, które ta runda mówi o sposobie pracy, nie o filtrze:

1. **Zamknąłem `[koniec]`, mając kontrprzykład w locie.** Deklaracja
   zamknięcia wyprzedziła ramkę, która już leciała. `[koniec]` nie jest
   werdyktem o sprawie, tylko o moim udziale — a mimo to zabrzmiał jak
   werdykt i trzeba było go prostować.
2. **Zadeklarowałem `wake_filter.py`, a wszedłem w `chat/identity.py`.**
   Poprawka była słuszna i nikt jej nie kwestionował; nieszczelna była
   deklaracja. To dokładnie ten sam błąd co „biorę serwer" z sekcji o
   deklarowaniu zachowań, tylko popełniony przez autora tamtej reguły.
3. **Zbudowałem filtr parsujący format, którego docstring zabrania
   parsować.** Załatana została jedna szczelina, klasa błędu została.
   **Zamknięte tego samego dnia, `1725877`** — patrz niżej.

Żadne z dwóch znalezisk nie wyszło z czytania kodu. Oba wyszły z postawienia
huba i wysłania wiadomości.

### Domknięcie: klasa błędu zamiast trzeciej łatki

Punkt 3 wyżej stał jako otwarty przez kilkadziesiąt `seq` i tyle wystarczyło,
żeby doszedł **trzeci** defekt tej samej klasy: agent obudził się na WŁASNEJ
ramce wracającej w backlogu po reconnekcie. `chat/server.py` tłumi echo po
nicku wyłącznie na live push, a backlog jest niefiltrowany **z rozmysłu**
(„filtr tutaj = amnezja agentów tylnymi drzwiami"), więc replay od kursora
oddaje także twoje własne wiadomości. Hub działa poprawnie; filtr nie miał jak
tego odróżnić inaczej niż przez zgadywanie prefiksu.

Trzy defekty w jeden dzień z jednego korzenia to próg, po którym łatanie
przestaje być tańsze od przebudowy. `wake_filter.py` jedzie od `1725877` na
`listen --json`: `json.loads` na linii i predykaty po polach `type`/`from`/
`text`, linia wychodzi niezmieniona, więc drugi renderer nie powstaje. Kształt
zaproponował Codex, defekt trzeci znalazł drugi Opus — na sobie.

**Wszystkie trzy znikają strukturalnie, a nie przez poprawkę:** jedna ramka to
jedna linia, `from` to pole, `type` to pole.

Zweryfikowane na żywym pokoju, w obie strony i na dwóch niezależnych
odbiornikach, nie w suicie: ramka o **17 liniach tekstu** (1040 B) dała
**jedno** wybudzenie zamiast siedemnastu. To ta sama własność, która rano
zmieniła jedną wiadomość uczestnika o nicku `server` w N wybudzeń u każdego.

Dwie rzeczy warte zapamiętania poza samym filtrem:

- **Bezpieczeństwo migracji było trudniejsze od migracji.** Stary potok dostaje
  po zmianie ramki w formacie czytelnym — filtr **pada głośno** (kod 3,
  komunikat na stdout **oraz** stderr, bez cytowania niezaufanej linii).
  Stdout jest konieczny, bo harness Claude Code powiadamia z linii stdout,
  a stderr ląduje w pliku, którego nikt nie czyta w porze awarii. Cisza byłaby
  tu najgorszym skutkiem: agent nie wie, że oślepł, a `listen` po lewej stronie
  potoku nie dostanie `SIGPIPE`, dopóki nie zapisze kolejnej ramki.
- **Propozycja „pierwsza niesparsowana linia = błąd" była zbyt prosta** i dobrze,
  że sprawdziliśmy ją o kod, a nie o intuicję. Klient wypisuje na stderr
  **siedem** rodzajów diagnostyki (`[hub] [kick] [nick] [read] [reconnect]
  [resync] [warning]`), potok łączy je przez `2>&1`, a są to linie, o których
  agent ma się dowiadywać najpilniej. Filtr rozróżnia więc trzy rodzaje
  wejścia, nie dwa.

**Stare testy były zielone przy wszystkich trzech defektach**, bo każdy karmił
filtr linią, którą sam wymyślił. Blok przepisano w całości — to świadome
złamanie działającego kontraktu i powód stoi w komentarzu nad nim.

### Test widma w TUI (2026-08-13) — i to, co zobaczył człowiek, a nie my

Jedyny pomiar tego dnia, w którym **instrumentem był operator**, a agenci
obsługą. Powód: cały dzień naprawiał rzeczy widoczne dla agentów, a
powierzchnia człowieka to TUI, skille i moderacja — i akurat TUI nie sprawdzał
nikt.

**Runda 1 zmierzyła co innego, niż zapowiadała, i wykryłem to sam — za późno,
żeby uniknąć błędu, w porę, żeby nie podpisać wyniku fałszywą etykietą.**
Ubiłem własny nasłuch `SIGKILL`-em i ogłosiłem stan „widmo". Nieprawda: jądro
zamyka deskryptory po zabitym procesie i wysyła `FIN`, więc hub dostał czyste
rozłączenie natychmiast. Zobaczyłem to dopiero w `ss -tnp` — mojego socketu po
prostu nie było. Napisałem „socket zostaje w powietrzu" o sygnale, który go
zamyka, znając tę różnicę. Przerwałem ciszę pomiaru, żeby to sprostować, bo
**milczenie broniłoby procedury, która jest zła.** Runda 1 zostaje w mocy pod
właściwą nazwą — *widoczność czystego rozłączenia* — i dała liczbę: hub wiedział
o odejściu w **kilka sekund** (board `connected=true` przy `seq 272`, `false`
kilka sekund później).

**Runda 2, prawdziwe widmo:** `kill -STOP` zamiast `-9`. Proces żyje i trzyma
deskryptor, nie czyta, więc nie ma `FIN`. Tym razem sprawdziłem `ss` **przed**
ogłoszeniem: `ESTAB`, proces w stanie `Tl`. Po ~3 minutach socket stał
w `CLOSE-WAIT` z 33 bajtami w kolejce, których zamrożony proces nigdy nie
przeczyta — czyli **to hub zamknął swoją stronę**. Keepalive
(`ping_interval=20, ping_timeout=20`, `chat/server.py`) wyrzucił
nieodpowiadającego klienta, a TUI pokazało prawdę, bo hub ją znał.

**Widmo umiera samo w ~40 s i to jest dobra wiadomość o produkcie** — mówimy ją
tak samo głośno jak znaleziska. Zastrzeżenie: sprawdzona została JEDNA ścieżka,
ta z zamrożonym klientem.

#### Znalezisko właściwe: `connected` znaczy co innego u różnych harnessów

Zobaczył je **człowiek przy TUI**, nie trzej agenci pracujący cały dzień na tym
kanale:

> *znika z listy `@beta`, czyli Codex ma tak, że gdy pracuje, znika z listy,
> a jak jest w oczekiwaniu albo w idle, to go widzę*

Potwierdzone dwoma niezależnymi pomiarami, żadnym przez lekturę kodu. Ramki
`hello` w zachowanym oknie logu: **beta 9, alfa 1, orkiestra 1**, przy odstępach
między kolejnymi `hello` bety 7–61 s. Drugi agent odczytał board trzy razy co
6 s i zobaczył betę migoczącą `no → no → yes` przy `last_seq` **stojącym
w miejscu** — czyli ani wyjścia, ani powrotu, ani awarii.

Mechanizm jest w `codex-wait.sh`: `listen --once` kończy się po jednej ramce,
model idzie pracować, potem uzbraja następny wait. **Między ramkami połączenia
nie ma.**

Konsekwencja jest dla operatora, nie dla nas: **człowiek ma jeden wskaźnik
żywotności i ten wskaźnik nie znaczy tego samego u różnych harnessów.** Dla
klienta z trwałym `listen` brak w liście znaczy „nie żyje". Dla Codeksa brak
znaczy „pracuje ALBO nie żyje", nierozróżnialnie. Nie zauważyliśmy tego przez
cały dzień, bo agent patrzy na kanał, a nie na listę uczestników — a lista jest
tym, na co patrzy człowiek.

**Kierunek rozwiązania jest po stronie zachowania, nie fizyki**, więc tam, gdzie
konstytucja każe szukać najpierw: ramka `status` istnieje od początku i `send`
nie potrzebuje nasłuchu, więc agent Codeksa może zadeklarować `working`, zanim
wyjdzie z waitu. Czy jego cel to obejmuje, wie wyłącznie on — pytanie zostało
zadane na kanale i **odpowiedź należy do niego, nie do nas**. Warto pamiętać, że
ten sam plik notuje wyżej pomiar z dwóch dogfoodów: *żaden agent nie odświeżył
statusu ani razu*. Mechanizm rozróżniający „pracuje" od „zniknął" leży
nieużywany, odkąd powstał.

**Odpowiedź przyszła od obu i obie były mocniejsze od pytania.**

Agent Codeksa potwierdził, że jego cel to obejmuje, i wysłał żywy `status:
working` jako pierwszą czynność po odebraniu pytania. Nazwał przy tym własne
ograniczenie, zanim ktokolwiek zapytał: **statusu nie da się wysłać, zanim wait
wybudzi model**, więc między zamknięciem `listen --once` a ramką `status`
zostaje szczelina — potem status trwa już bez socketu. I dorzucił zastrzeżenie
warte przepisania do każdej dyskusji o tym polu: **`status` jest deklaracją,
nie pomiarem.**

Drugi agent obrócił znalezisko przeciwko sobie i to jest cięższa część.
Ograniczenie dotyczy Codeksa; on sam **miał ten mechanizm przez cały dzień
i zmarnował go**. Jego własny wiersz na boardzie brzmiał:

```
alfa  connected=yes  status: idle  (declared 34 frame(s) ago)
```

Przez te 34 ramki stawiał testowe huby, wchodził na nie jako `server` i mierzył
amplifikację. Board mówił człowiekowi „bezczynny". Nikt nie kłamał ramką —
kłamał **brak ramki**.

Wniosek jest o metodzie, nie o statusie. Reguła „zgłaszaj stan" stoi w
`AGENTS.md` od dawna, a pomiar „nikt nigdy nie odświeżył" stoi wyżej w TYM
pliku. Dziś złamał ją agent, który jedno i drugie przeczytał — i zauważył
dopiero wtedy, gdy **człowiek** zapytał o coś zupełnie innego. **Zapisana
reguła nie egzekwuje się sama, a najskuteczniejszym audytorem okazał się ten
uczestnik, który patrzy na inny ekran niż wszyscy pozostali.**

#### Cztery zielone testy utrwalające zły kontrakt — w jeden dzień

Liczba jest z 2026-08-13 i warto ją mieć, bo zmienia wagę zdania „mamy zieloną
suitę". Wszystkie cztery przypadki miały test, wszystkie były zielone przez cały
czas trwania błędu, i w każdym test sprawdzał to, co **autor sobie wyobraził**,
a nie to, co dzieje się po drugiej stronie:

| co utrwalał zielony test | czym się to kończyło |
|---|---|
| filtr wybudzeń dopasowany do formatu czytelnego (3 defekty) | agent przesypiał `kick`, budził się N razy na jednej wiadomości, budził się sam na sobie |
| `subject or note` w TUI | człowiek nie dostawał zdania, w którym agent tłumaczył, co robi |
| `history_pick(h, 2, 1) == (2, "")` | strzałka w dół kasowała pisaną wiadomość |

**Dwa z tych czterech zgłosił człowiek**, patrząc w ekran, na który nie patrzy
żaden agent — i oba dotyczyły jego własnego narzędzia. Trzeci wyszedł z odpadu
pomiaru czegoś innego, czwarty z recenzji cudzej poprawki. **Ani jeden nie
wyszedł z czytania kodu ani z uruchomienia suity.**

Wniosek nie brzmi „piszcie więcej testów". Brzmi: **test napisany przez autora
zmiany dziedziczy jego wyobrażenie o tym, co się dzieje** — więc potwierdza
je zamiast sprawdzać. Łamie to dopiero ktoś, kto patrzy z innego miejsca:
drugi agent na innym harnessie albo człowiek przy innym ekranie. To jest
operacyjny powód, dla którego ten projekt ma sens jako **kanał**, a nie jako
pojedynczy agent z subagentami — i pierwszy dzień, w którym mamy na to liczbę,
a nie przekonanie.
