import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

import send
from chat.client_session import Session

REPO = Path(__file__).resolve().parent.parent


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("localhost", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# --- jednostkowe: _print_message (kontrakt z fix-packa 842b71a) -----------

def test_print_message_malformed_frame_is_visible_and_next_frame_still_prints(
        capsys):
    send._print_message("{to nie jest json")
    send._print_message(json.dumps({"from": "beta", "text": "dalej dziala"}))

    assert capsys.readouterr().out.splitlines() == [
        "{to nie jest json",
        "beta: dalej dziala",
    ]


def test_print_message_valid_json_scalar_does_not_crash(capsys):
    send._print_message("null")
    assert capsys.readouterr().out.strip() == "null"


# --- jednostkowe: apply_frame (kursor-po-apply, dedup seq/activation) -----

@pytest.fixture
def session(tmp_path):
    return Session("localhost:9999", "beta", base_dir=tmp_path)


def test_apply_frame_advances_cursor_after_apply(session, capsys):
    assert send.apply_frame(session, {"from": "a", "text": "x", "seq": 1})
    assert session.last_applied_seq == 1
    assert "a: x" in capsys.readouterr().out


def test_apply_frame_suppresses_duplicate_seq(session, capsys):
    send.apply_frame(session, {"from": "a", "text": "x", "seq": 3})
    capsys.readouterr()
    assert send.apply_frame(session, {"from": "a", "text": "x", "seq": 3}) is False
    assert send.apply_frame(session, {"from": "a", "text": "y", "seq": 2}) is False
    assert capsys.readouterr().out == ""


def test_apply_frame_without_seq_prints_but_keeps_cursor(session, capsys):
    send.apply_frame(session, {"from": "a", "text": "bez seq"})
    assert session.last_applied_seq == 0
    assert "bez seq" in capsys.readouterr().out


def test_apply_frame_duplicate_activation_suppressed_cursor_moves(
        session, capsys):
    # (A3) activation_id to GENERYCZNY dedup wybudzen po stronie klienta, nie
    # scheduler — reprezentowany dowolna zywa ramka z activation_id (tu chat).
    offer = {"from": "server", "type": "chat", "seq": 13,
             "activation_id": "beta:13", "text": "@beta obudz sie"}
    assert send.apply_frame(session, offer) is True
    capsys.readouterr()
    retransmit = dict(offer, seq=14)  # retransmisja tej samej proby
    assert send.apply_frame(session, retransmit) is False
    assert session.last_applied_seq == 14  # suppress, ale kursor idzie
    assert capsys.readouterr().out == ""


def test_apply_frame_crash_between_apply_and_cursor_save(session, monkeypatch):
    """Crash w apply (print) NIE przesuwa kursora — ramka wroci po restarcie
    (at-least-once), nigdy nie zginie."""
    def boom(_):
        raise RuntimeError("crash w apply")
    monkeypatch.setattr(send, "_print_event", boom)
    with pytest.raises(RuntimeError):
        send.apply_frame(session, {"from": "a", "text": "x", "seq": 5})
    assert session.last_applied_seq == 0


def test_apply_frame_crash_before_mark_does_not_lose_activation(
        session, monkeypatch, capsys):
    """Review-changes codexa (1): crash w apply ramki z activation_id NIE
    zapisuje aktywacji — retry MUSI ja ponownie zastosowac, nie suppress."""
    offer = {"from": "server", "type": "chat", "seq": 13,
             "activation_id": "beta:13", "text": "@beta obudz sie"}
    def boom(_):
        raise RuntimeError("crash w apply")
    monkeypatch.setattr(send, "_print_event", boom)
    with pytest.raises(RuntimeError):
        send.apply_frame(session, offer)
    assert session.is_activation_applied("beta:13") is False
    assert session.last_applied_seq == 0
    monkeypatch.undo()
    assert send.apply_frame(session, offer) is True  # retry APLIKUJE
    assert "obudz sie" in capsys.readouterr().out
    assert session.is_activation_applied("beta:13") is True
    assert session.last_applied_seq == 13


def test_apply_hello_resync_emits_state_before_cursor(session, capsys):
    """Review-changes codexa (2): resync APLIKUJE (emituje) stan, dopiero
    potem przesuwa kursor — advance bez emisji = utrata stanu."""
    send._apply_hello_reply(session, {"type": "resync_required",
                                      "snapshot_seq": 42,
                                      "state": {"queue": {"tasks": [1]}}})
    out = capsys.readouterr().out
    assert "resync_state" in out and '"tasks": [1]' in out
    assert session.last_applied_seq == 42


def test_apply_hello_resync_without_state_fails_closed(session, capsys):
    """Finisz codexa (1): resync BEZ dict state = SessionError, kursor STOI —
    advance bez zastosowanego stanu deklarowalby posiadanie utraconego."""
    from chat.client_session import SessionError
    with pytest.raises(SessionError):
        send._apply_hello_reply(session, {"type": "resync_required",
                                          "snapshot_seq": 42})
    assert session.last_applied_seq == 0


def test_hello_ok_emits_session_metadata_before_backlog(session, capsys):
    """Finisz codexa (2): rules/role/groups/generation emitowane jako JEDNA
    ramka session_metadata PRZED backlogiem."""
    # C2: `last_seq` dopisane do ramki — nie zmiana intencji testu (broni
    # KOLEJNOSCI emisji), tylko urealnienie wejscia. Serwer w galezi `ok`
    # ZAWSZE niesie last_seq (chat/server.py, reply "ok"), wiec ramka bez
    # niego nie istnieje na drucie; od C2 klient fail-closes na jej brak,
    # bo to jedyny autorytatywny koniec logu.
    send._apply_hello_reply(session, {
        "type": "ok", "generation": 2, "role": "agent",
        "groups": ["workers"], "rules": "tekst", "rules_hash": "abc",
        "backlog": [{"from": "a", "text": "x", "seq": 1}], "last_seq": 1})
    lines = capsys.readouterr().out.splitlines()
    assert "session_metadata" in lines[0] and '"abc"' in lines[0]
    assert lines[1] == "a: x"
    assert session.last_applied_seq == 1


def test_hello_ok_without_metadata_emits_nothing_extra(session, capsys):
    # C2: last_seq=0 (pusty log) — patrz komentarz w tescie wyzej.
    send._apply_hello_reply(session, {"type": "ok", "backlog": [],
                                      "last_seq": 0})
    assert capsys.readouterr().out == ""


def test_token_is_optional_in_open_mode(monkeypatch):
    """B6: brak CHAT_TOKEN NIE jest juz bledem — hub w trybie otwartym
    wpuszcza agenta bez sekretu. Wymuszanie tokenu po stronie klienta
    blokowalo dokladnie to, na co serwer pozwala (zlapane w dogfoodzie:
    agent na VPS nie mogl wejsc mimo otwartego huba)."""
    monkeypatch.delenv("CHAT_TOKEN", raising=False)
    assert send._require_token() == ""
    monkeypatch.setenv("CHAT_TOKEN", "sekret")
    assert send._require_token() == "sekret"


# --- hub_id_from_url (Task 1: CHAT_URL / zdalne hub-y) --------------------

def test_hub_id_from_url():
    import send
    assert send.hub_id_from_url("ws://localhost:8766") == "localhost:8766"
    assert send.hub_id_from_url("wss://hub.tailnet.ts.net:8766") == \
        "hub.tailnet.ts.net:8766"
    # default bez CHAT_URL == dotychczasowy HUB_ID -> kursory przezywaja
    assert send.hub_id_from_url(f"ws://localhost:{send.PORT}") == send.HUB_ID
    # porty domyslne schematu (tunel publiczny nie niesie :443 jawnie)
    assert send.hub_id_from_url("wss://hub.trycloudflare.com") == \
        "hub.trycloudflare.com:443"
    assert send.hub_id_from_url("ws://hub.local") == "hub.local:80"
    with pytest.raises(ValueError):
        send.hub_id_from_url("ws://host:abc")   # zly port = czytelny ValueError


# --- integracyjny smoke gate (wsad b2): kill / offline / restart ----------

def test_listener_smoke_gate_kill_offline_restart(tmp_path):
    """listener -> msg1 -> SIGKILL -> msg2 offline -> restart -> msg2
    dokladnie raz, bez powtorki msg1, kursor monotoniczny na dysku."""
    from chat.server import ChatServer

    port = _free_port()
    tokens = {"beta": {"token": "tok-b", "role": "agent", "groups": []},
              "alfa": {"token": "tok-a", "role": "agent", "groups": []}}
    env = {**os.environ, "CHAT_PORT": str(port), "CHAT_NICK": "beta",
           "CHAT_TOKEN": "tok-b", "CHAT_SESSION_DIR": str(tmp_path / "sess"),
           "PYTHONUNBUFFERED": "1"}

    def start_listener():
        return subprocess.Popen(
            [sys.executable, str(REPO / "send.py"), "--listen"],
            env=env, cwd=REPO, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True)

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens=tokens,
                         port=port)
        await srv.start()

        async def alfa_chat(text):
            import websockets
            async with websockets.connect(f"ws://localhost:{port}") as ws:
                await ws.send(json.dumps(
                    {"type": "hello", "from": "alfa", "instance_id": "i-a",
                     "token": "tok-a", "ts": 1.0, "last_seq": 0}))
                await ws.recv()
                await ws.send(json.dumps({"type": "chat", "from": "alfa",
                                          "ts": 2.0, "text": f"@beta {text}"}))

        listener = start_listener()
        try:
            await asyncio.sleep(1.5)  # hello + backlog
            await alfa_chat("msg1")
            await asyncio.sleep(1.0)
            listener.send_signal(signal.SIGKILL)  # twardy kill
            listener.wait(timeout=5)
            out1 = listener.stdout.read()
            assert "msg1" in out1

            await alfa_chat("msg2")  # listener offline
            await asyncio.sleep(0.5)

            listener2 = start_listener()
            try:
                await asyncio.sleep(2.0)
                listener2.terminate()
                listener2.wait(timeout=5)
                out2 = listener2.stdout.read()
            finally:
                if listener2.poll() is None:
                    listener2.kill()
            assert out2.count("msg2") == 1   # dokladnie raz
            assert "msg1" not in out2        # kursor nie cofnal sie
            state = json.loads(
                next((tmp_path / "sess").glob("beta-*.json")).read_text())
            assert state["last_applied_seq"] >= 1
        finally:
            if listener.poll() is None:
                listener.kill()
            await srv.stop()

    asyncio.run(scenario())


