#!/usr/bin/env bash
set -u

if [[ -z "${CHAT_NICK:-}" ]]; then
  echo "codex-wait: ustaw CHAT_NICK; bez niego listen rozszczepia tozsamosc" >&2
  exit 2
fi

if ! command -v agentmachi >/dev/null 2>&1; then
  echo "codex-wait: brak binarki agentmachi w PATH" >&2
  exit 127
fi

# `listen --once` konczy sie wewnatrz klienta dopiero po apply_frame,
# Session.advance i trwalym zapisie kursora. Powloka niczego nie polluje
# ani nie zabija po arbitralnym czasie; koniec procesu budzi ten sam Codex.
exec agentmachi listen --once "$@"
