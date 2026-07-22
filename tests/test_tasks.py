import json
from decimal import Decimal

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
    c = make_claimed(q)  # generation=1
    with pytest.raises(StaleGeneration):
        q.heartbeat(c["id"], "beta", generation=2, now=1.0)  # nowsza sesja


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


def test_card_rejects_nonstandard_json_constants():
    q = TaskQueue()
    bad = dict(CARD, goal=float("nan"))
    with pytest.raises(TaskError):
        q.add(bad, command_id="nan-card", now=0.0)
    assert q.dump()["tasks"] == []


def test_add_reuse_with_different_card_conflicts():
    q = TaskQueue()
    q.add(CARD, "c1", 0)
    with pytest.raises(Conflict):
        q.add(dict(CARD, goal="INNY"), "c1", 0)


def test_lease_expiry_reopens_exactly_once():
    q = TaskQueue(lease_ttl=10.0)
    c = make_claimed(q, now=0.0)
    assert q.expire(now=5.0) == []            # jeszcze zyje
    expired = q.expire(now=11.0)
    assert [t["id"] for t in expired] == [c["id"]]
    t = q.get(c["id"])
    assert t["status"] == "open" and t["assignee"] is None
    assert q.expire(now=12.0) == []           # DOKLADNIE raz


def test_blocked_freezes_lease():
    q = TaskQueue(lease_ttl=10.0)
    c = make_claimed(q, now=0.0)
    q.block(c["id"], "beta", 1, "c-blk", expected_version=c["version"], now=1.0)
    assert q.expire(now=100.0) == []          # zamrozony nie wygasa
    t = q.get(c["id"])
    q.unblock(t["id"], "beta", 1, "c-unblk", expected_version=t["version"], now=100.0)
    assert q.get(c["id"])["status"] == "claimed"
    assert q.expire(now=105.0) == []          # swiezy lease po odmrozeniu
    assert len(q.expire(now=111.0)) == 1      # i normalnie wygasa


def test_review_cycle_changes_requested_keeps_assignee():
    q = TaskQueue(lease_ttl=10.0)
    c = make_claimed(q, now=0.0)
    q.to_review(c["id"], "beta", 1, "c-rev", expected_version=c["version"], now=1.0)
    assert q.expire(now=100.0) == []          # w review lease nie tyka
    t = q.get(c["id"])
    q.request_changes(t["id"], "c-chg", expected_version=t["version"], now=100.0)
    t = q.get(c["id"])
    assert t["status"] == "claimed" and t["assignee"] == "beta"
    t2 = q.get(c["id"])
    q.to_review(t2["id"], "beta", 1, "c-rev2", expected_version=t2["version"], now=101.0)
    t3 = q.get(c["id"])
    q.done(t3["id"], "beta", 1, "c-done", expected_version=t3["version"], now=102.0)
    assert q.get(c["id"])["status"] == "done"


def test_done_after_changes_not_deduped_with_first_done():
    # rozne command_id => rozne komendy; dedup nie sklei ich w jedno
    q = TaskQueue()
    c = make_claimed(q, now=0.0)
    q.to_review(c["id"], "beta", 1, "r1", expected_version=2, now=0.0)
    q.request_changes(c["id"], "chg", expected_version=3, now=0.0)
    q.to_review(c["id"], "beta", 1, "r2", expected_version=4, now=0.0)
    q.done(c["id"], "beta", 1, "d2", expected_version=5, now=0.0)
    assert q.get(c["id"])["status"] == "done"


def test_wip_limit_gates_offerable():
    q = TaskQueue(wip_limit=1)
    t1 = q.add(CARD, "a1", now=0.0)
    q.add(dict(CARD, goal="drugi"), "a2", now=0.0)
    assert q.offerable()["id"] == t1["id"]
    q.claim(t1["id"], "beta", 1, "cl", expected_version=1, now=0.0)
    assert q.offerable() is None              # WIP pelny
    # blocked parkuje POZA limitem WIP
    t1c = q.get(t1["id"])
    q.block(t1["id"], "beta", 1, "blk", expected_version=t1c["version"], now=0.0)
    assert q.offerable() is not None


def test_dump_restore_roundtrip():
    q = TaskQueue(lease_ttl=10.0)
    c = make_claimed(q, now=0.0)
    q2 = TaskQueue.restore(q.dump(), lease_ttl=10.0)
    assert q2.get(c["id"])["status"] == "claimed"
    assert len(q2.expire(now=11.0)) == 1      # lease przezyl podroz


