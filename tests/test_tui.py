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


def test_hello_error_carries_session_path(session):
    # Sciezke pliku sesji zna WYLACZNIE klient. Bez niej odmowa "kursor
    # z innego logu" jest slepym zaulkiem: czlowiek nie wie, ktory z
    # kilkunastu plikow w ~/.chat-sessions/ skasowac (2026-07-26).
    adapter = _adapter(session)
    ws = _FakeWs([{"type": "error", "text": "last_seq 269 > serwerowy 19"}])
    with pytest.raises(tui.FatalHubError) as exc:
        asyncio.run(adapter._hello(ws))
    assert str(session.path) in str(exc.value)


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
    roster jest cursor-coherent po kazdym hello, takze po restarcie.

    Do 2026-07-31 ta odpowiedz nie miala `last_seq`. Musiala go dostac, bo
    TUI fail-closes na jego braku — tak samo jak send.py. Precedens jest
    dokladnie ten sam: tests/test_send.py dostal te poprawke z komentarzem
    'ramka bez niego nie istnieje na drucie'. Serwer ZAWSZE wysyla `last_seq`
    w galezi `ok` (chat/server.py, protocol.make_frame przy budowie reply),
    wiec odpowiedz bez niego byla fikcja testowa, nie realnym wejsciem."""
    adapter = _adapter(session)
    order = []

    async def on_frame(frame):
        order.append(frame["type"])

    async def run():
        await adapter._apply_hello(
            {"type": "ok", "generation": 1, "last_seq": 11,
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
            # Input jest wieloliniowy (MessageInput/TextArea): Enter wstawia
            # nowa linie, wysylka jest jawna pod Ctrl+Enter.
            #
            # DRUGA zmiana kontraktu w tym miejscu, obie swiadome:
            #  1. jednoliniowy Input + Enter = wyslij  ->  TextArea + Ctrl+S,
            #     bo Enter wysylal wpol napisana wiadomosc przy zawinieciu,
            #  2. Ctrl+S -> Enter wysyla, Shift+Enter lamie linie (uklad jak
            #     w Claude Code, decyzja operatora z zywego TUI). Ctrl+S to
            #     historyczny XOFF i zamrazal terminal; Ctrl+Enter okazal sie
            #     w Windows Terminal NIEODROZNIALNY od Entera. Szczegoly
            #     kodowania klawiszy — BINDINGS w tui.py.
            inp.text = "czesc kanale"
            await pilot.press("enter")
            await pilot.pause()
            inp.text = "/groups beta head,admin"
            await pilot.press("enter")
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
                     "status": {"state": "working", "subject": "t2"}}]})
            assert app.roster["beta"].status == "working"
            assert app.roster["beta"].status_note == "t2"
            # live status frame aktualizuje roster; subject -> status_note (branch live)
            await app.apply_hub_frame({
                "type": "status", "from": "beta", "state": "review",
                "subject": "audyt", "seq": 50})
            assert app.roster["beta"].status == "review"
            assert app.roster["beta"].status_note == "audyt"
    asyncio.run(scenario())


def test_TUI_nie_gubi_note_gdy_jest_takze_subject(tmp_path):
    """Zgloszone przez OPERATORA przy TUI 2026-08-13: "to, co macie na
    boardzie, powinno byc 1:1 z tym, co widze".

    Bylo `subject or note` — czyli TUI brala JEDNO z dwoch pol, a `board`
    (send.py `_opis_statusu`) dokleja OBA. Agent deklarowal trzy pola, board
    pokazywal trzy, czlowiek widzial dwa i nie wiedzial, ze trzeciego nie ma.

    Zmierzone na zywym pokoju, na prawdziwych statusach:
      board:  idle — poligon zamkniety — czekam na sonde Dowodu B
      TUI:    idle (poligon zamkniety)
    Ginelo `note` — wolny tekst, JEDYNE miejsce, w ktorym agent mowi
    czlowiekowi cos, czego nie da sie zakodowac w stanie. Gubione akurat
    u tego odbiorcy, dla ktorego ma najwieksza wartosc: agent moze sobie
    doczytac `board`, czlowiek ma tylko TUI."""
    p = _write_tokens(tmp_path, {
        "Emil": {"token": "tok-e", "role": "human", "groups": []},
        "beta": {"token": "tok-b", "role": "agent", "groups": []},
    })
    identity, roster = load_human_identity(p)
    app = tui.AgentmachiApp(_StubQuietAdapter(identity), roster)

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.pause()
            await app.apply_hub_frame({
                "type": "participants_snapshot",
                "participants": [
                    {"nick": "beta", "role": "agent", "groups": [],
                     "connected": True,
                     "status": {"state": "idle", "subject": "poligon",
                                "note": "czekam na sonde"}}]})
            assert "poligon" in app.roster["beta"].status_note
            assert "czekam na sonde" in app.roster["beta"].status_note, \
                "note zginelo przy obecnym subject — czlowiek traci zdanie, " \
                "ktorego nie ma gdzie indziej"
            # Ta sama regula na ramce ZYWEJ, nie tylko w snapshocie.
            await app.apply_hub_frame({
                "type": "status", "from": "beta", "state": "working",
                "subject": "filtr", "note": "blokuje mnie brak tokenu",
                "seq": 50})
            assert "filtr" in app.roster["beta"].status_note
            assert "blokuje mnie brak tokenu" in app.roster["beta"].status_note
            # Kazde z pol z osobna dalej dziala i NIE zostawia separatora.
            await app.apply_hub_frame({
                "type": "status", "from": "beta", "state": "review",
                "note": "sam note", "seq": 51})
            assert app.roster["beta"].status_note == "sam note"
            await app.apply_hub_frame({
                "type": "status", "from": "beta", "state": "review",
                "subject": "sam subject", "seq": 52})
            assert app.roster["beta"].status_note == "sam subject"
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
            # presence online -> pojawia sie; subject renderowany (branch presence)
            await app.apply_hub_frame({"type": "presence", "nick": "beta",
                                       "connected": True,
                                       "status": {"state": "working",
                                                  "subject": "audyt"}})
            rendered = str(app.query_one("#participants").render())
            assert "beta" in rendered and "working" in rendered
            assert "audyt" in rendered
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
        # Zmienil sie JEZYK statusow, nie kontrakt.
        assert any("retrying" in s for s in statuses), statuses
        assert not any(s.startswith("connecting") for s in statuses)
        other.release_listener_lock()
        await asyncio.sleep(0.3)
        assert any(s.startswith("connecting to hub") for s in statuses), statuses
        adapter._closing = True
        await asyncio.wait_for(task, timeout=5)
    asyncio.run(scenario())


# --- historia wysylek (strzalki) ------------------------------------------

def test_history_pick_pusta_historia_nie_dotyka_pola():
    """None znaczy 'nie ma czego podstawic'. Gdyby zwracalo "", pierwsza
    strzalka w gore na swiezym TUI czyscilaby to, co wlasnie piszesz."""
    assert tui.history_pick([], 0, -1) == (0, None)
    assert tui.history_pick([], 0, 1) == (0, None)


def test_history_pick_w_gore_zatrzymuje_sie_na_najstarszym():
    h = ["a", "b", "c"]
    pos, tekst = tui.history_pick(h, 3, -1)
    assert (pos, tekst) == (2, "c")
    pos, tekst = tui.history_pick(h, pos, -1)
    assert (pos, tekst) == (1, "b")
    pos, tekst = tui.history_pick(h, pos, -1)
    assert (pos, tekst) == (0, "a")
    # NIE zawija: zawijanie gubi wpis, ktorego wlasnie szukasz
    assert tui.history_pick(h, pos, -1) == (0, "a")


def test_history_pick_w_dol_ODDAJE_SZKIC_a_nie_pustke():
    """KONTRAKT ZMIENIONY 2026-08-13 i stary byl bledny — dowod jest
    zgloszeniem operatora z zywego TUI, nie przekonaniem:

      "jak pisze aktualna wiadomosc i klikne strzalke w dol, to mi ja czysci
       w historii jako wartosc przyszla, a przyszlej nie ma, wiec czysci mi
       okno"

    Poprzedni test utrwalal `(2, "")` i byl zielony przez caly czas, gdy blad
    istnial — bo `""` czytalo sie jako "pusty szkic", a znaczylo "skasuj to,
    co jest w polu". To sa dwie rozne rzeczy dokladnie wtedy, gdy w polu
    cos JEST: szkic to tresc, ktorej jeszcze nie ma w historii, wiec zadne
    "w dol" jej nie odzyska.

    Teraz `None` znaczy jedno: nie ma czego podstawic Z HISTORII. Co zrobic
    z polem, wie widget, ktory trzyma szkic — patrz test nizej."""
    h = ["a", "b"]
    assert tui.history_pick(h, 0, 1) == (1, "b")
    assert tui.history_pick(h, 1, 1) == (2, None), \
        "powrot z historii do szkicu nie moze podstawiac pustki"
    assert tui.history_pick(h, 2, 1) == (2, None), \
        "strzalka w dol w samym szkicu nie ma prawa dotknac pola"


def test_MessageInput_strzalka_w_dol_NIE_KASUJE_pisanej_wiadomosci():
    """Zgloszenie operatora, odtworzone na widgecie: piszesz i naciskasz dol.

    Sprawdzamy tez droge powrotna, ktora jest ta sama usterka od drugiej
    strony: gora-gora-dol musi oddac to, co pisales, a nie pustke. Bez
    zapamietania szkicu przy WEJSCIU w historie draft ginie tak samo, tylko
    ciszej — bo wtedy czlowiek sam nacisnal gore i latwiej uwierzy, ze tak
    ma byc."""
    inp = tui.MessageInput()
    inp.remember("stara wiadomosc")

    # 1. Piszesz swiezy szkic i naciskasz DOL. Pole ma zostac nietkniete.
    inp.text = "wlasnie to pisze"
    inp._history_step(1)
    assert inp.text == "wlasnie to pisze", \
        "strzalka w dol skasowala wiadomosc, ktorej nikt nie wyslal"

    # 2. GORA wchodzi w historie, DOL wraca do TEGO SAMEGO szkicu.
    inp._history_step(-1)
    assert inp.text == "stara wiadomosc"
    inp._history_step(1)
    assert inp.text == "wlasnie to pisze", \
        "powrot z historii oddal pustke zamiast szkicu"

    # 3. Po wyslaniu szkic przestaje istniec — dol niczego nie wskrzesza.
    inp.remember("wlasnie to pisze")
    inp.text = ""
    inp._history_step(1)
    assert inp.text == ""


def test_message_input_remember_nie_dubluje_powtorzen():
    inp = tui.MessageInput()
    inp.remember("/stop")
    inp.remember("/stop")
    inp.remember("  /stop  ")
    assert inp._history == ["/stop"]
    inp.remember("czesc")
    assert inp._history == ["/stop", "czesc"]


def test_message_input_strzalka_w_gore_podstawia_ostatnia_wysylke():
    inp = tui.MessageInput()
    inp.remember("pierwsza")
    inp.remember("druga")
    inp.action_history_prev()
    assert inp.text == "druga"
    inp.action_history_prev()
    assert inp.text == "pierwsza"


def test_message_input_strzalka_nie_zjada_ruchu_w_wieloliniowym():
    """Powod, dla ktorego ten input jest TextArea, to wklejanie i komponowanie
    w wielu liniach. Historia MUSI wchodzic wylacznie z brzegu — inaczej
    poprawka w drugiej linii wklejonego bloku przestaje byc mozliwa."""
    inp = tui.MessageInput()
    inp.remember("stara")
    inp.text = "linia1\nlinia2"
    inp.move_cursor((1, 0))
    inp.action_history_prev()          # ma ruszyc KURSOR, nie podstawic
    assert inp.text == "linia1\nlinia2"
    assert inp.cursor_location[0] == 0
    inp.action_history_prev()          # z pierwszej linii juz historia
    assert inp.text == "stara"


# --- komendy lokalne operatora --------------------------------------------

def test_parse_stop_i_reset_sa_lokalne():
    """Zatrzymanie huba NIE jest ramka protokolu — to domena czlowieka przy
    maszynie. Gdyby szlo drutem, kazdy uczestnik moglby ubic pokoj."""
    assert parse_user_input("/stop") == {"type": "local", "action": "stop"}
    # Zmienila sie NAZWA komendy (/reset-kursor -> /reset-cursor), nie
    # kontrakt: reset kursora nadal jest akcja LOKALNA, nie ramka.
    assert parse_user_input("/reset-cursor") == {"type": "local",
                                                 "action": "reset-cursor"}


@pytest.mark.parametrize("bad", ["/stop teraz", "/reset-cursor x"])
def test_parse_lokalne_odrzucaja_argumenty(bad):
    with pytest.raises(TuiError):
        parse_user_input(bad)


def test_wszystkie_klawisze_wysylki_dzialaja_a_enter_zostaje_nowa_linia():
    """Regresja zgloszona z ZYWEGO TUI: Ctrl+Enter nie wysylal wcale.

    Binding nazywal sie `ctrl+enter` i dzialal wylacznie w terminalach
    z protokolem kitty/CSI-u. Reszta wysyla dla tego skrotu goly LF, ktory
    w Textualu jest ODREBNYM klawiszem `ctrl+j` — nie wpadal wiec ani
    w zaden binding, ani w insert TextArea. Po prostu ginal.

    Test jest tani i rozstrzygajacy dokladnie dlatego, ze pilot wstrzykuje
    klawisz z pominieciem terminala: sprawdza KONTRAKT widgetu, a nie
    zdolnosci emulatora, na ktorym akurat chodzi suita."""
    from textual.app import App, ComposeResult

    class _Probe(App):
        def __init__(self):
            super().__init__()
            self.wyslane = []

        def compose(self) -> ComposeResult:
            yield tui.MessageInput(id="i")

        def on_message_input_submitted(self, event):
            self.wyslane.append(event.text)

    async def scenario():
        app = _Probe()
        async with app.run_test() as pilot:
            inp = app.query_one("#i", tui.MessageInput)
            inp.focus()
            # ENTER WYSYLA. Bez priority=True binding nie odpala wcale —
            # `_on_key` TextArei polyka Enter przed rozwiazaniem bindingow
            # i zamiast wysylki dostajesz "\n" w polu.
            inp.text = "tresc"
            przed = len(app.wyslane)
            await pilot.press("enter")
            assert len(app.wyslane) > przed, "Enter NIE wyslal"
            assert "\n" not in inp.text, "Enter wstawil znak zamiast wyslac"

            # NOWA LINIA: jeden klawisz uzytkownika (Shift+Enter), trzy nazwy.
            # `ctrl+j` to droga, ktora realnie dziala w Windows Terminal/WSL;
            # `shift+enter` — terminale kitty; `ctrl+o` — bezpiecznik dla
            # terminali, ktore Shift+Enter wysylaja identycznie jak Enter.
            for klawisz in ("ctrl+j", "shift+enter", "ctrl+o"):
                inp.text = "tresc"
                przed = len(app.wyslane)
                await pilot.press(klawisz)
                assert len(app.wyslane) == przed, f"{klawisz} wyslal zamiast lamac"
                assert "\n" in inp.text, f"{klawisz} NIE zlamal linii"

            # Ctrl+S usuniety na zyczenie operatora: historyczny XOFF, przy
            # wlaczonym flow control zamrazal terminal. Gdyby ktos przywrocil
            # go "dla wygody", ten test padnie.
            inp.text = "tresc"
            przed = len(app.wyslane)
            await pilot.press("ctrl+s")
            assert len(app.wyslane) == przed, "Ctrl+S wysyla, a mial zniknac"
    asyncio.run(scenario())


def test_ctrl_q_wychodzi_takze_gdy_fokus_jest_w_inpucie():
    """Fokus siedzi w TextArea przez wieksza czesc sesji, a widget ma
    pierwszenstwo przed App. Bez `priority=True` skrot wyjscia dzialalby
    tylko wtedy, gdy akurat NIE piszesz — czyli prawie nigdy."""
    wiazania = {b.key: b for b in tui.AgentmachiApp.BINDINGS}
    assert "ctrl+q" in wiazania, "brak wyjscia pod Ctrl+Q"
    assert wiazania["ctrl+q"].action == "quit"
    assert wiazania["ctrl+q"].priority is True, \
        "bez priority TextArea polknie Ctrl+Q, gdy kursor jest w inpucie"


def test_parse_kill_wymaga_nazwy_pokoju():
    """`/kill` kasuje historie NA ZAWSZE, wiec potwierdzeniem jest NAZWA —
    ta sama zasada co `--yes-delete` w CLI, z tego samego powodu: flage
    dopisuje sie odruchowo, a nazwe trzeba przeczytac."""
    assert parse_user_input("/kill sklep") == {
        "type": "local", "action": "kill", "target": "sklep"}


@pytest.mark.parametrize("bad", ["/kill", "/kill   ", "/kill a b"])
def test_parse_kill_bez_nazwy_odrzucony(bad):
    with pytest.raises(TuiError):
        parse_user_input(bad)


def test_tui_importuje_z_cli_tylko_istniejace_funkcje():
    """`/stop` i `/kill` siegaja po agentmachi.cli WEWNATRZ metod, wiec zaden
    test nie wykonywal tego importu. Zmiana nazwy ktorejkolwiek funkcji
    przechodzila cala suite i wywalala sie dopiero, gdy czlowiek wpisal
    `/kill <pokoj>` na zywym pokoju — przy najbardziej NIEODWRACALNEJ
    operacji w produkcie.

    Test czyta, co tui.py NAPRAWDE importuje (AST), zamiast powtarzac liste
    z pamieci — inaczej rozjechalby sie przy dodaniu kolejnej funkcji."""
    import ast
    from pathlib import Path

    from agentmachi import cli

    zrodlo = Path(tui.__file__).read_text()
    nazwy = set()
    for wezel in ast.walk(ast.parse(zrodlo)):
        if (isinstance(wezel, ast.ImportFrom)
                and wezel.module == "agentmachi.cli"):
            nazwy |= {alias.name for alias in wezel.names}
    # POZYTYWNIE: sam brak trafien dalby green takze po skasowaniu importow.
    assert nazwy, "tui.py nie importuje juz nic z agentmachi.cli — sprawdz, " \
                  "czy to zamierzone, i zaktualizuj ten test"
    for nazwa in sorted(nazwy):
        assert hasattr(cli, nazwa), (
            f"tui.py importuje agentmachi.cli.{nazwa}, ktorego NIE MA — "
            f"`/stop` albo `/kill` wywali sie ImportError u czlowieka")


# --- regresje z przegladu klienta 2026-07-31 ------------------------------

def test_resync_dostarcza_rozmowe_a_nie_tylko_stan(session):
    """Serwer wysyla w `resync_required` pole `conversation` (do 200 ramek)
    — `send.py` i `node.py` je odtwarzaja, TUI NIE czytalo go wcale.

    Skutek: po kompakcji operator startowal TUI i panel czatu byl PUSTY,
    mimo ze rozmowa przyszla drutem. Ten sam objaw, ktory send.py juz raz
    naprawial ("agent wchodzil na kanal, na ktorym nic sie nie wydarzylo").

    Ramki `conversation` maja seq NIZSZE niz snapshot_seq, wiec ida SUROWO,
    nie przez apply_resumable_frame — inaczej dedup by je wyciol."""
    adapter = _adapter(session)
    frames = []

    async def on_frame(frame):
        frames.append(frame)

    async def run():
        await adapter._apply_hello(
            {"type": "resync_required", "snapshot_seq": 9,
             "state": {"registry": {}},
             "conversation": [
                 {"type": "chat", "from": "beta", "text": "stara rozmowa",
                  "seq": 3}]},
            on_frame, lambda m: None)
    asyncio.run(run())
    teksty = [f.get("text") for f in frames]
    assert "stara rozmowa" in teksty, \
        f"TUI zgubilo rozmowe z resync; dostal: {[f.get('type') for f in frames]}"


def test_ok_przesuwa_kursor_na_autorytatywny_last_seq(session):
    """Serwer wycina z backlogu NA DRUCIE ramki `hello` (54% backlogu
    w pomiarze B5), ale `last_seq` w odpowiedzi to prawdziwy koniec logu.
    Klient ufajacy tylko ramkom zostaje z kursorem sprzed filtra i przy
    kazdym reconnekcie zjezdza na sciezke resync.

    send.py ma to naprawione i pokryte trzema testami; TUI nie czytalo
    `last_seq` w ogole."""
    adapter = _adapter(session)

    async def run():
        await adapter._apply_hello(
            {"type": "ok", "backlog": [{"type": "chat", "seq": 2, "text": "x"}],
             "last_seq": 42},
            lambda f: None, lambda m: None)
    asyncio.run(run())
    assert session.last_applied_seq == 42, \
        f"kursor stanal na ramce z drutu ({session.last_applied_seq}), " \
        f"nie na autorytatywnym koncu logu"


def test_takeover_i_nieznany_typ_nie_gina_po_cichu(tmp_path):
    """`takeover` jest pushowany NA ZYWO WYLACZNIE do ludzi — bo to oni
    reaguja na widmo (restart, ubicie klienta). Jedyny adresat, do ktorego
    serwer celuje, zjadal go bez sladu: apply_hub_frame nie mial ani galezi
    `takeover`, ani `else`.

    `else` jest wazniejszy od samej galezi: bez niego NASTEPNY nowy typ
    OUTBOUND zniknie dokladnie tak samo."""
    p = _write_tokens(tmp_path, {
        "Emil": {"token": "tok-e", "role": "human", "groups": []}})
    identity, roster = load_human_identity(p)

    class _Stub:
        def __init__(self):
            self.identity = identity

        async def run(self, on_frame, on_metadata, on_status):
            await on_status("stub", True)

        async def close(self):
            pass

    app = tui.AgentmachiApp(_Stub(), roster)

    async def scenario():
        async with app.run_test():
            await app.apply_hub_frame({
                "type": "takeover", "from": "server", "nick": "beta",
                "generation": 2, "previous_generation": 1,
                "text": "beta: nowe polaczenie wyparlo poprzednie"})
            await app.apply_hub_frame({"type": "cos-nowego", "from": "server"})
    asyncio.run(scenario())
    log = " ".join(f"{a} {b}" for a, b in app.history)
    assert "wyparlo" in log, "takeover zniknal bez sladu"
    assert "cos-nowego" in log, "nieznany typ ramki zniknal bez sladu"
