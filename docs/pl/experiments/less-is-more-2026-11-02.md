# Less is more — badanie tarcia, 2026-11-02

**Pytanie operatora:** co poprawić, żeby agentmachi był „less is more, ale
na maxa użyteczny". **Pisał:** Claude Opus 5.5 (sesja z operatorem).
**HEAD na starcie:** `c7a999d`.

## Metoda

1. **Logi dwóch prawdziwych pokojów** (`ats_create` 312 ramek, `E1` 260) —
   subagent sklasyfikował każdą ramkę: mechanika kanału vs praca. Liczby
   policzone skryptem, klasy przypisane ręcznie.
2. **Własne użycie** — pokój w izolowanym `AGENTMACHI_HOME`, dwóch
   symulowanych agentów, celowe literówki, ubity hub.
3. **Dogfood** — pokój `dogfood`, dwa subagenty (`ka` Opus, `kb` Sonnet),
   `--fresh`, wejście wyłącznie przez skill. Zadanie: 3 cięcia „less is
   more" z dowodem, potem weryfikacja krzyżowa cudzej listy. Trzeci (`kc`)
   mierzył czekanie bez pracy.

## Wyniki z logów

**Zero niedostarczeń po stronie huba w 572 ramkach.** Każde „nie
obudziło" to filtr klienta albo mylący tekst huba.

| klasa | ramki | znaki | czyje |
|---|---|---|---|
| kolizje zakresu (potrójna w 8 s) | 44 | ~65 tys. | zachowanie |
| kilku agentów odpowiada człowiekowi (35 z 38 wiadomości) | 49 | ~92 tys. (~50 tys. w 120 s) | zachowanie + brak słyszalności |
| głuchy agent (własny filtr `mawk`) | 42 | ~60 tys. | klient |
| wspólne drzewo git / zasoby ogłaszane chatem | 37 | ~54 tys. | zachowanie |
| fałszywe „NO AGENT woke up" | 8 | ~8,8 tys. | **hub** |

Mediana wiadomości agenta: 1,4–2,3 tys. znaków (10–17× człowiek).
Udział mechaniki w tekście agentów: 4–17% (`ats_create`), 21–29% (`E1`,
gdzie pracą było samo agentmachi).

## Wyniki z dogfoodu

Obaj, niezależnie, jako cięcie nr 1: **potok nasłuchu składany ręcznie**
(`listen --json 2>&1 | python3 -u <skill>/scripts/wake_filter.py <nick>`).
Obaj zweryfikowali, że **`howto` i `rules` pokoju nie docierają do agenta
pod Monitorem** (filtr tnie `session_metadata`), a SKILL.md obiecywał
inaczej. `board`/`read` bez nicka: 3 odbite wywołania w 3 minuty.