def test_second_listener_rejected_lock(tmp_path):
    """Dokladnie jeden listener per hub+nick: drugi proces exit code 3."""
    port = _free_port()  # hub nie musi zyc — lock lapiemy przed connect
    env = {**os.environ, "CHAT_PORT": str(port), "CHAT_NICK": "beta",
           "CHAT_TOKEN": "tok-b", "CHAT_SESSION_DIR": str(tmp_path / "sess"),
           "PYTHONUNBUFFERED": "1"}
    p1 = subprocess.Popen([sys.executable, str(REPO / "send.py"), "--listen"],
                          env=env, cwd=REPO, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL)
    try:
        time.sleep(1.0)  # p1 trzyma lock (i probuje reconnectowac do huba)
        p2 = subprocess.run(
            [sys.executable, str(REPO / "send.py"), "--listen"],
            env=env, cwd=REPO, capture_output=True, text=True, timeout=10)
        assert p2.returncode == 3
        assert "listener" in p2.stderr
    finally:
        p1.kill()


def test_corrupt_session_fail_closed_exit_code(tmp_path):
    """Uszkodzony plik sesji: exit 4 z instrukcja naprawy, zero resetu."""
    sess_dir = tmp_path / "sess"
    s = Session("localhost:7777", "beta", base_dir=sess_dir)
    s.path.write_text("{urwane")
    env = {**os.environ, "CHAT_PORT": "7777", "CHAT_NICK": "beta",
           "CHAT_TOKEN": "tok-b", "CHAT_SESSION_DIR": str(sess_dir)}
    p = subprocess.run([sys.executable, str(REPO / "send.py"), "--listen"],
                       env=env, cwd=REPO, capture_output=True, text=True,
                       timeout=10)
    assert p.returncode == 4
    assert "skasuj" in p.stderr


