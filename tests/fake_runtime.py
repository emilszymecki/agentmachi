#!/usr/bin/env python3
"""Fake `claude -p --output-format stream-json`: drukuje init z session_id
(nowym albo z --resume), potem result. Sluzy testom node'a bez instalacji CC."""
import json, sys, time

if "--hang" in sys.argv:
    # Stub regresyjny (review taska 3): dziecko, ktore NIE czyta stdin i NIC
    # nie pisze — symuluje zawieszony proces, zeby test mogl zweryfikowac,
    # ze max_duration jest twardym sufitem CALEJ rundy (stdin write+drain,
    # pump stdout, wait), nie tylko samego pump() stdout. Skonczone (nie
    # nieskonczone) spanie, zeby ewentualny nieubity proces sam sie kiedys
    # skonczyl zamiast wisiec w nieskonczonosc.
    time.sleep(120)
    sys.exit(0)

sid = "fresh-session"
if "--resume" in sys.argv:
    sid = sys.argv[sys.argv.index("--resume") + 1]
print(json.dumps({"type": "system", "subtype": "init", "session_id": sid}),
      flush=True)
print(json.dumps({"type": "result", "subtype": "success", "session_id": sid}),
      flush=True)
