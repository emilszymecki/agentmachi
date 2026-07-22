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


def test_envelope_deterministic_activation_id():
    frames = [protocol.make_frame("chat", "beta", ts=1.0, text="@alfa hej")]
    e1 = protocol.make_envelope("alfa", frames, seq_from=5, seq_to=9)
    e2 = protocol.make_envelope("alfa", frames, seq_from=5, seq_to=9)
    assert e1["activation_id"] == e2["activation_id"] == "alfa:5-9"
    assert e1["backlog"] == frames
    assert e1["seq_from"] == 5 and e1["seq_to"] == 9
