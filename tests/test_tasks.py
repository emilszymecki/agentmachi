import pytest
from chat.tasks import TaskQueue, Conflict, StaleGeneration

CARD = {"goal": "napisz foo", "acceptance": "test przechodzi",
        "verify": "pytest -k foo", "files": ["foo.py"],
        "head": "abc123", "brief": "def456"}


def make_claimed(q, now=0.0):
    t = q.add(CARD, command_id="c-add", now=now)
    return q.claim(t["id"], "beta", generation=1, command_id="c-claim",
                   expected_version=t["version"], now=now)


def test_add_and_claim():
    q = TaskQueue()
    t = q.add(CARD, command_id="c1", now=0.0)
    assert t["status"] == "open" and t["version"] == 1 and t["card"] == CARD
    c = q.claim(t["id"], "beta", generation=1, command_id="c2",
                expected_version=1, now=0.0)
    assert c["status"] == "claimed" and c["assignee"] == "beta"
    assert c["version"] == 2 and c["lease_until"] > 0.0


def test_command_id_dedup_returns_same_result_no_double_mutation():
    q = TaskQueue()
    t = q.add(CARD, command_id="c1", now=0.0)
    again = q.add(CARD, command_id="c1", now=1.0)  # duplikat komendy
    assert again["id"] == t["id"]
    c1 = q.claim(t["id"], "beta", 1, "c2", expected_version=1, now=0.0)
    c2 = q.claim(t["id"], "beta", 1, "c2", expected_version=1, now=0.0)
    assert c1 == c2 and q.get(t["id"])["version"] == 2  # jedna mutacja


def test_cas_conflict_without_mutation():
    q = TaskQueue()
    t = q.add(CARD, command_id="c1", now=0.0)
    with pytest.raises(Conflict):
        q.claim(t["id"], "beta", 1, "c2", expected_version=99, now=0.0)
    assert q.get(t["id"])["status"] == "open"
    assert q.get(t["id"])["version"] == 1


def test_stale_generation_rejected():
    q = TaskQueue()
    c = make_claimed(q)
    with pytest.raises(StaleGeneration):
        q.heartbeat(c["id"], "beta", generation=0, now=1.0)  # stara sesja
