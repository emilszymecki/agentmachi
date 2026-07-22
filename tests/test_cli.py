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
    assert "ws://localhost:8931" in out
    assert "worker1" in out and "agentmachi listen" in out
    assert "dolacz do agentmachi" in out
