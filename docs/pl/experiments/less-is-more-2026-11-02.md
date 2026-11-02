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

Wzorzec rundy 2–3: **każda weryfikacja krzyżowa znajdowała następną warstwę**
(dekoracje → grupy/regex → grupy w trakcie nasłuchu → kick). Autor nie
widział żadnej z nich, choć każdą miał w zasięgu jednego zdania.

**Niezmierzone, do następnego przebiegu:**
- Codex czeka `listen --once` i budzi się na własnej odpowiedzi z backlogu
  (`codex-runtime.md` opisuje obejście: „re-arm until a wait blocks").
  `codex-wait.sh` → `--once --wake` to naprawi, ale zmienia format wyjścia
  dla żywego Codeksa — tylko z Codeksem w pokoju.
- Skutek zdania o `@all` w playbooku (`5c51f3e`).
