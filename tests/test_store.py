# tests/test_store.py
import json

import pytest

from chat.store import EventLog, ForeignWriterError


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
    size_before_tear = log.events_path.stat().st_size

    # symulacja crashu w trakcie zapisu trzeciej linii: urwany ogon BEZ
    # koncowego newline (json.dumps nie wstawia \n w srodku, wiec brak \n
    # na koncu ostatniej linii jednoznacznie oznacza torn tail)
    with log.events_path.open("ab") as f:
        f.write(b'{"seq": 3, "type"')

    log2 = EventLog(tmp_path)  # nie moze sie wywalic na starcie
    assert log2.last_seq == 2
    assert [e["text"] for e in log2.replay()] == ["a", "b"]

    # plik na dysku przycięty do końca ostatniej poprawnej linii (truncate,
    # nie rewrite) — dokladnie do rozmiaru sprzed urwanego zapisu
    assert log2.events_path.stat().st_size == size_before_tear
    assert len(log2.events_path.read_text().splitlines()) == 2

    assert log2.append({"type": "chat", "text": "c"}) == 3
    assert log2.last_seq == 3


def test_corrupted_terminated_last_line_raises(tmp_path):
    log = EventLog(tmp_path)
    log.append({"type": "chat", "text": "a"})

    # ostatnia linia niepoprawna, ale ZAKONCZONA newline -> pelna korupcja,
    # nie torn tail (crash nigdy nie zdazylby dopisac konczacego \n do
    # niedokonczonego zapisu)
    with log.events_path.open("ab") as f:
        f.write(b'{bad json}\n')

    with pytest.raises(ValueError):
        EventLog(tmp_path)


def test_corrupted_middle_line_raises(tmp_path):
    log = EventLog(tmp_path)
    log.append({"type": "chat", "text": "a"})
    log.append({"type": "chat", "text": "b"})

    # zepsuj linie w SRODKU pliku (przed poprawna ostatnia linia)
    lines = log.events_path.read_text().splitlines()
    lines[0] = "{bad json}"
    log.events_path.write_text("\n".join(lines) + "\n")

    with pytest.raises(ValueError):
        EventLog(tmp_path)


def test_valid_last_line_without_newline_gets_repaired(tmp_path):
    log = EventLog(tmp_path)
    log.append({"type": "chat", "text": "a"})
    log.append({"type": "chat", "text": "b"})
    assert log.last_seq == 2

    # symulacja crashu PO zapisie kompletnego, poprawnego JSON-a, ale PRZED
    # dopisaniem koncowego \n: usuwamy z pliku tylko ostatni bajt (\n),
    # zostawiajac poprawny, ale niezakonczony ostatni rekord
    size = log.events_path.stat().st_size
    with log.events_path.open("r+b") as f:
        f.truncate(size - 1)

    log2 = EventLog(tmp_path)  # recovery: dopisuje brakujacy \n
    assert log2.last_seq == 2

    assert log2.append({"type": "chat", "text": "c"}) == 3

    log3 = EventLog(tmp_path)
    got = log3.events_after(0)
    assert [e["seq"] for e in got] == [1, 2, 3]
    assert len(got) == 3


def test_snapshot_persists_and_replay_after_restart(tmp_path):
    log = EventLog(tmp_path)
    for i in range(3):
        log.append({"type": "chat", "text": str(i)})
    log.save_snapshot({"s": 1})
    log.append({"type": "chat", "text": "x"})
    log2 = EventLog(tmp_path)
    assert log2.snapshot_seq == 3 and log2.last_seq == 4
    assert [e["text"] for e in log2.replay()] == ["x"]


def test_append_rejects_nan_without_advancing_or_touching_log(tmp_path):
    log = EventLog(tmp_path)
    assert log.append({"type": "chat", "text": "dobry"}) == 1
    before = log.events_path.read_bytes()

    with pytest.raises(ValueError):
        log.append({"type": "chat", "nested": {"value": float("nan")}})

    assert log.last_seq == 1
    assert log.events_path.read_bytes() == before
    assert [e["seq"] for e in log.replay()] == [1]


def test_snapshot_rejects_nan_without_replacing_previous_snapshot(tmp_path):
    log = EventLog(tmp_path)
    log.append({"type": "chat", "text": "dobry"})
    log.save_snapshot({"queue": {"ok": True}})
    before = log.snapshot_path.read_bytes()
    before_seq = log.snapshot_seq

    with pytest.raises(ValueError):
        log.save_snapshot({"queue": {"bad": float("inf")}})

    assert log.snapshot_path.read_bytes() == before
    assert log.snapshot_seq == before_seq
    assert log.load_snapshot() == ({"queue": {"ok": True}}, before_seq)


# --- F1 (B5): pamiec kanalu przezywa kompakcje ---------------------------
# Kanal JEST pamiecia agenta. Kompakcja projektowana pod odtworzenie
# maszyny (queue/registry) kasowala rozmowe z DYSKU — zmierzone na
# produkcji: snapshot_seq=105 zostawil 1 ramke ze 105. Ramki sluzbowe
# (hello/status/task_*) nadal kompaktujemy: ich stan jest w snapshocie.

