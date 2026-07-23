from chat import protocol


def test_parse_mentions():
    assert protocol.parse_mentions("hej @alfa i @beta, reszta nie") == {"alfa", "beta"}
    assert protocol.parse_mentions("@all ruszamy") == {"all"}
    assert protocol.parse_mentions("bez wzmianek") == set()
    assert protocol.parse_mentions("mail x@y.z to nie wzmianka") == set()


def test_parse_groups():
    assert protocol.parse_groups("hej $workers i $review, reszta nie") == {"workers", "review"}
    assert protocol.parse_groups("bez grup") == set()
    assert protocol.parse_groups("cena5$workers to nie grupa") == set()
    assert protocol.parse_groups("") == set()


def test_make_frame_and_validate_ok():
    f = protocol.make_frame("chat", "alfa", ts=123.0, text="siema")
    assert f == {"type": "chat", "from": "alfa", "ts": 123.0, "text": "siema"}
    assert protocol.validate(f) is None


def test_validate_rejects():
    assert protocol.validate({"from": "x", "ts": 1.0}) == "missing type"
    assert protocol.validate({"type": "nope", "from": "x", "ts": 1.0}) == "unknown type: nope"
    assert protocol.validate({"type": "chat", "ts": 1.0}) == "missing from"
    assert protocol.validate({"type": "chat", "from": "x"}) == "missing ts"


# -- Runda 4 #5: schemat inbound per typ ramki -------------------------------

def test_validate_common_from_must_be_nonempty_string():
    assert protocol.validate({"type": "chat", "from": "", "ts": 1.0, "text": "x"})
    assert protocol.validate({"type": "chat", "from": 5, "ts": 1.0, "text": "x"})


def test_validate_common_ts_must_be_number_not_bool():
    assert protocol.validate({"type": "chat", "from": "a", "ts": "x", "text": "y"})
    assert protocol.validate({"type": "chat", "from": "a", "ts": True, "text": "y"})
    assert protocol.validate({"type": "chat", "from": "a", "ts": 1, "text": "y"}) is None


def test_validate_fyi_requires_nonempty_text():
    assert protocol.validate({"type": "fyi", "from": "a", "ts": 1.0}) is not None
    assert protocol.validate({"type": "fyi", "from": "a", "ts": 1.0, "text": ""}) is not None
    assert protocol.validate({"type": "fyi", "from": "a", "ts": 1.0, "text": "hej"}) is None


def test_validate_status_requires_nonempty_string_state():
    assert protocol.validate({"type": "status", "from": "a", "ts": 1.0}) is not None
    assert protocol.validate({"type": "status", "from": "a", "ts": 1.0, "state": []}) is not None
    assert protocol.validate({"type": "status", "from": "a", "ts": 1.0, "state": "idle"}) is None


def test_validate_status_state_is_free_text_up_to_32_chars():
    # (t4) hub nie waliduje przynaleznosci do enuma — dowolny wolny tekst
    # (niepusty, <=32 znaki) przechodzi; STATUS_STATES zostaje wylacznie
    # dokumentacja stanow umownych.
    assert protocol.validate({"type": "status", "from": "a", "ts": 1.0,
                              "state": "sleeping"}) is None
    assert protocol.validate({"type": "status", "from": "a", "ts": 1.0,
                              "state": "cokolwiek-innego"}) is None
    assert protocol.validate({"type": "status", "from": "a", "ts": 1.0,
                              "state": "x" * 32}) is None            # brzeg OK
    assert protocol.validate({"type": "status", "from": "a", "ts": 1.0,
                              "state": "x" * 33}) is not None        # za dlugie
    assert protocol.validate({"type": "status", "from": "a", "ts": 1.0,
                              "state": ""}) is not None              # puste
    assert protocol.validate({"type": "status", "from": "a", "ts": 1.0,
                              "state": 5}) is not None                # nie-str


def test_validate_status_target_optional_but_nonempty_string_if_present():
    base = {"type": "status", "from": "a", "ts": 1.0, "state": "working"}
    assert protocol.validate(base) is None                            # brak target OK
    assert protocol.validate({**base, "target": "gamma"}) is None
    assert protocol.validate({**base, "target": ""}) is not None       # puste
    assert protocol.validate({**base, "target": 7}) is not None        # nie-str


