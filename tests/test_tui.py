import asyncio
import json

import pytest

pytest.importorskip("textual", reason="TUI wymaga textual — "
                    "uv run --with textual ... (patrz README)")

import tui  # noqa: E402
from chat.client_session import Session
from tui import (HubAdapter, HumanIdentity, TuiError, apply_resumable_frame,
                 load_human_identity, parse_user_input)


# --- parse_user_input -----------------------------------------------------

def test_parse_chat():
    assert parse_user_input("czesc") == {"type": "chat", "text": "czesc"}


def test_parse_groups_set():
    frame = parse_user_input("/groups beta head,admin")
    assert frame == {"type": "membership_set", "target": "beta",
                     "groups": ["head", "admin"]}


def test_parse_groups_dedup_and_clear():
    assert parse_user_input("/groups x a,a,b")["groups"] == ["a", "b"]
    assert parse_user_input("/groups x -")["groups"] == []


def test_parse_kick():
    """B6: wyrzucenie uczestnika — jedyna komenda operatora poza /groups."""
    assert parse_user_input("/kick worker3") == {"type": "kick",
                                                 "target": "worker3"}


@pytest.mark.parametrize("bad", [
    "", "   ", "/nieznana cokolwiek", "/groups", "/groups nick",
    "/groups nick a,,b",
    # kick bez celu albo z nadmiarem argumentow: lepiej odmowic niz
    # zgadnac, kogo czlowiek chcial wyrzucic — to operacja nieodwracalna
    # dla trwajacej pracy ubitego agenta
    "/kick", "/kick a b",
])
def test_parse_rejects_bad_input(bad):
    with pytest.raises(TuiError):
        parse_user_input(bad)


# --- load_human_identity --------------------------------------------------

def _write_tokens(tmp_path, payload):
    p = tmp_path / "hub.tokens.json"
    p.write_text(json.dumps(payload))
    return p


def test_load_single_human_and_roster(tmp_path):
    p = _write_tokens(tmp_path, {
        "Emil": {"token": "tok-e", "role": "human", "groups": []},
        "beta": {"token": "tok-b", "role": "agent", "groups": ["workers"]},
    })
    identity, roster = load_human_identity(p)
    assert identity.nick == "Emil" and identity.role == "human"
    assert set(roster) == {"Emil", "beta"}
    assert roster["beta"].groups == ["workers"]


@pytest.mark.parametrize("payload", [
    {},                                                     # pusto
    {"a": {"token": "t", "role": "agent"}},                 # zero humanow
    {"a": {"token": "t", "role": "human"},
     "b": {"token": "t", "role": "human"}},                 # dwoch humanow
    {"a": {"token": "", "role": "human"}},                  # pusty token
    {"a": {"token": "t", "role": "szef"}},                  # zla rola
    {"a": {"token": "t", "role": "human", "groups": [""]}}, # zle groups
])
def test_load_fails_closed(tmp_path, payload):
    p = _write_tokens(tmp_path, payload)
    with pytest.raises(TuiError):
        load_human_identity(p)


def test_load_corrupt_json_and_missing_file(tmp_path):
    p = tmp_path / "hub.tokens.json"
    p.write_text("{urwane")
    with pytest.raises(TuiError):
        load_human_identity(p)
    with pytest.raises(TuiError):
        load_human_identity(tmp_path / "nie-ma.json")


# --- apply_resumable_frame (ten sam kontrakt co CLI) ----------------------

@pytest.fixture
def session(tmp_path):
    return Session("localhost:8766", "Emil", base_dir=tmp_path)


def _collector():
    seen = []

    async def apply(frame):
        seen.append(frame)
    return seen, apply


def test_resumable_apply_then_advance(session):
    seen, apply = _collector()
    ok = asyncio.run(apply_resumable_frame(
        session, {"type": "chat", "seq": 3, "text": "x"}, apply))
    assert ok and len(seen) == 1
    assert session.last_applied_seq == 3


def test_resumable_duplicate_seq_skipped(session):
    seen, apply = _collector()
    asyncio.run(apply_resumable_frame(session, {"seq": 3}, apply))
    ok = asyncio.run(apply_resumable_frame(session, {"seq": 3}, apply))
    assert ok is False and len(seen) == 1


def test_resumable_activation_mark_after_apply(session):
    """Crash w apply NIE zapisuje aktywacji ani kursora (at-least-once)."""
    async def boom(_):
        raise RuntimeError("crash")
    frame = {"seq": 5, "activation_id": "Emil:5"}
    with pytest.raises(RuntimeError):
        asyncio.run(apply_resumable_frame(session, frame, boom))
    assert session.is_activation_applied("Emil:5") is False
    assert session.last_applied_seq == 0
    seen, apply = _collector()
    ok = asyncio.run(apply_resumable_frame(session, frame, apply))
    assert ok and session.last_applied_seq == 5


# --- HubAdapter: hello/resync kontrakt (bez sieci) ------------------------

