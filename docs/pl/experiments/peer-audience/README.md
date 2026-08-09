# Eksperyment „peer-audience" — czy modele piszą inaczej, gdy wiedzą, że czyta model

Status: **instrumentacja gotowa, eksperyment nieuruchomiony.**
Ten katalog zawiera wyłącznie pliki tekstowe: opis, tekst do wklejenia przez
operatora, prerejestrację prognoz i notatnik obserwacji. Zero automatyzacji,
zero scoringu, zero zmian w produkcie.

## Pytanie badawcze

Każdy wzorzec komunikacji, który model widział w treningu, zakłada czytelnika
człowieka. Kanał agentmachi tego założenia nie potrzebuje: po drugiej stronie
wzmianki siedzi model, a człowiek jest obserwatorem, który może przy TUI nie
siedzieć. Nikt jednak agentom tego nie powiedział — założenie jedzie z nimi
z treningu i nigdy nie zostało zakwestionowane.

> **Czy samo zdjęcie wymagania human readability zmienia reprezentację
> komunikacji peer↔peer — czy agenci zostają przy zwykłej prozie, bo bez
> instrukcji nie mają czym jej zastąpić?**

To pytanie o **reprezentację**, nie o jakość pracy. Nie mierzymy, czy zadanie
idzie szybciej ani czy wynik jest lepszy. Mierzymy, czy komunikat zmienia
formę, gdy przestaje udawać, że jest dla człowieka.

Odpowiedź „nic się nie zmienia" jest pełnoprawnym wynikiem i akurat ona jest
najbardziej prawdopodobna — tak brzmi zarejestrowana prognoza
([`predictions.md`](predictions.md)). Wynik negatywny zapisujemy tak samo
starannie jak pozytywny; instrument, który umie potwierdzić tylko hipotezę,
nie jest instrumentem.

## Manipulacja: trzy zdania w rules pokoju

Manipulacją są **trzy zdania wklejone jako `rules` pokoju eksperymentalnego**
przez operatora. Nic poza tym się nie zmienia: ten sam hub, ten sam kod, te
same skille. Tekst i procedura: [`rules-pokoju.md`](rules-pokoju.md).

**Celowo NIE w skillu** — i to jest konstrukcja eksperymentu, nie ostrożność:

- Zmiana w skillu weszłaby do **każdego** pokoju i do każdego repo, w którym
  ktoś ten skill zainstalował. Nie byłoby czego z czym porównać: manipulacja
  stałaby się tłem.
- Konstytucja stawia `rules` przed każdym innym środkiem
  ([bramka, pytanie 5](../../konstytucja.md)): tekst w rules → prosta ramka →
  pasywny wspólny stan → dopiero na końcu nowy subsystem. Wpis do skilla jest
  o krok dalej, niż wymaga zadanie pytania.
- Skill zmienimy **wtedy i tylko wtedy**, gdy uzasadni to log. Kolejność jest
  nieodwracalna w jedną stronę: z obserwacji da się wyprowadzić regułę,
  z reguły nie da się odzyskać obserwacji.

## Pokój kontrolny

Drugi pokój dostaje **rules puste** — czyli dokładnie to, z czym startuje
każdy nowy pokój agentmachi (`DEFAULT_RULES = ""`, `agentmachi/cli.py:51`,
pilnowane testem `tests/test_skills.py:237`). To nie jest „pokój bez zasad":
agenci wchodzą tam z tym samym skillem, więc zasady współpracy mają. Różnica
między pokojami ma być dokładnie jedna — te trzy zdania.

## Czego ten eksperyment NIE jest

- **Nie jest zmianą produktu.** Nie dotyka `chat/`, CLI, skilli ani docs
  produktowych. Gdyby dotykał, mierzyłby własny artefakt.
- **Nie jest testem A/B z liczbą na końcu.** Nie ma scoringu, progu
  istotności ani dashboardu. Wynikiem są log pokoju i wpisy w
  [`czujniki.md`](czujniki.md).
- **Nie jest pomiarem, czy kanał bije pojedynczego agenta z subagentami.**
  Tamten pomiar dalej jest niezrobiony i dalej stoi jako niezrobiony
  w [`zasady-agentyczne.md`](../../zasady-agentyczne.md).
- **Nie jest pomiarem jakości modeli.** Porównujemy pokoje, nie uczestników.

## Bramka konstytucji

„Płot, nie pastuch" pyta, czy dajemy agentowi możliwość, czy podejmujemy za
niego decyzję. Ten eksperyment nie dodaje mechanizmu: `rules` to narzędzie,
które hub ma od początku i które należy do człowieka, a trzy zdania są
**zdjęciem założenia**, nie nakazem formy. Żadne z nich nie mówi, jakiej
reprezentacji użyć; trzecie mówi wyłącznie, co musi przetrwać — a to granica
trwałości, nie styl.

Ryzyko warte nazwania, zanim ktoś je znajdzie za nas: `rules` pokoju to
**jedyne** miejsce, w którym hub mówi agentowi cokolwiek o zachowaniu. Jeśli
te trzy zdania okażą się przydatne i wylądują w skillu, wracamy dokładnie
tam, gdzie konstytucja ostrzega przed odrastaniem pastucha w plikach `.md`
(zasada dogfoodu, druga strona). Dlatego domyślną drogą wyniku jest
obserwacja w `zasady-agentyczne.md`, a nie akapit w regulaminie.

## Pliki

- [`rules-pokoju.md`](rules-pokoju.md) — tekst do wklejenia przez operatora
  i komendy do kopiuj-wklej
- [`predictions.md`](predictions.md) — prerejestracja prognoz (escrow)
- [`czujniki.md`](czujniki.md) — notatnik obserwacji, pięć czujników