# -- walidacja karty w add ---------------------------------------------------

def test_add_rejects_card_missing_required_fields():
    q = TaskQueue()
    with pytest.raises(TaskError):
        q.add({"goal": "x"}, command_id="c1", now=0.0)


def test_add_rejects_non_dict_card():
    q = TaskQueue()
    with pytest.raises(TaskError):
        q.add({"x": object()}, command_id="c1", now=0.0)


def test_add_rejects_unserializable_card_value_not_typeerror():
    q = TaskQueue()
    bad = dict(CARD, files=object())  # wszystkie pola obecne, jedna wartosc zla
    with pytest.raises(TaskError):
        q.add(bad, command_id="c1", now=0.0)


def test_add_valid_card_still_works():
    q = TaskQueue()
    t = q.add(CARD, command_id="c1", now=0.0)
    assert t["status"] == "open" and t["card"] == CARD


# -- walidacja wejsc mutacji (_check_inputs) --------------------------------

def test_claim_rejects_non_str_nick():
    q = TaskQueue()
    t = q.add(CARD, command_id="c1", now=0.0)
    with pytest.raises(TaskError):
        q.claim(t["id"], [], generation=1, command_id="c2",
                expected_version=1, now=0.0)


def test_claim_rejects_bool_generation():
    q = TaskQueue()
    t = q.add(CARD, command_id="c1", now=0.0)
    with pytest.raises(TaskError):
        q.claim(t["id"], "beta", generation=True, command_id="c2",
                expected_version=1, now=0.0)


def test_heartbeat_rejects_negative_generation():
    q = TaskQueue()
    c = make_claimed(q)
    with pytest.raises(TaskError):
        q.heartbeat(c["id"], "beta", generation=-1, now=1.0)


def test_to_review_rejects_zero_expected_version():
    q = TaskQueue()
    c = make_claimed(q)
    with pytest.raises(TaskError):
        q.to_review(c["id"], "beta", 1, "c-rev", expected_version=0, now=1.0)


def test_expire_rejects_non_finite_now():
    q = TaskQueue()
    with pytest.raises(TaskError):
        q.expire(now=float("nan"))


# -- 1: add() waliduje now --------------------------------------------------

def test_add_rejects_nan_now():
    q = TaskQueue()
    with pytest.raises(TaskError):
        q.add(CARD, "c", float("nan"))


def test_add_rejects_bool_now():
    q = TaskQueue()
    with pytest.raises(TaskError):
        q.add(CARD, "c", True)


# -- 2: generation >= 1 w mutacjach -----------------------------------------

def test_heartbeat_rejects_zero_generation():
    q = TaskQueue()
    c = make_claimed(q)
    with pytest.raises(TaskError) as exc_info:
        q.heartbeat(c["id"], "beta", generation=0, now=1.0)
    # to guard wejscia (generation < 1), nie StaleGeneration z _check_owner
    assert not isinstance(exc_info.value, StaleGeneration)


# -- 3 + 4: dedup w dump/restore, bez TTL ------------------------------------

def test_dedup_survives_json_roundtrip_dump_restore():
    q = TaskQueue()
    t = q.add(CARD, "c1", 0)
    dumped = json.loads(json.dumps(q.dump()))  # fingerprint krotki -> listy
    q2 = TaskQueue.restore(dumped)
    again = q2.add(CARD, "c1", 1)
    assert again == t                          # dedup przezyl podroz przez JSON
    with pytest.raises(Conflict):
        q2.add(dict(CARD, goal="INNY"), "c1", 1)


def test_dedup_never_expires():
    q = TaskQueue()
    t = q.add(CARD, "c1", now=0.0)
    much_later = q.add(CARD, "c1", now=10**9)  # dawno po dawnym dedup_ttl=3600
    assert much_later == t


# -- 5: claim egzekwuje WIP --------------------------------------------------

