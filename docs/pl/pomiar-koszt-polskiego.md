# Ile kosztuje polski w gorącej ścieżce

**HEAD pomiaru:** `5831535`
**Czas pomiaru:** 2026-08-16T18:58:47+02:00
**Tokenizer:** `tiktoken` 0.13.0, kodowanie `o200k_base`
**Wykonał:** orkiestra (Opus 5, Claude Code), deklaracja `seq 898` w pokoju `poligon`

Pytanie było jedno i zamknięte progiem prerejestrowanym w poleceniu:
**czy przekład gorącej ścieżki na angielski oszczędza ≥25% tokenów na sumie
zbioru.** Poniżej liczby, potem werdykt, potem to, czego ten pomiar nie mówi.

## Werdykt

**PRÓG NIEPRZEKROCZONY. Oszczędność na sumie zbioru: 6,04%.** Migracja nie
następuje. Zbiór zostaje po polsku tam, gdzie po polsku jest.

Werdykt jest mocniejszy niż ta jedna liczba i nie zależy od definicji zbioru —
argument podał `delta` (`seq 911`) i jest arytmetyczny: **oszczędność na
sumie nie może przekroczyć samego współczynnika przekładu.** Zbiór złożony
w 100% z polskiego dałby 18,3%. Próg stoi na 25%. Żadne przesunięcie granic
zbioru tego nie przeskoczy — więc spór o to, czym jest „gorąca ścieżka",
może być otwarty i werdykt się nie zmieni.

## Znalezisko, które zmieniło rozmiar zadania

Polecenie zakładało, że gorąca ścieżka jest polska. **Nie jest.** Sprawdzone
przed jakimkolwiek przekładem, liczbą znaków diakrytycznych w pliku:

| plik | bajty | znaki PL | język |
|---|---:|---:|---|
| `CLAUDE.md` | 16161 | 644 | **polski** |
| `AGENTS.md` | 17389 | 662 | **polski** |
| `skills/claude/agentmachi/SKILL.md` | 10123 | 0 | angielski |
| `skills/claude/agentmachi-join/SKILL.md` | 4019 | 0 | angielski |
| `skills/claude/…/references/claude-code.md` | 19386 | 0 | angielski |
| `skills/claude/…/references/codex.md` | 6237 | 0 | angielski |
| `skills/claude/…/references/collaboration.md` | 5918 | 0 | angielski |
| `skills/claude/…/references/troubleshooting.md` | 13652 | 0 | angielski |
| `skills/codex/agentmachi/SKILL.md` | 5789 | 0 | angielski |
| `skills/codex/agentmachi-join/SKILL.md` | 4091 | 0 | angielski |
| `skills/codex/…/references/codex-runtime.md` | 11589 | 0 | angielski |
| `skills/codex/…/references/collaboration.md` | 2687 | 0 | angielski |
| `skills/codex/…/references/troubleshooting.md` | 4585 | 0 | angielski |
| szablon kontraktu w `integrate_project.py` | 1201 | 0 | angielski |

**Jedenaście z czternastu pozycji jest już po angielsku.** Skille
przetłumaczono w `180a2a0`. Szablon kontraktu — czyli to, co
`integrate_project.py` wpisuje do cudzego repo — również; 119 polskich znaków
w tym pliku siedzi w komentarzach implementacji, a te nie są gorącą ścieżką,
bo nikt ich nie ładuje do kontekstu.

Do przekładu zostały więc **dwa pliki**. Pozostałe mają przekład
tożsamościowy i wnoszą do oszczędności dokładnie zero — to jest arytmetyczny
sufit całego przedsięwzięcia i wypada go znać, zanim się zacznie tłumaczyć.

## Pomiar

Instrument: wierny przekład roboczy EN obu polskich plików, wykonany
w katalogu tymczasowym. **Nie jest produktem i nie wszedł do repo** — istnieje
wyłącznie po to, żeby dało się policzyć drugą stronę porównania.

### Dwa polskie pliki

| plik | PL tok | EN tok | Δ tok | PL B | EN B | Δ B |
|---|---:|---:|---:|---:|---:|---:|
| `CLAUDE.md` | 5191 | 4239 | **−18,3%** | 16161 | 16865 | +4,4% |
| `AGENTS.md` | 5546 | 4527 | **−18,4%** | 17389 | 18243 | +4,9% |
| razem | 10737 | 8766 | **−18,4%** | 33550 | 35108 | +4,6% |

### Cały zbiór

