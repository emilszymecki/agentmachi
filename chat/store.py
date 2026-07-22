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
    def __init__(self, dirpath):
        self.dir = Path(dirpath)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.dir / "events.jsonl"
        self.snapshot_path = self.dir / "snapshot.json"
        self.snapshot_seq = 0
        self._events = []  # [{seq, ...frame}] tylko > snapshot_seq
        if self.snapshot_path.exists():
            data = json.loads(self.snapshot_path.read_text())
            self.snapshot_seq = data["snapshot_seq"]
        self.last_seq = self.snapshot_seq
        if self.events_path.exists():
            with self.events_path.open() as f:
                lines = f.readlines()
            keep = len(lines)  # ile linii zostawic na dysku (przycinanie ogona)
            for i, line in enumerate(lines):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    e = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    if i == len(lines) - 1:
                        # urwana OSTATNIA linia (crash w trakcie zapisu) — tolerujemy,
                        # plik zostanie przycięty do ostatniej poprawnej linii
                        keep = i
                        break
                    raise ValueError(
                        f"events.jsonl uszkodzony w linii {i + 1} (nie ostatniej) — "
                        "to korupcja, nie urwany ogon po crashu"
                    ) from exc
                if e["seq"] > self.snapshot_seq:
                    self._events.append(e)
                    self.last_seq = e["seq"]
            if keep < len(lines):
                with self.events_path.open("w") as f:
                    f.writelines(lines[:keep])
                    f.flush()
                    os.fsync(f.fileno())

    def append(self, frame):
        seq = self.last_seq + 1
        event = {**frame, "seq": seq}
        with self.events_path.open("a") as f:
            f.write(json.dumps(event) + "\n")
            f.flush()
            os.fsync(f.fileno())
        # last_seq/_events aktualizowane DOPIERO po udanym zapisie — nieudany
        # zapis (wyjatek powyzej) nie podbija numeracji i nie zostawia dziury
        self.last_seq = seq
        self._events.append(event)
        return self.last_seq

    def events_after(self, seq):
        if seq < self.snapshot_seq:
            return None  # resync_required
        return [e for e in self._events if e["seq"] > seq]

    def save_snapshot(self, state):
        seq = self.last_seq
        tmp = self.dir / "snapshot.json.tmp"
        with tmp.open("w") as f:
            f.write(json.dumps({"snapshot_seq": seq, "state": state}))
            f.flush()
            os.fsync(f.fileno())
        tmp.rename(self.snapshot_path)  # atomowo; dopiero teraz kompakcja
        self.snapshot_seq = seq
        self._events = [e for e in self._events if e["seq"] > seq]
        events_tmp = self.dir / "events.jsonl.tmp"
        with events_tmp.open("w") as f:
            for e in self._events:
                f.write(json.dumps(e) + "\n")
            f.flush()
            os.fsync(f.fileno())
        events_tmp.rename(self.events_path)  # atomowo; crash w polowie nie obcina eventow

    def load_snapshot(self):
        if not self.snapshot_path.exists():
            return None
        data = json.loads(self.snapshot_path.read_text())
        return data["state"], data["snapshot_seq"]

    def replay(self):
        return list(self._events)
