#!/usr/bin/env bash
set -u

if ! command -v agentmachi >/dev/null 2>&1; then
  echo "codex-wait: brak binarki agentmachi w PATH" >&2
  exit 127
fi

# `listen --once` konczy sie wewnatrz klienta dopiero po apply_frame,
# Session.advance i trwalym zapisie kursora. Powloka niczego nie polluje
# ani nie zabija po arbitralnym czasie. Koniec procesu NIE budzi modelu:
# ten skrypt musi byc prowadzony przez aktywny /goal biezacego watku.
# CHAT_NICK jest opcjonalny przy pierwszym wejsciu: aktualny klient przyjmie
# nick nadany przez otwarty hub, zalozy pod nim trwala Session i wypisze go.
exec agentmachi listen --once "$@"
