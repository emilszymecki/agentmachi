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
    # Deklaracja ma poprzedzac prace, nie ja opisywac po fakcie — regula
    # pekala nam dokladnie przy pilnych zadaniach, wiec warunek jest
    # w rules wprost (dogfood B5: dwie rownolegle naprawy tego samego).
    assert "ZANIM ruszysz" in rules
    assert "KROTSZA deklaracja" in rules
    # C1 (laka nie obora): branie roboty to nie jedyny ustroj — deklaracja
    # dopuszcza WZIAC/DELEGACJE/UZGODNIC jako rowne opcje, a orchestrator to
    # ROLA, ktora agent moze przyjac, nie wymog systemu.
    assert "DELEGACJE" in rules and "UZGODNIC" in rules
    # C2: rules nie opisuja juz ZADNEJ roli organizacyjnej. Orchestrator
    # i worker znikly — nie dlatego, ze agent nie moze koordynowac (moze,
    # rozmowa), tylko dlatego, ze koordynacja nie daje trwalej tozsamosci
    # ani specjalnych praw. Wczesniejsza wersja tego testu pilnowala, zeby
    # rules MOWILY "$orchestrator to nie wymog systemu"; teraz w ogole
    # o nim nie mowia, bo w kodzie nie znaczy nic (patrz
    # test_orchestrator_group_grants_nothing).
    assert "orchestrator" not in rules.lower()
    assert "Worker wykonuje" not in rules


def test_rules_human_precedence_is_scoped_not_absolute(home):
    """Konstytucja (docs/konstytucja.md, pkt 2): pierwszenstwo czlowieka ma
    ZAKRES. Stara regula 1 brzmiala "Polecenie czlowieka ma pierwszenstwo
    przed poleceniem agenta." — bezwarunkowo, wiec czynila go merytorycznie
    nieomylnym kierownikiem, czego konstytucja wprost zabrania ("czlowiek
    obserwuje i moderuje, ale nie jest centralnym orchestrator-em pracy").
    Test pilnuje OBU polowek: moderacja/bezpieczenstwo/infrastruktura sa
    ostateczne, merytoryka jest do zakwestionowania faktami. Skasowanie
    ktorejkolwiek polowki lamie konstytucje w druga strone."""
    d, _ = cli.ensure_hub("alpha", 8931)
    rules = (d / "data" / "rules.md").read_text()
    assert "MODERACJI" in rules and "BEZPIECZENSTWIE" in rules
    assert "INFRASTRUKTURY" in rules and "ostateczne" in rules
    assert "MERYTORYCZNEJ" in rules and "nie kierownikiem" in rules


def test_rules_board_status_is_a_hint_not_a_duty(home):
    """Board nie jest obowiazkiem uczestnika. Podstawa nie jest estetyka,
    tylko pomiar: w DWOCH dogfoodach zaden agent nie odswiezyl statusu ani
    razu po pierwszym ustawieniu (0%), bo kazda wiadomosc i tak szla wprost
    do adresata. Regula w trybie rozkazujacym, ktorej nikt nie wykonuje,
    uczy ignorowania rules jako calosci — wiec status jest WSKAZOWKA."""
    d, _ = cli.ensure_hub("alpha", 8931)
    rules = (d / "data" / "rules.md").read_text()
    assert "WSKAZOWKA" in rules and "nie obowiazkiem" in rules


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

_LIMITER_ENVS = ("MAX_AGENT_WAKES_PER_HOUR", "AGENT_WAKE_COOLDOWN",
                 "MAX_WAKE_DURATION")


def test_node_parser_defaults(monkeypatch):
    # izolacja od operator env: defaulty limitera czytaja te 3 envy (D1),
    # wiec czyscimy je, zeby test nie zalezal od srodowiska CI.
    for var in _LIMITER_ENVS:
        monkeypatch.delenv(var, raising=False)
    args = cli._build_parser().parse_args(
        ["node", "alpha", "--nick", "worker1", "--workspace", "/tmp/w"])
    assert args.hub == "alpha" and args.nick == "worker1"
    assert args.workspace == "/tmp/w"
    assert args.humans == "human"
    assert args.max_wakes_per_hour == 6
    assert args.cooldown == 60.0
    assert args.max_wake_duration == 1200.0