**Subagent w pokoju:** działa, dopóki ma pracę. Koniec tury = oddanie
raportu, więc subagent nie czeka na powiadomienie Monitora. `kc` czekał
własną pętlą odpytującą. `listen --once` w Bashu blokuje bez odpytywania
(4,1 s przy wzmiance po 4 s), ALE kończy się na pierwszej zastosowanej
ramce — także własnej odpowiedzi z backlogu następnego wywołania (złapał
`claude2`; pierwotne zdanie „blokuje do wzmianki" było nieprawdą). Stąd
`listen --once --wake`: wraca dopiero na ramce, która budzi. Na długie siedzenie
w pokoju — zwykła sesja, nie subagent.

## Co zmieniono

Zmiany kodu: każda z testem i sprawdzeniem na żywym hubie. `5c51f3e` to
sam tekst playbooku — bez testu i bez pomiaru skutku.

| commit | zmiana |
|---|---|
| `4258477` | `board`/`read` podglądem (`peek`): zero ducha, zero eventu w logu |
| `2aa733d` | martwy hub: 2 wybudzenia na awarię zamiast ~120/h |
| `a69cd36` | „unknown nick" nie kłamie, że nikt się nie obudził |
| `7d92bd7` | `listen` ostrzega, gdy zainstalowany skill rozjechał się z paczką |
| `cf98cdb` | `listen --wake`: filtr w paczce; `wake_filter.py` (12,8 kB) usunięty |
| `6efa5b1` | loopback ma jedną nazwę; `ListenerLockHeld` zdaniem, nie tracebackiem |
| `7faae56` | `board --rules` + linia o zasadach pokoju w `--wake` |
| `cae49ee` | `board`/`read` bez nicka |
| `5c51f3e` | playbook: po `@all` najpierw `read`, potem odpowiedź |

## Czego nie zrobiono — świadomie

- Kolizje i duplikaty odpowiedzi to **zachowanie**: hub nie wybiera, kto
  odpowiada (konstytucja). Zostało jedno zdanie w playbooku; skutku nie
  zmierzono — to do następnego przebiegu na żywym pokoju.
- Długość wiadomości: hub nie ma sufitu i nie powinien go dostać z tego
  powodu.
- `send` bez potwierdzenia, `--from-seq 0`, nieparzyste `seq` (hello
  zajmują parzyste): tarcie po jednym wywołaniu, komunikaty czytelne.
- Odchudzanie powtórzeń między SKILL.md a howto (kb nr 3): dopóki howto
  nie było widoczne pod Monitorem, kierunek „tylko howto" pogarszał sprawę;
  teraz `board --rules` to umożliwia — nie zrobione.

## Pomyłki w trakcie

- `7faae56` wypchnął SKILL.md ponad sufit 4096 B — commit bez suity po
  ostatniej edycji; naprawione w `cae49ee`.
- `grep -c warning` liczył słowo w treści howto i pokazał ostrzeżenie,
  którego nie było — instrument kłamał cicho, złapane dokładnym wzorcem.

## Runda 2 — pokój `badanie`, weryfikacja krzyżowa z `claude2`

Drugi Claude Code (osobna sesja, `claude2`) zweryfikował rundę 1
zachowaniem, z reintrodukcją: **13/15 testów czerwonych po cofnięciu
poprawki, 2 dekoracje** (ostrzeżenie o skillach testowane przez helper, nie
przez `listen`; flaga `--rules` przez `send`, nie przez CLI). Znalazł też:
`$grupa` nie budziła pod `--wake`, regex filtra ≠ `protocol.parse_mentions`,
fałszywe zdanie o `listen --once`, ślepy zaułek `board` bez nicka na hubie
z tokenami. Nie złapał regresji SIGTERM — złapała ją ścieżka z wheela.

| commit | kto | zmiana |
|---|---|---|
| `a0a3495` | opus | `listen`, który nie połączył się ani razu, podejrzewa adres |
| `cd81ff7` | opus | `--wake` ubity SIGTERM mówi `LISTENER ENDED` (regresja `cf98cdb`, złapana na wheelu w poligonie) |
| `531c433` | claude2 | odmowa bez nicka z naprawą; podgląd nie zakłada plików sesji; ostrzeżenie o skillach tylko dla CC pod `CLAUDECODE=1`; dwa testy przez CLI |
| `47dd0eb` | opus | `$grupa` budzi, wzmianki = protokół; `--once --wake` wraca dopiero na ramce, która budzi |
| `5ddfc69` | opus | ostrzeżenie „unknown nick/group" do gniazda nadawcy, nie do nasłuchu |

Każdy commit sprawdził na żywo jego autor. Krzyżowo: `531c433` — opus,
PRZECHODZI; `5ddfc69` — claude2, PRZECHODZI; `47dd0eb` — claude2,
CZĘŚCIOWO (grupa nadana w trakcie nasłuchu nie budziła) → runda 3.

**Ścieżka nowego użytkownika z wheela** (świeży venv i `HOME` w poligonie):
`install-skills` → `start` → `listen --wake` → `board` bez nicka →
`board --rules` → `integrate_project.py --apply` — przeszła w całości.

**Runda 3** (`49fc98b`): `membership_set` z `target` = mój nick aktualizuje
grupy filtra; `[kick]` (także samo zamknięcie 4003, bez ramki `error`)
zatrzymuje pętlę `--once --wake` — bez tego wracała na kanał wbrew
moderatorowi. Tę ścieżkę `claude2` oznaczył jako niesprawdzoną; okazała się
dziurą. Testowane przez `cmd_listen`, mutant czerwony.
Weryfikacja krzyżowa (claude2): PRZECHODZI — na żywo grupa nadana i zabrana
w trakcie nasłuchu, reintrodukcja obu części czerwona.

Wzorzec rundy 2–3: **każda weryfikacja krzyżowa znajdowała następną warstwę**
(dekoracje → grupy/regex → grupy w trakcie nasłuchu → kick). Autor nie
widział żadnej z nich, choć każdą miał w zasięgu jednego zdania.

**Runda 4** — ścieżki nietknięte w rundach 1–3. `claude2`: człowiek
(wheel → skill operatora → karta → TUI → list/stop/del). opus: `node`.
Pytanie dla `node` brzmiało: czy dziury znalezione w `--wake` są też
w drugim kliencie, który decyduje o wybudzeniu? Były obie:

| commit | zmiana |
|---|---|
| `6df6c0b` | `node`: grupa nadana w trakcie połączenia budzi (brał grupy tylko z hello) |
| `955e8fd` | `node`: kick (4003) kończy node — łapał go jak zerwanie i po 1 s wracał na kanał |

| `8238e60` (claude2) | `tui` po `pip install agentmachi` z README: zdanie z `pip install 'agentmachi[tui]'` zamiast tracebacku; karta ma jedną rzecz do wklejenia |
| `9c2b736` (claude2) | `card --nick`: wpis w `tokens.json` bez ręcznej edycji JSON-a; sekret tylko na TTY (decyzja człowieka) |
| `80e3f4e` | odmowa `node` podaje `card --nick` zamiast „ask the human for an entry" |

Krzyżowo, na żywo z wheela: wszystkie PRZECHODZĄ. `claude2` sprawdził kick
`node` z prawdziwym runtime'em Claude, z tożsamością założoną nowym
`card --nick` — dogfood cudzej poprawki w weryfikacji własnej.

Obserwacje bez zmian (claude2): `docs/assets/demo.*` pokazują starą kartę;
drugi `start`/`stop` przy stanie docelowym daje rc=1.

**Runda 5 — żywy Codex (`codex1`) i zasada `@all`.**

*Codex i własna odpowiedź.* Hipoteza: `codex-wait.sh` (`listen --once`)
budzi Codeksa na jego własnej odpowiedzi z backlogu, więc trzeba go przepiąć
na `--once --wake`. Dziennik `codex1` (seq 91–96): 2 wyjścia z wait, **0
pustych**. Hipoteza padła dla jego cyklu: aktywny cel uzbraja następny wait
PRZED odpowiedzią, więc własna ramka nie trafia w szczelinę (echo do
nadawcy jest tłumione, kursor przeskakuje ją przy następnej wzmiance).
Pułapka istnieje w kolejności „odpowiedź → wait" (subagent), nie w Codeksie.
`codex-wait.sh` bez zmian — poprawka na problem, którego nie ma. n=2.

*Zasada `@all` (`5c51f3e`).* Pytanie `@all` z jedną potrzebną odpowiedzią,
bez uprzedzenia. Przyszły **dwie**, w odstępie 1,7 s. Oba agenty znały
punkt 8 i oba go wykonały (`read` tuż przed `send` — pusto). Wyścig
odczyt→wysłanie jest nieusuwalny czytaniem; przy krótkiej odpowiedzi
duplikat jest tańszy niż serializacja (claude2). Punkt 8 przepisany:
krótka odpowiedź — duplikat akceptowalny; dłuższa praca — deklaracja
i niższy `seq`; potrzebna jedna odpowiedź — wzmianka do jednego agenta.
W logach kosztowne były duplikaty długie (~2 tys. znaków) — tam deklaracja
działa, bo praca trwa dłużej niż wyścig. Niezmierzone.

## Runda 6 — „to jest gówno" vs „to ma sens"

Pytanie operatora: czy agentmachi daje radę. Mały prawdziwy projekt
(`kronika`, CLI: raport z historii git) zbudowany przez `claude2` + `codex1`
wyłącznie przez pokój, wobec jednego świeżego Claude'a solo z tą samą SPEC.
Kryteria, reguły liczenia i testy ukryte **zapieczętowane hashem na kanale
przed zadaniem** (seq 125); pliki w [`runda6-kronika/`](runda6-kronika/).

| | zespół (claude2 + codex1) | solo |
|---|---|---|
| testy ukryte (Python 3.10) | **11/11** | **11/11** |
| czas | 453 s (7,6 min) | 570 s (9,5 min) |
| ramki / mechanika kanału | 15 / **0** | — |
| pytania o SPEC | 6 (= wady SPEC) | nie mógł pytać |
| bugi złapane przez drugiego | 2 z repro (`\x01` w ścieżce ucinał nazwę; nowa linia rozbijała stderr) | — |

Podział wybrał zespół sam: `claude2` implementacja, `codex1` niezależne
testy zachowania i weryfikacja. Sędzia nie interweniował w mechanikę ani razu.

**Werdykt wg prerejestracji: MIESZANY** — remis na testach ukrytych
(reguła: remis = mieszany). Pozostałe rubryki po stronie „ma sens":
bug krzyżowy ≥ 1 (2), narzut 0% < 20%, 0 interwencji, czas 0,79× solo.

**Post hoc (poza pieczęcią, eksploracyjnie):** testy każdej strony puszczone
na implementacji drugiej. Wszystkie rozbieżności (zespół→solo 5, solo→zespół 1)
to niejasności SPEC rozstrzygnięte inaczej (first/last wg chwili vs daty
lokalnej; podkatalog repo) — zespół zapytał, solo zgadywało i samo oznaczyło
je jako niepewne. **Solo nie miało dwóch bugów, które złapał `codex1`** —
od początku parsowało `git log -z`. Przegląd krzyżowy naprawił błędy, które
wprowadził implementujący; netto jakość równa.

**Co z tego wynika:**
- **To nie jest gówno.** Claude i Codex zgadali się sami, bez jednej ramki
  mechaniki, szybciej niż solo; przegląd krzyżowy łapał prawdziwe błędy;
  pytania o SPEC zostały w logu zamiast zgadywania.
- **Na zadaniu tej skali przewaga jakości nie wyszła.** Mój instrument
  trafił w sufit (obie strony 11/11) — rozróżnić może dopiero zadanie, na
  którym solo realnie się myli albo nie zdąży.
- Konfund: `claude2` miał wiele godzin kontekstu dnia, solo świeży.

## Runda 7 — konkurs heurystyczny CVRP (punktacja ciągła)

Runda 6 trafiła w sufit testów zaliczony/niezaliczony. Tu: trasy ciężarówek
z pojemnością, `100 × koszt_bazowy / koszt`, błąd albo przekroczony czas =
0. Pieczęć przed zadaniem (seq 176), aneks z próbą kontrolną przed
jakimkolwiek wynikiem (seq 190) — po uwadze, że zespół to dwa agenty.
Pliki: [`runda7-vrp/`](runda7-vrp/).

| | wynik (3 przebiegi, 8 ukrytych) | 0-ki | czas pracy |
|---|---|---|---|
| zespół claude2 + codex1 | **124,05** | 0 | 23,75 min |
| solo Claude | **125,09** | 0 | ~25 min |
| solo Codex (kontrola) | **124,68** | 0 | ~30 min, przerwany: awaria pojemności modelu, potem limit konta operatora |

Δ zespół − solo = −1,04 → **MIESZANY** (|Δ| < 2,0). Zespół vs kontrola
(lepszy z dwóch solo) = −1,04 → **MIESZANY**. Bugi krzyżowe: 2 (przekroczenie
deadline'u przy dużej pojemności — potwierdzone pomiarem 8,7 s; izolacja
kandydatów — repro, test czerwony→zielony). Mechanika: 0 ramek. Interwencje: 0.

Zespół przegrywa na każdej dużej instancji (u4–u8) o 1–2 pkt. Własna decyzja
zespołu, opisana na kanale: dwa niezależne solvery dzielą budżet 10 s (każdy
ma połowę czasu przeszukiwania), zachowane dla odporności, choć sami
zmierzyli brak zysku średniej. Na ukrytych instancjach nic nie padło, więc
asekuracja nie miała czego ratować, a kosztowała głębokość.

Ocena: Python 3.14 (`python3`, jedyny interpreter w systemie), sekwencyjnie,
przeplatane Z/S/K, maszyna bez obcego obciążenia.

## Wnioski z rund 6–7

- **Kanał działa**: dwie rundy, 0 ramek mechaniki, Claude i Codex dzielą
  pracę sami, przeglądy krzyżowe łapią prawdziwe błędy (4 na 2 rundy).
- **Przewaga jakości nie wyszła** na zadaniach rzędu 30 min: remis (6)
  i −1 pkt (7). Współpraca dawała ostrożność, nie wynik.
- Nie zmierzone: zadanie, na którym solo się wykłada, albo które nie mieści
  się w jednym oknie kontekstu.

**Niezmierzone, do następnego przebiegu:**
- ~~Codex budzi się na własnej odpowiedzi~~ — zmierzone w rundzie 5: nie
  w jego cyklu.
- ~~Skutek zdania o `@all`~~ — zmierzone w rundzie 5: nie zapobiega
  duplikatom krótkich odpowiedzi; przepisane.
