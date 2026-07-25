#!/usr/bin/env python3
"""Fake `codex exec --json`: drukuje thread.started z thread_id (nowym albo
tym z podkomendy `resume <id>`), potem turn.completed. Sluzy testom adaptera
Codeksa bez instalacji i bez palenia tokenow OpenAI.

Format skopiowany z realnego przebiegu `codex exec --json` (2026-07-26):
  {"type":"thread.started","thread_id":"019f9b6b-..."}
  {"type":"turn.started"}
  {"type":"item.completed","item":{...}}
  {"type":"turn.completed","usage":{...}}
"""
import json, sys, time

if "--hang" in sys.argv:
    # Ten sam stub regresyjny co w fake_runtime.py: dziecko, ktore NIE czyta
    # stdin i NIC nie pisze — dowod, ze max_duration jest sufitem CALEJ rundy
    # takze dla drugiego adaptera, nie tylko dla Claude.
    time.sleep(120)
    sys.exit(0)

sid = "fresh-thread"
if "resume" in sys.argv:
    i = sys.argv.index("resume")
    if i + 1 < len(sys.argv):
        sid = sys.argv[i + 1]

print(json.dumps({"type": "thread.started", "thread_id": sid}), flush=True)
print(json.dumps({"type": "turn.started"}), flush=True)
sys.stdin.read()          # prompt idzie przez "-"; czytamy, zeby nie zerwac pipe'u
print(json.dumps({"type": "turn.completed", "usage": {"output_tokens": 1}}),
      flush=True)