def test_node_parser_limiter_defaults_from_env(monkeypatch):
    # D1: defaulty limitera czytane z env; jawne flagi wygrywaja nad env.
    monkeypatch.setenv("MAX_AGENT_WAKES_PER_HOUR", "9")
    monkeypatch.setenv("AGENT_WAKE_COOLDOWN", "2.5")
    monkeypatch.setenv("MAX_WAKE_DURATION", "33")
    base = ["node", "alpha", "--nick", "w1", "--workspace", "/tmp/w"]
    args = cli._build_parser().parse_args(base)
    assert args.max_wakes_per_hour == 9
    assert args.cooldown == 2.5
    assert args.max_wake_duration == 33.0
    # jawne flagi nadpisuja env
    args2 = cli._build_parser().parse_args(base + [
        "--max-wakes-per-hour", "4", "--cooldown", "1.5",
        "--max-wake-duration", "7"])
    assert args2.max_wakes_per_hour == 4
    assert args2.cooldown == 1.5
    assert args2.max_wake_duration == 7.0


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
    # limiter defaulty czytaja env (D1) — czyscimy, by asercja 6/60 nizej nie
    # byla flake gdy operator ma te envy ustawione.
    for var in _LIMITER_ENVS:
        monkeypatch.delenv(var, raising=False)
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

    # Skaner wyklucza CALE nasze drzewo przodkow (my + rodzic + wrapper
    # powloki), bo zaden z nich nie jest "innym hubem", tylko nami w drodze
    # do startu. Rodzic nie nadaje sie wiec na proxy dla obcego procesu —
    # udajemy, ze nasze drzewo to my sami, i dopiero wtedy PPID gra role
    # cudzego, zywego huba.
    other = os.getppid()

    def fake(pid):
        if pid == other:
            return "python3 -m agentmachi.cli serve --name h3"
        return real(pid)

    monkeypatch.setattr(cli, "_cmdline_of", fake)
    monkeypatch.setattr(cli, "_ancestor_pids", lambda: {os.getpid()})
    monkeypatch.setattr(cli, "_is_shell_wrapper", lambda pid: False)
    row = next(r for r in cli.hub_rows() if r["name"] == "h3")
    assert row["running"] is True
    assert row["pid"] == other
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


def test_scan_never_reports_the_calling_process_as_running_hub(tmp_path, monkeypatch):
    """REGRESJA (produkcja): hub startowal, pytal 'czy juz dzialam?', skaner
    znajdowal JEGO WLASNY proces i serve odmawial startu — hub nie mogl wstac
    w ogole. Ten sam wzorzec co pkill trafiajacy we wlasny wrapper."""
    monkeypatch.setenv("AGENTMACHI_HOME", str(tmp_path))
    cli.ensure_hub("h9", 8919)
    # nasz wlasny proces udaje huba tej nazwy — skaner MUSI go pominac
    real = cli._cmdline_of

    def only_me_looks_like_hub(pid):
        if pid == os.getpid():
            return "python3 -m agentmachi.cli serve --name h9"
        cmd = real(pid)
        # zaden inny proces w systemie nie moze udawac tego huba
        return None if cmd and "h9" in cmd else cmd

    monkeypatch.setattr(cli, "_cmdline_of", only_me_looks_like_hub)
    assert cli._scan_hub_pid("h9") is None


def test_scanner_ignores_shell_wrapper_and_own_tree(tmp_path, monkeypatch):
    """Regresja B2/F8: wrapper powloki NIE jest hubem.

    `zsh -c "... agentmachi serve --name X"` trzyma cale polecenie we
    wlasnym argv, wiec pasuje do wzorca tak samo jak prawdziwy serwer.
    Startujacy przez powloke hub znajdowal wiec swojego rodzica i odmawial
    startu — ta sama pulapka, co `pkill -f` trafiajacy we wlasny wrapper,
    tylko o pietro wyzej. Rozstrzyga plik wykonywalny, nie tresc argv.
    """
    monkeypatch.setenv("AGENTMACHI_HOME", str(tmp_path))
    cli.ensure_hub("h4", 8913)
    other = os.getppid()
    monkeypatch.setattr(
        cli, "_cmdline_of",
        lambda pid: "zsh -c cd repo && agentmachi serve --name h4"
        if pid == other else None)
    monkeypatch.setattr(cli, "_ancestor_pids", lambda: {os.getpid()})
    monkeypatch.setattr(cli, "_is_shell_wrapper", lambda pid: pid == other)

    row = next(r for r in cli.hub_rows() if r["name"] == "h4")
    assert row["running"] is False, "powloka udajaca huba nie moze blokowac startu"


