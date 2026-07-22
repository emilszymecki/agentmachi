# tests/test_store.py
import pytest

from chat.store import EventLog


def test_append_assigns_monotonic_seq(tmp_path):
    log = EventLog(tmp_path)
    assert log.append({"type": "chat", "text": "a"}) == 1
    assert log.append({"type": "chat", "text": "b"}) == 2
    assert log.last_seq == 2


def test_events_after(tmp_path):
    log = EventLog(tmp_path)
    for t in "abc":
        log.append({"type": "chat", "text": t})
    got = log.events_after(1)
    assert [e["text"] for e in got] == ["b", "c"]
    assert [e["seq"] for e in got] == [2, 3]
    assert log.events_after(3) == []


def test_append_ignores_seq_in_frame(tmp_path):
    log = EventLog(tmp_path)
    assert log.append({"type": "chat", "seq": 999}) == 1
    assert log.events_after(0)[0]["seq"] == 1
    log2 = EventLog(tmp_path)  # nowy obiekt, ten sam katalog
    assert log2.last_seq == 1


def test_survives_restart(tmp_path):
    log = EventLog(tmp_path)
    log.append({"type": "chat", "text": "a"})
    log2 = EventLog(tmp_path)  # nowy obiekt, ten sam katalog
    assert log2.last_seq == 1
    assert log2.events_after(0)[0]["text"] == "a"


def test_snapshot_then_old_cursor_requires_resync(tmp_path):
    log = EventLog(tmp_path)
    for i in range(5):
        log.append({"type": "chat", "text": str(i)})
    log.save_snapshot({"queue": "stan"})
    assert log.snapshot_seq == 5
    log.append({"type": "chat", "text": "po-snapshocie"})
    # kursor sprzed snapshotu -> jawny resync, nigdy partial replay
    assert log.events_after(3) is None
    # kursor na snapshocie -> zwykly replay nowszych
    assert [e["text"] for e in log.events_after(5)] == ["po-snapshocie"]
    state, seq = log.load_snapshot()
    assert state == {"queue": "stan"} and seq == 5


def test_append_failure_does_not_advance_seq(tmp_path, monkeypatch):
    log = EventLog(tmp_path)
    log.append({"type": "chat", "text": "a"})
    assert log.last_seq == 1

    with monkeypatch.context() as m:
        # katalog zamiast pliku -> open(..., "a") rzuci przy probie zapisu
        m.setattr(log, "events_path", log.dir)
        with pytest.raises(OSError):
            log.append({"type": "chat", "text": "b"})
    assert log.last_seq == 1  # nieudany zapis nie podbil seq — brak dziury

    # kolejny udany append dostaje wlasciwy numer, bez dziury po nieudanej probie
    assert log.append({"type": "chat", "text": "c"}) == 2
    assert log.last_seq == 2


def test_torn_trailing_line_is_tolerated(tmp_path):
    log = EventLog(tmp_path)
    log.append({"type": "chat", "text": "a"})
    log.append({"type": "chat", "text": "b"})
    assert log.last_seq == 2

    # symulacja crashu w trakcie zapisu trzeciej linii: urwany ogon bez newline
    with log.events_path.open("a") as f:
        f.write('{"seq": 3, "type"')

    log2 = EventLog(tmp_path)  # nie moze sie wywalic na starcie
    assert log2.last_seq == 2
    assert [e["text"] for e in log2.replay()] == ["a", "b"]

    # plik na dysku przycięty do ostatniej poprawnej linii
    assert len(log2.events_path.read_text().splitlines()) == 2

    assert log2.append({"type": "chat", "text": "c"}) == 3
    assert log2.last_seq == 3


def test_snapshot_persists_and_replay_after_restart(tmp_path):
    log = EventLog(tmp_path)
    for i in range(3):
        log.append({"type": "chat", "text": str(i)})
    log.save_snapshot({"s": 1})
    log.append({"type": "chat", "text": "x"})
    log2 = EventLog(tmp_path)
    assert log2.snapshot_seq == 3 and log2.last_seq == 4
    assert [e["text"] for e in log2.replay()] == ["x"]
