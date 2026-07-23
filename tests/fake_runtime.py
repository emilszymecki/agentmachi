#!/usr/bin/env python3
"""Fake `claude -p --output-format stream-json`: drukuje init z session_id
(nowym albo z --resume), potem result. Sluzy testom node'a bez instalacji CC."""
import json, sys

sid = "fresh-session"
if "--resume" in sys.argv:
    sid = sys.argv[sys.argv.index("--resume") + 1]
print(json.dumps({"type": "system", "subtype": "init", "session_id": sid}),
      flush=True)
print(json.dumps({"type": "result", "subtype": "success", "session_id": sid}),
      flush=True)