def test_oneshot_frame_uses_session_identity(tmp_path, monkeypatch):
    """Regresja bugu z testu skilla: one-shot MUSI współdzielić instance_id
    z listenerem (zero takeoveru/ping-ponga generacji gubiącego lease)."""
    from chat.server import ChatServer

    port = _free_port()
    tokens = {"beta": {"token": "tok-b", "role": "agent", "groups": []}}
    monkeypatch.setenv("CHAT_TOKEN", "tok-b")
    monkeypatch.setenv("CHAT_SESSION_DIR", str(tmp_path / "sess"))
    monkeypatch.setattr(send, "URI", f"ws://localhost:{port}")
    monkeypatch.setattr(send, "HUB_ID", f"localhost:{port}")

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens=tokens,
                         port=port)
        await srv.start()
        try:
            listener_session = send._session("beta")
            # "listener" hello ustala generacje 1 dla instance sesji
            import websockets
            async with websockets.connect(f"ws://localhost:{port}") as ws:
                await ws.send(json.dumps({
                    "type": "hello", "from": "beta", "ts": 0.0,
                    "instance_id": listener_session.instance_id,
                    "token": "tok-b", "last_seq": 0}))
                await ws.recv()
                gen_before = srv.registry.generation_of("beta")
                # one-shot status: TA SAMA tozsamosc -> zero bumpa
                reply = await send.oneshot_frame(
                    "beta", {"type": "status", "state": "idle"})
                assert reply is None  # status bez ACK
                assert srv.registry.generation_of("beta") == gen_before
        finally:
            await srv.stop()

    asyncio.run(scenario())