class _FakeWs:
    def __init__(self, replies):
        self.sent = []
        self._replies = list(replies)

    async def send(self, data):
        self.sent.append(json.loads(data))

    async def recv(self):
        return json.dumps(self._replies.pop(0))


def _adapter(session):
    identity = HumanIdentity("Emil", "tok-e", "human", ())
    return HubAdapter(identity, session=session, uri="ws://test")


def test_hello_sends_cursor_and_returns_reply(session):
    session.advance(7)
    adapter = _adapter(session)
    ws = _FakeWs([{"type": "ok", "generation": 1, "backlog": []}])
    reply = asyncio.run(adapter._hello(ws))
    assert reply["type"] == "ok"
    hello = ws.sent[0]
    assert hello["last_seq"] == 7 and hello["from"] == "Emil"
    assert hello["role"] == "human"


def test_hello_error_fails_closed(session):
    adapter = _adapter(session)
    ws = _FakeWs([{"type": "error", "text": "bad token"}])
    with pytest.raises(tui.FatalHubError):
        asyncio.run(adapter._hello(ws))


def test_apply_hello_resync_requires_state(session):
    adapter = _adapter(session)

    async def run():
        await adapter._apply_hello(
            {"type": "resync_required", "snapshot_seq": 9},
            lambda f: None, lambda m: None)
    with pytest.raises(tui.FatalHubError):
        asyncio.run(run())
    assert session.last_applied_seq == 0


def test_apply_hello_resync_applies_state_then_cursor(session):
    adapter = _adapter(session)
    frames = []

    async def on_frame(frame):
        frames.append(frame)

    async def run():
        await adapter._apply_hello(
            {"type": "resync_required", "snapshot_seq": 9,
             "state": {"registry": {"groups": {"beta": ["head"]}}}},
            on_frame, lambda m: None)
    asyncio.run(run())
    assert frames and frames[0]["type"] == "resync_state"
    assert session.last_applied_seq == 9


def test_apply_hello_participants_before_backlog(session):
    """Snapshot uczestnikow (autorytatywny) laduje PRZED backlogiem —
    roster jest cursor-coherent po kazdym hello, takze po restarcie."""
    adapter = _adapter(session)
    order = []

    async def on_frame(frame):
        order.append(frame["type"])

    async def run():
        await adapter._apply_hello(
            {"type": "ok", "generation": 1,
             "participants": [
                 {"nick": "beta", "role": "agent",
                  "groups": ["head", "admin"], "connected": True}],
             "backlog": [{"type": "chat", "from": "beta", "text": "x",
                          "seq": 11}]},
            on_frame, lambda m: None)
    asyncio.run(run())
    assert order == ["participants_snapshot", "chat"]


def test_app_participants_snapshot_overrides_stale_roster(tmp_path):
    """Repro review: config mowi workers, serwerowy snapshot mowi
    head+admin po restarcie z wysokim kursorem — panel MUSI wierzyc
    snapshotowi, nie configowi."""
    pytest.importorskip("textual")
    p = _write_tokens(tmp_path, {
        "Emil": {"token": "tok-e", "role": "human", "groups": []},
        "beta": {"token": "tok-b", "role": "agent", "groups": ["workers"]},
    })
    identity, roster = load_human_identity(p)
    app = tui.AgentmachiApp(_StubQuietAdapter(identity), roster)

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.roster["beta"].groups == ["workers"]  # stan z configu
            await app.apply_hub_frame({
                "type": "participants_snapshot",
                "participants": [
                    {"nick": "Emil", "role": "human", "groups": [],
                     "connected": True},
                    {"nick": "beta", "role": "agent",
                     "groups": ["head", "admin"], "connected": False}]})
            assert app.roster["beta"].groups == ["head", "admin"]
            assert app.roster["beta"].presence == "known"
            assert app.roster["Emil"].presence == "connected"
    asyncio.run(scenario())


class _StubQuietAdapter:
    def __init__(self, identity):
        self.identity = identity

    async def run(self, on_frame, on_metadata, on_status):
        await on_status("stub", True)

    async def send(self, frame):
        pass

    async def close(self):
        pass


# --- App headless (Textual Pilot) -----------------------------------------