# --- zlecenie operatora: start / stop / list / del ----------------------
# Czlowiek ma odpalac i moderowac pokoje, nie pamietac zakleć powloki.
# Dotad start w tle wymagal `setsid nohup ... & disown` wklejanego recznie.

def test_start_runs_hub_in_background_and_prints_card(home, monkeypatch, capsys):
    spawned = {}

    def fake_spawn(argv, log_path):
        spawned["argv"] = argv
        spawned["log"] = log_path
        return 4242

    monkeypatch.setattr(cli, "_spawn_detached", fake_spawn)
    monkeypatch.setattr(cli, "_port_accepts", lambda port, bind: False)
    monkeypatch.setattr(cli, "_wait_until_listening",
                        lambda *a, **kw: True)
    rc = cli.cmd_start(argparse.Namespace(name="pokoj", port=8951,
                                          bind="127.0.0.1"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "serve" in " ".join(spawned["argv"])
    assert "ws://localhost:8951" in out           # karta wejsciowa od razu
    assert "agentmachi stop" in out               # mowi, co dalej
    # pidfile zapisany przez start; hub_pid() go NIE potwierdzi, bo weryfikuje
    # zywotnosc procesu, a 4242 jest atrapa — sprawdzamy wiec sam zapis
    assert (cli.hub_dir("pokoj") / "hub.pid").read_text() == "4242"


def test_start_refuses_when_already_running(home, monkeypatch, capsys):
    cli.ensure_hub("pokoj", 8952)
    (cli.hub_dir("pokoj") / "hub.pid").write_text(str(os.getpid()))
    monkeypatch.setattr(cli, "_pid_is_our_hub", lambda pid, name: True)
    rc = cli.cmd_start(argparse.Namespace(name="pokoj", port=8952,
                                          bind="127.0.0.1"))
    assert rc == 1
    assert "juz dziala" in capsys.readouterr().err


def test_del_requires_typing_the_room_name(home, capsys):
    cli.ensure_hub("pokoj", 8953)
    rc = cli.cmd_del(argparse.Namespace(name="pokoj", confirm=None))
    assert rc == 1 and cli.hub_dir("pokoj").exists()
    assert "--tak-kasuj pokoj" in capsys.readouterr().err

    rc = cli.cmd_del(argparse.Namespace(name="pokoj", confirm="zla-nazwa"))
    assert rc == 1 and cli.hub_dir("pokoj").exists()

    rc = cli.cmd_del(argparse.Namespace(name="pokoj", confirm="pokoj"))
    assert rc == 0 and not cli.hub_dir("pokoj").exists()


def test_del_refuses_while_hub_is_running(home, monkeypatch, capsys):
    cli.ensure_hub("pokoj", 8954)
    (cli.hub_dir("pokoj") / "hub.pid").write_text(str(os.getpid()))
    monkeypatch.setattr(cli, "_pid_is_our_hub", lambda pid, name: True)
    rc = cli.cmd_del(argparse.Namespace(name="pokoj", confirm="pokoj"))
    assert rc == 1 and cli.hub_dir("pokoj").exists()
    assert "agentmachi stop" in capsys.readouterr().err


def test_serve_does_not_treat_its_own_pidfile_as_another_hub(home, monkeypatch,
                                                             capsys):
    """REGRESJA z zywego testu: `start` zapisuje hub.pid z PID-em dziecka,
    a dziecko (`serve`) czytalo ten sam plik i uznawalo SAMO SIEBIE za juz
    dzialajacy hub — wiec nie wstawalo. Trzeci wariant tej samej pulapki
    w jednym dniu (pkill po argv, skan procesow, teraz pidfile)."""
    cli.ensure_hub("pokoj", 8961)
    (cli.hub_dir("pokoj") / "hub.pid").write_text(str(os.getpid()))
    monkeypatch.setattr(cli, "_pid_is_our_hub", lambda pid, name: True)

    started = {}
    monkeypatch.setattr(cli, "ensure_hub",
                        lambda n, p, bind="127.0.0.1": (cli.hub_dir(n), 8961))
    monkeypatch.setattr(cli, "print_card",
                        lambda *a, **k: started.setdefault("card", True))

    class Boom(RuntimeError):
        pass

    def fake_server_main():
        started["ran"] = True
        raise Boom()

    import chat.server
    monkeypatch.setattr(chat.server, "main", fake_server_main)
    try:
        cli.cmd_serve(argparse.Namespace(name="pokoj", port=8961,
                                         bind="127.0.0.1"))
    except Boom:
        pass
    assert started.get("ran"), ("serve odmowil startu z powodu WLASNEGO "
                                "pidfile: " + capsys.readouterr().err)


def test_start_fails_loudly_when_child_dies_even_if_port_is_taken(
        home, monkeypatch, capsys):
    """KRYTYCZNE (znalezione przy weryfikacji skilla): gdy port zajmuje CUDZY
    proces, nasz serve pada, ale `_wait_until_listening` laczylo sie z tym
    cudzym nasluchem i `start` meldowal sukces z PID-em trupa. Potwierdzenie
    startu musi patrzec na NASZ proces, nie na to, czy cokolwiek slucha."""
    cli.ensure_hub("pokoj", 8766)

    def spawn_that_dies(argv, log_path):
        with open(log_path, "a") as f:      # dziecko zdazylo krzyknac i paść
            f.write("OSError: [Errno 98] Address already in use\n")
        return 999999                        # PID, ktorego juz nie ma

    monkeypatch.setattr(cli, "_spawn_detached", spawn_that_dies)
    # port "odpowiada" — ale to cudzy serwer
    monkeypatch.setattr(cli, "_port_accepts", lambda port, bind: True)

    rc = cli.cmd_start(argparse.Namespace(name="pokoj", port=8766,
                                          bind="127.0.0.1"))
    err = capsys.readouterr().err
    assert rc == 1, "start nie moze meldowac sukcesu, gdy port trzyma ktos inny"
    assert "zajety przez inny proces" in err, "powiedz czlowiekowi, co jest nie tak"
    assert "ss -tlnp" in err, "pokaz, jak sprawdzic czyj to port"
    assert not (cli.hub_dir("pokoj") / "hub.pid").exists(), \
        "martwy pidfile wprowadza w blad `list` i `stop`"


def test_start_fails_when_child_dies_without_ready_line(home, monkeypatch,
                                                        capsys):
    """Drugi bezpiecznik: port byl wolny, ale nasz serwer i tak padl.
    Dowodem startu jest linia z NASZEGO logu, nie sam fakt, ze cos slucha."""
    cli.ensure_hub("pokoj", 8967)
    monkeypatch.setattr(cli, "_port_accepts", lambda port, bind: False)

    def spawn_that_dies(argv, log_path):
        with open(log_path, "a") as f:
            f.write("Traceback: cos poszlo nie tak\n")
        return 999999                        # PID, ktorego juz nie ma

    monkeypatch.setattr(cli, "_spawn_detached", spawn_that_dies)
    rc = cli.cmd_start(argparse.Namespace(name="pokoj", port=8967,
                                          bind="127.0.0.1"))
    err = capsys.readouterr().err
    assert rc == 1
    assert "cos poszlo nie tak" in err, "pokaz POWOD z logu"
    assert not (cli.hub_dir("pokoj") / "hub.pid").exists()


def test_failed_start_leaves_no_ghost_room(home, monkeypatch, capsys):
    """Nieudany start NIE moze zostawic pokoju: czlowiek widzialby w `list`
    pokoj, ktory nigdy nie wstal."""
    monkeypatch.setattr(cli, "_port_accepts", lambda port, bind: True)
    rc = cli.cmd_start(argparse.Namespace(name="widmo", port=8766,
                                          bind="127.0.0.1"))
    assert rc == 1
    assert not cli.hub_dir("widmo").exists(), "start zostawil pokoj-widmo"
    assert [r["name"] for r in cli.hub_rows()] == []


def test_explicit_port_overrides_config_of_existing_room(home, monkeypatch,
                                                         capsys):
    """PULAPKA BEZ WYJSCIA (znaleziona przy weryfikacji): komunikat radzil
    'wybierz inny port', ale ensure_hub ignorowal --port dla istniejacego
    pokoju — wiec pokoj zostawal na trwale przypisany do zajetego portu
    i jedynym wyjsciem bylo `del` albo reczna edycja config.json."""
    cli.ensure_hub("pokoj", 8766)
    assert cli.hub_port("pokoj") == 8766

    zajete = {8766}
    monkeypatch.setattr(cli, "_port_accepts", lambda port, bind: port in zajete)
    monkeypatch.setattr(cli, "_spawn_detached", lambda argv, log: 4243)
    monkeypatch.setattr(cli, "_wait_until_listening", lambda *a, **kw: True)

    rc = cli.cmd_start(argparse.Namespace(name="pokoj", port=8823,
                                          bind="127.0.0.1"))
    assert rc == 0, capsys.readouterr().err
    assert cli.hub_port("pokoj") == 8823, "jawny --port musi nadpisac config"


def test_restart_stops_then_starts_in_one_command(home, monkeypatch, capsys):
    """Czlowiek ma miec JEDEN czasownik. Dotad restart wymagal trzech komend
    (stop, start, list) — to nie jest interfejs dla operatora, to instrukcja
    obslugi. `restart` czeka, az stary proces naprawde zejdzie, i dopiero
    wtedy stawia nowy; inaczej trafi na wlasny, jeszcze zyjacy port."""
    cli.ensure_hub("pokoj", 8981)
    (cli.hub_dir("pokoj") / "hub.pid").write_text("777777")
    kolejnosc = []

    monkeypatch.setattr(cli, "_pid_is_our_hub", lambda pid, name: True)
    monkeypatch.setattr(cli.os, "kill",
                        lambda pid, sig: kolejnosc.append(("kill", pid)))
    # po ubiciu: proces znika, port sie zwalnia
    stan = {"zyje": True}

    def cmdline(pid):
        return "agentmachi serve --name pokoj" if stan["zyje"] else None

    def kill(pid, sig):
        kolejnosc.append(("kill", pid))
        stan["zyje"] = False

    monkeypatch.setattr(cli, "_cmdline_of", cmdline)
    monkeypatch.setattr(cli.os, "kill", kill)
    monkeypatch.setattr(cli, "_port_accepts", lambda port, bind: stan["zyje"])
    monkeypatch.setattr(cli, "_spawn_detached",
                        lambda argv, log: kolejnosc.append(("start", argv)) or 555)
    monkeypatch.setattr(cli, "_wait_until_listening", lambda *a, **kw: True)

    rc = cli.cmd_restart(argparse.Namespace(name="pokoj", port=None, bind=None))
    assert rc == 0, capsys.readouterr().err
    assert [k[0] for k in kolejnosc] == ["kill", "start"], "najpierw stop, potem start"


def test_restart_starts_room_that_was_not_running(home, monkeypatch, capsys):
    """Restart zatrzymanego pokoju ma go po prostu odpalic, a nie krzyczec."""
    cli.ensure_hub("pokoj", 8982)
    monkeypatch.setattr(cli, "_port_accepts", lambda port, bind: False)
    monkeypatch.setattr(cli, "_spawn_detached", lambda argv, log: 556)
    monkeypatch.setattr(cli, "_wait_until_listening", lambda *a, **kw: True)
    rc = cli.cmd_restart(argparse.Namespace(name="pokoj", port=None, bind=None))
    assert rc == 0, capsys.readouterr().err


# --- agentmachi kill: pkill, ktory nie zabija sam siebie -------------------

def test_wlasne_pidy_zawieraja_nas_i_rodzicow():
    """Sedno komendy: `pkill -f <wzorzec>` dopasowuje WLASNY wrapper powloki,
    bo wzorzec siedzi w jego argv, i zabija sam siebie (exit 144). W jednej
    sesji dogfoodu weszlo w te pulapke dwoch agentow, obaj po przeczytaniu
    ostrzezenia w skillu — dokumentacja nie jest zabezpieczeniem."""
    from agentmachi.cli import _wlasne_pidy
    swoje = _wlasne_pidy()
    assert os.getpid() in swoje
    assert os.getppid() in swoje      # cala linia rodzicow, nie tylko my
    assert len(swoje) >= 2


def test_kill_nie_ubija_wlasnego_procesu(capsys):
    """Wzorzec dopasowujacy nasza wlasna linie polecen ma dac 'nic nie pasuje',
    a nie samobojstwo."""
    from agentmachi import cli
    args = argparse.Namespace(wzorzec="pytest", force=False, dry_run=True)
    rc = cli.cmd_kill(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert str(os.getpid()) not in out       # my sami NIGDY na liscie
