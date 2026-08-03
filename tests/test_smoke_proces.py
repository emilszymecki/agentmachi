"""Smoke na poziomie PROCESU: hub i klient odpalane jako subprocess.

Uzupelniaja, nie dubluja testow in-process z test_server_integration.py —
tamte wolaja ChatServer bezposrednio, te sprawdzaja, czy `python -m
chat.server` i `send.py` naprawde startuja, gadaja i schodza. Trzy rzeczy
mozna zweryfikowac WYLACZNIE tedy: czysty SIGTERM zapisujacy snapshot,
przezycie rozlaczenia klienta i niezerowy exit `send.py` przy padlym hubie.

(Plik lezal do 2026-07-31 w korzeniu jako `test_chat.py` i NIE byl w suicie
— `pytest tests/` go nie dotykalo. Przez ten czas zgnil: asertowal pozycyjny
`send.py <nick> "tekst"`, wycofany w 4f30cdc. Przeniesiony i naprawiony.)

Serwer odpalany raz na sesje testowa jako subprocess na porcie CHAT_PORT
(domyślnie efemerycznym, zeby nie zderzyc sie z reczna instancja), z
tymczasowym plikiem tokenow (CHAT_TOKENS) i tymczasowym katalogiem danych
(CHAT_DATA) — zero wplywu na prawdziwy tokens.json/chat-data/. Kursory
klienta (CHAT_SESSION_DIR) tez ida w tmp — patrz `_sesje_klienta_poza_domem`.

Uzywa pytest-asyncio jesli jest dostepny; w przeciwnym razie kazdy test
async jest owijany w asyncio.run() recznie (patrz `run_async` nizej).
"""
import asyncio
import functools
import json
import os
import select
import socket
import subprocess
import sys
import time

import pytest
import websockets

try:
    import pytest_asyncio  # noqa: F401
    HAVE_PYTEST_ASYNCIO = True
except ImportError:
    HAVE_PYTEST_ASYNCIO = False

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("localhost", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


TEST_PORT = (int(os.environ["CHAT_TEST_PORT"])
             if "CHAT_TEST_PORT" in os.environ else _free_port())
URI = f"ws://localhost:{TEST_PORT}"
SERVER_START_TIMEOUT = 10.0
RECV_TIMEOUT = 2.0

# tokeny tymczasowe uzywane wylacznie przez te testy (nie prawdziwy tokens.json)
TOKENS = {"alfa": "ta", "beta": "tb", "s1": "t1", "s2": "t2"}


def _port_open(port, host="localhost"):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.2)
    try:
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()


def _wait_for_server(proc, timeout):
    """Czekaj na jawny readiness serwera, nie na przypadkowy otwarty TCP port."""
    deadline = time.monotonic() + timeout
    output = []
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            if proc.stdout is not None:
                output.extend(proc.stdout.readlines())
            return False, "".join(output)
        remaining = max(0.0, deadline - time.monotonic())
        ready, _, _ = select.select([proc.stdout], [], [], min(0.1, remaining))
        if not ready:
            continue
        line = proc.stdout.readline()
        if not line:
            continue
        output.append(line)
        if line.startswith("chat server on ws://"):
            return True, "".join(output)
    return False, "".join(output)