def test_claim_enforces_wip_limit():
    q = TaskQueue(wip_limit=1)
    t1 = q.add(CARD, "a1", now=0.0)
    t2 = q.add(dict(CARD, goal="drugi"), "a2", now=0.0)
    q.claim(t1["id"], "beta", 1, "cl1", expected_version=1, now=0.0)
    with pytest.raises(Conflict):
        q.claim(t2["id"], "beta", 1, "cl2", expected_version=1, now=0.0)
    t1c = q.get(t1["id"])
    q.to_review(t1["id"], "beta", 1, "c-rev", expected_version=t1c["version"], now=0.0)
    with pytest.raises(Conflict):  # review tez liczy sie do WIP
        q.claim(t2["id"], "beta", 1, "cl3", expected_version=1, now=0.0)
    t1r = q.get(t1["id"])
    q.done(t1["id"], "beta", 1, "c-done", expected_version=t1r["version"], now=0.0)
    claimed2 = q.claim(t2["id"], "beta", 1, "cl4", expected_version=1, now=0.0)
    assert claimed2["status"] == "claimed"


# -- 6: heartbeat/mutacje vs status i zywosc lease ---------------------------

def test_heartbeat_after_done_rejected():
    q = TaskQueue()
    c = make_claimed(q, now=0.0)
    r = q.to_review(c["id"], "beta", 1, "r1", expected_version=c["version"], now=0.0)
    q.done(c["id"], "beta", 1, "d1", expected_version=r["version"], now=0.0)
    with pytest.raises(TaskError):
        q.heartbeat(c["id"], "beta", 1, now=1.0)


def test_heartbeat_on_expired_lease_rejects_and_expire_still_reopens():
    q = TaskQueue(lease_ttl=10.0)
    c = make_claimed(q, now=0.0)
    with pytest.raises(TaskError):
        q.heartbeat(c["id"], "beta", 1, now=11.0)   # lease wygasl, bez odnowienia
    expired = q.expire(now=11.0)
    assert [t["id"] for t in expired] == [c["id"]]


def test_to_review_on_expired_claim_conflicts():
    q = TaskQueue(lease_ttl=10.0)
    c = make_claimed(q, now=0.0)
    with pytest.raises(Conflict):
        q.to_review(c["id"], "beta", 1, "c-rev", expected_version=c["version"], now=11.0)


# -- fix po re-review: WIP gate w unblock ------------------------------------

def test_unblock_respects_wip_limit():
    q = TaskQueue(wip_limit=1)
    t1 = q.add(CARD, "a1", now=0.0)
    t2 = q.add(dict(CARD, goal="drugi"), "a2", now=0.0)
    c1 = q.claim(t1["id"], "beta", 1, "cl1", expected_version=1, now=0.0)
    q.block(t1["id"], "beta", 1, "blk", expected_version=c1["version"], now=0.0)
    # t1 blocked jest poza WIP -> slot wolny, t2 moze byc zaklejmowany
    q.claim(t2["id"], "beta", 1, "cl2", expected_version=1, now=0.0)
    t1b = q.get(t1["id"])
    with pytest.raises(Conflict, match="WIP"):
        q.unblock(t1["id"], "beta", 1, "unblk", expected_version=t1b["version"], now=0.0)
    assert q.get(t1["id"])["status"] == "blocked"  # bez mutacji po Conflict
    # dopiero po zwolnieniu t2 unblock odzyskuje slot atomowo
    t2r = q.get(t2["id"])
    r = q.to_review(t2["id"], "beta", 1, "rev", expected_version=t2r["version"], now=0.0)
    q.done(t2["id"], "beta", 1, "done", expected_version=r["version"], now=0.0)
    unblocked = q.unblock(t1["id"], "beta", 1, "unblk2",
                          expected_version=t1b["version"], now=0.0)
    assert unblocked["status"] == "claimed"


# -- fix po re-review: now musi byc jawnie int|float -------------------------

def test_claim_rejects_decimal_now():
    q = TaskQueue()
    t = q.add(CARD, command_id="c1", now=0.0)
    with pytest.raises(TaskError):
        q.claim(t["id"], "beta", 1, "c2", expected_version=1, now=Decimal("1"))


def test_add_rejects_decimal_now():
    q = TaskQueue()
    with pytest.raises(TaskError):
        q.add(CARD, "c1", Decimal("1"))


# -- fix po re-review: dedup_ttl przyjmowany dla kompatybilnosci -------------

def test_dedup_ttl_param_accepted_for_compat_and_ignored():
    q = TaskQueue(dedup_ttl=3600.0)  # stare API — nie moze rzucic TypeError
    t = q.add(CARD, "c1", now=0.0)
    much_later = q.add(CARD, "c1", now=10**9)  # dawno po "starym" dedup_ttl
    assert much_later == t