# --- F10 (B5): klient nie moze gubic tego, co hub obiecuje --------------
# Audyt docs znalazl bug w KODZIE: hub wysyla w hello `participants` (board,
# B4) i `howto` (instrukcja obslugi, F5), a listener wyrzucal je do kosza —
# agent uzywajacy jedynej udokumentowanej drogi wejscia nie dostawal ich
# wcale. Obietnica protokolu musi docierac do odbiorcy.

def test_session_metadata_carries_board_and_howto():
    import send
    printed = []
    original = send._print_event
    send._print_event = printed.append
    try:
        send._emit_session_metadata({
            "type": "ok", "rules": "zasady", "role": "agent",
            "groups": ["workers"], "generation": 3,
            "participants": [{"nick": "w1", "connected": True,
                              "status": {"state": "working"}}],
            "howto": "jak sie poruszac po kanale",
        })
    finally:
        send._print_event = original
    meta = printed[0]
    assert meta["type"] == "session_metadata"
    assert meta["howto"] == "jak sie poruszac po kanale"
    assert meta["participants"][0]["nick"] == "w1"
    assert meta["rules"] == "zasady" and meta["generation"] == 3


def test_resync_reply_also_carries_conversation():
    """Po kompakcji rozmowa wraca w `conversation` (F1) — listener ma ja
    pokazac, inaczej wracajacy agent widzi kanal, na ktorym 'nic sie nie
    wydarzylo'."""
    import send
    from chat.client_session import Session
    import tempfile
    printed = []
    original = send._print_event
    send._print_event = printed.append
    try:
        session = Session("h:1", "w2", base_dir=tempfile.mkdtemp())
        send._apply_hello_reply(session, {
            "type": "resync_required", "snapshot_seq": 5,
            "state": {"registry": {}},
            "conversation": [{"type": "chat", "from": "w1", "seq": 3,
                              "text": "ustalenie sprzed snapshotu"}],
        })
    finally:
        send._print_event = original
    teksty = [e.get("text") for e in printed if e.get("type") == "chat"]
    assert "ustalenie sprzed snapshotu" in teksty


# --- wejscie bez nicka: cala droga klienta (dogfood worker4) --------------
# Serwer od B6 przyjmuje hello bez 'from' i nadaje nick, ale KLIENT padal
# lokalnie na _session('') -> SessionError('invalid nick: '') ZANIM hello
# wyszlo w drut. Bug siedzial w POPRZEK warstw: strona serwera dzialala,
# kliencka byla martwa, i zaden unit tego nie lapal, bo zaden nie odpalal
# calej drogi wejscia. Agent na VPS (git clone HEAD) padal tak przy kazdym
# nickless wejsciu.

def test_boot_identity_is_ephemeral_not_a_session():
    """_BootIdentity zyje TYLKO na pierwsze hello: duck-typuje to, czego
    do_hello potrzebuje (instance_id + last_applied_seq=0), ale NIE jest
    Session — nie ma listener-locka ani kursora. Dlatego po nadaniu nicka
    listen przechodzi na prawdziwa Session, a gdy hub nicka nie nada,
    fail-closes zamiast udawac sesje."""
    boot = send._BootIdentity()
    assert isinstance(boot.instance_id, str) and boot.instance_id
    assert boot.last_applied_seq == 0
    assert not hasattr(boot, "acquire_listener_lock")
    assert not hasattr(boot, "release_listener_lock")


