# Machine-id w boardzie: hub wystawia w participants adres peera (host socketu,
# ktory WIDZI), zeby dalo sie odroznic "kto jest na ktorej maszynie" — dwie
# lokalne instancje wygladaja z kanalu jak dwie zdalne (nauka z B5). Zrodlo to
# ws.remote_address, to samo, ktorego B7 uzywa do wiazania nick->adres.
#
# Test deterministyczny (fake ws, zero sieci): remote_address realnego socketu
# zalezy od routingu tailnetu maszyny testowej, wiec integracje po prawdziwym
# IP robimy recznie na zywym hubie; tu utrwalamy KONTRAKT logiki _peer_host.
import socket

from chat.server import ChatServer


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("localhost", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _FakeWS:
    def __init__(self, host):
        self.remote_address = (host, 12345)


def _server(tmp_path, bind):
    return ChatServer(data_dir=tmp_path, tokens={}, port=_free_port(), bind=bind)


def test_addr_exposed_przy_bindzie_tailnet(tmp_path):
    s = _server(tmp_path, bind="100.84.163.11")
    s.conns["codex"] = {_FakeWS("100.104.23.30")}
    assert s._peer_host("codex") == "100.104.23.30"
    board = {p["nick"]: p for p in s._participants_snapshot()}
    assert board["codex"]["addr"] == "100.104.23.30"


def test_addr_none_przy_bindzie_loopback(tmp_path):
    # loopback bind: wszyscy peer to 127.0.0.1 (test/proxy), adres nie rozroznia
    # podmiotow — zwracamy None zamiast falszywej informacji (jak w B7).
    s = _server(tmp_path, bind="127.0.0.1")
    s.conns["codex"] = {_FakeWS("100.104.23.30")}
    assert s._peer_host("codex") is None


def test_addr_none_gdy_peer_loopback_przy_tailnecie(tmp_path):
    # tailnet bind ale peer=127.0.0.1 to sygnal proxy/tunelu (B7): remote_address
    # jest wtedy proxy, nie prawdziwy peer — nie ufamy, None.
    s = _server(tmp_path, bind="100.84.163.11")
    s.conns["codex"] = {_FakeWS("127.0.0.1")}
    assert s._peer_host("codex") is None


def test_addr_none_gdy_niepolaczony(tmp_path):
    s = _server(tmp_path, bind="100.84.163.11")
    assert s._peer_host("kogo-nie-ma") is None
