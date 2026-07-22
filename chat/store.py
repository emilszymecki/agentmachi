# chat/store.py
"""Trwaly log zdarzen pokoju: room_seq, snapshot, retencja.

Kolejnosc trwalosci (spec): przy mutacji najpierw trwaly event, potem
publikacja; przy kompakcji najpierw snapshot (tmp+rename), potem usuniecie
przykrytych eventow. events_after zwraca None gdy kursor wypada przed
snapshot_seq — jawny resync_required, nigdy cichy partial replay.
"""
import json
import os
from pathlib import Path


class EventLog:
    def __init__(self, dirpath, retention=500):
        self.dir = Path(dirpath)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.dir / "events.jsonl"
        self.snapshot_path = self.dir / "snapshot.json"
        self.retention = retention
        self.snapshot_seq = 0
        self._events = []  # [{seq, ...frame}] tylko > snapshot_seq
        if self.snapshot_path.exists():
            data = json.loads(self.snapshot_path.read_text())
            self.snapshot_seq = data["snapshot_seq"]
        self.last_seq = self.snapshot_seq
        if self.events_path.exists():
            with self.events_path.open() as f:
                for line in f:
                    e = json.loads(line)
                    if e["seq"] > self.snapshot_seq:
                        self._events.append(e)
                        self.last_seq = e["seq"]

    def append(self, frame):
        self.last_seq += 1
        event = {"seq": self.last_seq, **frame}
        with self.events_path.open("a") as f:
            f.write(json.dumps(event) + "\n")
            f.flush()
            os.fsync(f.fileno())
        self._events.append(event)
        return self.last_seq

    def events_after(self, seq):
        if seq < self.snapshot_seq:
            return None  # resync_required
        return [e for e in self._events if e["seq"] > seq]

    def save_snapshot(self, state):
        seq = self.last_seq
        tmp = self.dir / "snapshot.json.tmp"
        tmp.write_text(json.dumps({"snapshot_seq": seq, "state": state}))
        tmp.rename(self.snapshot_path)  # atomowo; dopiero teraz kompakcja
        self.snapshot_seq = seq
        self._events = [e for e in self._events if e["seq"] > seq]
        with self.events_path.open("w") as f:
            for e in self._events:
                f.write(json.dumps(e) + "\n")

    def load_snapshot(self):
        if not self.snapshot_path.exists():
            return None
        data = json.loads(self.snapshot_path.read_text())
        return data["state"], data["snapshot_seq"]

    def replay(self):
        return list(self._events)
