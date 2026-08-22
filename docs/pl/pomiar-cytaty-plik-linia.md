# Czy opłaca się strażnik cytatów `plik:linia`

**HEAD pomiaru:** `9d7fd6e`
**Czas pomiaru:** 2026-08-22, pokój `poligon2`
**Wykonał:** agent2 (Opus 5, Claude Code), deklaracja `seq 59`; niezależny
pomiar kontrolny i dwie kontrofensywy: agent1 (Opus 5, Claude Code)

Pytanie było jedno i operacyjne: **czy warto postawić w CI test, który
pilnuje, żeby wskaźniki `plik:linia` w dokumentacji trafiały tam, gdzie
obiecują.** Poniżej liczby, potem werdykt, potem to, czego ten pomiar nie
mówi.

Powstało, bo w jednej sesji **jedenaście** wskaźników okazało się fałszywych —
w `SECURITY.md`, `AGENTS.md`, `CONTRIBUTING.md`, runbooku, playbooku zasad
i w trzech plikach eksperymentu. Nie znalazł ich żaden test. Znalazło je
czytanie plików, jeden po drugim.

## Werdykt

**NIE PISZEMY GO.** Najtańszy możliwy strażnik („cytowana linia istnieje
i nie jest pusta") widzi **4 z 11** defektów, jest ślepy na **7**, i przy tym
krzyczy na **9** miejsc, w których nic złego nie ma. Zielony wynik takiego
testu czytałoby się jako „cytaty sprawdzone", a znaczyłby „żaden nie wpadł
w pustkę" — czyli mniej, niż wie dziś każdy, kto tu pracuje.

Wariant mocniejszy — „symbol nazwany w tekście obok cytatu musi wystąpić
w cytowanym zakresie (+4 linie)" — sprawdzony na 40 wskaźnikach dał **11
alarmów, z czego prawdziwe były 2**, i tak przepuścił `tui.py:130`. 82%
fałszywych przy pominięciu połowy klasy. To zamyka też furtkę „napiszmy
mądrzejszy".

`docs/pl/konstytucja.md` każe w takiej sytuacji zapisać obserwację zamiast
budować. To jest ta obserwacja.

### Liczba rozstrzygająca: na dzisiejszym `main` byłoby 0 trafień na 11 alarmów

Zmierzone niezależnie przez oboje autorów, dwoma instrumentami, z tym samym
wynikiem co do sztuki — i **odtwarzalne u każdego, kto sklonuje repo**, bo
nazwy plików rozwiązujemy przez `git ls-files`, a nie chodzeniem po drzewie:

    wskaźników w żywych docs (oba końce zakresów)   79
    alarmów „pusta linia / poza plikiem"            11
      9  ←  ten plik
      2  ←  experiments/peer-audience/czujniki.md  (zapis historyczny)
      0  ←  wszystko inne

Liczba 79 obejmuje ten plik i zmienia się przy każdym dopisaniu do niego
akapitu — liczba alarmów nie. Kto ją odtwarza, dostanie inną wartość w lewej
kolumnie i tę samą w prawej.

**Wszystkie jedenaście są fałszywe.** Dziewięć na dokumencie, który tłumaczy,
dlaczego strażnika nie napisaliśmy; dwa na zapisie tego, co agent czytał
w przebiegu #1.

A trzy defekty, które NAPRAWDĘ zostały dziś w repo (`experiments/README.md`
×2, `rules-pokoju.md` ×1), w tym wyniku **nie występują** — trafiają w linie
niepuste. Jeden przebieg pokazuje więc 11 rzeczy, których nie ma, i milczy
o 3, które są. Stosunek prawdziwych do fałszywych na `main`: **0 : 11**.

## Dane

Zmierzone na wszystkich `.md` w gicie: **47 plików, 116 wskaźników** — 53
w żywych dokumentach, 63 w archiwum.

**Za archiwum uznajemy `docs/pl/superpowers/plans/`, `docs/pl/superpowers/specs/`
i `docs/pl/archive/`** — i to jest decyzja, nie fakt. `CLAUDE.md` nadaje status
archiwum wyłącznie `plans/`; `specs/` doliczamy przez analogię (to dokumenty
projektowe planów już wykonanych), a `docs/pl/experiments/` do archiwum **nie
należy**, bo to katalog czynnego eksperymentu. Ta granica jest tu wypisana,
bo dokładnie na niej rozjechały się nasze dwa niezależne pomiary.

Jedenaście defektów znalezionych **ręcznie**, przez porównanie treści cytowanej
linii z tym, co obiecuje zdanie obok:

| dokument | cytat | co tam naprawdę stało | gdzie mechanizm jest |
|---|---|---|---|
| `SECURITY.md` | `cli.py:67` | *pusta linia* | `:70` `_write_0600` |
| `AGENTS.md` | `cli.py:69` | *pusta linia* | `:70` `_write_0600` |
| `runbook-migracja-kanalu.md` | `cli.py:199` | *pusta linia* | `:200` `odswiez_howto` |
| `runbook-migracja-kanalu.md` | `cli.py:266` | *pusta linia* | `:267` `ensure_hub` |
| `CONTRIBUTING.md` | `cli.py:715` | `if _procfs_dostepne():` | `:1159` `signal.SIGKILL` |
| `runbook-migracja-kanalu.md` | `cli.py:240` | `biezacy = howto.read_text(…)` | `:245` `return "aktualne"` |
| `zasady-agentyczne.md` | `client_session.py:203` | `def _state_lock` | `:256` `uuid.uuid4()` |
| `zasady-agentyczne.md` | `tui.py:130` | `groups = _normalized_groups(…)` | `:211` `/kick` |
| `experiments/peer-audience/README.md` | `cli.py:51` | komentarz | `:52` `DEFAULT_RULES = ""` |
| `experiments/peer-audience/README.md` | `test_skills.py:237` | `sprawdzone = 0`, środek cudzego testu | `:446` `assert DEFAULT_RULES == ""` |
| `experiments/peer-audience/rules-pokoju.md` | `chat/server.py:1014` | komentarz o `open_addr` i replayu | `:1057` odczyt `rules` w hello, `:567` `_load_rules` |

Pierwsze cztery lądują na pustej linii — **widzi je najtańszy strażnik.**
Siedem pozostałych ląduje na linii niepustej, w poprawnym pliku, i **żadna
heurystyka „linia istnieje i coś na niej jest" nie odróżni ich od trafienia.**

Osiem pierwszych poprawiono tego dnia (`c644f37`, `a305828`, `9d7fd6e`). Trzy
ostatnie **zostawiono świadomie**: `experiments/peer-audience/` to katalog
przebiegu prerejestrowanego w `f7240d3`, a robota nad artefaktami
eksperymentu w jego trakcie należy do operatora albo do chwili po zamknięciu
przebiegu.

## Trzy rzeczy, których strażnik nie umie — i nie jest to kwestia implementacji

**Ten plik jest dowodem sam na siebie.** Wskaźniki `cli.py:69`, `cli.py:199`,
`cli.py:266`, `cli.py:239` w tabelach powyżej trafiają w puste linie,
a `chat.client_session.py:21` w plik, którego nie ma — i **każdy z nich jest
tu poprawny**, bo dokumentuje defekt, a nie mechanizm. Strażnik postawiony
w CI zapaliłby się na dokumencie, który tłumaczy, dlaczego go nie ma.

1. **Cytat w zapisie historycznym trafia w pustkę i JEST prawdziwy.**
   `experiments/peer-audience/czujniki.md` notuje, że agent czytał wtedy
   `cli.py:239-263` i `czujniki.md:107-110`. Oba trafiają dziś w pustkę i oba
   są poprawnym zapisem tego, co się wydarzyło. Przenumerowanie ich
   sfałszowałoby dowód eksperymentu — strażnik żądałby edycji niszczącej
   zapis. To najważniejszy wynik całej sprawy: dowodzi, że kryterium „pusta
   linia" **mierzy co innego niż „cytat kłamie"**.
2. **Bliźniaki są niejednoznaczne z założenia.** `collaboration.md`
   i `troubleshooting.md` istnieją po dwa razy — w skillu Claude'a i Codeksa —
   a `tests/test_skills.py` wprost pilnuje, żeby były bliźniakami. Strażnik
   musiałby umieć powiedzieć „nie wiem" inaczej niż „źle".
3. **Cytat bywa prozą, nie ścieżką.** `chat.client_session.py:21` (nazwa
   modułu z kropkami), `agentmachi/justjoinet/data/howto.md:19` (ścieżka
   w `~/.agentmachi`, nie w repo). Zdania poprawne, plików w repo nie ma.

Do tego **archiwum**: `superpowers/plans/` i `specs/` to zapis stanu sprzed
miesiąca, a nie dług. Plan B7 cytuje `server.py:591` („wejście jako human
wymaga tokenu") i `server.py:503` (`ChatServer._handler`); w `chat/server.py`
pierwsza z tych linii to dziś zdanie z cudzego docstringa, druga komentarz o aktualizowaniu
statusu, a `_handler` stoi w 791. Oba są **ślepe** dla strażnika na pustkę i oba są
poprawnym zapisem stanu z 23 lipca. Strażnik krzyczący na archiwum jest
bezużyteczny z konstrukcji.

Każda z tych czterech granic to **ludzka decyzja zaszyta w konfiguracji
testu**. Bramka z `CLAUDE.md` mówi, czym to jest: podejmowaniem decyzji za
agenta zamiast dawania mu brakującej możliwości.

## Strażnik chodziłby po czystym klonie, a agent pracuje w swoim drzewie

To wyszło na końcu i nie zależy od tego, jak dobry byłby strażnik.

Te same dwa cytaty z planu B7 — `server.py:591` i `:503` — u jednego z autorów
rozwiązały się na `chat/server.py` (linie niepuste, zwykłe zgnicie), a u
drugiego **wypadły poza koniec pliku**. Nie z powodu wzorca: w drzewie roboczym
leży `./server.py`, 37-linijkowy plik-scratch, który wyciekł do repo przez
`git add -A` w B6, został z niego usunięty (`4f55c9e`) i wpisany do
`.gitignore:49` — ale nikt go fizycznie nie skasował. Goła nazwa `server.py`
w cytacie trafiła u jednej strony na niego.

Wynik pomiaru zależał więc od **nieskomitowanego śmiecia w cudzym katalogu**.
Nie „mógł zależeć" — zależał, i różnica była cicha.

Strażnik w CI chodzi po czystym klonie, gdzie tego pliku nie ma. Jego werdykt
rozjeżdżałby się z tym, co widzi agent u siebie, i to bez żadnego sygnału:
zielone CI przy cytacie, który u człowieka w drzewie prowadzi donikąd, albo
czerwone przy takim, który lokalnie trafia.

To ta sama wada, którą `CLAUDE.md` zarzuca ledgerowi — **wiedza zależna od
stanu jednej maszyny nie jest wiedzą repozytorium.** Instrument pomiarowy też
jej podlega, i stąd reguła, którą warto wynieść poza tę sprawę: *nazwy plików
rozwiązuj przez `git ls-files`, nie przez chodzenie po drzewie.* Trzy z sześciu
dzisiejszych wpadek instrumentu znikają od tej jednej zmiany.

## Przesłanka, która nie przetrwała — i dlaczego to ważne

W trakcie pomiaru padło zdanie: „CI łapie gnicie; liczby, której nikt nigdy
nie sprawdził, nie złapie żaden strażnik" — z obserwacji, że część cytatów
była fałszywa **w dniu wpisania**, a nie zgniła później.

**Obalone.** Strażnik liczy stan przy KAŻDYM commicie, więc cytat zły od
urodzenia zapala się na tym samym przebiegu, który go wprowadza — dla CI jest
łatwiejszy niż zgnicie, nie trudniejszy. Podział urodzenie/gnicie nie ma
z wartością strażnika nic wspólnego.

Zostaje to tutaj, bo werdykt stoi wyłącznie na tym, **gdzie ląduje zły
cytat** — i tylko dlatego się broni. Gdyby stał na obalonej przesłance,
byłby prawdziwy przez przypadek.

## Czego ten pomiar NIE mówi

- **11 to dolna granica, nie bilans — i wiadomo to z zachowania samej
  liczby.** W ciągu jednej godziny urosła **8 → 10 → 11**, za każdym razem gdy
  jedno z nas spojrzało z innej strony: raz przez błędną klasyfikację
  `experiments/`, raz przez przeliczenie po pełnej ścieżce zamiast po nazwie
  pliku. Po dniu patrzenia we dwoje nadal nie znamy rozmiaru próbki. To jest
  mocniejszy argument za werdyktem niż którakolwiek z tych trzech liczb.
- **Nie wszystko zostało sprawdzone treściowo.** Sprawdzone: cały
  `SECURITY.md` (dwoma niezależnymi przebiegami), 6 wskaźników poprawionych
  ręcznie, `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `docs/philosophy.md`.
  Niesprawdzone zostają m.in. wskaźniki bliźniacze i prozą w
  `zasady-agentyczne.md` oraz trzy w `czujniki.md`. Reszta jest „zdrowa"
  wyłącznie w sensie **niepusta** — czyli w sensie, o którym ten pomiar
  właśnie ustalił, że nic nie znaczy.
- **Liczby zależą od instrumentu i my też się nie zgodziliśmy.** Cytatów
  w żywych dokumentach: 53 u jednego z nas, 52 u drugiego; cytatów
  w `SECURITY.md`: 27 i 34, zależnie od tego, czy liczyć drugie końce zakresów
  i gołe liczby w nawiasach. Żadna z tych różnic nie zmienia werdyktu i żadnej
  nie rozstrzygamy — podajemy je, bo plik o zgniłych cytatach nie ma prawa
  udawać, że jego własne liczby są jedyne możliwe.
- **Nie mierzy archiwum treściowo** — tylko stwierdza, że nie powinno podlegać
  strażnikowi.
- **Nie mówi, że cytaty `plik:linia` są złym pomysłem.** Mówi, że ich
  poprawności nie da się tanio zautomatyzować. Kotwiczenie w nazwanym symbolu
  obok liczby (`_write_0600`, `MAX_FRAME_BYTES`) kosztuje jedno słowo i daje
  czytelnikowi drogę odzyskania celu, gdy liczba zgnije — ale to konwencja
  pisania, nie test.

## Dwa instrumenty, dwie różne liczby — i to też jest wynik

Pomiar robiliśmy niezależnie i dostaliśmy różne liczby (4 vs 5 defektów
w żywych dokumentach). Rozjazd nie wziął się z kodu, tylko z **zakresu**:
jedna strona wrzuciła `docs/pl/experiments/` do archiwum razem z `plans/`,
a to katalog czynnego eksperymentu. Właśnie te dwa pominięte wskaźniki
okazały się trzecią kategorią z listy wyżej.

Druga strona przeszła cztery wersje własnego instrumentu i **trzy pierwsze
były zielone na swój sposób, każda kłamiąc inaczej**: gubiły skrócone ścieżki,
potem gubiły je ciszej (`.venv` robił z `cli.py` dwóch kandydatów, więc wpis
szedł do kosza jako „nierozstrzygalny"), potem gubiły drugie końce zakresów.

Wniosek, który dotyczy każdego przyszłego pomiaru w tym repo, nie tylko tego:
**wzorzec grepa jest pomiarem i sam wymaga kontroli.** Instrument, który nie
mógł cię sfalsyfikować, wygląda dokładnie jak instrument, który cię
potwierdził.
