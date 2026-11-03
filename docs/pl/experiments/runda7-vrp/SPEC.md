# vrp — konkurs heurystyczny (specyfikacja zamrożona)

**Problem: CVRP.** Magazyn i klienci na płaszczyźnie; każdy klient ma
zapotrzebowanie. Ciężarówki (dowolnie wiele) o pojemności `capacity` ruszają
z magazynu i do niego wracają. Każdego klienta obsługuje dokładnie jedna
trasa, suma zapotrzebowań na trasie ≤ `capacity`. **Minimalizuj łączną
długość tras** (odległość euklidesowa, liczby rzeczywiste, bez zaokrągleń).

## Wywołanie

    python -m vrp <instancja.json>

z katalogu tego projektu (pakiet `vrp/`). Python ≥ 3.10, **tylko biblioteka
standardowa**, jeden proces (bez wielu rdzeni). Na stdout jeden obiekt JSON:

    {"routes": [[3, 17, 5], [8, 1], ...]}

— lista tras, każda to lista `id` klientów w kolejności odwiedzin; magazyn
jest domyślnie na początku i końcu każdej trasy (nie wpisuj go).

**Czas: program musi sam zakończyć się w 10 s** (oceniacz zabija po 12 s).
Pomiar na tej samej maszynie, uruchomienia jedno po drugim.

## Instancja

    {"name": str, "capacity": int, "depot": [x, y],
     "customers": [{"id": int, "x": int, "y": int, "demand": int}, ...]}

`id` = 1..n. Współrzędne 0..1000, zapotrzebowanie 1..10.

## Punktacja

Na instancję: `100 × koszt_bazowy / twój_koszt`, gdzie koszt bazowy to
zachłanny najbliższy sąsiad z ograniczeniem pojemności (patrz `ocen.py`).
Rozwiązanie nieprawidłowe, błąd, nie-JSON albo przekroczony czas = **0**.
Wynik = średnia po instancjach ukrytych.

Instancje ukryte: inne niż publiczne, **do 400 klientów**, różne rozkłady
(także skupiska) i położenia magazynu. Publiczne przykłady: `publiczne/`.
Oceniacz (ten sam co w ocenie końcowej): `python ocen.py . publiczne/*.json`.
