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
    offer = {"from": "server", "type": "task_offer", "seq": 13,
             "activation_id": "beta:13", "task": {}}
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
    offer = {"from": "server", "type": "task_offer", "seq": 13,
             "activation_id": "beta:13", "task": {}}
    def boom(_):
        raise RuntimeError("crash w apply")
    monkeypatch.setattr(send, "_print_event", boom)
    with pytest.raises(RuntimeError):
        send.apply_frame(session, offer)
    assert session.is_activation_applied("beta:13") is False
    assert session.last_applied_seq == 0
    monkeypatch.undo()
    assert send.apply_frame(session, offer) is True  # retry APLIKUJE
    assert "task_offer" in capsys.readouterr().out
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


def test_apply_hello_resync_without_state_still_moves_cursor(session, capsys):
    send._apply_hello_reply(session, {"type": "resync_required",
                                      "snapshot_seq": 42})
    assert session.last_applied_seq == 42


def test_require_token_fails_fast(monkeypatch):
    monkeypatch.delenv("CHAT_TOKEN", raising=False)
    with pytest.raises(SystemExit) as e:
        send._require_token()
    assert e.value.code == 2


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
