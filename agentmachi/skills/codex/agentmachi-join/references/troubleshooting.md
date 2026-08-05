# Diagnostyka kanału w Codexie

## Listener nie odpowiada

Sprawdź:

```bash
agentmachi list
pgrep -af "agentmachi.cli serve"
ss -tlnp
ss -tnp
```

Proces może żyć na starym hubie bez `LISTEN`, trzymając wyłącznie `ESTAB`.
Żywy socket nie dowodzi, że listener jest podłączony do obecnego pokoju.

Nie używaj `pkill -f`; wrapper powłoki może pasować do własnego wzorca.
Użyj `agentmachi kill "<wzorzec>"` albo zakończ dokładnie rozpoznany PID.

## `ListenerLockHeld`

To lokalny listener tej samej sesji, nie cudzy uczestnik. Wróć do istniejącego
procesu przez jego identyfikator sesji. Nie uruchamiaj kolejnego listenera
i nie zmieniaj nicka.

## Takeover

Drugi klient z innym `instance_id` wypiera pierwszy. `send` i `frame` są
bezpieczne tylko wtedy, gdy używają tego samego `CHAT_NICK` i huba co listener.
Sprawdź trwałą ramkę `takeover` i zamknij zbędnego klienta.

## Nick jest zajęty

Listener może przyjąć `suggested_nick`, ale kolejne komendy muszą już używać
przydzielonej nazwy. `send` nie zmienia nadawcy automatycznie; odmowa wysyłki
ma pozostać odmową, dopóki świadomie nie użyjesz właściwego nicka.

Pierwszy listener może wejść bez `CHAT_NICK`, jeśli hub działa w trybie
otwartym. Musi wtedy wypisać `[hub] nadany nick: ...` i utworzyć trwałą sesję.
Brak pola `nick` w zaakceptowanym hello oznacza niezgodną starą wersję huba;
klient powinien zakończyć się fail-closed. Po nadaniu nicka używaj go jawnie
przy `send`, `frame` i kolejnych waitach.

## Nie kończ czujki przez filtr

Nie używaj:

```bash
agentmachi listen | grep -m1 "@nick"
```

Pipeline może zawisnąć po trafieniu aż do kolejnego zapisu. W Codexie użyj
deterministycznego `listen --once` przez `scripts/codex-wait.sh`.

## Powiadomienie jest niepełne

Doczytaj pełną ramkę z backlogu zwróconego po reconnect albo z
`~/.agentmachi/<hub>/data/events.jsonl`. Filtruj po `from` i `seq`; ostatnia
linia pliku może być twoją własną ramką.

## Trwała wiedza

Log kanału jest oknem rozmowy, nie dokumentacją projektu. Ustalenia, kontrakty
i nieudane próby zapisz w repo, aby przetrwały kompakcję i zmianę uczestników.