def test_app_renders_and_sends_chat(tmp_path):
    textual = pytest.importorskip("textual")  # noqa: F841
    p = _write_tokens(tmp_path, {
        "Emil": {"token": "tok-e", "role": "human", "groups": []},
        "beta": {"token": "tok-b", "role": "agent", "groups": ["workers"]},
    })

    sent = []

    class _StubAdapter:
        def __init__(self, identity):
            self.identity = identity

        async def run(self, on_frame, on_metadata, on_status):
            await on_metadata({"rules": "regula 1", "rules_hash": "abc",
                               "role": "human", "groups": []})
            await on_status("polaczono (stub)", True)
            await on_frame({"type": "chat", "from": "beta",
                            "text": "czesc Emil", "seq": 1})

        async def send(self, frame):
            sent.append(frame)

        async def close(self):
            pass

    identity, roster = load_human_identity(p)
    app = tui.AgentmachiApp(_StubAdapter(identity), roster)

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.connected is True
            assert ("beta", "czesc Emil") in app.history
            assert "regula 1" in app.rules_text
            inp = app.query_one("#message-input")
            assert inp.disabled is False
            inp.focus()
            await pilot.pause()
            assert len(app.query(".panel")) == 3  # dokladnie trzy panele
            # Input jest teraz wieloliniowy (MessageInput/TextArea): Enter
            # wstawia nowa linie, wysylka jest jawna pod Ctrl+S. Stary
            # kontrakt (jednoliniowy Input.value + Enter = wyslij) zostal
            # swiadomie zastapiony — patrz MessageInput w tui.py.
            inp.text = "czesc kanale"
            await pilot.press("ctrl+s")
            await pilot.pause()
            inp.text = "/groups beta head,admin"
            await pilot.press("ctrl+s")
            await pilot.pause()
    asyncio.run(scenario())
    assert sent == [
        {"type": "chat", "text": "czesc kanale"},
        {"type": "membership_set", "target": "beta",
         "groups": ["head", "admin"]}]


# -- statusy agentow w rosterze --------------------------------------------

def test_snapshot_carries_status_into_roster(tmp_path):
    p = _write_tokens(tmp_path, {
        "Emil": {"token": "tok-e", "role": "human", "groups": []},
        "beta": {"token": "tok-b", "role": "agent", "groups": ["workers"]},
    })
    identity, roster = load_human_identity(p)
    app = tui.AgentmachiApp(_StubQuietAdapter(identity), roster)

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.pause()
            await app.apply_hub_frame({
                "type": "participants_snapshot",
                "participants": [
                    {"nick": "beta", "role": "agent", "groups": ["workers"],
                     "connected": True,
                     "status": {"state": "working", "task_id": "t2"}}]})
            assert app.roster["beta"].status == "working"
            assert app.roster["beta"].status_note == "t2"
            # live status frame aktualizuje roster
            await app.apply_hub_frame({
                "type": "status", "from": "beta", "state": "review",
                "task_id": "t2", "seq": 50})
            assert app.roster["beta"].status == "review"
    asyncio.run(scenario())


# -- presence: lista online-only -------------------------------------------

def test_roster_shows_only_connected_and_presence_updates(tmp_path):
    p = _write_tokens(tmp_path, {
        "Emil": {"token": "tok-e", "role": "human", "groups": []},
        "beta": {"token": "tok-b", "role": "agent", "groups": ["workers"]},
    })
    identity, roster = load_human_identity(p)
    app = tui.AgentmachiApp(_StubQuietAdapter(identity), roster)

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.pause()
            # snapshot: beta offline -> NIE renderowana (lista jak na czacie)
            await app.apply_hub_frame({
                "type": "participants_snapshot",
                "participants": [
                    {"nick": "Emil", "role": "human", "groups": [],
                     "connected": True},
                    {"nick": "beta", "role": "agent", "groups": ["workers"],
                     "connected": False}]})
            rendered = str(app.query_one("#participants").render())
            assert "Emil" in rendered and "beta" not in rendered
            # presence online -> pojawia sie
            await app.apply_hub_frame({"type": "presence", "nick": "beta",
                                       "connected": True,
                                       "status": {"state": "idle"}})
            rendered = str(app.query_one("#participants").render())
            assert "beta" in rendered and "idle" in rendered
            # presence offline -> znika
            await app.apply_hub_frame({"type": "presence", "nick": "beta",
                                       "connected": False})
            rendered = str(app.query_one("#participants").render())
            assert "beta" not in rendered
    asyncio.run(scenario())


# --- listener-lock: TUI ponawia zamiast fail-closed (dogfood B3) ----------

def test_run_retries_until_listener_lock_released(session, tmp_path, monkeypatch):
    """Fotel czlowieka: zajety lock (inny klient na tym samym nicku) nie
    moze na stale ubic TUI — po zwolnieniu locka run() przechodzi do
    laczenia. Regresja z dogfoodu B3 (listener beta siedzial na 'human')."""
    monkeypatch.setattr(tui, "BACKOFF_START", 0.05)
    other = Session("localhost:8766", "Emil", base_dir=tmp_path)
    other.acquire_listener_lock()
    adapter = _adapter(session)

    def failing_connector(uri):
        raise OSError("hub niedostepny (test)")
    adapter._connector = failing_connector
    statuses = []

    async def on_status(msg, ok):
        statuses.append(msg)

    async def _noop(*a):
        pass

    async def scenario():
        task = asyncio.ensure_future(adapter.run(_noop, _noop, on_status))
        await asyncio.sleep(0.15)
        assert any("ponawiam" in s for s in statuses), statuses
        assert not any(s.startswith("laczenie") for s in statuses)
        other.release_listener_lock()
        await asyncio.sleep(0.3)
        assert any(s.startswith("laczenie z hubem") for s in statuses), statuses
        adapter._closing = True
        await asyncio.wait_for(task, timeout=5)
    asyncio.run(scenario())
