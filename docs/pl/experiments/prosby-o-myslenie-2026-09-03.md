# Prośby o myślenie — pomiar na dwóch korpusach

**Liczył:** `nowy` (sesja spoza przebiegu E1) · **Data:** 2026-09-03
**HEAD przebiegu:** `c6a3887` — rodzic commita zapisującego ten plik
(`1edbe8e~1`, 2026-09-03 12:12:38). Odtworzone, ale **nie niezależnie**:
artefaktem jest wyłącznie relacja rodzic–dziecko w gicie, a to, że pomiar
szedł w tym samym drzewie, jest świadectwem liczącego i po fakcie nikt tego
nie sprawdzi. Z logów kanałów odtworzyć się nie da — `E1` był kompaktowany
(`seq=357`), a `interwizję` skasowano 2026-09-03.
Osobno, i ważniejsze niż sam numer: ten pomiar szedł **po logach kanałów,
nie po drzewie repo**, więc HEAD repo mówi tu o środowisku zapisu, nie
o materiale badania.

Powstało przy okazji zadania operatora, żeby dopisać do skilla pozwolenie
„needs include thinking". Zadanie **stanęło na warunku stopu** — akapit nie
mieści się w sufitach `BUDZETY` (`claude` +171 B, `codex` +145 B ponad
4096 B; trzy niezależne pomiary zgodne co do bajta). Pytanie badawcze
zostało, bo dotyczy nie akapitu, tylko tego, czy brakowało pozwolenia.

## Pytanie i kryterium, zamrożone przed liczeniem

Ile razy ktoś poprosił drugiego o **samo przemyślenie problemu** — bez
artefaktu do wydania — a ile o wykonanie albo weryfikację czegoś gotowego.

- **prośba o myślenie** = wzmianka + prośba o cudzy osąd nad problemem,
  który **nie ma jeszcze artefaktu** (brak commita, diffu, pliku, pomiaru),
- **prośba o wykonanie/weryfikację** = artefakt istnieje albo jest deliverable.

**Predykcja zamrożona przed policzeniem: zero próśb o myślenie.**

## Wynik

| korpus | prośby o wykonanie/weryfikację | prośby o myślenie |
|---|---|---|
| pokój `E1` (88 ramek, po fakcie) | 32 | **0** |
| pokój `interwizja` (surowy log, w trakcie roboty) | — | **3** |

Zero w korpusie 1 broni się przy **celowo szerszej** liście wzorców
(`podważ`, `zakwestionuj`, `oceń`, `twoim zdaniem`, `omówmy`, `zanim
zacznę`…): cztery trafienia, wszystkie po ręcznym sprawdzeniu okazały się
prośbami o osąd nad artefaktem, który **już istniał**.

**Predykcja padła na korpusie 2** i tak ma zostać zapisane.

## Trzy prośby o myślenie — cytaty dosłowne

Wszystkie od jednej sesji (`agent4`), w oknie 130 sekund, przed wynikami.
Przepisane **znak w znak z surowego logu**, łącznie z brakiem polskich
znaków w trzecim — pierwsza wersja tego raportu „poprawiła" tam diakrytyki
i złapał to autor cytowanych ramek:

    [623] 09:52:52  ale to MOJA ocena i chcę, żebyś ją zakwestionował,
                    jeśli się nie zgadzasz.
    [625] 09:54:03  Jesli masz zastrzezenie do ktoregokolwiek promptu —
                    powiedz TERAZ.
    [627] 09:55:02  i dokładnie dlatego chcę, żebyś ją podważył.

## Co rozstrzyga

**Odpowiedź na te trzy prośby przyszła o 09:56:43 — po komplecie wyników.
Odpalenie nastąpiło o 09:55:02, 59 sekund po ostatniej z nich.**

Pytający poprosił trzy razy i nie doczekał ani razu, bo sam nie czekał.

Stąd wniosek, i jest on **węższy niż liczba**: pozwolenia nie brakowało.
Prośby padły bez żadnego pozwolenia w skillu i bez potrzeby takiego
pozwolenia. Brakowało **czekania**. Prośba o przemyślenie, po której nie
czeka się na odpowiedź, jest prośbą o alibi — i tak wypadła raz, tego dnia,
kosztem jedynej kontroli całego eksperymentu ([E1](e1-subagent-swiezy-kontekst-2026-09-03.md),
sekcja „Fakt proceduralny").

Czego ten pomiar **nie** mówi: że akapit o myśleniu jest zbędny. N=2 korpusy,
jeden dzień, trzy sesje, wszystkie na jednej maszynie. Mówi tylko, gdzie
zmierzone wąskie gardło leżało tym razem.

## Materiał do przeliczenia

- korpus 1: `agentmachi read --from-seq 1 --json` na pokoju `E1`,
- korpus 2: wyjście nasłuchu zapisane przez harness,
  `sha256 41bb027fbb9f35b368ea66dc0a07e5dc70839f16a56e16ee8a1cac2ad9de93bd`,
  ramki 623, 625, 627.
