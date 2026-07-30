# Współpraca przez agentmachi

Traktuj ten plik jako playbook. Zasady użytkownika i docelowego repo mają
pierwszeństwo.

## Zmierz sprzężenie przed podziałem

Jeśli zakresy dzielą jeden plik, format danych, wspólny budżet albo częste
zmiany wejścia, praca jest ciasno sprzężona. Zamiast dzielić implementację,
wykonajcie niezależne warianty i zestawcie wyniki.

Jeśli zakresy są rozłączne, podzielcie je. Przy niezależnym wariancie użyj
`listen --fresh`, aby cudze rozumowanie nie kotwiczyło wyniku.

## Zadeklaruj odpowiedzialność

Przed pracą napisz na kanale, jaki efekt bierzesz i czego nie dotykasz.
Deklaruj zachowanie od wejścia do wyniku, nie ogólną warstwę typu „serwer”.

Kolizję wyłącznego zasobu rozstrzyga wcześniejsza deklaracja w logu (`seq`).
Jeden zasób ma jednego piszącego; ten sam problem może mieć kilku świadomie
niezależnych autorów.

## Chroń wspólne drzewo

- Dodawaj do indeksu wyłącznie jawne ścieżki; nie używaj `git add -A`.
- Nie cofaj pliku do `HEAD`, jeśli może zawierać cudze lub niezapisane zmiany.
- Użyj osobnego worktree, gdy niezależne warianty dotykają tych samych plików.
- Sprawdź `git status` przed i po zmianie.

## Raportuj dowodem

Podaj commit, ścieżkę i linię, wynik testu albo dokładne repro. Nie uznawaj
ciszy komendy za potwierdzenie — najpierw sprawdź kod wyjścia i cel polecenia.

Nie zatwierdzaj własnej pracy jako jedyny recenzent. Test naprawy sprawdź
również przez kontrolowane przywrócenie błędu, jeśli da się to zrobić bez
naruszania cudzych zmian.

## Oszczędzaj uwagę

Wzmiankuj tylko wtedy, gdy potrzebujesz reakcji. Do publikacji bez budzenia
użyj `send --quiet`. Łącz finding, dowód i prośbę w jedną wiadomość.

Status na boardzie jest deklaracją, nie diagnozą. Porównuj `status_seq`
z bieżącym `last_seq`, zanim uznasz go za aktualny.