def test_snapshot_preserves_conversation(tmp_path):
    log = EventLog(tmp_path)
    for i in range(3):
        log.append({"type": "chat", "from": "w1", "ts": 0.0, "text": f"ustalenie {i}"})
        log.append({"type": "hello", "from": "w1", "ts": 0.0, "instance_id": "i1"})
    log.save_snapshot({"registry": {}})

    on_disk = [json.loads(line) for line in
               (tmp_path / "events.jsonl").read_text().splitlines() if line.strip()]
    typy = {e["type"] for e in on_disk}
    assert typy == {"chat"}, "sluzbowe maja zniknac, rozmowa ma zostac"
    assert [e["text"] for e in on_disk] == ["ustalenie 0", "ustalenie 1", "ustalenie 2"]


def test_conversation_after_survives_restart(tmp_path):
    log = EventLog(tmp_path)
    for i in range(3):
        log.append({"type": "chat", "from": "w1", "ts": 0.0, "text": f"m{i}"})
    log.save_snapshot({"registry": {}})
    log.append({"type": "chat", "from": "w1", "ts": 0.0, "text": "po snapshocie"})

    revived = EventLog(tmp_path)   # restart procesu huba
    conv = revived.conversation_after(0)
    assert [e["text"] for e in conv] == ["m0", "m1", "m2", "po snapshocie"]
    assert [e["seq"] for e in conv] == sorted(e["seq"] for e in conv)
    # kursor w srodku: tylko nowsze
    assert [e["text"] for e in revived.conversation_after(2)] == \
        ["m2", "po snapshocie"]
    # limit tnie NAJSTARSZE (agent chce swiezy kontekst)
    assert [e["text"] for e in revived.conversation_after(0, limit=2)] == \
        ["m2", "po snapshocie"]


def test_conversation_after_does_not_break_events_after(tmp_path):
    log = EventLog(tmp_path)
    log.append({"type": "chat", "from": "w1", "ts": 0.0, "text": "a"})
    log.save_snapshot({"registry": {}})
    assert log.events_after(0) is None      # kontrakt resync bez zmian
    assert log.conversation_after(0)        # ale pamiec jest dostepna


# --- F7 (B5): ochrona przed split-brain ---------------------------------
# Zmierzone DWUKROTNIE na produkcji: dwa procesy huba na jednym katalogu.
# Przy zamykaniu starszy robil snapshot ze SWOIM (nieaktualnym) stanem i
# nadpisywal events.jsonl, kasujac ramki zapisane przez nowszy proces.

def test_save_snapshot_refuses_when_disk_has_newer_seq(tmp_path):
    log = EventLog(tmp_path)
    log.append({"type": "chat", "from": "w1", "ts": 0.0, "text": "moje"})
    # inny proces dopisal nowsza ramke do TEGO SAMEGO pliku
    with (tmp_path / "events.jsonl").open("a") as f:
        f.write(json.dumps({"seq": 99, "type": "chat", "from": "w2",
                            "ts": 0.0, "text": "z drugiego procesu"}) + "\n")
    with pytest.raises(ForeignWriterError):
        log.save_snapshot({"registry": {}})
    on_disk = (tmp_path / "events.jsonl").read_text()
    assert "z drugiego procesu" in on_disk, "cudze ramki maja przezyc"
    assert "moje" in on_disk


def test_save_snapshot_works_when_we_are_the_only_writer(tmp_path):
    log = EventLog(tmp_path)
    log.append({"type": "chat", "from": "w1", "ts": 0.0, "text": "moje"})
    log.save_snapshot({"registry": {}})       # brak obcych zapisow = OK
    assert log.snapshot_seq == 1


# --- korekta F1 po uwadze @Emil: okno wznowienia, nie archiwum ----------
# F1 naprawil kasowanie rozmowy, ale przestrzelil w druga strone: log rosl
# w nieskonczonosc. Kanal ma byc DYSKUSJA (bufor, zeby nikt nie stracil
# watku), a twarda wiedza mieszka w plikach .md pisanych swiadomie.

def test_compaction_keeps_only_resume_window(tmp_path, monkeypatch):
    monkeypatch.setattr("chat.store.CONVERSATION_KEEP", 5)
    log = EventLog(tmp_path)
    for i in range(12):
        log.append({"type": "chat", "from": "w1", "ts": 0.0, "text": f"m{i}"})
    log.save_snapshot({"registry": {}})

    on_disk = [json.loads(line) for line in
               (tmp_path / "events.jsonl").read_text().splitlines() if line.strip()]
    assert [e["text"] for e in on_disk] == ["m7", "m8", "m9", "m10", "m11"]


def test_resume_window_never_drops_frames_after_snapshot(tmp_path, monkeypatch):
    """Ogon po snapshocie to stan biezacy — przycinamy tylko HISTORIE."""
    monkeypatch.setattr("chat.store.CONVERSATION_KEEP", 2)
    log = EventLog(tmp_path)
    for i in range(4):
        log.append({"type": "chat", "from": "w1", "ts": 0.0, "text": f"stare{i}"})
    log.save_snapshot({"registry": {}})
    log.append({"type": "chat", "from": "w1", "ts": 0.0, "text": "nowe"})
    log.append({"type": "hello", "from": "w1", "ts": 0.0, "instance_id": "i1"})
    log.save_snapshot({"registry": {}})

    on_disk = [json.loads(line) for line in
               (tmp_path / "events.jsonl").read_text().splitlines() if line.strip()]
    teksty = [e.get("text") for e in on_disk]
    assert "nowe" in teksty, "ramka po snapshocie nie moze wypasc"
    assert len([e for e in on_disk if e["type"] == "chat"]) == 2
