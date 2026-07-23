import argparse
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


def test_ensure_hub_writes_rules_v1(home):
    d, _ = cli.ensure_hub("alpha", 8931)
    text = (d / "data" / "rules.md").read_text()
    assert ("Wiadomosc agenta budzi innego agenta tylko przez "
            "bezposrednia wzmianke.") in text
    assert "task_approve" not in text


def test_rules_v11_have_seq_wins_arbiter(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTMACHI_HOME", str(tmp_path))
    cli.ensure_hub("h", 8899)
    rules = (tmp_path / "h" / "data" / "rules.md").read_text()
    assert "wygrywa deklaracja z nizszym seq" in rules


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


def test_agent_env_chat_url_from_env_wins_over_config(home, monkeypatch):
    """C1: na maszynie zdalnej (VPS bez lokalnego ~/.agentmachi/<hub>) env
    CHAT_URL musi wygrac nad configem lokalnym — inaczej _agent_env kasuje
    adres operatora i zawsze celuje w localhost z lokalnego config.json."""
    cli.ensure_hub("alpha", 8931)  # config lokalny: bind 127.0.0.1
    monkeypatch.setenv("CHAT_URL", "ws://100.64.0.7:8766")
    monkeypatch.setenv("CHAT_TOKEN", "remote-token")
    monkeypatch.setenv("CHAT_NICK", "")

    class Args:
        name = "alpha"
        nick = "worker1"
    cli._agent_env(Args())
    assert os.environ["CHAT_URL"] == "ws://100.64.0.7:8766"


def test_tui_env_sets_chat_url_from_hub_bind(home, monkeypatch):
    """I3: cmd_tui musi ustawiac CHAT_URL z bindu huba (nie tylko CHAT_PORT),
    inaczej tui.py fallbackuje do ws://localhost i nie polaczy sie z hubem
    bindowanym na adres tailnetowy."""
    cli.ensure_hub("alpha", 8931, bind="100.64.0.5")
    monkeypatch.setenv("CHAT_URL", "")
    cli._tui_env("alpha")
    assert os.environ["CHAT_URL"] == "ws://100.64.0.5:8931"


def test_tui_env_chat_url_from_env_wins(home, monkeypatch):
    """I3 (symetria z C1): preset CHAT_URL nie moze zostac nadpisany."""
    cli.ensure_hub("alpha", 8931, bind="100.64.0.5")
    monkeypatch.setenv("CHAT_URL", "ws://preset-host:1234")
    cli._tui_env("alpha")
    assert os.environ["CHAT_URL"] == "ws://preset-host:1234"


# --- Task 3: subkomenda `agentmachi node` ----------------------------------

def test_node_parser_defaults():
    args = cli._build_parser().parse_args(
        ["node", "alpha", "--nick", "worker1", "--workspace", "/tmp/w"])
    assert args.hub == "alpha" and args.nick == "worker1"
    assert args.workspace == "/tmp/w"
    assert args.humans == "human"
    assert args.max_wakes_per_hour == 6
    assert args.cooldown == 60.0
    assert args.max_wake_duration == 1200.0


def test_node_cmd_wires_url_token_state_path_without_running_loop(
        home, monkeypatch):
    """cmd_node NIE odpala petli w tym tescie: node_loop podmieniony na
    fake — sprawdzamy tylko okablowanie (URL/token/state_path/humans/
    limiter) i katalog stanu 0700."""
    # izolacja: CHAT_TOKEN/URL/NICK czyszczone jawnie — _agent_env muta
    # os.environ WPROST (poza monkeypatch), wiec bez tego leak z innego
    # testu w tym samym procesie ominalby walidacje nicka i realny (nie
    # podmieniony) node_loop probowalby laczyc sie z nieistniejacym hubem
    # w nieskonczonej petli reconnect (test wisi na 120s timeout).
    monkeypatch.setenv("CHAT_TOKEN", "")
    monkeypatch.setenv("CHAT_URL", "")
    monkeypatch.setenv("CHAT_NICK", "")
    cli.ensure_hub("alpha", 8931)
    tokens, d = cli.load_tokens("alpha")

    calls = []

    async def fake_node_loop(url, nick, token, state_path, runtime, humans,
                             limiter=None, now=None):
        calls.append(dict(url=url, nick=nick, token=token,
                          state_path=state_path, runtime=runtime,
                          humans=humans, limiter=limiter))

    monkeypatch.setattr("agentmachi.node.node_loop", fake_node_loop)
    rc = cli.main(["node", "alpha", "--nick", "worker1",
                  "--workspace", "/tmp/ws-test", "--humans", "emil,ola"])
    assert rc == 0
    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == f"ws://localhost:{cli.hub_port('alpha')}"
    assert call["nick"] == "worker1"
    assert call["token"] == tokens["worker1"]["token"]
    assert call["humans"] == {"emil", "ola"}

    state_path = d / "nodes" / "worker1" / "state.json"
    assert call["state_path"] == state_path
    assert stat.S_IMODE(os.stat(state_path.parent).st_mode) == 0o700

    from agentmachi.node import RateLimiter
    assert isinstance(call["limiter"], RateLimiter)
    assert call["limiter"].max_wakes_per_hour == 6
    assert call["limiter"].cooldown == 60.0

    from agentmachi.node import ClaudeRuntime
    assert isinstance(call["runtime"], ClaudeRuntime)
    assert call["runtime"].workspace == "/tmp/ws-test"


def test_node_cmd_rejects_unknown_nick(home, monkeypatch):
    monkeypatch.setenv("CHAT_TOKEN", "")
    monkeypatch.setenv("CHAT_URL", "")
    monkeypatch.setenv("CHAT_NICK", "")
    cli.ensure_hub("alpha", 8931)
    rc = cli.main(["node", "alpha", "--nick", "nikt-taki",
                  "--workspace", "/tmp/w"])
    assert rc == 2


def test_ensure_hub_writes_howto_for_agents(tmp_path, monkeypatch):
    """F5 (B5): swiezy hub serwuje howto — agent na golym sockecie dostaje
    onboarding protokolem, bez dostepu do repo."""
    monkeypatch.setenv("AGENTMACHI_HOME", str(tmp_path))
    cli.ensure_hub("h", 8901)
    howto = (tmp_path / "h" / "data" / "howto.md").read_text()
    assert "ZAKAZ: czujka konczaca sie po trafieniu" in howto
    assert "wygrywa deklaracja z nizszym" in howto
    assert "instance_id" in howto


# --- F6 (B5): start/list/stop — cykl zycia huba jedna komenda -----------

def test_start_writes_pidfile_and_list_sees_running(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTMACHI_HOME", str(tmp_path))
    cli.ensure_hub("h1", 8910)
    pid_path = cli.hub_dir("h1") / "hub.pid"
    pid_path.write_text(str(os.getpid()))          # zywy proces = my sami
    rows = cli.hub_rows()
    row = next(r for r in rows if r["name"] == "h1")
    assert row["running"] is True and row["pid"] == os.getpid()
    assert row["port"] == 8910


def test_list_sees_running_hub_without_pidfile(tmp_path, monkeypatch):
    """F8 (B5): brak pidfile NIE znaczy 'zatrzymany'.

    Huby sprzed F6 nie maja pliku, a `list` pokazywal je jako zatrzymane
    i podpowiadal `serve` — czyli zachecal do postawienia drugiego huba na
    tym samym katalogu. To droga prosto do split-brainu z F7, ktory raz juz
    skasowal rozmowe. Przy braku pidfile pytamy wiec system o procesy.
    """
    monkeypatch.setenv("AGENTMACHI_HOME", str(tmp_path))
    cli.ensure_hub("h3", 8912)
    assert not (cli.hub_dir("h3") / "hub.pid").exists()

    real = cli._cmdline_of

    def fake(pid):
        if pid == os.getpid():
            return "python3 -m agentmachi.cli serve --name h3"
        return real(pid)

    monkeypatch.setattr(cli, "_cmdline_of", fake)
    row = next(r for r in cli.hub_rows() if r["name"] == "h3")
    assert row["running"] is True
    assert row["pid"] == os.getpid()
    assert row["pidfile"] is False   # `list` ma to pokazac, nie przemilczec


def test_list_reports_dead_hub_and_cleans_stale_pidfile(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTMACHI_HOME", str(tmp_path))
    cli.ensure_hub("h2", 8911)
    pid_path = cli.hub_dir("h2") / "hub.pid"
    pid_path.write_text("999999")                  # PID, ktorego nie ma
    row = next(r for r in cli.hub_rows() if r["name"] == "h2")
    assert row["running"] is False and row["pid"] is None
    assert not pid_path.exists(), "martwy pidfile ma zniknac sam"


def test_stop_refuses_foreign_process(tmp_path, monkeypatch):
    """Bezpiecznik: stop ubija WYLACZNIE proces, ktory jest hubem tego
    katalogu. Pidfile moze byc nieaktualny i wskazywac cudzy PID."""
    monkeypatch.setenv("AGENTMACHI_HOME", str(tmp_path))
    cli.ensure_hub("h3", 8912)
    (cli.hub_dir("h3") / "hub.pid").write_text(str(os.getpid()))
    monkeypatch.setattr(cli, "_cmdline_of", lambda pid: "vim notatki.txt")
    killed = []
    monkeypatch.setattr(cli.os, "kill", lambda pid, sig: killed.append(pid))
    rc = cli.cmd_stop(argparse.Namespace(name="h3"))
    assert rc == 1 and killed == []