def test_nickless_listen_enters_open_hub_and_gets_assigned_nick(
        tmp_path, monkeypatch, capsys):
    """REGRES glowny: 'agentmachi listen' BEZ nicka na otwartym hubie MUSI
    wejsc — hub nadaje nick, klient go przyjmuje i zaklada pod nim sesje.
    Dowod calej drogi: powstaje plik sesji nazwany NADANYM nickiem (z pustym
    nickiem Session by rzucila i pliku by nie bylo) + stderr niesie nadanie."""
    from chat.server import ChatServer
    port = _free_port()
    monkeypatch.delenv("CHAT_TOKEN", raising=False)   # open mode: bez sekretu
    monkeypatch.delenv("CHAT_NICK", raising=False)
    monkeypatch.setenv("CHAT_SESSION_DIR", str(tmp_path / "sess"))
    monkeypatch.setattr(send, "URI", f"ws://localhost:{port}")
    monkeypatch.setattr(send, "HUB_ID", f"localhost:{port}")

    async def scenario():
        # bind domyslny 127.0.0.1 => open_mode: agent wchodzi bez tokenu/nicka
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            task = asyncio.create_task(send.listen(""))
            await asyncio.sleep(1.5)   # hello + nadanie nicka + zapis sesji
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        finally:
            await srv.stop()

    asyncio.run(scenario())

    sess_files = list((tmp_path / "sess").glob("*.json"))
    assert sess_files, "brak pliku sesji => klient nie przyjal nadanego nicka"
    # pusty nick dalby slug fallback 'nick-*'; nadany to 'worker*'
    assert not any(f.name.startswith("nick-") for f in sess_files), \
        [f.name for f in sess_files]
    err = capsys.readouterr().err
    assert "invalid nick" not in err, err
    assert "[hub] nadany nick:" in err, err


def test_nickless_listen_failcloses_when_hub_assigns_no_nick(monkeypatch):
    """Review worker2: gdy hub przyjmuje nickless hello, ale nie odsyla
    nadanego nicka (version-skew), listen NIE moze paln AttributeError —
    _BootIdentity nie jest sesja. Kontrakt: czysty fail-closed (exit 1),
    a finally nie siega po None.release_listener_lock()."""
    monkeypatch.delenv("CHAT_TOKEN", raising=False)

    class _FakeConn:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *a):
            return False

    # C2: atrapa duck-typuje do_hello, wiec przyjmuje takze `context`
    # (dopisany przy wejsciu fresh). Kontrakt testu bez zmian.
    async def _fake_hello(ws, nick, session, token, role=None, context=None):
        return {"type": "ok"}   # przyjete, ale BEZ pola 'nick'

    monkeypatch.setattr(send.websockets, "connect", lambda *a, **k: _FakeConn())
    monkeypatch.setattr(send, "do_hello", _fake_hello)

    with pytest.raises(SystemExit) as ei:
        asyncio.run(send.listen(""))
    assert ei.value.code == 1


# -- C2: kursor konczy na AUTORYTATYWNYM koncu logu ------------------------

def test_hello_ok_z_pustym_backlogiem_przesuwa_kursor_na_wire_last_seq(session):
    """Autorytatywny koniec logu jest w `last_seq`, NIE w ostatniej ramce
    backlogu — serwer swiadomie filtruje z drutu cudze hello (54% backlogu
    w pomiarze B5). Klient, ktory ufa wylacznie ramkom, zostaje z kursorem
    sprzed filtra i prosi w kolko o to, czego nigdy nie dostanie. Przy
    wejsciu `context=fresh` backlog jest pusty ZAWSZE, wiec bez tego
    kontraktu niezaleznosc trwalaby do pierwszego reconnectu."""
    send._apply_hello_reply(session, {
        "type": "ok", "backlog": [], "last_seq": 42})
    assert session.last_applied_seq == 42


def test_hello_ok_last_seq_zero_nie_wywraca_wejscia(session):
    """PUSTY log: Session.advance rzuca SessionError dla seq < 1
    (chat/client_session.py:221), wiec bezwarunkowe advance wysypywaloby
    wejscie na swiezym kanale. Zero jest legalne — po prostu nie ma czego
    przesuwac."""
    send._apply_hello_reply(session, {
        "type": "ok", "backlog": [], "last_seq": 0})
    assert session.last_applied_seq == 0


