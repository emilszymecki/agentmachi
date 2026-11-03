# Runda 7 — prerejestracja: konkurs heurystyczny CVRP

Złożona przed zadaniem. Budujący jej nie znają.

Zadanie: `vrp` wg SPEC.md (sha256 3c7b4c30…7c21), oceniacz ocen.py
(sha256 dbfa30ec…90dd, publiczny, sprawdzony na 5 atrapach: najbliższy
sąsiad = 100,00; „jeden klient na trasę" = poprawny, nisko; pominięty
klient, przekroczona pojemność, przekroczony czas = 0). Instancje ukryte:
ukryte.tar (sha256 1f8bf136…50af), 8 sztuk, n = 60…400, uniform/skupiska,
magazyn w środku/w rogu.

- ZESPÓŁ: claude2 + codex1, wyłącznie przez pokój `badanie`, repo
  agentmachi_poligon/vrp.
- SOLO: świeży subagent Claude, agentmachi_poligon/vrp-solo, ta sama SPEC,
  bez kanału, start w tej samej minucie.
- Twardy koniec: 90 min od ramki z zadaniem; ocena na drzewie roboczym.

## Pomiar

Ocena po końcu obu stron, sekwencyjnie na tej samej maszynie, **3 przebiegi**
na stronę (przeplatane: Z, S, Z, S, Z, S); wynik strony = średnia z trzech
średnich po 8 instancjach ukrytych. Wyniki dosłownie do plików.

## Werdykt — jakość decyduje o kierunku

| różnica Δ = zespół − solo | jakość |
|---|---|
| Δ ≥ +2,0 pkt | MA SENS |
| \|Δ\| < 2,0 pkt | MIESZANY |
| Δ ≤ −2,0 pkt | GÓWNO |

Pozostałe rubryki jak w rundzie 6 (muszą trzymać, żeby „ma sens" stało):
bug krzyżowy ≥ 1 (wada, która dałaby 0 na instancji, albo repro z wynikiem
komendy); narzut mechaniki < 20% ramek zespołu; 0 interwencji sędziego
w mechanikę. Czas nie jest rubryką (heurystyka zużywa limit z założenia).

Werdykt łączny: jakość MA SENS i reszta trzyma → „ma sens"; jakość GÓWNO →
„gówno" niezależnie od reszty; inaczej „mieszany", opisany rubryka po rubryce.

## Reguły liczenia

- Mechanika / koordynacja / pytania o SPEC / interwencje: jak w rundzie 6.
- Pytania o SPEC: każde = wada SPEC; odpowiedź na kanale i w raporcie.
- Konfund: claude2 i codex1 po rundzie 6 znają się i mają rozgrzany
  kontekst; solo świeży. Zespół zna wynik rundy 6 (remis) — może grać
  ambitniej. Nazwane, nie usuwane.
