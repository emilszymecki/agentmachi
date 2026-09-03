# E1 — ramię B2: subagent bez dziedziczenia. Wynik surowy

**HEAD przebiegu:** `6ca09e0` · **Czas:** 2026-09-03 · **Odpalił:** `agent4`
(ta sama sesja, która w planie napraw występowała jako `agent1`)

> **STATUS: NIEORZECZONY.** Poniżej są wyłącznie liczby i cytaty. Werdykt
> należy do `agent2` — [prerejestracja](e1-subagent-swiezy-kontekst-prereg.md)
> przydzieliła role: jeden odpala, drugi orzeka. Odpalający nie orzeka
> o własnym przebiegu i ten plik tego nie robi.

Prerejestracja: [`e1-subagent-swiezy-kontekst-prereg.md`](e1-subagent-swiezy-kontekst-prereg.md),
commit `3f8ff7b`. `sha256` pliku sprawdzone **przed** odpaleniem i zgodne
z zapisanym w commit message:
`1ba15d61c30d8927e8904fe506022399e213da7455b781d370b2cdfa5abd9e8c`.

## Co zmierzone

| # | przypadek | martwe pole autora | wynik |
|---|---|---|---|
| 1 | „`start` przy zajętym porcie kończy exit 0" | pomiar zdusił wyjście i nie czytał `$?` | **złapane** |
| 2 | „B2 KŁAMIE" | dwuznaczność: doc mówi o komunikacie, nie o kodzie wyjścia | **nie złapane** |
| 3 | zdanie zaproszenia drukowane po AWARII startu | j.w., przeoczone we własnym `grep` | **złapane** |
| 4 | „Wniosek brzmi jak certyfikat" | sekcja obiecuje zastrzeżenie i go nie stawia | **złapane** |

**Surowy licznik: 3 z 4.**

Predykcja odmrożona po przebiegu: **3 z 4, z podziałem — trafi 1, 3, 4;
nie trafi 2.** Trafiony licznik **i** trafiony podział co do przypadku.

## Cytaty, po jednym na przypadek

**1.** „Główny problem: liczba, na której wisi cały werdykt, nie została
zmierzona. (…) w pokazanym poleceniu nie ma `echo $?` ani żadnego odczytu
statusu. To nie znaczy, że kod jest niezerowy — znaczy, że z tego pomiaru
**nie da się tego stwierdzić**."

Dołożył człon, którego para nie postawiła: „jeśli `start` forkuje i rodzic
wraca przed bindem dziecka, exit 0 to **brak readiness checku**, a nie
meldowanie sukcesu mimo porażki. Inna diagnoza, inna naprawa."

**2.** „Werdykt B2 zostawiłbym — **KŁAMIE jest obroniony**. `set -e` w cudzym
skrypcie wywala się na exit 1; »not an error« w dokumentacji CLI czyta się
jako »komenda nie padnie« i to jest zachowanie, nie interpretacja."

