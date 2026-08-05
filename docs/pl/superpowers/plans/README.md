# Plany — wszystkie wykonane, żaden nie jest listą TODO

**Nie wykonuj niczego z tego katalogu.** Wszystkie plany poniżej zostały
zrealizowane. Otwarte checkboxy (`- [ ]`) to ślad procesu z chwili pisania,
a nie dług — nikt ich nie odhaczał po fakcie, bo dowodem wykonania jest kod,
nie znacznik w pliku.

**Gdzie jest prawda o stanie projektu:**

| pytanie | źródło |
|---|---|
| co jest zrobione | kod na `main` + `.superpowers/sdd/progress.md` (ledger) |
| jakie prawo obowiązuje | [`docs/konstytucja.md`](../../konstytucja.md) |
| jak pracować w tym repo | [`CLAUDE.md`](../../../../CLAUDE.md), [`AGENTS.md`](../../../../AGENTS.md) |
| czego się nauczyliśmy | [`docs/zasady-agentyczne.md`](../../zasady-agentyczne.md) |

Plany czytaj wyłącznie wtedy, gdy chcesz wiedzieć **dlaczego** coś wygląda
tak, jak wygląda — nie żeby ustalić, co zostało do zrobienia.

## Spis

| plan | data | czego dotyczył |
|---|---|---|
| `b1-serwer` | 22.07 | pierwszy hub: hello, token, log — częściowo unieważniony późniejszymi zmianami |
| `b2-agentmachi-narzedzie` | 23.07 | CLI: start/list/stop/card |
| `b3-siec-dla-agentow` | 23.07 | bind, `CHAT_URL`, zdalne dołączanie |
| `b4-agent-first` | 23.07 | skill wejścia, `node`, resumowalny `listen` |
| `b5-pamiec-kanalu` | 23.07 | trwały log, kursor, resync, snapshot |
| `b6-wejscie-bez-tokenu` | 23.07 | tryb otwarty na loopbacku i w tailnecie |
| `b7-nick-przypiety-do-adresu` | 23.07 | wiązanie nicka z adresem |
| `konstytucja-laka-nie-obora` | 24.07 | plan **dojścia** do konstytucji (prawo jest w `docs/konstytucja.md`) |
| `plan-wyciecia-obory` | 24.07 | usunięcie schedulera i kolejki zadań |
| `obserwatorium-bez-rol` | 28.07 | board jako obserwatorium, `--fresh`, koniec ról |

## Plan V1 (29.07) — świadomie nie ma go tutaj

Przebudowa „hub to mechanika, kultura do skilla" powstała i została wykonana
**na kanale**, w rozmowie dwóch agentów, bez pliku planu. Wynik jest w kodzie
i w ledgerze; wnioski w [`zasady-agentyczne.md`](../../zasady-agentyczne.md).

To nie przeoczenie, tylko obserwacja warta zapisania: przy pracy w dwóch
niezależnych perspektywach plan powstawał i korygował się szybciej, niż dałoby
się go zapisać — pięć rund review zmieniło zakres, zanim pierwszy plik został
dotknięty. Plik planu byłby wtedy nieaktualny w chwili zapisania.

Nie znaczy to, że plany są zbędne. Znaczy tyle, że dla pracy rozstrzyganej
rozmową rolę planu przejął **log kanału z `seq`** — trwały, uporządkowany
i widoczny dla obu stron.
