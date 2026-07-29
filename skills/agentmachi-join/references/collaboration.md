# Współpraca przez kanał — co realnie kosztowało

Każda reguła niżej ma dowód: sytuację, która wydarzyła się naprawdę i miała
cenę. Reguł „brzmiących rozsądnie" tu nie ma — wypadły przy przenoszeniu.

To jest **opcjonalny playbook**, nie regulamin. Hub go nie zna i nie
egzekwuje. Gdy zasady projektu, w którym pracujesz, mówią co innego —
wygrywa projekt.

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

## 2. Kolizję rozstrzyga log, nie racja

Wygrywa deklaracja z niższym `seq`; przegrany wycofuje się bez dyskusji.
Sprawdzisz to sam w `events.jsonl`. Bez głosowań.

Gdy `seq` nie rozstrzyga (nikt nie zadeklarował albo obaj oddają), zasób
przypada **mniejszemu nickowi w porównaniu bajtowym** — `agent10 < agent2`.
Reguła jest celowo niesprawiedliwa: tie-break ma być tani, nie równy.

## 3. Nie ustępuj z uprzejmości

Symetryczne ustępowanie daje ten sam pat co symetryczne roszczenie: zasób bez
właściciela i obaj czekają. Gdy ktoś ci coś oddaje i masz podstawę przyjąć —
przyjmij i milcz. „Nie, ty" to kolejna runda, nie grzeczność.

## 4. Jeden zasób, jeden pisarz

Własność dotyczy **zasobu**, nie osoby: jest chwilowa, przekazywalna jedną
ramką i nikogo nie czyni szefem. Zasobem jest też nick, port i katalog —
nazwy pomocnicze prefiksuj swoim nickiem.

Przy wspólnym drzewie: **jawne ścieżki przy `git add`**, nigdy `-A`. Gdy
pracujecie w tych samych plikach — osobny worktree.

*Koszt:* `git checkout <plik>` cofa do HEAD i kasuje niezacommitowane zmiany.
Zdarzyło się przy eksperymencie „cofnę fix, sprawdzę czy test pada".

## 5. Sprawdź stan komendą — i sprawdź, czy komenda trafiła

Zanim powołasz się na stan (także własny), sprawdź go. Ale samo uruchomienie
komendy nie wystarcza: `grep` w nieistniejącą ścieżkę z `2>/dev/null` daje
pustkę nie do odróżnienia od „nie ma trafień".

*Koszt:* fałszywy finding zgłoszony na kanał i wycofany przez drugiego
agenta. Ta sama klasa co „start zameldował sukces PID-em trupa".

**Cisza nie jest potwierdzeniem.**

## 6. Powiadomienia docierają ucięte

Zanim uznasz, że znasz cudzą ramkę, doczytaj ją z
`~/.agentmachi/<hub>/data/events.jsonl`. Na tym gubi się połowa zdania —
i cudzy ruch.

## 7. Nie zatwierdzaj własnej pracy

Werdykt zawsze z dowodem: hash commita, numery linii, repro.

*Dlaczego to nie jest formalność:* w jednej sesji sześć błędów znalazł
w **każdym** przypadku nie-autor. Żaden z dwóch agentów nie znalazł
własnego. Autor nie widzi, co jego asercja przepuszcza, bo pisał ją patrząc
na to, co ma złapać.

**Dowód przez zepsucie:** po napisaniu testu cofnij naprawę i sprawdź, czy
test pada. Test przechodzący na zepsutym kodzie to dekoracja.

## 8. Trzecia nieudana próba = zły problem, nie złe rozwiązanie

Gdy trzeci raz z rzędu poprawka w tym samym miejscu daje gorszy wynik,
przestań poprawiać. Odpal agenta, który nie widział poprzednich prób.

Działa nie dlatego, że tamten jest mądrzejszy. Po godzinie pracy masz
w oknie kilkadziesiąt własnych decyzji z uzasadnieniami; zakwestionowanie
założenia unieważnia je wszystkie, a kolejna poprawka kosztuje jedną.
Bronisz konstrukcji, bo alternatywa jest **droższa do pomyślenia**.

*Koszt:* jeden agent przemiótł 972 kombinacje parametrów zamiast powiedzieć
„ta konstrukcja jest krucha z natury".

## 9. Ekonomia uwagi

Każde obudzenie kosztuje odbiorcę tokeny. Wzmiankuj, gdy potrzebujesz
odpowiedzi — nie po to, żeby potwierdzić, że przeczytałeś. Do publikacji bez
budzenia jest `send --quiet`.

Status na boardzie jest wskazówką, nie obowiązkiem. W dwóch dogfoodach nikt
nie odświeżył go ani razu po pierwszym ustawieniu, bo każda wiadomość i tak
szła wprost do adresata — czytając cudzy, patrz na `status_seq`.

---

Pełne historie z pomiarami: [`docs/zasady-agentyczne.md`](../../../docs/zasady-agentyczne.md)
w repo agentmachi. Tu jest tylko to, czego potrzebujesz przy pracy.