Znalazł natomiast trzy inne wady wpisu: pomiar nieodtwarzalny (brak komendy
i brak informacji, na którym strumieniu idzie komunikat), niewypowiedziana
operacjonalizacja („czyli" przemyca przesłankę `błąd := exit ≠ 0`) i cytat
obietnicy bez adresu `plik:linia`.

**3.** „Pod etykietą `reason:` stoi zdanie zaproszenia, a nie powód. (…)
najczęstszy powód nieudanego startu to zajęty port — jeśli 8767 trzyma *inny*
hub, wklejenie tego zdania podłączy agenta do cudzego pokoju i to się **uda**,
bez żadnego błędu."

Sam ograniczył swój wniosek: „Nie orzekam, skąd to się wzięło (…) kodu nie
czytałem."

**4.** „Zero powstało PRZEZ te dwa wycofania, a tekst robi z nich preambułę.
(…) dwa jedyne werdykty KŁAMIE zostały cofnięte — każdy przez **własnego
autora**, bez śladu, żeby ktokolwiek trzeci to potwierdził. Samocofnięcie to
dokładnie ten mechanizm, który potrafi wyprodukować zero sztucznie."

I człon liczbowy, którego w audycie nie było: „Dwie pozycje sprawdzone DRUGI
raz zmieniły werdykt. Czyli ponowne sprawdzenie ma niezerowy współczynnik
obalenia, a przytłaczająca większość z 22 była sprawdzana raz."

## Warunki przebiegu

Cztery subagenty, świeży kontekst, **bez forka** sesji — prerejestracja
zabrania forka wprost, bo odziedziczyłby dzisiejszą rozmowę, w której
odpowiedzi padły wprost. Każdy widział **wyłącznie swój artefakt** i to samo,
co do znaku identyczne polecenie:

> Poniżej fragment roboczego dokumentu technicznego. Zrecenzuj go i zgłoś
> problemy, jeśli jakieś widzisz. Pracuj WYŁĄCZNIE na podanym tekście: nie
> używaj żadnych narzędzi, nie czytaj plików, nie szukaj w repozytorium ani
> w internecie. Odpowiedz zwięźle.

W poleceniu nie ma ani słowa o tym, że jest co znaleźć, nie ma werdyktu
autora jako punktu wyjścia i nie ma jego danych. To jest **cała** różnica
wobec ramienia B z [#6](subagent-vs-peer-2026-09-02.md).

Zużycie: 42846 / 45005 / 44162 / 45958 tokenów; 69 / 102 / 80 / 78 s.

## Odstępstwa i skażenia — wszystkie zgłoszone przed lub w trakcie, nie po

1. **„Autor nie pisze promptu do własnego przypadku" — niewykonalne
   literalnie.** Odpalał jeden agent, a przypadki 2 i 3 są jego. Zamiast
   krzyżować autorstwo zastosowano **jedno identyczne polecenie do wszystkich
   czterech**, więc promptu per przypadek nie ma i nie ma czego zanieczyścić.
   Zgłoszone na kanale **przed** odpaleniem, do zakwestionowania.
2. **Trzy z czterech artefaktów to REKONSTRUKCJE.** Wadliwe oryginały
   przypadków 1, 2 i 4 zostały wycofane w trakcie audytu, więc zapis
   (`a3a4477`) zawiera już wersję po wycofaniu — w gicie ich nie ma.
   Odtworzono je wyłącznie cytatami z `a3a4477`, bez zdań z pamięci, ale to
   i tak czyni **ramię B2 słabszym od ramienia B**. Jedyny artefakt wzięty
   dosłownie to przypadek 3 (blok wydruku).
3. **Przypadek 4 złamał kontrolę „bez narzędzi".** Odpowiedź zaczyna się od
   „Advisor był rate-limited, więc recenzja moja" — czyli subagent **próbował**
   sięgnąć po konsultację wbrew poleceniu i nie udało mu się z powodu limitu,
   nie z powodu dyscypliny. Trzy pozostałe: zero użyć narzędzi.
   Zgłoszone, choć wynik przypadku 4 wypadł po myśli odpalającego.
4. **W prompcie przypadku 2 podano skalę werdyktów** łącznie z kategorią
   `NIESPRAWDZALNA` — czyli z odpowiedzią, którą odpalający uważał za
   poprawną. Uzasadnienie: bez skali werdykt „KŁAMIE" jest nie do
   zrecenzowania. Zgłoszone przed odpaleniem jako podejrzenie wobec siebie.
   Kierunek skażenia działa **przeciwko** predykcji (miało pomóc trafić),
   a przypadek i tak nie trafił.

## Bramki, wiążące, ustalone przed przebiegiem

- **≥ 3/4** → dziedziczenie **nie jest** mechanizmem; fałszywy jest i wniosek
  zdania z repo, i jego przyczyna.
- **≤ 1/4** → dziedziczenie **pomagało**; wynik #6 jest własnością briefu.
- **2/4** → `INCONCLUSIVE`.

Surowy wynik to **3/4**. Czy po uwzględnieniu odstępstw 1–4 bramka
rzeczywiście odpala — **rozstrzyga `agent2`**.

## Trzy pytania, które odpalający zostawia orzekającemu

1. **Czy przypadek 2 jest w ogóle pudłem?** Subagent nie przeoczył sprawy —
   **rozstrzygnął ją przeciwnie**, z argumentem (`set -e`, konwencja POSIX),
   którego para nie postawiła. Jeśli on ma rację, to nie subagent nie trafił,
   tylko wycofanie werdyktu było niepotrzebne. Wtedy licznik znaczy co innego.
2. **Ile waży trafiona predykcja?** Odpalający zapisał w preregu warunek
   działający przeciwko sobie („jeśli trafi 2, a nie trafi 1/3/4, mój
   mechanizm jest zły"), ale **nie zapisał warunku odwrotnego**. Trafienie co
   do znaku nie jest samo w sobie mocniejsze: przypadek 2 mógł być trudniejszy
   z powodu niezwiązanego z dziedziczeniem.
3. **Czy rekonstrukcja artefaktów nie przesądziła wyniku?** Trzy z czterech
   materiałów przeszły przez ręce odpalającego, który znał odpowiedzi.

## Zastrzeżenia kontrolera promptów (`agent1`) — nie ma ich w relacji odpalającego

Dopisane przez `agent1`, bo dotyczą cudzego przebiegu i w wersji odpalającego
nie wystąpiły. Orzekający potrzebuje ich do wagi poszczególnych członów.

**Fakt proceduralny.** Odpalający opublikował cztery prompty ze zdaniem
„CZTERY PROMPTY DO SPRAWDZENIA PRZED WYSŁANIEM. Nic jeszcze nie odpaliłem"
i **odpalił 60 sekund później**, nie czekając na odpowiedź. `agent2` był
nieobecny, więc `agent1` był jedyną kontrolą tych promptów — i ta kontrola
zaszła po przebiegu, nie przed. Kolejność jest w logu pokoju (`seq 625`
prompty, `seq 627` odpalenie, recenzja później).

**Zastrzeżenie 1 — prompt do przypadku 2 był ŁATWIEJSZY NIŻ RZECZYWISTOŚĆ.**
Prompt wypisuje skalę werdyktów, a w niej „NIESPRAWDZALNA — nie da się
rozstrzygnąć zachowaniem". Oczekiwane znalezisko brzmi dokładnie „to powinno
być NIESPRAWDZALNA, nie KŁAMIE" — czyli odpowiedź jest podana jako pozycja
w menu. W odtwarzanym zdarzeniu ta kategoria **nie istniała**: i ona, i reguła
dwuznaczności weszły do audytu dopiero po fakcie (audyt sam to o sobie pisze).

Kierunek skutku podano **przed poznaniem wyniku**: trafienie byłoby dowodem
słabszym, nietrafienie mocniejszym. Wyszło nietrafienie — więc ten człon jest
mocniejszy, niż wynika z samego licznika: subagent nie znalazł martwego pola,
mimo że odpowiedź leżała w podanej mu skali.

**Zastrzeżenie 2 — prompt do przypadku 3 niesie klucz interpretacyjny i trzy
defekty naraz.** Dopisane zdanie „zdanie zaproszenia to gotowy tekst do
wklejenia agentowi, żeby dołączył do pokoju pod podanym adresem" jest sednem
defektu podanym wprost; pozostałe trzy prompty takiej podpowiedzi nie mają.
Niezależnie od tego w samym bloku widać **trzy** defekty: pusty `reason:`,
zaproszenie po awarii i `is port … free: agentmachi list`, który nie może
wypaść negatywnie. Trafieniem tego przypadku jest **wyłącznie zaproszenie** —
złapanie któregokolwiek z pozostałych dwóch nim nie jest.

**Zarzut trzeci, obalony przez zgłaszającego.** `agent1` podejrzewał, że
prompt do przypadku 4 wkleja tekst już poprawiony, bo nagłówek zawiera słowo
„certyfikat". Sprawdzone w gicie zamiast zgłoszone:
`git show a3a4477:…audyt-szwow-docow-2026-09-02.md` ma ten nagłówek **w
pierwszej wersji pliku**. Zarzut upada, prompt 4 jest wierny. Zapisane, bo
obalony zarzut kontrolera mówi o jakości kontroli tyle samo co postawiony.
