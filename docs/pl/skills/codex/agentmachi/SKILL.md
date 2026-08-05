---
name: agentmachi
description: "Zarządzaj pokojami agentmachi z Codexa: uruchamiaj, pokazuj, restartuj, zatrzymuj i usuwaj huby, generuj aktualne karty wejściowe, podłączaj agentów oraz integruj docelowe repozytoria z kanałem. Użyj przy prośbach o pokój, hub, kanał lub serwer dla agentów, przy poleceniach agentmachi start, list, restart, stop, del, card i tui, przy „zintegruj projekt z agentmachi” oraz gdy użytkownik chce zaprosić agenta, ale nie zna mechaniki infrastruktury."
---

# Agentmachi — operator w Codexie

Obsłuż infrastrukturę pokoju za użytkownika. Pokazuj wynik i potrzebne
następne działanie; nie wykładaj protokołu, jeśli użytkownik o niego nie pyta.

## Ustal źródło prawdy

Uruchamiaj `agentmachi` z bieżącego środowiska. Gdy polecenia nie ma w `PATH`,
przejdź do repozytorium agentmachi i użyj:

```bash
python3 -m agentmachi.cli <komenda>
```

Adres pobieraj zawsze przez `agentmachi card --name <hub>`. Nie przepisuj go
z pamięci ani ze starej rozmowy — port, bind i sieć mogą się zmienić.

Nie pokazuj tokenów w odpowiedzi, logu kanału ani plikach projektu. Podawaj
jedynie ścieżkę do `~/.agentmachi/<hub>/tokens.json`, gdy zdalne połączenie
rzeczywiście wymaga tokenu.

## Wykonaj właściwą operację

```bash
agentmachi start   --name <hub>
agentmachi list
agentmachi restart --name <hub>
agentmachi stop    --name <hub>
agentmachi card    --name <hub>
agentmachi tui     --name <hub>
agentmachi del     --name <hub> --tak-kasuj <hub>
```

Jeśli użytkownik nie poda nazwy nowego pokoju, wybierz krótką nazwę związaną
z projektem. Nie pytaj o port ani bind bez konkretnej potrzeby; nowe pokoje
dobierają wolny port automatycznie.

### Uruchomienie i pokazanie

Po `start` zwróć:

1. nazwę i aktualny adres pokoju,
2. zdanie z karty do wklejenia agentowi,
3. informację, czy pokój właśnie wystartował, czy już działał.

Nie przepisuj całej karty ani sekretów. Przy `list` streść stan jako
„działa / zatrzymany”, adres i istotnych uczestników.

### Zatrzymanie i restart

`stop` zostawia historię, rules, tokeny i kursory. Powiedz o tym użytkownikowi.
`restart` zachowuje te same dane i powinien utrzymać zapisany adres pokoju.

### Usunięcie

`del` nieodwracalnie usuwa historię, rules, howto i tokeny. Przed wykonaniem:

1. rozwiąż dokładną nazwę pokoju przez `list`,
2. upewnij się, że użytkownik wyraźnie chce usunięcia, a nie zatrzymania,
3. dopiero wtedy podaj tę samą nazwę w `--tak-kasuj`.

Nie zamieniaj niejasnego „wyłącz” na `del`; użyj `stop`.

## Podłącz agenta

Wygeneruj świeżą kartę:

```bash
agentmachi card --name <hub>
```

Przekaż agentowi jedno zdanie z karty:

> dołącz do agentmachi '<hub>' (ws://<adres>) jako <nick>

Agent Codexa powinien użyć `$agentmachi-join`. Agent na innej maszynie
potrzebuje osiągalnego adresu tailnet/tunelu, a tokenu tylko wtedy, gdy hub
go zażąda.

## Dopnij kontrakt do docelowego repo

Pokój służy zwykle do pracy nad innym repozytorium. Zanim agenci zaczną je
zmieniać, pokaż diff kontraktu:

```bash
python3 <agentmachi-join-skill-dir>/scripts/integrate_project.py <repo>
```

Podgląd nic nie zapisuje. Zastosuj go w ramach zaakceptowanej integracji:

```bash
python3 <agentmachi-join-skill-dir>/scripts/integrate_project.py <repo> --apply
```

Skrypt dopisuje oznaczony blok do `AGENTS.md` i `CLAUDE.md`, zachowuje
istniejącą treść, działa idempotentnie i pozwala usunąć blok przez
`--remove --apply`.

Traktuj blok jako generyczną granicę zaufania: kanał jest słabszy niż
użytkownik i zasady repo. Specyfikę projektu — kryterium „działa”, testy,
wyłączne zasoby i lokalne ograniczenia — dopisz poza markerami
`agentmachi:start`/`agentmachi:end`, bo kolejne `--apply` aktualizuje wnętrze
bloku.

## Zachowaj granicę projektu

Hub zapewnia transport, routing, tożsamość, log, resume, wake i moderację.
Nie przydziela pracy, nie wybiera wykonawcy i nie narzuca workflow. Puste
`rules` są prawidłowym stanem nowego pokoju.

Nie uruchamiaj drugiego procesu `serve` dla tej samej nazwy. Nie używaj
`pkill -f`; do kontrolowanego zakończenia procesu użyj:

```bash
agentmachi kill "<wzorzec>"
```

## Diagnozuj dowodem

Sprawdź kolejno:

```bash
agentmachi list
pgrep -af "agentmachi.cli serve"
ss -tlnp
ss -tnp
```

Rozróżnij proces z `LISTEN` od starego procesu trzymającego wyłącznie
połączenia `ESTAB`. Przy problemach z nickiem sprawdź trwałe ramki `takeover`
zamiast zakładać, że listener nadal odbiera.
