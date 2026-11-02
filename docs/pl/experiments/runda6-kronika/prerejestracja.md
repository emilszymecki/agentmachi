# Runda 6 — prerejestracja: „to jest gówno" vs „to ma sens"

Złożona przed wysłaniem zadania. Budujący jej nie znają (znane kryterium
zmienia zachowanie, które mierzy).

Zadanie: `kronika` wg SPEC.md (sha256 770fad4b…98b9).
- ZESPÓŁ: claude2 + codex1, wyłącznie przez pokój `badanie`, repo
  agentmachi_poligon/kronika.
- SOLO: jeden świeży subagent Claude, agentmachi_poligon/kronika-solo,
  ten sam SPEC, bez kanału, start w tej samej minucie.
- Sędzia: opus. Nie buduje. Testy ukryte: test_akceptacja.py (11 testów,
  sha256 w ramce pieczęci), wykonane na pustym projekcie: 11/11 czerwone
  z powodu braku modułu; fixture sprawdzony surowym `git log --numstat`.

Twardy koniec: 90 min od ramki z zadaniem, dla obu stron. Potem testy lecą
na tym, co jest w drzewie roboczym.

## Werdykt

| | MA SENS | GÓWNO |
|---|---|---|
| testy ukryte | zespół ≥ solo | zespół < solo |
| bug krzyżowy | ≥ 1 | 0 |
| narzut mechaniki | < 20% ramek | > 40% ramek |
| kanał | 0 interwencji człowieka/sędziego w mechanikę | ≥ 1 |
| czas | ≤ 1,5× solo | > 2× solo bez zysku jakości |

Wszystkie po stronie MA SENS → „ma sens". Którekolwiek po stronie GÓWNO →
„gówno" w tej rubryce, werdykt łączny „mieszany" albo „gówno" wg przewagi —
opisany rubryka po rubryce, nie naciągany. Remis na testach = „mieszany".

## Reguły liczenia (spisane teraz, nie po fakcie)

- **Bug krzyżowy** = wada w części jednego, znaleziona przez drugiego,
  która zawaliłaby test ukryty ALBO ma repro z wynikiem komendy. Nie styl.
- **Mechanika** = reconnect, lock, nick, filtr, „żyjesz?", „dlaczego nie
  słyszę", zły adres, ponowne uzbrajanie nasłuchu. **Koordynacja** (podział,
  deklaracja zakresu, kontrakt danych, review) to NIE mechanika.
- **Pytania o SPEC** od zespołu: dozwolone, każde = wada SPEC, nie zespołu;
  odpowiedź sędziego idzie na kanał i do raportu. Solo nie może pytać.
- **Interwencja** sędziego w mechanikę kanału = punkt do GÓWNO, zapisany.
- Czas zespołu: od seq ramki zadania do ostatniego `[koniec]` (ts z logu).
  Czas solo: duration_ms subagenta. Tokenów zespołu nie widać — poza
  werdyktem.

## Konfund (nazwany, nie usuwany)

claude2 ma za sobą wiele godzin kontekstu tego dnia (i kompakcję), codex1
krótszy; solo startuje świeży. Projekt jest spoza agentmachi, więc wiedza
o kanale nie pomaga w kodzie — ale znajomość playbooka pomaga zespołowi.
