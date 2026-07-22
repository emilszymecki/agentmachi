# chat/store.py
"""Trwaly log zdarzen pokoju: room_seq, snapshot, kompakcja.

Kolejnosc trwalosci (spec): przy mutacji najpierw trwaly event, potem
publikacja; przy kompakcji najpierw snapshot (tmp+rename), potem usuniecie
przykrytych eventow. events_after zwraca None gdy kursor wypada przed
snapshot_seq — jawny resync_required, nigdy cichy partial replay.

Polityka snapshotow (kiedy i jak czesto kompaktowac) nalezy do serwera;
EventLog dostarcza tylko mechanizm (save_snapshot/load_snapshot).
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
            raw = self.events_path.read_bytes()
            n = len(raw)
            pos = 0
            good_end_offset = 0  # offset za ostatnia poprawna linia (do przyciecia)
            while pos < n:
                nl_idx = raw.find(b"\n", pos)
                if nl_idx == -1:
                    line_bytes = raw[pos:]
                    has_newline = False
                    line_end = n
                else:
                    line_bytes = raw[pos:nl_idx]
                    has_newline = True
                    line_end = nl_idx + 1
                is_last_chunk = line_end == n
                stripped = line_bytes.strip()
                if stripped:
                    try:
                        e = json.loads(stripped)
                    except json.JSONDecodeError as exc:
                        if is_last_chunk and not has_newline:
                            # json.dumps nigdy nie wstawia \n w srodku zapisu,
                            # a koncowy \n dopisujemy osobno PO tresci — wiec
                            # brak \n na koncu ostatniej linii jednoznacznie
                            # oznacza urwany zapis w trakcie crashu (torn
                            # tail), nie korupcje. Tolerujemy: przycinamy
                            # plik do offsetu ostatniej poprawnej linii
                            # (ponizej pentli) i jedziemy dalej.
                            break
                        raise ValueError(
                            f"events.jsonl uszkodzony w linii zaczynajacej sie "
                            f"na offsecie {pos} bajtow — linia zakonczona "
                            "znakiem nowej linii (albo nie jest ostatnia w "
                            "pliku), to korupcja, nie urwany ogon po crashu"
                        ) from exc
                    else:
                        if e["seq"] > self.snapshot_seq:
                            self._events.append(e)
                            self.last_seq = e["seq"]
                pos = line_end
                good_end_offset = pos
            if good_end_offset < n:
                # truncate zamiast open("w")+rewrite: crash w trakcie naprawy
                # nie moze skasowac juz-przyjetego zdrowego prefiksu, bo
                # truncate tylko obcina ogon pliku, nigdy go nie przepisuje
                with self.events_path.open("r+b") as f:
                    f.truncate(good_end_offset)
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
