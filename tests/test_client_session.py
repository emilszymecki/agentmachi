import json
import os
import stat
import threading

import pytest

from chat.client_session import (ListenerLockHeld, Session, SessionError,
                                 MAX_ACTIVATIONS, _slug)


HUB = "localhost:8766"


def make(tmp_path, nick="beta", hub=HUB, legacy=None):
    return Session(hub, nick, base_dir=tmp_path, legacy_instance_file=legacy)


def test_create_persists_identity_and_mode(tmp_path):
    s1 = make(tmp_path)
    assert s1.last_applied_seq == 0
    mode = stat.S_IMODE(os.stat(s1.path).st_mode)
    assert mode == 0o600
    s2 = make(tmp_path)
    assert s2.instance_id == s1.instance_id


def test_namespace_per_hub_and_nick_with_safe_slug(tmp_path):
    a = make(tmp_path, nick="beta", hub="localhost:8766")
    b = make(tmp_path, nick="beta", hub="localhost:8765")
    c = make(tmp_path, nick="alfa", hub="localhost:8766")
    assert len({a.path, b.path, c.path}) == 3
    nasty = make(tmp_path, nick="../../etc/passwd")
    assert nasty.path.parent == tmp_path  # zero path traversal
    assert "/" not in nasty.path.name.replace(".json", "")
    assert ".." not in _slug(HUB, "../x").split("-")[0]


def test_advance_monotonic_and_persisted(tmp_path):
    s = make(tmp_path)
    assert s.advance(5) is True
    assert s.advance(5) is False   # duplikat
    assert s.advance(3) is False   # cofniecie
    assert s.advance(6) is True
    assert make(tmp_path).last_applied_seq == 6
    assert not (s.path.with_name(s.path.name + ".tmp")).exists()


@pytest.mark.parametrize("bad", [0, -1, True, "5", 1.5, None])
def test_advance_rejects_bad_seq(tmp_path, bad):
    s = make(tmp_path)
    with pytest.raises(SessionError):
        s.advance(bad)


def test_corrupt_state_fails_closed_with_repair_instruction(tmp_path):
    s = make(tmp_path)
    s.path.write_text("{urwane")
    with pytest.raises(SessionError) as e:
        make(tmp_path)
    assert "skasuj" in str(e.value)
    assert str(s.path) in str(e.value)


def test_wrong_schema_fails_closed(tmp_path):
    s = make(tmp_path)
    s.path.write_text(json.dumps({"schema": 999, "instance_id": "x",
                                  "last_applied_seq": 0,
                                  "applied_activations": []}))
    with pytest.raises(SessionError):
        make(tmp_path)


def test_no_silent_cursor_reset_on_bool_seq_in_file(tmp_path):
    s = make(tmp_path)
    state = json.loads(s.path.read_text())
    state["last_applied_seq"] = True
    s.path.write_text(json.dumps(state))
    with pytest.raises(SessionError):
        make(tmp_path)


def test_legacy_instance_migration(tmp_path):
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({"instance_id": "stary-iid"}))
    s = make(tmp_path, legacy=legacy)
    assert s.instance_id == "stary-iid"
    # zepsuty legacy -> swieza tozsamosc, bez wyjatku
    legacy2 = tmp_path / "legacy2.json"
    legacy2.write_text("{zepsute")
    s2 = make(tmp_path, nick="gamma", legacy=legacy2)
    assert s2.instance_id and s2.instance_id != "stary-iid"


def test_activation_check_does_not_mark(tmp_path):
    """is_activation_applied to czysty odczyt — mark osobno, PO apply."""
    s = make(tmp_path)
    assert s.is_activation_applied("beta:13") is False
    assert s.is_activation_applied("beta:13") is False  # nadal nic nie zapisal
    s.mark_activation("beta:13")
    assert s.is_activation_applied("beta:13") is True
    s.mark_activation("beta:13")  # idempotentne
    state = json.loads(s.path.read_text())
    assert state["applied_activations"].count("beta:13") == 1


def test_mark_activation_trims_window(tmp_path):
    s = make(tmp_path)
    s.mark_activation("beta:13")
    for i in range(MAX_ACTIVATIONS + 10):
        s.mark_activation(f"beta:{100 + i}")
    state = json.loads(s.path.read_text())
    assert len(state["applied_activations"]) == MAX_ACTIVATIONS
    # najstarsze wypchniete z okna
    assert "beta:13" not in state["applied_activations"]


def test_listener_lock_exclusive_and_releasable(tmp_path):
    s1 = make(tmp_path)
    s1.acquire_listener_lock()
    s2 = make(tmp_path)
    with pytest.raises(ListenerLockHeld):
        s2.acquire_listener_lock()
    s1.release_listener_lock()
    s2.acquire_listener_lock()
    s2.release_listener_lock()


def test_send_once_reads_identity_while_listener_advances(tmp_path):
    """State-lock jest krotki: rownolegly odczyt instance_id (send_once)
    nie blokuje sie o advance listenera."""
    listener = make(tmp_path)
    listener.acquire_listener_lock()
    errors = []

    def sender():
        try:
            for _ in range(20):
                s = make(tmp_path)
                assert s.instance_id == listener.instance_id
        except Exception as e:  # pragma: no cover
            errors.append(e)

    t = threading.Thread(target=sender)
    t.start()
    for i in range(1, 40):
        listener.advance(i)
    t.join(timeout=10)
    assert not t.is_alive() and not errors
    listener.release_listener_lock()


def test_advance_sees_disk_state_from_other_instance(tmp_path):
    """Read-modify-write pod lockiem: dwie instancje nie gubia kursora."""
    a = make(tmp_path)
    b = make(tmp_path)
    a.advance(5)
    assert b.advance(4) is False    # b widzi 5 z dysku, nie swoje 0
    assert b.advance(7) is True
    assert make(tmp_path).last_applied_seq == 7


def test_mode_0600_preserved_after_advance(tmp_path):
    s = make(tmp_path)
    s.advance(1)
    assert stat.S_IMODE(os.stat(s.path).st_mode) == 0o600