def test_validate_heartbeat_requires_nonempty_task_id_only():
    assert protocol.validate({
        "type": "heartbeat", "from": "beta", "ts": 1.0,
        "task_id": "t1",
    }) is None
    assert protocol.validate({
        "type": "heartbeat", "from": "beta", "ts": 1.0,
    }) is not None
    assert protocol.validate({
        "type": "heartbeat", "from": "beta", "ts": 1.0,
        "task_id": "",
    }) is not None


def test_validate_membership_set_requires_target_and_group_list():
    base = {"type": "membership_set", "from": "emil", "ts": 1.0}
    assert protocol.validate({**base, "target": "beta", "groups": []}) is None
    assert protocol.validate({**base, "target": "beta",
                              "groups": ["head", "admin"]}) is None
    assert protocol.validate({**base, "target": "", "groups": []}) is not None
    assert protocol.validate({**base, "target": "beta", "groups": "admin"}) is not None
    assert protocol.validate({**base, "target": "beta", "groups": [""]}) is not None


def test_validate_task_frames_require_command_id_and_task_id_where_relevant():
    # task_new: tylko command_id (task_id jeszcze nie istnieje)
    assert protocol.validate({"type": "task_new", "from": "a", "ts": 1.0}) is not None
    assert protocol.validate({"type": "task_new", "from": "a", "ts": 1.0,
                              "command_id": "n1", "card": {}}) is None
    # task_claim: command_id + task_id
    assert protocol.validate({"type": "task_claim", "from": "a", "ts": 1.0,
                              "command_id": "c1"}) is not None      # brak task_id
    assert protocol.validate({"type": "task_claim", "from": "a", "ts": 1.0,
                              "task_id": "t1"}) is not None          # brak command_id
    assert protocol.validate({"type": "task_claim", "from": "a", "ts": 1.0,
                              "command_id": "c1", "task_id": "t1"}) is None


def test_validate_rejects_outbound_only_types_inbound_but_known():
    for ftype in ("task_offer", "backlog", "resync_required", "error", "ok",
                  "task_expired", "offer_resolved"):
        msg = protocol.validate({"type": ftype, "from": "a", "ts": 1.0})
        assert msg is not None                    # odrzucone inbound-em
        assert "unknown type" not in msg          # ale to ZNANE typy (nie nieznane)


# -- Runda 5: walidacja inbound pelna (type nie-str, ts skonczone) ----------

def test_validate_nonstring_type_does_not_raise_unhashable():
    # (C1) type=[] / {} to unhashable — membership `in FRAME_TYPES` PRZED
    # sprawdzeniem ze type to str rzucalo TypeError. Musi zwrocic error, nie rzucic.
    assert protocol.validate({"type": [], "from": "a", "ts": 1.0}) is not None
    assert protocol.validate({"type": {}, "from": "a", "ts": 1.0}) is not None
    assert protocol.validate({"type": "", "from": "a", "ts": 1.0}) is not None
    # znany zly typ (str) nadal daje czytelne "unknown type: ..."
    assert protocol.validate({"type": "nope", "from": "a", "ts": 1.0}) == "unknown type: nope"


def test_validate_ts_must_be_finite():
    # (C2) NaN/inf przechodzily (validate=None) -> logowany niestandardowy JSON
    assert protocol.validate({"type": "chat", "from": "a", "ts": float("nan"),
                              "text": "x"}) is not None
    assert protocol.validate({"type": "chat", "from": "a", "ts": float("inf"),
                              "text": "x"}) is not None
    assert protocol.validate({"type": "chat", "from": "a", "ts": float("-inf"),
                              "text": "x"}) is not None
    assert protocol.validate({"type": "chat", "from": "a", "ts": 1.5,
                              "text": "x"}) is None


def test_validate_huge_int_ts_rejected_no_overflow():
    # (Runda 6 #3) math.isfinite(10**400) rzuca OverflowError (legalny JSON int
    # za duzy na float) — wysypywalo CALA walidacje zamiast zwrocic blad. int
    # poza zakresem float odrzucony KOMUNIKATEM (bez OverflowError); normalny
    # int ts nadal przechodzi (isfinite wolane tylko dla float).
    frame = {"type": "chat", "from": "a", "ts": 10**400, "text": "x"}
    msg = protocol.validate(frame)                 # NIE moze rzucic OverflowError
    assert isinstance(msg, str) and msg            # ramka odrzucona komunikatem
    assert protocol.validate({"type": "chat", "from": "a", "ts": 1,
                              "text": "x"}) is None  # zwykly int nadal ok
