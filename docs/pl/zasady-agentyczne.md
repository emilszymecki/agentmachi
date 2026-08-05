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
