#!/usr/bin/env python3
"""Odlicza 30 minut w dol, stan zapisuje do countdown.json co sekunde."""
import json
import sys
import time
from pathlib import Path

TOTAL = int(sys.argv[1]) if len(sys.argv) > 1 else 30 * 60
STATE = Path(__file__).with_name("countdown.json")


def write(remaining: int, done: bool) -> None:
    STATE.write_text(json.dumps({
        "done": done,
        "remaining": remaining,
        "mmss": f"{remaining // 60:02d}:{remaining % 60:02d}",
    }, indent=2) + "\n")


for remaining in range(TOTAL, 0, -1):
    write(remaining, False)
    print(f"\r{remaining // 60:02d}:{remaining % 60:02d}", end="", flush=True)
    time.sleep(1)

write(0, True)
print("\rDONE      ", flush=True)