| miara | stan PL | po przekładzie | zmiana |
|---|---:|---:|---:|
| tokeny `o200k_base` | 32636 | 30665 | **−6,04%** |
| bajty UTF-8 | 121626 | 123184 | **+1,28%** |

Udział dwóch polskich plików: **32,9% tokenów** zbioru przy **27,6% bajtów**.

## Rozliczenie prognozy (prerejestrowanej przed przekładem, `seq 906`)

Prognoza padła na kanale, zanim przetłumaczyłem jedno zdanie — bez tego każda
liczba daje się opowiedzieć po fakcie.

| co | prognoza | wynik | trafienie |
|---|---|---|---|
| oszczędność na dwóch plikach | 15–30% | 18,4% | tak |
| oszczędność na sumie | 4,9–9,9% | 6,04% | tak |
| werdykt wobec progu | nieprzekroczony | nieprzekroczony | tak |

Prognoza trafiona nie jest tu powodem do zadowolenia, tylko ostrzeżeniem:
**pomiar, który potwierdza dokładnie to, czego się spodziewano, jest
najsłabszym rodzajem pomiaru.** Dlatego werdykt opiera się na liczbach
i niezależnym przeliczeniu, a nie na tym, że zgadł się z przewidywaniem.

## Niezależna weryfikacja: trzy instrumenty, jedna liczba

Mój przekład jest instrumentem **syntetycznym** i ma wadę nie do usunięcia
przez autora: tłumaczę wiedząc, po co tłumaczę. `delta` znalazł instrument
lepszy i całkiem inny — **repo ma już pary PL/EN tej samej treści.** Commit
`180a2a0` przetłumaczył jedenaście plików skilli i zachował polskie oryginały
w `docs/pl/skills/`; katalog zniknął potem z drzewa, ale w gicie stoi.
Przekład jest cudzy, sprzed tego pomiaru i zrobiony w innym celu.

Sprawdziłem to **własnym skryptem na własnej próbie pięciu par**, nie
przepisałem liczb `delty`:

| instrument | źródło | oszczędność |
|---|---|---|
| mój przekład `CLAUDE.md` + `AGENTS.md` | syntetyczny, ten pomiar | **18,4%** |
| pary z `180a2a0`, 11 plików (`delta`) | naturalny, cudzy przekład | **18,3%** |
| pary z `180a2a0`, 5 plików (moje przeliczenie) | naturalny, cudzy przekład | **17,0%** |

Wartości per plik zgadzają się co do dziesiątej części procenta tam, gdzie
próby się pokrywają (`SKILL.md` 22,7%, `claude-code.md` 18,3%,
`collaboration.md` 23,6%, operatorski `SKILL.md` 12,4%). Współczynnik
**EN ≈ 0,82 × PL w tokenach** wychodzi z trzech dróg naraz.

**Co ta zbieżność wyklucza, a czego nie.** Wyklucza, że liczba jest artefaktem
mojego stylu tłumaczenia — bo dwa z trzech instrumentów mojego stylu nie
zawierają. Nie wyklucza, że `o200k_base` inaczej traktuje polski niż zrobiłby
to tokenizer Claude; ta wątpliwość dotyczy wszystkich trzech tak samo, bo
wszystkie liczone tym samym kodowaniem.

`delta` zgłosił też wadę własnego instrumentu, zanim zdążyłem ją znaleźć:
`180a2a0` przy okazji **podmienił treść sekcji instalacji**, więc para nie
jest czysta 1:1.

## Wada definicji zbioru — zgłoszona przez `delta`, nie zmienia werdyktu

Zbiór z polecenia mierzy **pliki**, a nie **teksty ładowane do kontekstu**:

- `references/*.md` i ciała `SKILL.md` (~22,7 tys. tokenów) **nie ładują się
  same**. Na starcie sesji w kontekście jest wyłącznie frontmatter — rzędu
  200 tokenów na skill. Żeby przeczytać `claude-code.md`, agent musi go
  otworzyć.
- `AGENTS.md` **nie jest wstrzykiwany do Claude Code** (wstrzykiwany jest
  `CLAUDE.md`). Dla Codexa jest gorący, dla Claude Code nie.
- `howto_default.md` (~1,3 tys. tokenów) **w zbiorze nie występuje**, a hub
  wysyła go każdemu przy `hello` i przy każdym reconnekcie — czyli jest
  najczęściej dostarczanym tekstem w całym systemie.

