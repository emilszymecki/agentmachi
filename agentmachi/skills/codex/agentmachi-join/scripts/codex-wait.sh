#!/usr/bin/env bash
set -u

if ! command -v agentmachi >/dev/null 2>&1; then
  echo "codex-wait: no agentmachi binary on PATH" >&2
  exit 127
fi

# `listen --once` konczy sie wewnatrz klienta dopiero po apply_frame,
# Session.advance i trwalym zapisie kursora. Powloka niczego nie polluje
# ani nie zabija po arbitralnym czasie. Koniec procesu NIE budzi modelu:
# ten skrypt musi byc prowadzony przez aktywny /goal biezacego watku.
# CHAT_NICK jest opcjonalny przy pierwszym wejsciu: aktualny klient przyjmie
# nick nadany przez otwarty hub, zalozy pod nim trwala Session i wypisze go.
# Stal tu kiedys guard `exit 2` ("without it listen splits your identity").
# Zmierzone 2026-08-23 CALA DROGA, bo sam plik sesji niczego nie dowodzi:
# hub nadal `agent3` -> `send --as agent3` przy ZYWYM listenerze wszedl z tym
# samym instance_id, nie wyparl go i zostawil ramke w logu. Rozszczepienia nie
# ma; guard opisywal awarie naprawiona w B6/C4 i blokowal dzialajaca sciezke.
exec agentmachi listen --once "$@"
