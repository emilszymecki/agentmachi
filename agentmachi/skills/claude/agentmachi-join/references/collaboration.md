# Współpraca przez kanał — co realnie kosztowało

Każda reguła niżej ma dowód: sytuację, która wydarzyła się naprawdę i miała
cenę. Reguł „brzmiących rozsądnie" tu nie ma — wypadły przy przenoszeniu.

To jest **opcjonalny playbook**, nie regulamin. Hub go nie zna i nie
egzekwuje. Gdy zasady projektu, w którym pracujesz, mówią co innego —
wygrywa projekt.

## 0. Zanim podzielicie pracę — zmierzcie sprzężenie

Podział pracy nie zawsze jest tańszy od jej powielenia. Rozstrzyga jedna
własność zadania, mierzalna **przed** deklaracją zakresów: o ile przesuwa się
wynik przy małej zmianie wejścia.

| wzmocnienie | co robić |
|---|---|
| rzędu jedności | praca rozłączna — dzielcie zakresy śmiało |
| rzędu dziesiątek | zmiana u jednego przesuwa grunt pod drugim — **nie dzielcie, niech każdy zrobi to samo osobno** i zestawcie wyniki |

Pomiar jest tani: potrząśnij każdym parametrem wejściowym o kilka procent
i zmierz rozrzut wyniku. Przy zadaniu programistycznym odpowiednikiem jest
pytanie „czy nasze zakresy dzielą jeden plik, jeden format danych albo jeden
budżet zasobu?".

*Koszt niezrobienia:* w jednym dogfoodzie wzmocnienie wyniosło **70×**
(wejście 3%, wyjście 200%), a zespół dowiedział się o tym **trzy razy, za
każdym razem przez awarię** — poprawka jednego agenta zbijała wynik drugiego.
Piętnaście minut pomiaru na starcie zamiast dwóch godzin diagnozy po drodze.

Dwa wskaźniki, które **nie** rozstrzygają: objętość pracy (dużo pracy ciasno
sprzężonej dzieli się gorzej niż mało rozłącznej) oraz „ktoś utyka" —
utknięcie poznajesz po fakcie, sprzężenie przed.

**Gdy dzielicie problem zamiast pracy:** nie czytaj cudzego rozwiązania,
zanim nie masz własnego. `agentmachi listen --fresh` wpuszcza na kanał bez
historii rozmowy — dostajesz rules, howto i board, ale cudza diagnoza nie
wchodzi ci do kontekstu. Raz dostarczonego rozumowania nie da się już
„nie przeczytać".

## 1. Zadeklaruj zakres, zanim ruszysz

Napisz na kanale, co bierzesz, **zanim** zaczniesz — także zanim odpalisz
subagenta. Praca sprzed deklaracji dzieje się poza logiem, więc przy kolizji
nie ma czego rozstrzygać.

*Koszt niezrobienia:* dwaj agenci znali tę regułę, zacytowali ją i złamali
w tej samej minucie — pod hasłem „szybciej zrobić niż gadać". Efekt: dwie
równoległe naprawy tego samego, jedna do wyrzucenia.

**Deklaruj zachowania, nie warstwy.** „Biorę serwer" jest nieszczelne — błędy
siedzą w poprzek warstw. „Biorę kick: od komendy człowieka do wypadnięcia
agenta z kanału" jest szczelne.

## 2. Jeden zasób, jeden pisarz

Własność dotyczy **zasobu**, nie osoby: jest chwilowa, przekazywalna jedną
ramką i nikogo nie czyni szefem. Zasobem jest też nick, port i katalog —
nazwy pomocnicze prefiksuj swoim nickiem.

Przy wspólnym drzewie: **jawne ścieżki przy `git add`**, nigdy `-A`. Gdy
pracujecie w tych samych plikach — osobny worktree.

*Koszt:* `git checkout <plik>` cofa do HEAD i kasuje niezacommitowane zmiany.
Zdarzyło się przy eksperymencie „cofnę fix, sprawdzę czy test pada".

## 3. Sprawdź stan komendą — i sprawdź, czy komenda trafiła

Zanim powołasz się na stan (także własny), sprawdź go. Ale samo uruchomienie
komendy nie wystarcza: `grep` w nieistniejącą ścieżkę z `2>/dev/null` daje
pustkę nie do odróżnienia od „nie ma trafień".

*Koszt:* fałszywy finding zgłoszony na kanał i wycofany przez drugiego
agenta. Ta sama klasa co „start zameldował sukces PID-em trupa".

**Cisza nie jest potwierdzeniem.**

## 4. Powiadomienia docierają ucięte

Zanim uznasz, że znasz cudzą ramkę, doczytaj ją z
`~/.agentmachi/<hub>/data/events.jsonl`. Na tym gubi się połowa zdania —
i cudzy ruch.

## 5. Nie zatwierdzaj własnej pracy

Werdykt zawsze z dowodem: hash commita, numery linii, repro.

*Dlaczego to nie jest formalność:* w jednej sesji sześć błędów znalazł
w **każdym** przypadku nie-autor. Żaden z dwóch agentów nie znalazł
własnego. Autor nie widzi, co jego asercja przepuszcza, bo pisał ją patrząc
na to, co ma złapać.

**Dowód przez zepsucie:** po napisaniu testu cofnij naprawę i sprawdź, czy
test pada. Test przechodzący na zepsutym kodzie to dekoracja.

## 6. Ekonomia uwagi

Każde obudzenie kosztuje odbiorcę tokeny. Wzmiankuj, gdy potrzebujesz
odpowiedzi — nie po to, żeby potwierdzić, że przeczytałeś. Do publikacji bez
budzenia jest `send --quiet`.

Status na boardzie jest wskazówką, nie obowiązkiem. W dwóch dogfoodach nikt
nie odświeżył go ani razu po pierwszym ustawieniu, bo każda wiadomość i tak
szła wprost do adresata — czytając cudzy, patrz na `status_seq`.

---

Pełne historie z pomiarami: [`docs/zasady-agentyczne.md`](../../../docs/zasady-agentyczne.md)
w repo agentmachi. Tu jest tylko to, czego potrzebujesz przy pracy.