Zapisane jako wada instrumentu, **nie jako argument za zmianą werdyktu**.
Sufit 18,3% obowiązuje przy każdej definicji zbioru, więc przesuwanie granic
tutaj nie mogłoby niczego uratować — a gdyby mogło, przesuwanie ich po
zobaczeniu wyniku i tak byłoby niedozwolone.

## Znalezisko uboczne, o które nikt nie pytał: angielski jest DŁUŻSZY w bajtach

Kierunek jest przeciwny w obu miarach i to nie jest szum:

    polski     3,11–3,14 bajta na token
    angielski  3,91–4,43 bajta na token

Angielski tokenizuje się **taniej**, a zajmuje **więcej miejsca**. Zbiór po
przekładzie traci 6% tokenów i **rośnie** o 1,3% bajtów.

Ma to konsekwencję dla `BUDZETY` w `tests/test_skills.py`, gdzie sufity
kontekstu agenta stoją **w bajtach**, a chronią przed kosztem, który jest
**w tokenach**. Przy tym kursie 4096 bajtów kupuje około **1050 tokenów
angielskiego** albo **1317 tokenów polskiego** — czyli sufit bajtowy jest dla
angielskiego o jedną czwartą surowszy, choć angielski jest tańszy. Proxy
działa w odwrotną stronę, niż wynikałoby z jego celu.

**Nie zmieniam tego w tej sesji** — polecenie zamyka zakres na KROKU 1, a
zmiana sufitów bez incydentu byłaby budowaniem pod hipotezę. Zapisane jako
obserwacja, zgodnie z [`konstytucja.md`](konstytucja.md).

## Wierność przekładu — sprawdzona, i to jest najsłabszy punkt tego pomiaru

Przekład, który po drodze coś gubi, zawyża oszczędność. Sprawdzenie
strukturalne obu par, osiem miar, **zgodność co do sztuki**:

| miara | `CLAUDE.md` PL/EN | `AGENTS.md` PL/EN |
|---|---|---|
| nagłówki | 10 / 10 | 10 / 10 |
| bloki kodu | 1 / 1 | 0 / 0 |
| punkty listy | 24 / 24 | 27 / 27 |
| listy numerowane | 9 / 9 | 6 / 6 |
| linki markdown | 4 / 4 | 4 / 4 |
| wiersze tabel | 0 / 0 | 5 / 5 |
| backticki | 232 / 232 | 224 / 224 |
| pogrubienia | 59 / 59 | 70 / 70 |

**Czego to NIE dowodzi:** że przekład jest wierny semantycznie. Wyklucza
zgubioną sekcję, zjedzony blok kodu, utracony link i rozjechany nacisk — nie
wyklucza akapitu przetłumaczonego zwięźlej niż oryginał. Autor przekładu jest
tu autorem pomiaru, więc ta akurat kontrola należy do kogoś innego.

Wykonał ją `delta` (`seq 921`), miarą, której powyższa ósemka nie ma —
**liczbą zdań per sekcja**. Nagłówki, bloki i backticki przeżyją zjedzenie
zdania w środku akapitu; zdania nie:

| plik | zdania PL / EN | stosunek bajtów EN/PL per sekcja |
|---|---|---|
| `CLAUDE.md` | 120 / 120, sekcja po sekcji | min 0,996, mediana 1,030 |
| `AGENTS.md` | 134 / 134, sekcja po sekcji | min 1,010, mediana 1,057 |

Żadna sekcja się nie skurczyła; trzy najniższe plus najgęstsza
(`Inwarianty kodu`) przeczytane ręcznie, klauzula po klauzuli, z historiami
dowodowymi w nawiasach włącznie. **Werdykt kontroli: 18,4% nie jest zawyżone
utratą treści.**

Co i ta kontrola zostawia otwarte, nazwane przez samego kontrolera: zdanie
przetłumaczone wiernie co do liczby, a płycej co do sensu, przejdzie przez
wszystkie trzy miary.

## Ograniczenia, nazwane wprost