@pytest.fixture(scope="module", autouse=True)
def _sesje_klienta_poza_domem(tmp_path_factory):
    """Kursory klienta z tego pliku NIE moga wpasc do ~/.chat-sessions.

    Kazdy podproces tutaj buduje env z `dict(os.environ)`, wiec bez tego
    `send.py` zapisuje sesje do prawdziwego katalogu domowego. Port jest
    efemeryczny, a slug to sha256("host:port\\nnick") — przy kazdym przebiegu
    INNY. Smieci wiec przyrastaja w nieskonczonosc i zaden `agentmachi del`
    ich nie sprzatnie, bo nie naleza do zadnego istniejacego pokoju (purge
    chodzi po nickach skasowanego huba).

    Zmierzone 2026-08-03: przebieg zostawial pare `beta-<hash>.json/.lock`,
    a docstring tego pliku obiecywal „zero wplywu" juz wtedy — obietnica
    pokrywala CHAT_TOKENS i CHAT_DATA, a o sesjach klienta milczala.

    Autouse zamiast parametru `send_env`, bo wtedy KAZDY podproces tego
    pliku jest zabezpieczony, takze ten dopisany jutro."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("CHAT_SESSION_DIR", str(tmp_path_factory.mktemp("sesje")))
        yield


@pytest.fixture(scope="session")
def chat_server(tmp_path_factory):
    """Odpala `python -m chat.server` jako subprocess na TEST_PORT i czeka,
    az przyjmuje polaczenia. CHAT_TOKENS/CHAT_DATA wskazuja na tymczasowe
    pliki/katalogi (mktemp), zeby nie dotykac prawdziwych danych huba."""
    tokens_path = tmp_path_factory.mktemp("tok") / "tokens.json"
    tokens_path.write_text(json.dumps(TOKENS))
    data_dir = tmp_path_factory.mktemp("data")

    env = dict(os.environ)
    env["CHAT_PORT"] = str(TEST_PORT)
    env["CHAT_TOKENS"] = str(tokens_path)
    env["CHAT_DATA"] = str(data_dir)
    proc = subprocess.Popen(
        [sys.executable, "-m", "chat.server"],
        cwd=REPO_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        ready, startup_out = _wait_for_server(proc, SERVER_START_TIMEOUT)
        if not ready:
            proc.terminate()
            out = startup_out
            try:
                out += proc.communicate(timeout=5)[0]
            except Exception:
                pass
            raise RuntimeError(f"chat.server nie wystartowal na porcie {TEST_PORT}:\n{out}")
        yield TEST_PORT
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def send_env(token):
    env = dict(os.environ)
    env["CHAT_PORT"] = str(TEST_PORT)
    env["CHAT_TOKEN"] = token
    return env


def run_send_py(args, token, timeout=5):
    """Odpala send.py <args> jako subprocess (z CHAT_TOKEN), zwraca CompletedProcess."""
    return subprocess.run(
        [sys.executable, os.path.join(REPO_DIR, "send.py"), *args],
        env=send_env(token),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Async helper layer: uzyj pytest-asyncio jesli jest, inaczej recznie asyncio.run.
# ---------------------------------------------------------------------------

if HAVE_PYTEST_ASYNCIO:
    import pytest_asyncio as _pa

    def async_test(func):
        return pytest.mark.asyncio(func)

    @_pa.fixture
    async def _noop():
        yield

else:
    def async_test(func):
        @functools.wraps(func)  # zachowuje sygnature -> pytest widzi fixture'y
        def wrapper(*args, **kwargs):
            return asyncio.run(func(*args, **kwargs))
        return wrapper


async def hello(nick, token, instance="i1", last_seq=0, role="agent"):
    """Kazdy klient najpierw musi wyslac hello (kontrakt chat/server.py)."""
    ws = await websockets.connect(URI)
    await ws.send(json.dumps({"type": "hello", "from": nick, "ts": 0.0,
                              "instance_id": instance, "token": token,
                              "last_seq": last_seq, "role": role}))
    reply = json.loads(await ws.recv())
    return ws, reply


async def recv_or_timeout(ws, timeout=RECV_TIMEOUT):
    return await asyncio.wait_for(ws.recv(), timeout=timeout)


async def recv_frame(ws, timeout=RECV_TIMEOUT):
    return json.loads(await recv_or_timeout(ws, timeout))


# ---------------------------------------------------------------------------
# 1) broadcast: @all od A dociera do B i C (dawny "broadcast do wszystkich").
# ---------------------------------------------------------------------------

@async_test
async def test_broadcast_reaches_other_clients(chat_server):
    a, _ = await hello("alfa", TOKENS["alfa"])
    b, _ = await hello("beta", TOKENS["beta"])
    c, _ = await hello("s1", TOKENS["s1"])
    try:
        await a.send(json.dumps({"type": "chat", "from": "alfa", "ts": 0.0,
                                 "text": "@all czesc wszystkim"}))

        got_b = await recv_frame(b)
        got_c = await recv_frame(c)

        assert got_b["text"] == "@all czesc wszystkim"
        assert got_c["text"] == "@all czesc wszystkim"
    finally:
        await a.close()
        await b.close()
        await c.close()


# ---------------------------------------------------------------------------
# 2) echo po nicku: dwa sockety TEGO SAMEGO nicka — zaden nie dostaje wlasnej
#    ramki; odbiorca musi byc wspomniany (@beta).
# ---------------------------------------------------------------------------

@async_test
async def test_sender_does_not_receive_own_frame(chat_server):
    a1, _ = await hello("alfa", TOKENS["alfa"])   # ten sam instance_id ("i1") ->
    a2, _ = await hello("alfa", TOKENS["alfa"])   # bez takeover, oba sockety zyja
    b, _ = await hello("beta", TOKENS["beta"])
    try:
        await a1.send(json.dumps({"type": "chat", "from": "alfa", "ts": 0.0,
                                  "text": "@beta echo test"}))

        # b powinien dostac (dowod ze serwer w ogole przetworzyl wiadomosc)
        got_b = await recv_frame(b)
        assert got_b["text"] == "@beta echo test"

        # zaden socket alfy (nadawcy) nie powinien dostac niczego
        with pytest.raises(asyncio.TimeoutError):
            await recv_or_timeout(a1, timeout=0.5)
        with pytest.raises(asyncio.TimeoutError):
            await recv_or_timeout(a2, timeout=0.5)
    finally:
        await a1.close()
        await a2.close()
        await b.close()


# ---------------------------------------------------------------------------
# 3) send.py w trybie wysylki: exit 0, poprawna ramka dociera do sluchacza.
# ---------------------------------------------------------------------------

@async_test
async def test_send_py_success_delivers_json(chat_server):
    listener, _ = await hello("s1", TOKENS["s1"])
    try:
        result = run_send_py(["--as", "beta", "@s1 hej alfa"],
                             token=TOKENS["beta"])
        assert result.returncode == 0, f"stderr: {result.stderr}"

        data = await recv_frame(listener)
        assert data["from"] == "beta"
        assert data["text"] == "@s1 hej alfa"
    finally:
        await listener.close()


# ---------------------------------------------------------------------------
# 4) send.py przy zgaszonym serwerze: exit 1 i komunikat na stderr.
# ---------------------------------------------------------------------------

def test_send_py_fails_when_server_down():
    dead_port = _free_port()  # port przydzielony przez OS, zamiast TEST_PORT+1
    env = dict(os.environ)
    env["CHAT_PORT"] = str(dead_port)
    env["CHAT_TOKEN"] = "irrelevant"
    assert not _port_open(dead_port), "port powinien byc wolny do tego testu"

    result = subprocess.run(
        [sys.executable, os.path.join(REPO_DIR, "send.py"), "alfa", "hello"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert result.stderr.strip() != ""


# ---------------------------------------------------------------------------
# 5) rozlaczenie klienta nie wywala serwera - pozostali dalej dostaja wiadomosci.
# ---------------------------------------------------------------------------

@async_test
async def test_server_survives_client_disconnect(chat_server):
    a, _ = await hello("alfa", TOKENS["alfa"])
    b, _ = await hello("beta", TOKENS["beta"])
    c, _ = await hello("s1", TOKENS["s1"])
    try:
        # c sie rozlacza w trakcie
        await c.close()

        # serwer wciaz dziala: a i b dalej wymieniaja ramki
        await a.send(json.dumps({"type": "chat", "from": "alfa", "ts": 0.0,
                                 "text": "@beta jeszcze zyje"}))
        got_b = await recv_frame(b)
        assert got_b["text"] == "@beta jeszcze zyje"

        # dodatkowo nowy klient wciaz moze sie polaczyc
        d, _ = await hello("s2", TOKENS["s2"])
        try:
            await b.send(json.dumps({"type": "chat", "from": "beta", "ts": 0.0,
                                     "text": "@alfa @s2 nowy klient dziala"}))
            got_a = await recv_frame(a)
            got_d = await recv_frame(d)
            assert got_a["text"] == "@alfa @s2 nowy klient dziala"
            assert got_d["text"] == "@alfa @s2 nowy klient dziala"
        finally:
            await d.close()
    finally:
        await a.close()
        await b.close()


def test_sigterm_clean_shutdown_writes_snapshot(tmp_path):
    """SIGTERM ma przejsc przez ChatServer.stop(), nie zabic proces sygnalem."""
    port = _free_port()
    tokens_path = tmp_path / "tokens.json"
    tokens_path.write_text(json.dumps(TOKENS))
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    env = dict(os.environ)
    env["CHAT_PORT"] = str(port)
    env["CHAT_TOKENS"] = str(tokens_path)
    env["CHAT_DATA"] = str(data_dir)
    proc = subprocess.Popen(
        [sys.executable, "-m", "chat.server"],
        cwd=REPO_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        ready, startup_out = _wait_for_server(proc, SERVER_START_TIMEOUT)
        assert ready, startup_out

        async def create_durable_identity():
            ws = await websockets.connect(f"ws://localhost:{port}")
            await ws.send(json.dumps({
                "type": "hello", "from": "alfa", "ts": 0.0,
                "instance_id": "sigterm-i1", "token": TOKENS["alfa"],
                "last_seq": 0, "role": "agent",
            }))
            reply = json.loads(await ws.recv())
            assert reply["type"] == "ok" and reply["generation"] == 1
            await ws.close()

        asyncio.run(create_durable_identity())
        proc.terminate()
        assert proc.wait(timeout=5) == 0

        snapshot_path = data_dir / "snapshot.json"
        assert snapshot_path.exists()
        snapshot = json.loads(snapshot_path.read_text())
        assert snapshot["snapshot_seq"] >= 1
        assert snapshot["state"]["registry"]["gen"]["alfa"] == 1
        assert snapshot["state"]["registry"]["instance"]["alfa"] == "sigterm-i1"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