def test_hello_ok_bez_poprawnego_last_seq_failcloses(session):
    """Fail-closed jak przy resync_required: brak wiarygodnego konca logu
    znaczy 'nie wiem, gdzie jestem'. Ciche pominiecie przesuniecia to
    pozniejsza powodz duplikatow albo luka, ktorej nikt nie powiaze
    z tym wejsciem."""
    from chat.client_session import SessionError
    with pytest.raises(SessionError):
        send._apply_hello_reply(session, {"type": "ok", "backlog": []})
    with pytest.raises(SessionError):
        send._apply_hello_reply(session, {
            "type": "ok", "backlog": [], "last_seq": True})
    with pytest.raises(SessionError):
        send._apply_hello_reply(session, {
            "type": "ok", "backlog": [], "last_seq": -1})


def test_fresh_leci_tylko_w_pierwszym_hello(tmp_path, monkeypatch):
    """Regresja C2: --fresh to jednorazowa decyzja przy STARCIE procesu,
    nie tryb polaczenia. Gdyby leciala przy kazdym obiegu petli reconnectu,
    kursor przeskakiwalby na koniec logu po kazdym zerwaniu, a wiadomosci
    z okna rozlaczenia gineliby dla tego agenta bezpowrotnie.

    Flage gasimy DOPIERO po zastosowaniu poprawnej odpowiedzi — gdy socket
    padnie wczesniej, kolejna proba nadal ma byc fresh (inaczej niezaleznosc
    gubi sie przez zwykly retry transportu)."""
    monkeypatch.delenv("CHAT_TOKEN", raising=False)
    widziane = []

    class _FakeWs:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration      # natychmiastowy koniec -> reconnect

    class _FakeConn:
        async def __aenter__(self):
            return _FakeWs()

        async def __aexit__(self, *a):
            return False

    async def _fake_hello(ws, nick, session, token, role=None, context=None):
        widziane.append(context)
        if len(widziane) >= 2:
            sys.exit(7)                   # przerywa petle reconnectu
        return {"type": "ok", "backlog": [], "last_seq": 0}

    monkeypatch.setattr(send.websockets, "connect", lambda *a, **k: _FakeConn())
    monkeypatch.setattr(send, "do_hello", _fake_hello)
    monkeypatch.setattr(send, "_session",
                        lambda nick: Session("localhost:9999", nick,
                                             base_dir=tmp_path))

    with pytest.raises(SystemExit):
        asyncio.run(send.listen("beta", context="fresh"))
    assert widziane == ["fresh", None]


def test_listen_podnosi_sie_na_proponowanym_nicku(tmp_path, monkeypatch):
    """C4: gdy nick zajmuje KTOS INNY, listener nie umiera — bierze nick,
    ktory hub podal w `suggested_nick`, i wchodzi. Zmierzone na kanale rube:
    Codex stracil nick 'codex', dostal propozycje 'worker3' w tresci bledu
    i utknal na kilkanascie minut, bo nie mial jej z czego odczytac ani
    instrukcji, ze ma jej uzyc. Agent bez nicka jest gluchy i niemy —
    podniesienie sie pod innym nickiem jest zawsze lepsze niz smierc."""
    monkeypatch.delenv("CHAT_TOKEN", raising=False)
    nicki = []

    class _FakeWs:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _FakeConn:
        async def __aenter__(self):
            return _FakeWs()

        async def __aexit__(self, *a):
            return False

    async def _fake_hello(ws, nick, session, token, role=None, context=None):
        nicki.append(nick)
        if len(nicki) == 1:                      # pierwsze wejscie: zajete
            return {"type": "error", "suggested_nick": "worker3",
                    "text": "nick codex jest zajety przez polaczonego uczestnika"}
        sys.exit(7)                              # drugie: konczymy test

    monkeypatch.setattr(send.websockets, "connect", lambda *a, **k: _FakeConn())
    monkeypatch.setattr(send, "do_hello", _fake_hello)
    monkeypatch.setattr(send, "_session",
                        lambda nick: Session("localhost:9999", nick,
                                             base_dir=tmp_path))

    with pytest.raises(SystemExit):
        asyncio.run(send.listen("codex"))
    assert nicki == ["codex", "worker3"], f"nie podnioslo sie: {nicki}"


def _atrapa_polaczenia(wyslane):
    """Fake socket zbierajacy to, co klient PROBOWAL wyslac."""
    class _FakeWs:
        async def send(self, data):
            wyslane.append(data)

        async def recv(self):
            raise AssertionError("nie powinnismy dojsc do odbioru")

    class _FakeConn:
        async def __aenter__(self):
            return _FakeWs()

        async def __aexit__(self, *a):
            return False

    return lambda *a, **k: _FakeConn()


