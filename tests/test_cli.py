import json
import os
import stat

import pytest

from agentmachi import cli


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTMACHI_HOME", str(tmp_path))
    return tmp_path


def test_ensure_hub_creates_structure_0600(home):
    d, port = cli.ensure_hub("alpha", 8931)
    assert d == home / "alpha" and port == 8931
    tokens = json.loads((d / "tokens.json").read_text())
    assert stat.S_IMODE(os.stat(d / "tokens.json").st_mode) == 0o600
    roles = {v["role"] for v in tokens.values()}
    assert roles == {"human", "agent"}
    humans = [n for n, v in tokens.items() if v["role"] == "human"]
    assert len(humans) == 1  # kontrakt TUI: dokladnie jeden human
    assert (d / "data" / "rules.md").exists()
    assert json.loads((d / "config.json").read_text())["port"] == 8931


def test_ensure_hub_idempotent_keeps_tokens_and_port(home):
    d, _ = cli.ensure_hub("alpha", 8931)
    before = (d / "tokens.json").read_text()
    _, port = cli.ensure_hub("alpha", 9999)  # inny port NIE nadpisuje
    assert (d / "tokens.json").read_text() == before
    assert port == 8931


@pytest.mark.parametrize("bad", ["", "../x", ".ukryty", "a/b"])
def test_hub_dir_rejects_traversal(home, bad):
    with pytest.raises(cli.CliError):
        cli.hub_dir(bad)


def test_load_tokens_missing_hub_fail_closed(home):
    with pytest.raises(cli.CliError):
        cli.load_tokens("nie-ma")


def test_card_lists_participants_and_join_commands(home, capsys):
    cli.ensure_hub("alpha", 8931)
    tokens, _ = cli.load_tokens("alpha")
    cli.print_card("alpha", 8931, tokens)
    out = capsys.readouterr().out
    assert "ws://localhost:8931" in out  # connect_host: bind 127.0.0.1 -> localhost
    assert "worker1" in out and "agentmachi listen" in out
    assert "dolacz do agentmachi" in out


# --- Task 1: CHAT_BIND / CHAT_URL ------------------------------------------

def test_ensure_hub_stores_bind_in_config(home):
    d, _ = cli.ensure_hub("alpha", 8931, bind="0.0.0.0")
    config = json.loads((d / "config.json").read_text())
    assert config["bind"] == "0.0.0.0"


def test_ensure_hub_idempotent_keeps_bind(home):
    cli.ensure_hub("alpha", 8931, bind="0.0.0.0")
    d, _ = cli.ensure_hub("alpha", 8931, bind="127.0.0.1")  # inny bind NIE nadpisuje
    assert cli.hub_bind("alpha") == "0.0.0.0"


def test_card_shows_chat_url_and_remote_hint_for_0000(home, capsys):
    """Review fix (CRITICAL 1 + Minor): adres POLACZENIOWY != bind — dla
    0.0.0.0 karta drukuje localhost (routowalny), nie nieroutowalny
    0.0.0.0, ale wiersz-podpowiedz o tailnecie zostaje."""
    cli.ensure_hub("alpha", 8931, bind="0.0.0.0")
    tokens, _ = cli.load_tokens("alpha")
    cli.print_card("alpha", 8931, tokens, bind="0.0.0.0")
    out = capsys.readouterr().out
    assert "ws://localhost:8931" in out
    assert "CHAT_URL=ws://localhost:8931" in out
    assert "0.0.0.0" not in out.split("uwaga:")[0]  # adres sam nie niesie 0.0.0.0
    assert "tailnecie" in out  # wiersz podpowiedzi dla 0.0.0.0


def test_connect_host_maps_loopback_and_wildcard_to_localhost():
    """Review fix (CRITICAL 1): bind loopback/wildcard/localhost -> localhost;
    prawdziwy adres tailnetu/publiczny zostaje bez zmian."""
    assert cli.connect_host("127.0.0.1") == "localhost"
    assert cli.connect_host("0.0.0.0") == "localhost"
    assert cli.connect_host("localhost") == "localhost"
    assert cli.connect_host("100.64.1.2") == "100.64.1.2"


def test_agent_env_sets_chat_url(home, monkeypatch):
    """Review fix (CRITICAL 1): _agent_env uzywa connect_host, nie surowego
    bindu — inaczej hub_id agenta zmienialby sie z 'localhost:port' na
    'X.X.X.X:port' i kasowal trwaly kursor po kazdym upgradzie huba."""
    cli.ensure_hub("alpha", 8931, bind="0.0.0.0")
    # setenv (nie delenv) — _agent_env muta os.environ WPROST (poza
    # monkeypatch), wiec monkeypatch musi miec zarejestrowana wartosc DO
    # przywrocenia; delenv na nieobecnej zmiennej (raising=False) nic nie
    # rejestruje i zostawilby wyciek do kolejnych testow w tym procesie.
    monkeypatch.setenv("CHAT_TOKEN", "")
    monkeypatch.setenv("CHAT_URL", "")
    monkeypatch.setenv("CHAT_NICK", "")

    class Args:
        name = "alpha"
        nick = "worker1"
    cli._agent_env(Args())
    assert os.environ["CHAT_URL"] == "ws://localhost:8931"


def test_agent_env_upgrade_hub_without_bind_in_config_keeps_localhost(
        home, monkeypatch):
    """IMPORTANT 1 (review): hub sprzed B3 ma config.json BEZ klucza 'bind'
    (stary format {"port": N}) — _agent_env MUSI dac CHAT_URL z hostem
    localhost, inaczej hub_id agenta ('127.0.0.1:port' zamiast
    'localhost:port') kasuje trwaly kursor kazdego agenta po upgradzie."""
    d, _ = cli.ensure_hub("alpha", 8931)
    (d / "config.json").write_text(json.dumps({"port": 8931}))  # stary format
    monkeypatch.setenv("CHAT_TOKEN", "")
    monkeypatch.setenv("CHAT_URL", "")
    monkeypatch.setenv("CHAT_NICK", "")

    class Args:
        name = "alpha"
        nick = "worker1"
    cli._agent_env(Args())
    assert os.environ["CHAT_URL"] == "ws://localhost:8931"
    import send
    assert send.hub_id_from_url(os.environ["CHAT_URL"]) == "localhost:8931"