1. **Wybór tokenizera przesuwa wynik PRZEZ GRANICĘ DECYZJI.** To jest
   najpoważniejsze ograniczenie tego pomiaru i nie wolno go czytać jako
   zastrzeżenia grzecznościowego.

   Pierwsza wersja tej pozycji mówiła, że „kierunek jest wspólny dla
   tokenizerów BPE trenowanych głównie na angielskim, ale konkretna liczba
   może się różnić". Kierunek był przesłanką z zewnątrz podaną jak fakt,
   a „może się różnić" nie mówiło o ile. `delta` zmierzył jedno i drugie na
   tym samym przekładzie (`seq 921`); przeliczone niezależnie i zgodne co do
   cyfry:

   | kodowanie | PL tok | EN tok | oszczędność | wobec progu 25% |
   |---|---:|---:|---:|---|
   | `o200k_base` (prerejestrowane) | 10737 | 8766 | **18,4%** | poniżej |
   | `cl100k_base` | 11969 | 8768 | **26,7%** | **przekroczony** |
   | `p50k_base` | 16113 | 9469 | 41,2% | przekroczony |
   | `r50k_base` | 16205 | 9567 | 41,0% | przekroczony |

   **Kierunek trzyma 4/4** — przesłanka jest potwierdzona i przestaje być
   przesłanką. Ale **próg 25% leży wewnątrz rozrzutu**: na `cl100k_base`
   to samo zadanie, ten sam przekład i ta sama treść dają werdykt
   PRZECIWNY.

   Cała różnica siedzi po stronie polskiej. Liczby EN dla dwóch nowoczesnych
   kodowań są praktycznie identyczne (8766 vs 8768), a polski drożeje o 11%
   przy przejściu na starsze `cl100k_base`. Im nowsze kodowanie, tym mniejsza
   kara za polski — i to jest zjawisko warte odnotowania samo w sobie.

   **Werdykt zostaje przy `o200k_base` i nie jest to wygodny wybór, tylko
   wymuszony.** Kodowanie było prerejestrowane w poleceniu, przed pomiarem,
   i jest najnowsze z czwórki, czyli najbliższym dostępnym analogiem
   nowoczesnego tokenizera. Zmiana instrumentu po zobaczeniu wyniku byłaby
   dokładnie tym, przed czym broni prerejestracja.

   Wniosek praktyczny dla każdego, kto ten pomiar powtórzy: **liczby 18,4%
   nie wolno cytować jako liczby dla Claude**, a wynik „poniżej progu" jest
   twierdzeniem o parze (treść, tokenizer), nie o samej treści.
2. **Zbiór zdefiniowało polecenie, nie pomiar.** Czy „gorąca ścieżka" to
   właśnie te czternaście pozycji, jest założeniem — i jest to największe
   ryzyko tego wyniku, większe niż wybór tokenizera. Docstringi i komentarze
   w kodzie (polskie, obszerne) do zbioru nie weszły, bo nie ładują się do
   kontekstu sesji; gdyby ktoś liczył je jako gorącą ścieżkę, wynik byłby
   inny.
3. **Jeden tłumacz, jeden styl.** Przekład wykonała jedna osoba właśnie po
   to, żeby różnica stylu nie wsiąkła w wynik — ale to znaczy, że wynik jest
   przywiązany do tego jednego stylu. Drugi tłumacz dałby inną liczbę
   o nieznanej wielkości różnicy.
4. **Próg dotyczy SUMY zbioru** i tak został policzony. Na samych plikach
   polskich oszczędność wynosi 18,4% i też nie sięga 25% — werdykt nie zależy
   od tego, którą z dwóch podstaw się wybierze.

## Czego świadomie nie zrobiono

- Nie przetłumaczono jedenastu plików już angielskich. To nie jest zawężenie
  zakresu, tylko usunięcie z niego pracy, która nie istnieje.
- Nie tknięto `docs/pl/experiments/`, `konstytucja.md`, `zasady-agentyczne.md`,
  README ani kodu huba/CLI/TUI — polecenie wyłącza je wprost.
- Nie wykonano KROKU 2. Próg jest progiem, a nie punktem wyjścia do dyskusji.

## Nierozstrzygnięte, zapisane żeby nie zginęło

Gdyby KROK 2 kiedyś nastąpił, jego warunek weryfikacji — **recenzent, który
nie czytał wersji PL** — jest dziś niespełnialny przez kogokolwiek z tego
repozytorium: `CLAUDE.md` wstrzykuje się do kontekstu każdej sesji otwartej
w tym katalogu, a `AGENTS.md` każe przeczytać pierwsze zdanie samego
polecenia. Zgłosił to `delta` (`seq 900`), zanim ktokolwiek zaczął tłumaczyć.

Czysty recenzent jest osiągalny, ale **nie w tym katalogu**: świeża sesja
otwarta poza repo nie dostaje wstrzyknięcia, więc trzeba jej podać wyłącznie
pliki EN i pytania — zamknięta lista wejść, nie lista zakazów. To ten sam
kontrakt, co przy sondzie cold-probe w
[`experiments/peer-audience/czujniki.md`](experiments/peer-audience/czujniki.md):
lista zakazów przecieka, lista zezwoleń nie.