ODMOWA = {"type": "error", "suggested_nick": "worker3",
          "text": "nick codex jest zajety przez polaczonego uczestnika"}


@pytest.mark.parametrize("wolaj", [
    lambda: send.send_once("codex", "tresc, ktora NIE MOZE zniknac"),
    lambda: send.oneshot_frame("codex", {"type": "status", "state": "idle"}),
])
def test_wysylka_po_odmowie_hello_pada_glosno_i_nie_wysyla_ramki(
        wolaj, tmp_path, monkeypatch, capsys):
    """CICHY FALSE-SUCCESS — najgorsza klasa bledu, jaka ten produkt ma.

    Zmierzone na zywym kanale przez drugiego agenta (Codex), nie znalezione
    z czytania kodu: dwa `agentmachi send --as codex` skonczyly sie kodem 0,
    a zadnej z tych ramek nie ma w logu huba.

    Mechanizm: `do_hello` celowo NIE umiera przy odmowie z `suggested_nick`,
    bo dla NASLUCHU to nie jest blad koncowy (listen podnosi sie pod nowym
    nickiem — 7ea4130). Wolajacy po stronie WYSYLKI tej zwrotki nie
    sprawdzali i leciali dalej: ramka szla na socket, ktory hub wlasnie
    zamykal, a proces konczyl sie zerem. Czyli fix nasluchu z tego samego
    dnia otworzyl dziure w wysylce.

    W `oneshot_frame` bylo to jeszcze lepiej zamaskowane: brak ACK jest tam
    LEGALNY (status go nie dostaje), wiec funkcja zwracala None — dokladnie
    tak samo jak przy sukcesie.

    POPRZEDNIA WERSJA TEGO TESTU BYLA ATRAPA: konczyla sie asercja na
    wlasnym literale (`assert reply.get("suggested_nick") == "worker3"`)
    i nie wolala `send_once` ani razu. Przechodzila zawsze — takze wtedy,
    gdy produkt cicho gubil wiadomosci. Test, ktory nie dotyka SUT, jest
    gorszy niz brak testu, bo kupuje falszywy spokoj."""
    monkeypatch.delenv("CHAT_TOKEN", raising=False)
    wyslane = []
    monkeypatch.setattr(send.websockets, "connect",
                        _atrapa_polaczenia(wyslane))
    monkeypatch.setattr(send, "_session",
                        lambda nick: Session("localhost:9999", nick,
                                             base_dir=tmp_path))

    async def _fake_hello(ws, nick, session, token, role=None, context=None):
        return ODMOWA

    monkeypatch.setattr(send, "do_hello", _fake_hello)

    with pytest.raises(SystemExit) as wyjscie:
        asyncio.run(wolaj())
    assert wyjscie.value.code != 0, \
        "wysylka, ktora nie dotarla, nie moze konczyc sie sukcesem"
    assert wyslane == [], \
        f"ramka poszla na socket zamykany przez huba: {wyslane}"

    err = capsys.readouterr().err
    assert "NIE zostala wyslana" in err, "czlowiek musi wiedziec, ze nie poszlo"
    assert "worker3" in err, "podaj wolny nick — agent ma czym wejsc"


def test_odmowa_wysylki_nie_podstawia_nadawcy(tmp_path, capsys):
    """Granica: hub PODAJE wolny nick, a mimo to nie wolno go uzyc za
    plecami czlowieka. Przy nasluchu podmiana nazwy jest ratunkiem, przy
    wysylce byloby podpisaniem sie cudza tozsamoscia — ta sama klasa bledu,
    ktora kosztowala ramke 4244 znakow podpisana cudzym nickiem."""
    sesja = Session("localhost:9999", "codex", base_dir=tmp_path)
    with pytest.raises(SystemExit):
        send._wysylka_albo_padnij(ODMOWA, "codex", sesja)
    err = capsys.readouterr().err
    assert "--as worker3" in err, "propozycja ma byc JAWNA komenda czlowieka"


def test_odmowa_wysylki_przepuszcza_poprawne_hello(tmp_path):
    """Bezpiecznik nie moze blokowac zdrowej sciezki."""
    sesja = Session("localhost:9999", "codex", base_dir=tmp_path)
    send._wysylka_albo_padnij({"type": "ok", "last_seq": 3}, "codex", sesja)
