import pytest
from chat.tasks import TaskQueue, Conflict, StaleGeneration, TaskError

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


def test_command_id_reuse_across_ops_conflicts():
    q = TaskQueue()
    t = q.add(CARD, "same", 0)
    with pytest.raises(Conflict):
        q.claim(t["id"], "beta", 1, "same", 1, 0)


def test_command_id_reuse_different_task_conflicts():
    q = TaskQueue()
    a = q.add(CARD, command_id="add-a", now=0.0)
    b = q.add(CARD, command_id="add-b", now=0.0)
    q.claim(b["id"], "beta", 1, "c-claim", expected_version=1, now=0.0)
    with pytest.raises(Conflict):
        q.claim(a["id"], "beta", 1, "c-claim", expected_version=1, now=0.0)


def test_unknown_task_id_raises_taskerror():
    q = TaskQueue()
    with pytest.raises(TaskError):
        q.get("t999")
    with pytest.raises(TaskError):
        q.claim("t999", "beta", 1, "c1", expected_version=1, now=0.0)
    with pytest.raises(TaskError):
        q.heartbeat("t999", "beta", 1, now=0.0)


def test_unhashable_ids_raise_taskerror():
    q = TaskQueue()
    with pytest.raises(TaskError):
        q.claim([], "beta", 1, "c2", expected_version=1, now=0.0)
    with pytest.raises(TaskError):
        q.add(CARD, command_id={}, now=0.0)


def test_card_mutation_after_add_has_no_effect():
    q = TaskQueue()
    card = dict(CARD)
    t = q.add(card, command_id="c1", now=0.0)
    card["goal"] = "ZMIENIONE"
    assert q.get(t["id"])["card"]["goal"] != "ZMIENIONE"


def test_add_reuse_with_different_card_conflicts():
    q = TaskQueue()
    q.add(CARD, "c1", 0)
    with pytest.raises(Conflict):
        q.add(dict(CARD, goal="INNY"), "c1", 0)
