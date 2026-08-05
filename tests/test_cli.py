import argparse
import argparse
import json
import os
import stat
import time
from pathlib import Path

import pytest

from agentmachi import cli


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTMACHI_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture(autouse=True)
def _bez_wyciekow_env():
    """`_tui_env`/`_agent_env` pisza WPROST do os.environ — tak musza, bo
    skladaja srodowisko dla `import tui` i dla podprocesow. monkeypatch nie
    cofnie zapisu, ktorego nie widzial, wiec sprzatamy tu jawnie.

    Bez tego `AGENTMACHI_HUB` ustawiony w tym pliku przeciekal do
    tests/test_send.py, gdzie smoke-testy odpalaja podprocesy dziedziczace
    os.environ — i te podprocesy celowaly w hub 'alpha' zamiast we wlasny.
    Objaw byl mylacy w najgorszy sposob: test_send.py przechodzil URUCHOMIONY
    OSOBNO (34 zielone) i padal w calej suicie. To ta sama klasa co zasada 13
    w docs/zasady-agentyczne.md — komenda, ktora nie trafila tam, gdzie
    myslisz."""
    klucze = ("AGENTMACHI_HUB", "AGENTMACHI_TOKENS", "CHAT_PORT", "CHAT_URL")
    przed = {k: os.environ.get(k) for k in klucze}
    yield
    for klucz, wartosc in przed.items():
        if wartosc is None:
            os.environ.pop(klucz, None)
        else:
            os.environ[klucz] = wartosc


def test_ensure_hub_creates_structure_0600(home):
    d, port = cli.ensure_hub("alpha", 8931)
    assert d == home / "alpha" and port == 8931
    tokens = json.loads((d / "tokens.json").read_text())
    assert stat.S_IMODE(os.stat(d / "tokens.json").st_mode) == 0o600
    roles = {v["role"] for v in tokens.values()}
    assert roles == {"human"}, \
        f"swiezy pokoj tworzy tozsamosci, ktorych nikt nie zajal: {tokens}"
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
    # PAKIET 0: uczestnik nazywa sie agent1, nie worker1 — nazwa "worker"
    # niesie ustroj (jest wykonawca czyjegos polecenia), a hub ma byc
    # mechanika. Karta musi nadal DZIALAC: nick + komenda + zdanie do wklejenia.
    assert "agent1" in out and "agentmachi listen" in out
    # Zmienil sie JEZYK karty, nie kontrakt: karta nadal musi niesc
    # gotowe zdanie do wklejenia agentowi.
    assert "join agentmachi" in out


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
    # Zmienil sie JEZYK karty, nie kontrakt: naglowek ostrzezenia to teraz
    # "warning:", a podpowiedz mowi o "tailnet".
    assert "0.0.0.0" not in out.split("warning:")[0]  # adres sam nie niesie 0.0.0.0
    assert "tailnet" in out  # wiersz podpowiedzi dla 0.0.0.0


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


# -- pokoj, ktorego tu nie ma: dolaczanie NIE zgaduje portu --------------

@pytest.mark.parametrize("argv", [
    ["send", "raport gotowy", "--name", "openrepo", "--as", "reviewer"],
    ["listen", "--name", "openrepo", "--nick", "reviewer"],
    ["frame", '{"type":"status","state":"idle"}', "--name", "openrepo",
     "--nick", "reviewer"],
    ["node", "openrepo", "--nick", "reviewer", "--workspace", "/tmp/ws-brak"],
])
def test_dolaczenie_do_nieistniejacego_pokoju_nie_zgaduje_portu(
        home, monkeypatch, capsys, argv):
    """Zmierzone na zywo 2026-08-05, nie wyczytane z kodu: agent przeszedl
    README doslownie, zrobil `agentmachi listen --name openrepo` (pokoju NIE
    bylo w lokalnym ~/.agentmachi/) i wylandowal w CUDZYM pokoju 'test' —
    z poprawnym session_metadata, boardem, howto i exit 0. Zero ostrzezenia,
    pewnosc, ze jest na openrepo.

    `send` domknal dowod: exit 0 i komunikat "unknown nick: orchestrator",
    ktory brzmi jak literowka w nicku, a nie jak "jestes w zlym pokoju".
    Ramka wyladowala w ~/.agentmachi/test/data/events.jsonl. Raport przepadl,
    a nadawca byl pewien, ze go wyslal.

    Przyczyna: hub_port(name, fallback=DEFAULT_PORT) przy braku config.json
    oddawalo twarde 8766. To fizyka, nie ergonomia — klient MELDUJE SUKCES,
    wysylajac dane obcemu odbiorcy.

    Test NIE dotyka drutu i tak ma zostac: przy pierwszym uruchomieniu (bez
    zaslony `_import_send`) wersja z bugiem NIE padala — ona wisiala,
    probujac sie polaczyc z tym, co akurat stoi na 8766 u operatora. Test,
    ktory celuje w domyslny port, jest dokladnie ta sama pomylka co
    naprawiana."""
    cli.ensure_hub("test", cli.DEFAULT_PORT)     # CUDZY pokoj na domyslnym
    for zmienna in ("CHAT_URL", "CHAT_TOKEN", "CHAT_NICK"):
        monkeypatch.setenv(zmienna, "")

    def _bez_drutu():
        raise AssertionError(
            "klient ruszyl do sieci mimo braku pokoju — to jest ten bug")
    monkeypatch.setattr(cli, "_import_send", _bez_drutu)

    rc = cli.main(argv)

    assert rc == 2, "wejscie do nieistniejacego pokoju nie moze konczyc sie 0"
    err = capsys.readouterr().err
    assert "openrepo" in err, err
    assert "agentmachi list" in err, "komunikat ma pokazac, jakie pokoje SA"
    assert "CHAT_URL" in err, "komunikat ma dac droge do pokoju na innej maszynie"
    assert os.environ.get("CHAT_URL", "") != f"ws://localhost:{cli.DEFAULT_PORT}", \
        "klient wycelowal w domyslny port mimo braku pokoju"


def test_dolaczenie_bez_lokalnego_pokoju_dziala_z_jawnym_chat_url(
        home, monkeypatch):
    """Granica poprzedniego testu. Tak wchodza agenci z INNYCH maszyn: nie ma
    tam zadnego ~/.agentmachi/<pokoj>, a jawny CHAT_URL musi wystarczyc
    (C1 — env wygrywa nad configiem lokalnym)."""
    monkeypatch.setenv("CHAT_URL", "ws://100.64.0.7:8931")
    monkeypatch.setenv("CHAT_TOKEN", "")
    monkeypatch.setenv("CHAT_NICK", "")

    class Args:
        name = "openrepo"       # pokoju NIE MA lokalnie — i nie musi byc
        nick = "reviewer"
    cli._agent_env(Args())
    assert os.environ["CHAT_URL"] == "ws://100.64.0.7:8931"


def test_card_nieistniejacego_pokoju_nie_drukuje_zgadnietego_adresu(
        home, capsys):
    """Karta to zdanie do WKLEJENIA agentowi. Adres zgadniety z DEFAULT_PORT
    rozsiewa blad dalej — kazdy, kto dostanie taka karte, wejdzie w cudzy
    pokoj."""
    cli.ensure_hub("test", cli.DEFAULT_PORT)
    assert cli.main(["card", "--name", "openrepo"]) == 2
    wyjscie = capsys.readouterr()
    assert f"ws://localhost:{cli.DEFAULT_PORT}" not in wyjscie.out


def test_tworzenie_pokoju_nadal_bierze_domyslny_port(home, monkeypatch,
                                                     capsys):
    """Rozroznienie, ktorego nie wolno zgubic: komenda TWORZACA pokoj ma
    prawo do DEFAULT_PORT, bo pokoj dopiero powstaje i domyslny adres nie
    nalezy jeszcze do nikogo. Odmowa tutaj zablokowalaby pierwsze
    uruchomienie produktu."""
    monkeypatch.setattr(cli, "_port_accepts", lambda port, bind: False)
    monkeypatch.setattr(cli, "_spawn_detached", lambda argv, log: 4243)
    monkeypatch.setattr(cli, "_wait_until_listening", lambda *a, **kw: True)

    rc = cli.cmd_start(argparse.Namespace(name="nowy", port=None, bind=None))
    assert rc == 0, capsys.readouterr().err
    assert cli.hub_port("nowy") == cli.DEFAULT_PORT


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
    monkeypatch.setenv("CHAT_SESSION_DIR", str(home / "sessions"))
    # limiter defaulty czytaja env (D1) — czyscimy, by asercja 6/60 nizej nie
    # byla flake gdy operator ma te envy ustawione.
    for var in _LIMITER_ENVS:
        monkeypatch.delenv(var, raising=False)
    cli.ensure_hub("alpha", 8931)
    # Swiezy pokoj ma juz TYLKO humana, wiec tozsamosc dla node'a zaklada
    # tu test — tak samo jak zrobi to operator, gdy bedzie mu potrzebny
    # nick z tokenem (bind publiczny, cudza maszyna). Kontrakt pod testem
    # sie nie zmienil: node MA przekazac token, gdy nick jest w pliku.
    _p = cli.hub_dir("alpha") / "tokens.json"
    _t = json.loads(_p.read_text())
    _t["agent1"] = {"token": "tok-agent1", "role": "agent", "groups": []}
    _p.write_text(json.dumps(_t))
    tokens, d = cli.load_tokens("alpha")

    calls = []

    async def fake_node_loop(url, nick, token, state_path, runtime, humans,
                             limiter=None, now=None, instance_id=None):
        # Node jest listenerem tej samej logicznej sesji co send/frame.
        # Lock MUSI juz byc trzymany, zeby budzony runtime nie odpalil
        # drugiego `listen`, nie stracil nicka i nie podniosl sie jako workerN.
        send = cli._import_send()
        with pytest.raises(send.ListenerLockHeld):
            send._session(nick).acquire_listener_lock()
        calls.append(dict(url=url, nick=nick, token=token,
                          state_path=state_path, runtime=runtime,
                          humans=humans, limiter=limiter,
                          instance_id=instance_id))

    monkeypatch.setattr("agentmachi.node.node_loop", fake_node_loop)
    rc = cli.main(["node", "alpha", "--nick", "agent1",
                  "--workspace", "/tmp/ws-test", "--humans", "emil,ola"])
    assert rc == 0
    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == f"ws://localhost:{cli.hub_port('alpha')}"
    assert call["nick"] == "agent1"
    assert call["token"] == tokens["agent1"]["token"]
    assert call["humans"] == {"emil", "ola"}
    assert isinstance(call["instance_id"], str) and call["instance_id"]

    state_path = d / "nodes" / "agent1" / "state.json"
    assert call["state_path"] == state_path
    assert stat.S_IMODE(os.stat(state_path.parent).st_mode) == 0o700

    from agentmachi.node import RateLimiter
    assert isinstance(call["limiter"], RateLimiter)
    assert call["limiter"].max_wakes_per_hour == 6
    assert call["limiter"].cooldown == 60.0

    from agentmachi.node import ClaudeRuntime
    assert isinstance(call["runtime"], ClaudeRuntime)
    assert call["runtime"].workspace == "/tmp/ws-test"

    # Po zakonczeniu node lock jest zwolniony — restart ma byc legalny.
    send = cli._import_send()
    session = send._session("agent1")
    assert session.instance_id == call["instance_id"]
    session.acquire_listener_lock()
    session.release_listener_lock()


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
    # PAKIET 1: kontrakt F5 ZOSTAJE — swiezy hub serwuje howto protokolem,
    # bo agent na golym sockecie nie ma repo. Zmienila sie TRESC: howto
    # opisuje wylacznie mechanike, wiec zniknelo "wygrywa deklaracja
    # z nizszym seq" (to zasada wspolpracy, nalezy do skilla). Zostaje to,
    # czego agent nie odkryje sam.
    assert "grep -m1" in howto, "brak ostrzezenia o czujce konczacej sie"
    assert "instance_id" in howto
    assert "agentmachi send" in howto and "--fresh" in howto


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
    # Atrapa obcego huba musi udawac takze JEGO INSTALACJE. Skan porownuje
    # teraz AGENTMACHI_HOME procesu z naszym (bo nazwa kanalu jest unikalna
    # w obrebie instalacji, nie maszyny) — a proxy jest tu PPID, czyli realny
    # proces, ktory realnie zyje w domyslnym ~/.agentmachi. Bez tej linii test
    # sprawdzalby, czy skan przechodzi przez granice instalacji, a ma
    # sprawdzac, ze brak pidfile NIE znaczy "zatrzymany". Kontrakt F8 zostaje
    # bez zmian; dopelniona jest tylko atrapa.
    monkeypatch.setattr(cli, "_home_procesu", lambda pid: str(tmp_path))
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
    # Zmienil sie JEZYK komunikatu, nie kontrakt.
    assert "already running" in capsys.readouterr().err


def test_del_requires_typing_the_room_name(home, capsys):
    cli.ensure_hub("pokoj", 8953)
    rc = cli.cmd_del(argparse.Namespace(name="pokoj", confirm=None))
    assert rc == 1 and cli.hub_dir("pokoj").exists()
    # Zmienila sie NAZWA flagi (--tak-kasuj -> --yes-delete), nie kontrakt:
    # potwierdzeniem nadal jest powtorzona nazwa pokoju.
    assert "--yes-delete pokoj" in capsys.readouterr().err

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
    # Zmienil sie JEZYK komunikatu, nie kontrakt.
    assert "taken by another process" in err, "powiedz czlowiekowi, co jest nie tak"
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

def test_ancestor_pids_zawieraja_nas_i_rodzicow():
    """Sedno komendy: `pkill -f <wzorzec>` dopasowuje WLASNY wrapper powloki,
    bo wzorzec siedzi w jego argv, i zabija sam siebie (exit 144). W jednej
    sesji dogfoodu weszlo w te pulapke dwoch agentow, obaj po przeczytaniu
    ostrzezenia w skillu — dokumentacja nie jest zabezpieczeniem."""
    from agentmachi.cli import _ancestor_pids
    swoje = _ancestor_pids()
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


# -- macOS: te same wlasnosci bez /proc ----------------------------------
#
# Znalezione przez CI, nie przez czytanie kodu: 8 failed na macos-latest,
# identycznie na 3.11/3.12/3.13, wszystkie od `FileNotFoundError: '/proc'`.
# macOS nie ma /proc w ogole, wiec nie dzialalo tam wykrywanie zywego huba
# bez pidfile, zapora przed split-brainem, `kill` ani `list`.
#
# Nie mamy macOS pod reka, wiec sciezke bez /proc przechodzimy na Linuksie:
# fixture `bez_procfs` odbiera modulowi `cli` dostep do /proc tak, jak robi
# to macOS — katalogu po prostu nie ma. Kazdy kod, ktory wciaz siegnie po
# /proc, dostanie tu FileNotFoundError, czyli dokladnie to, co na CI.

@pytest.fixture
def bez_procfs(tmp_path, monkeypatch):
    """Symulacja macOS: dla modulu `cli` /proc nie istnieje.

    Podmieniamy `cli.Path` tak, by kazda sciezka pod /proc wskazywala
    w nieistniejacy katalog. To mocniejsze niz zaslepienie samego
    `_procfs_dostepne`: gdyby ktos dolozyl nowe czytanie /proc z pominieciem
    tej bramki, test padnie tym samym bledem, co macos-latest, zamiast
    cicho przejsc."""
    brak = tmp_path / "system-bez-proc"

    def sciezka(*a, **kw):
        p = Path(*a, **kw)
        try:
            return brak / p.relative_to("/proc")
        except ValueError:
            return p

    sciezka.home = Path.home          # hub_home() nadal musi dzialac
    monkeypatch.setattr(cli, "Path", sciezka)
    assert cli._procfs_dostepne() is False, "fixture ma udawac system bez /proc"
    return brak


def _ps_atrapa(snapshot, comm=None, environ=None):
    """Atrapa `ps` rozrozniajaca wywolania po argumentach — jak prawdziwe.

    Pytanie o pojedynczy pid odpowiada z tego samego zdjecia, co `-A`:
    kod pyta o cmdline dwa razy (raz przy skanie, raz przy sprawdzaniu
    `--name`) i atrapa, ktora znalaby tylko jedno z tych wywolan, kłamalaby
    inaczej niz system."""
    linie = {}
    for linia in snapshot.splitlines():
        pid_txt, _, cmd = linia.strip().partition(" ")
        if pid_txt.isdigit():
            linie[pid_txt] = cmd.strip()

    def ps(*argv):
        if "-A" in argv:
            return snapshot
        pid = argv[-1]
        if "comm=" in argv:
            return (comm or {}).get(pid, "/usr/bin/python3.13") + "\n"
        if "-E" in argv or "eww" in argv:
            return (environ or {}).get(pid)
        if "command=" in argv:
            return (linie.get(pid) or "") + "\n" if pid in linie else None
        return None
    return ps


_PS_SNAPSHOT = """\
    1 /sbin/launchd
  501 /usr/libexec/logd
 4242 /opt/homebrew/bin/python3.13 -m agentmachi.cli serve --name warsztat
 4243 /bin/zsh -c cd repo && agentmachi serve --name warsztat
"""


def test_bez_procfs_ancestor_pids_nadal_zna_rodzicow(bez_procfs):
    """Bez tego `kill` na macOS zabijalby wlasny wrapper powloki (exit 144):
    zbior 'nasze procesy' redukowal sie do samego getpid()."""
    swoje = cli._ancestor_pids()
    assert os.getpid() in swoje
    assert os.getppid() in swoje
    assert len(swoje) >= 2


def test_bez_procfs_skan_znajduje_huba_bez_pidfile(home, bez_procfs,
                                                   monkeypatch):
    """F8 na macOS: brak pidfile nadal NIE znaczy 'zatrzymany'."""
    monkeypatch.setattr(cli, "_ps", _ps_atrapa(_PS_SNAPSHOT))
    monkeypatch.setattr(cli, "_ancestor_pids", lambda: {os.getpid()})
    monkeypatch.setattr(cli, "_home_procesu", lambda pid: str(cli.hub_home()))
    assert cli._scan_hub_pid("warsztat") == 4242, \
        "hub z tego samego home musi byc widziany — inaczej wraca split-brain"


def test_bez_procfs_skan_omija_wrapper_powloki(home, bez_procfs, monkeypatch):
    """Wlasnosc, ktorej `ps` nie dostaje za darmo: PID 4243 pasuje do wzorca
    rownie dobrze jak hub, bo trzyma cale polecenie we wlasnym argv.
    Rozstrzyga plik wykonywalny (`ps -o comm=`, nie `command=`)."""
    monkeypatch.setattr(cli, "_ps", _ps_atrapa(
        _PS_SNAPSHOT.replace(" 4242 /opt/homebrew/bin/python3.13 -m "
                             "agentmachi.cli serve --name warsztat\n", ""),
        comm={"4243": "/bin/zsh"}))
    monkeypatch.setattr(cli, "_ancestor_pids", lambda: {os.getpid()})
    monkeypatch.setattr(cli, "_home_procesu", lambda pid: str(cli.hub_home()))
    assert cli._scan_hub_pid("warsztat") is None, \
        "powloka udajaca huba nie moze blokowac startu"


def test_bez_procfs_skan_nie_myli_huba_z_innej_instalacji(home, bez_procfs,
                                                          monkeypatch):
    """Izolacja po AGENTMACHI_HOME zostaje takze bez /proc — inaczej suita
    na macOS zalezalaby od tego, co akurat chodzi na maszynie."""
    monkeypatch.setattr(cli, "_ps", _ps_atrapa(_PS_SNAPSHOT))
    monkeypatch.setattr(cli, "_ancestor_pids", lambda: {os.getpid()})
    monkeypatch.setattr(cli, "_home_procesu", lambda pid: "/gdzie/indziej")
    assert cli._scan_hub_pid("warsztat") is None


def test_bez_procfs_skan_nie_raportuje_wlasnego_procesu(home, bez_procfs,
                                                        monkeypatch):
    """REGRESJA z produkcji, ta sama na kazdej platformie: startujacy hub
    pytal 'czy juz dzialam?', skaner znajdowal JEGO WLASNY proces i serve
    odmawial startu."""
    snapshot = f"{os.getpid()} python3 -m agentmachi.cli serve --name warsztat\n"
    monkeypatch.setattr(cli, "_ps", _ps_atrapa(snapshot))
    monkeypatch.setattr(cli, "_home_procesu", lambda pid: str(cli.hub_home()))
    assert cli._scan_hub_pid("warsztat") is None


def test_bez_procfs_list_widzi_zywy_hub_z_pidfile(home, bez_procfs):
    """Cala droga na prawdziwym `ps`, bez atrap: pidfile -> _cmdline_of ->
    `list`. Na macOS `_cmdline_of` zwracalo None dla KAZDEGO pid-u, wiec
    `list` kasowal zywy pidfile i meldowal 'stopped'."""
    cli.ensure_hub("h1", 8910)
    (cli.hub_dir("h1") / "hub.pid").write_text(str(os.getpid()))
    row = next(r for r in cli.hub_rows() if r["name"] == "h1")
    assert row["running"] is True and row["pid"] == os.getpid()
    assert (cli.hub_dir("h1") / "hub.pid").exists(), "zywy pidfile ma zostac"


def test_bez_procfs_kill_nie_ubija_wlasnego_procesu(bez_procfs, capsys):
    """Na macOS ta komenda padala z FileNotFoundError na samym `/proc` —
    czyli narzedzie ratunkowe nie dzialalo tam w ogole."""
    args = argparse.Namespace(wzorzec="pytest", force=False, dry_run=True)
    assert cli.cmd_kill(args) == 0
    assert str(os.getpid()) not in capsys.readouterr().out


def test_bez_procfs_wrapper_powloki_poznaje_sie_po_pliku_wykonywalnym(
        bez_procfs):
    """Na zywych procesach, bez atrap. `/proc/<pid>/exe` nie ma, wiec pytamy
    `ps -o comm=` — pole wziete z pliku wykonywalnego, nie z argv."""
    import subprocess
    # DWIE komendy, nie jedna. Przy `sh -c "sleep 30"` powloka ma prawo
    # zrobic `exec sleep` i ZNIKNAC — proces przestaje byc powloka i staje
    # sie `sleep`. Linuksowy /bin/sh (dash) tego nie robil, macOS-owy (bash
    # w trybie sh) owszem, wiec test padal na CI na macOS przy poprawnym
    # kodzie. `; true` odbiera powloce prawo do tej optymalizacji.
    dziecko = subprocess.Popen(["sh", "-c", "sleep 30; true"])
    try:
        time.sleep(0.3)
        assert cli._is_shell_wrapper(dziecko.pid) is True, (
            f"ps -o comm= dalo {cli._exe_nazwa(dziecko.pid)!r} dla `sh -c`; "
            f"oczekiwano czegos z {cli._SHELLS}"
        )
        assert cli._is_shell_wrapper(os.getpid()) is False   # to python
    finally:
        dziecko.kill()
        dziecko.wait()


def test_bez_procfs_home_procesu_czyta_srodowisko(bez_procfs):
    """Jedyna wlasnosc, ktorej przenosnie odtworzyc SIE NIE DA na pewno:
    `/proc/<pid>/environ` czyta sie zawsze, a `ps -E`/`ps eww` pokazuje
    srodowisko tylko procesow, ktore system zechce pokazac (na macOS bywa,
    ze dla cudzego uid albo binarki z hardened runtime nie pokaze).

    Kontrakt jest wiec dwuczlonowy i oba czlony sa tu sprawdzane: albo
    znamy home procesu, albo NIE ZGADUJEMY (None) — a None zostawia
    trafienie skanu, bo falszywe 'dziala' jest tansze niz falszywe
    'zatrzymany' (split-brain F7 raz zzarl nam rozmowe)."""
    import subprocess
    srodowisko = {**os.environ, "AGENTMACHI_HOME": "/tmp/nie ma takiego/machi"}
    dziecko = subprocess.Popen(["sh", "-c", "sleep 30"], env=srodowisko)
    try:
        time.sleep(0.3)
        home = cli._home_procesu(dziecko.pid)
        if home is None:
            # Jawny brak, nie ciche klamstwo: mowimy, ze na tej platformie
            # tej wlasnosci nie mamy, i pilnujemy tanszej strony bledu.
            assert cli._ten_sam_home(dziecko.pid) is True
            pytest.skip("ps nie pokazuje environ na tej platformie — "
                        "_home_procesu oddaje None i skan zostawia trafienie")
        assert home == "/tmp/nie ma takiego/machi", \
            "sciezka ze spacja tez musi przezyc plaski tekst z ps"
    finally:
        dziecko.kill()
        dziecko.wait()


def test_bez_procfs_niewidoczne_environ_to_none_a_nie_domyslny_home(
        bez_procfs, monkeypatch):
    """Granica poprzedniego: wynik `ps` BEZ `PATH=` znaczy 'srodowiska nie
    pokazano', a nie 'hub startowal bez AGENTMACHI_HOME'. Gdyby wpadl tu
    domyslny ~/.agentmachi, skan uznalby hub z TEJ SAMEJ instalacji za obcy
    i powiedzial 'zatrzymany' — czyli zaprosil do split-brainu."""
    monkeypatch.setattr(cli, "_ps", _ps_atrapa(
        "", environ={"4242": "python3 -m agentmachi.cli serve --name w\n"}))
    assert cli._home_procesu(4242) is None
    assert cli._ten_sam_home(4242) is True

    monkeypatch.setattr(cli, "_ps", _ps_atrapa("", environ={
        "4242": "python3 -m agentmachi.cli serve --name w PATH=/usr/bin "
                "AGENTMACHI_HOME=/opt/machi SHELL=/bin/zsh\n"}))
    assert cli._home_procesu(4242) == "/opt/machi"


# -- C3: `send` nie pozwala pomylic nadawcy z adresatem -------------------

def _parse_send(argv):
    """Zbuduj args tak, jak zrobi to prawdziwe wejscie CLI."""
    return cli._build_parser().parse_args(argv)


def test_send_stara_skladnia_pozycyjna_to_blad_uzycia(home, capsys, monkeypatch):
    """Dawne `send <nick> "tekst"` czytalo sie jak 'wyslij DO nicka', a bylo
    PODPISEM nadawcy. Zmierzony koszt: ramka 4244 znakow wyslana w cudzym
    imieniu na zywym kanale (goldberg seq 275; sprostowanie w seq 281),
    przez agenta, ktory mial repo otwarte. Stary wariant NIE zostaje
    'dla kompatybilnosci' — dopoki dziala, pulapka dziala razem z nim.
    Kontrakt: nic nie leci w drut, exit 2, komunikat pokazuje NOWA forme."""
    wyslane = []
    monkeypatch.setattr(cli, "_import_send",
                        lambda: type("S", (), {"send_once": staticmethod(
                            lambda *a, **k: wyslane.append(a))})())
    args = _parse_send(["send", "opus_c", "tresc wiadomosci"])
    assert cli.cmd_send(args) == 2
    assert wyslane == []                      # NIC nie poszlo w drut
    err = capsys.readouterr().err
    # Zmienil sie JEZYK komunikatu, nie kontrakt: pokazuje NOWA forme.
    assert "--as opus_c" in err and "@someone" in err


def test_send_as_ustawia_nadawce(home, monkeypatch):
    """--as mowi KIM jestem; adresata wskazuje @wzmianka w tresci."""
    wyslane = []
    monkeypatch.setattr(cli, "_import_send",
                        lambda: type("S", (), {"send_once": staticmethod(
                            lambda nick, text, quiet=False: wyslane.append(
                                (nick, text)))})())
    monkeypatch.setattr(cli.asyncio, "run", lambda coro: coro)
    # _agent_env muta os.environ WPROST (poza monkeypatch) — setenv rejestruje
    # wartosci DO PRZYWROCENIA, inaczej CHAT_* wyciekaja do testow, ktore
    # odpalaja prawdziwe podprocesy listenera (padaly tylko w pelnej suicie).
    for zmienna in ("CHAT_URL", "CHAT_TOKEN", "CHAT_NICK"):
        monkeypatch.setenv(zmienna, "")
    cli.ensure_hub("alpha", 8931)
    args = _parse_send(["send", "@opus_c czesc", "--as", "worker2",
                        "--name", "alpha"])
    assert cli.cmd_send(args) == 0
    assert wyslane == [("worker2", "@opus_c czesc")]


def test_send_bierze_nadawce_z_chat_nick(home, monkeypatch):
    wyslane = []
    monkeypatch.setattr(cli, "_import_send",
                        lambda: type("S", (), {"send_once": staticmethod(
                            lambda nick, text, quiet=False: wyslane.append(
                                (nick, text)))})())
    monkeypatch.setattr(cli.asyncio, "run", lambda coro: coro)
    for zmienna in ("CHAT_URL", "CHAT_TOKEN"):
        monkeypatch.setenv(zmienna, "")     # patrz komentarz w tescie wyzej
    monkeypatch.setenv("CHAT_NICK", "worker2")
    cli.ensure_hub("alpha", 8931)
    args = _parse_send(["send", "@opus_c czesc", "--name", "alpha"])
    assert cli.cmd_send(args) == 0
    assert wyslane == [("worker2", "@opus_c czesc")]


def test_send_bez_nicka_failcloses(home, monkeypatch, capsys):
    """Bez --as i bez CHAT_NICK hub nadalby nick sam, a wiadomosc poszlaby
    podpisana czyms, czego nadawca nie wybral. Lepiej odmowic."""
    for zmienna in ("CHAT_URL", "CHAT_TOKEN", "CHAT_NICK"):
        monkeypatch.setenv(zmienna, "")     # patrz komentarz wyzej
    cli.ensure_hub("alpha", 8931)
    args = _parse_send(["send", "@opus_c czesc", "--name", "alpha"])
    assert cli.cmd_send(args) == 2
    assert "--as" in capsys.readouterr().err


# -- tresc ze stdin: droga, ktorej powloka nie tyka -----------------------
#
# Zgloszone z Windows 11 / PowerShell przez agenta, ktory MIERZYL, nie
# zgadywal: tresc konczaca sie backslashem (a tak konczy sie kazda sciezka
# `C:\Users\x\`) trafia do huba PRZEKLAMANA, z exit 0 i bez ostrzezenia.
# Hub, protokol i CLI sa czyste — psuje to powloka, ZANIM CLI cokolwiek
# zobaczy, wiec CLI nie ma tego jak wykryc. Jedyna naprawa to droga, ktorej
# powloka nie dotyka: stdin.

class _Stdin:
    """Atrapa stdin. Zapamietuje, czy ktokolwiek ja PRZECZYTAL — kilka
    testow nizej pilnuje wlasnie tego, ze CLI po stdin nie siega."""

    def __init__(self, tresc):
        self.bajty = (tresc if isinstance(tresc, bytes)
                      else tresc.encode("utf-8"))
        self.czytany = False
        atrapa = self

        class _Buf:
            def read(self):
                atrapa.czytany = True
                return atrapa.bajty

        self.buffer = _Buf()

    def read(self):
        self.czytany = True
        return self.bajty.decode("utf-8")

    def isatty(self):
        return False


def _lapacz_wysylki(monkeypatch, wyslane):
    monkeypatch.setattr(cli, "_import_send",
                        lambda: type("S", (), {"send_once": staticmethod(
                            lambda nick, text, quiet=False: wyslane.append(
                                (nick, text)))})())
    monkeypatch.setattr(cli.asyncio, "run", lambda coro: coro)


def _pokoj_alpha(monkeypatch):
    for zmienna in ("CHAT_URL", "CHAT_TOKEN", "CHAT_NICK"):
        monkeypatch.setenv(zmienna, "")     # patrz komentarz przy test_send_as_
    cli.ensure_hub("alpha", 8931)


# Dokladnie ta tresc, ktora ginie w powloce: backslash na koncu, cudzyslowy
# w srodku, apostrof i nowa linia. Ma dojsc bajt w bajt.
TRESC_Z_WINDOWS = (
    'raport z "C:\\Users\\test\\" i \'apostrofu\'\n'
    'sciezka koncowa: C:\\Users\\test\\')


@pytest.mark.parametrize("argv", [
    ["send", "-", "--as", "worker2", "--name", "alpha"],
    ["send", "--stdin", "--as", "worker2", "--name", "alpha"],
])
def test_send_czyta_tresc_ze_stdin_bajt_w_bajt(argv, home, monkeypatch):
    """`-` i `--stdin` znacza to samo i nie ruszaja ani jednego bajtu."""
    wyslane = []
    _lapacz_wysylki(monkeypatch, wyslane)
    _pokoj_alpha(monkeypatch)
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(TRESC_Z_WINDOWS + "\n"))
    assert cli.cmd_send(_parse_send(argv)) == 0
    assert wyslane == [("worker2", TRESC_Z_WINDOWS)]


def test_send_ze_stdin_zdejmuje_dokladnie_jedna_koncowa_nowa_linie(
        home, monkeypatch):
    """`echo` dokleja \\n, a wiadomosc czatu go nie potrzebuje. Zdejmujemy
    JEDEN (z CRLF-em Windowsa), zeby backslash tuz przed nim przezyl —
    i zeby druga, celowa pusta linia nie zniknela."""
    wyslane = []
    _lapacz_wysylki(monkeypatch, wyslane)
    _pokoj_alpha(monkeypatch)
    monkeypatch.setattr(cli.sys, "stdin", _Stdin("C:\\Users\\test\\\r\n"))
    assert cli.cmd_send(_parse_send(
        ["send", "-", "--as", "worker2", "--name", "alpha"])) == 0
    assert wyslane == [("worker2", "C:\\Users\\test\\")]

    wyslane.clear()
    monkeypatch.setattr(cli.sys, "stdin", _Stdin("dwie\nlinie\n\n"))
    assert cli.cmd_send(_parse_send(
        ["send", "-", "--as", "worker2", "--name", "alpha"])) == 0
    assert wyslane == [("worker2", "dwie\nlinie\n")]


@pytest.mark.parametrize("argv", [
    ["send", "--stdin", "tresc z argumentu", "--as", "worker2",
     "--name", "alpha"],
    ["send", "-", "tresc z argumentu", "--as", "worker2", "--name", "alpha"],
])
def test_send_tresc_z_dwoch_zrodel_naraz_to_blad(argv, home, monkeypatch,
                                                 capsys):
    """Podano tresc I argumentem, I przez stdin. Cichy wybor jednego z nich
    jest dokladnie ta klasa bledu, ktora ta zmiana naprawia: wysylajacy
    zobaczylby exit 0 i nie dowiedzialby sie, ktora wersje dostal kanal.
    Odmawiamy — i nie tykamy stdin, bo nie my o nim decydujemy."""
    wyslane = []
    _lapacz_wysylki(monkeypatch, wyslane)
    _pokoj_alpha(monkeypatch)
    stdin = _Stdin("tresc ze stdin")
    monkeypatch.setattr(cli.sys, "stdin", stdin)
    assert cli.cmd_send(_parse_send(argv)) == 2
    assert wyslane == []
    assert not stdin.czytany, "odmowa nie ma prawa zjesc cudzego strumienia"
    assert "--stdin" in capsys.readouterr().err


@pytest.mark.parametrize("tresc", ["", "\n", "   \n\t\n"])
def test_send_pusty_stdin_to_blad_a_nie_pusta_wiadomosc(tresc, home,
                                                        monkeypatch, capsys):
    """Pusta wiadomosc na kanale to szum, ktory budzi adresata i nic nie
    niesie. Zadany stdin bez tresci = blad, exit 2, zero ramek."""
    wyslane = []
    _lapacz_wysylki(monkeypatch, wyslane)
    _pokoj_alpha(monkeypatch)
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(tresc))
    assert cli.cmd_send(_parse_send(
        ["send", "-", "--as", "worker2", "--name", "alpha"])) == 2
    assert wyslane == []
    assert "empty" in capsys.readouterr().err.lower()


def test_send_nigdy_nie_zgaduje_stdin_z_tego_ze_nie_jest_terminalem(
        home, monkeypatch, capsys):
    """ZAMEK NA AUTODETEKCJE. Kusi napisac `if not sys.stdin.isatty(): czytaj`
    — i to jest blad zmierzony na zywym srodowisku: agent headless ma stdin
    podpiety do /dev/null, wiec autodetekcja poszlaby czytac, dostala EOF
    i wyslala PUSTA wiadomosc z exit 0. Czyli ta sama cicha porazka udajaca
    sukces, ktora naprawiamy.

    Kontrakt: bez `-` i bez `--stdin` stdin NIE ISTNIEJE dla `send`."""
    wyslane = []
    _lapacz_wysylki(monkeypatch, wyslane)
    _pokoj_alpha(monkeypatch)
    stdin = _Stdin("tresc, po ktora nikt nie prosil")
    monkeypatch.setattr(cli.sys, "stdin", stdin)
    assert cli.cmd_send(_parse_send(
        ["send", "--as", "worker2", "--name", "alpha"])) == 2
    assert wyslane == [], "brak tresci nie moze skonczyc sie wysylka"
    assert not stdin.czytany, "stdin przeczytany bez `-`/`--stdin`"
    err = capsys.readouterr().err
    assert "--stdin" in err, "odmowa ma pokazac droge, ktorej powloka nie tyka"


def test_send_argument_wygrywa_i_zostawia_stdin_w_spokoju(home, monkeypatch):
    """Odwrotna strona tego samego zamka: tresc podana argumentem idzie
    w drut nietknieta, a strumien (np. `while read` czytajacy plik) zostaje
    caly dla tego, kto go otworzyl."""
    wyslane = []
    _lapacz_wysylki(monkeypatch, wyslane)
    _pokoj_alpha(monkeypatch)
    stdin = _Stdin("cudze dane")
    monkeypatch.setattr(cli.sys, "stdin", stdin)
    assert cli.cmd_send(_parse_send(
        ["send", "@opus_c czesc", "--as", "worker2", "--name", "alpha"])) == 0
    assert wyslane == [("worker2", "@opus_c czesc")]
    assert not stdin.czytany


def test_send_stdin_nie_jest_utf8_to_blad_zamiast_mojibake(home, monkeypatch,
                                                           capsys):
    """Polski Windows potrafi wypchnac cp1250. Mojibake w logu huba jest
    nieodwracalne i wyglada na wine autora — lepiej odmowic."""
    wyslane = []
    _lapacz_wysylki(monkeypatch, wyslane)
    _pokoj_alpha(monkeypatch)
    monkeypatch.setattr(cli.sys, "stdin",
                        _Stdin("zażółć".encode("cp1250")))
    assert cli.cmd_send(_parse_send(
        ["send", "-", "--as", "worker2", "--name", "alpha"])) == 2
    assert wyslane == []
    assert "UTF-8" in capsys.readouterr().err


# -- to samo dla `frame`: cudzyslowy w JSON to ten sam problem, tylko gorszy

def _lapacz_ramek(monkeypatch, ramki):
    monkeypatch.setattr(cli, "_import_send",
                        lambda: type("S", (), {
                            "SessionError": RuntimeError,
                            "oneshot_frame": staticmethod(
                                lambda nick, frame: ramki.append(
                                    (nick, frame)))})())
    monkeypatch.setattr(cli.asyncio, "run", lambda coro: None)


@pytest.mark.parametrize("argv", [
    ["frame", "-", "--nick", "agent1", "--name", "alpha"],
    ["frame", "--stdin", "--nick", "agent1", "--name", "alpha"],
])
def test_frame_czyta_json_ze_stdin(argv, home, monkeypatch, capsys):
    """W `frame` cytowanie boli podwojnie: JSON JEST z cudzyslowow. W apostrofach
    PowerShell zjada `"`, wiec agent wysyla niepoprawny JSON i dostaje blad
    parsera zamiast statusu na boardzie."""
    ramki = []
    _lapacz_ramek(monkeypatch, ramki)
    _pokoj_alpha(monkeypatch)
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(
        '{"type":"status","state":"working","note":"sciezka C:\\\\tmp\\\\"}\n'))
    assert cli.cmd_frame(_parse_send(argv)) == 0
    assert ramki == [("agent1", {"type": "status", "state": "working",
                                 "note": "sciezka C:\\tmp\\"})]


def test_frame_tresc_z_dwoch_zrodel_naraz_to_blad(home, monkeypatch):
    ramki = []
    _lapacz_ramek(monkeypatch, ramki)
    _pokoj_alpha(monkeypatch)
    stdin = _Stdin('{"type":"status"}')
    monkeypatch.setattr(cli.sys, "stdin", stdin)
    with pytest.raises(cli.CliError) as blad:
        cli.cmd_frame(_parse_send(["frame", "--stdin", '{"type":"status"}',
                                   "--nick", "agent1", "--name", "alpha"]))
    assert "--stdin" in str(blad.value)
    assert ramki == [] and not stdin.czytany


def test_frame_pusty_stdin_to_blad(home, monkeypatch):
    ramki = []
    _lapacz_ramek(monkeypatch, ramki)
    _pokoj_alpha(monkeypatch)
    monkeypatch.setattr(cli.sys, "stdin", _Stdin("\n"))
    with pytest.raises(cli.CliError) as blad:
        cli.cmd_frame(_parse_send(["frame", "-", "--nick", "agent1",
                                   "--name", "alpha"]))
    assert "empty" in str(blad.value).lower()
    assert ramki == []


def test_frame_bez_json_i_bez_stdin_to_blad(home, monkeypatch):
    """Ten sam zamek na autodetekcje co przy `send`."""
    ramki = []
    _lapacz_ramek(monkeypatch, ramki)
    _pokoj_alpha(monkeypatch)
    stdin = _Stdin('{"type":"status"}')
    monkeypatch.setattr(cli.sys, "stdin", stdin)
    with pytest.raises(cli.CliError) as blad:
        cli.cmd_frame(_parse_send(["frame", "--nick", "agent1",
                                   "--name", "alpha"]))
    assert "--stdin" in str(blad.value)
    assert ramki == [] and not stdin.czytany


# -- C5: nowy hub nie kradnie portu istniejacemu -------------------------

def test_nowy_hub_bierze_wolny_port_gdy_domyslny_zajety(home):
    """Zmierzone na zywej maszynie: hub 'agentmachi' utworzony bez --port
    dostal DEFAULT_PORT 8766 — ten sam, co dzialajacy 'goldberg'. Skutek nie
    byl gloszny: nowy hub wstal z PUSTYM logiem na porcie starego, a kursory
    klientow sa per host:port, wiec TUI czlowieka dostalo fail-closed
    'last_seq 303 > serwerowy last_seq 0'. Do tego `list` pokazywal oba huby
    jako dzialajace, bo rozpoznaje je po porcie.

    Port to zasob systemowy, nie decyzja organizacyjna — alokacja nalezy do
    narzedzia. Hub ISTNIEJACY zachowuje swoj port bez zmian."""
    d1, p1 = cli.ensure_hub("pierwszy", 8931)
    assert p1 == 8931
    d2, p2 = cli.ensure_hub("drugi", 8931)          # ten sam domyslny port
    assert p2 != 8931, "drugi hub ukradl port pierwszemu"
    assert p2 > 8931
    # idempotencja: ponowne ensure_hub NIE przesuwa juz przydzielonego portu
    assert cli.ensure_hub("drugi", 8931)[1] == p2
    assert cli.ensure_hub("pierwszy", 8931)[1] == 8931


def test_jawny_port_ma_pierwszenstwo_ale_kolizja_jest_widoczna(home, capsys):
    """Gdy operator PODAJE port jawnie i jest wolny — dostaje dokladnie ten."""
    cli.ensure_hub("a", 8940)
    _, p = cli.ensure_hub("b", 8941)
    assert p == 8941


def test_skan_nie_myli_huba_z_innej_instalacji(home, monkeypatch):
    """Nazwa kanalu jest unikalna w obrebie INSTALACJI, nie maszyny.

    Zmierzone (zgloszone przez drugiego agenta na kanale, nie z czytania
    kodu): pelna suita przestawala byc zielona, gdy na maszynie chodzil
    pokoj o nazwie uzytej w tescie. Fixture przekierowuje AGENTMACHI_HOME do
    tmp_path — katalogi byly rozdzielone — a mimo to skan po `--name`
    znajdowal PRODUKCYJNY proces i cmd_start meldowal "pokoj juz dziala".
    Wynik suity zalezal wiec od tego, co akurat chodzi na maszynie, a nie od
    kodu; deklarowane "322 green" bylo wlasciwoscia maszyny, nie commita."""
    cmd = "python3 -m agentmachi.cli serve --name warsztat --port 8767"
    monkeypatch.setattr(cli, "_cmdline_of", lambda pid: cmd)
    monkeypatch.setattr(cli, "_is_shell_wrapper", lambda pid: False)

    monkeypatch.setattr(cli, "_home_procesu", lambda pid: str(cli.hub_home()))
    assert cli._scan_hub_pid("warsztat") is not None, \
        "hub z TEGO SAMEGO home musi byc widziany — inaczej wraca split-brain"

    monkeypatch.setattr(cli, "_home_procesu", lambda pid: "/gdzie/indziej")
    assert cli._scan_hub_pid("warsztat") is None, \
        "hub o tej samej nazwie w innej instalacji to INNY hub"


def test_nieczytelne_environ_zostawia_trafienie(home, monkeypatch):
    """Granica poprzedniego testu. Gdy nie da sie ustalic home procesu,
    zostajemy przy trafieniu. Skan istnieje po to, zeby nie kusic czlowieka
    do postawienia drugiego huba na tym samym katalogu (split-brain F7, ktory
    raz zzarl rozmowe) — falszywe "dziala" jest tu tansze niz falszywe
    "zatrzymany"."""
    cmd = "python3 -m agentmachi.cli serve --name warsztat --port 8767"
    monkeypatch.setattr(cli, "_cmdline_of", lambda pid: cmd)
    monkeypatch.setattr(cli, "_is_shell_wrapper", lambda pid: False)
    monkeypatch.setattr(cli, "_home_procesu", lambda pid: None)
    assert cli._scan_hub_pid("warsztat") is not None


def test_start_nowego_pokoju_omija_port_zajety_przez_obcy_proces(
        home, monkeypatch, capsys):
    """C5 czesc druga: alokacja portu w `ensure_hub` byla martwa dla `start`.

    Zmierzone: `agentmachi start --name warsztat` na maszynie z dzialajacym
    hubem na 8766 padalo z 'port zajety — wybierz inny', mimo ze wolny port
    lezal obok. Kolejnosc w cmd_start byla taka, ze _port_accepts zwracalo 1
    ZANIM ensure_hub w ogole dostal szanse przesunac port.

    NOWY pokoj bez --port nie ma jeszcze zadnej umowy o adres: nikt go nie
    zna, zaden kursor nie wskazuje. Wiec przesuwamy zamiast padac."""
    zajete = {8766}
    monkeypatch.setattr(cli, "_port_accepts", lambda port, bind: port in zajete)
    monkeypatch.setattr(cli, "_spawn_detached", lambda argv, log: 4243)
    monkeypatch.setattr(cli, "_wait_until_listening", lambda *a, **kw: True)

    rc = cli.cmd_start(argparse.Namespace(name="warsztat", port=None,
                                          bind=None))
    assert rc == 0, capsys.readouterr().err
    assert cli.hub_port("warsztat") == 8767, "pokoj mial przeskoczyc o jeden"
    # Zmienil sie JEZYK komunikatu, nie kontrakt.
    assert "gets 8767" in capsys.readouterr().err, \
        "czlowiek musi zobaczyc, ze adres jest inny niz domyslny"


def test_start_istniejacego_pokoju_nigdy_nie_przesuwa_portu(
        home, monkeypatch, capsys):
    """Granica poprzedniego testu. Pokoj ISTNIEJACY ma adres, ktory ludzie
    maja wklejony, a klienci maja pod nim kursor (per host:port). Cichy
    przeskok dalby pusty log pod znanym adresem — czyli dokladnie te awarie,
    ktore C5 usuwal. Tu jedynym poprawnym wyjsciem jest glosna odmowa."""
    cli.ensure_hub("stary", 8766)
    monkeypatch.setattr(cli, "_port_accepts", lambda port, bind: True)

    rc = cli.cmd_start(argparse.Namespace(name="stary", port=None, bind=None))
    assert rc == 1, "istniejacy pokoj nie moze zmienic adresu za plecami ludzi"
    assert cli.hub_port("stary") == 8766
    # Zmienil sie JEZYK komunikatu, nie kontrakt.
    assert "taken by another process" in capsys.readouterr().err


# -- C6: nazwa huba dopasowywana jako ARGUMENT, nie podciag ---------------

def test_pid_is_our_hub_nie_myli_nazwy_pakietu_z_nazwa_huba(monkeypatch):
    """Zmierzone na zywej maszynie: hub nazwany 'agentmachi' byl NIEUSUWALNY.
    `_pid_is_our_hub` sprawdzalo `name in cmd`, a kazdy hub ma w cmdline
    `-m agentmachi.cli`, wiec nazwa pakietu trafiala jako nazwa kanalu.
    Skutki: `del` odmawial ("pokoj DZIALA", pokazujac PID CUDZEGO huba),
    `list` raportowal oba jako dzialajace, a `stop` mogl ubic nie ten proces.

    Ta sama pulapka co `pkill -f` trafiajacy we wlasny wrapper: dopasowanie
    TEKSTOWE tam, gdzie potrzebne jest dopasowanie ARGUMENTU."""
    cmd_goldberg = "python3 -m agentmachi.cli serve --name goldberg --port 8766"
    monkeypatch.setattr(cli, "_cmdline_of", lambda pid: cmd_goldberg)
    # proces goldberga NIE jest hubem 'agentmachi' — mimo ze slowo wystepuje
    assert cli._pid_is_our_hub(1, "agentmachi") is False
    # ...ani hubem 'cli', 'serve' czy 'port' (inne podciagi z cmdline)
    assert cli._pid_is_our_hub(1, "cli") is False
    assert cli._pid_is_our_hub(1, "serve") is False
    # ...ale JEST hubem 'goldberg'
    assert cli._pid_is_our_hub(1, "goldberg") is True


def test_pid_is_our_hub_domyslny_kanal_bez_flagi_name(monkeypatch):
    """Hub odpalony bez --name obsluguje kanal domyslny (DEFAULT_HUB)."""
    monkeypatch.setattr(cli, "_cmdline_of",
                        lambda pid: "python3 -m agentmachi.cli serve --port 8766")
    assert cli._pid_is_our_hub(1, cli.DEFAULT_HUB) is True
    assert cli._pid_is_our_hub(1, "goldberg") is False


def test_pid_is_our_hub_nazwa_jako_prefiks_nie_wystarcza(monkeypatch):
    """'gold' nie jest hubem 'goldberg' i odwrotnie."""
    monkeypatch.setattr(cli, "_cmdline_of",
                        lambda pid: "python3 -m agentmachi.cli serve --name goldberg")
    assert cli._pid_is_our_hub(1, "gold") is False
    assert cli._pid_is_our_hub(1, "goldberg2") is False


# -- PAKIET 0 (plan V1): rdzen neutralny — hub nie nadaje kultury ---------
#
# Konstytucja, sekcja "Zasada dogfoodu": "lekcja z dogfoodu domyslnie idzie do
# obserwacji, nie do regulaminu. Wyciecie pastucha z kodu nic nie daje, jesli
# odrasta w plikach .md jako kolejny obowiazkowy paragraf."
#
# Dokladnie to sie stalo: scheduler wyleciał z kodu, a pastuch odrosl jako
# 15 regul w rules.md, 13 kB howto i domyslny zespol worker1/worker2 w
# grupie `workers`. Ponizsze testy pilnuja, ze hub jest MECHANIKA — daje
# przestrzen, nie ustroj.

def test_nowy_hub_nie_narzuca_zadnych_regul(home):
    """DEFAULT_RULES pusty. Pokoj MOZE miec zasady — gdy wpisze je czlowiek.

    Roznica jest ustrojowa, nie kosmetyczna: `rules` jako FUNKCJA (opcjonalne
    ograniczenia konkretnego pokoju) wobec `rules` jako DOMYSLNEJ KULTURY,
    ktora hub narzuca kazdemu, kto go postawi."""
    d, _ = cli.ensure_hub("neutralny", 8951)
    assert (d / "data" / "rules.md").read_text().strip() == "", \
        "hub nadaje domyslna kulture zamiast zostawiac pusta przestrzen"


def test_istniejacy_rules_nigdy_nie_jest_nadpisywany(home):
    """Granica poprzedniego testu: pusty DOMYSLNY rules nie moze skasowac
    zasad, ktore czlowiek juz wpisal do dzialajacego pokoju."""
    d, _ = cli.ensure_hub("z-zasadami", 8952)
    (d / "data" / "rules.md").write_text("1. Tu obowiazuje cisza nocna.\n")
    cli.ensure_hub("z-zasadami", 8952)
    assert "cisza nocna" in (d / "data" / "rules.md").read_text()


def test_nowy_hub_nie_tworzy_domyslnego_zespolu(home):
    """Hub nie sugeruje modelu zespolu — ANI nazwami, ANI grupami, ANI ETATEM.

    Poprzednia wersja tego zamku wymagala dokladnie {agent1, agent2} i byla
    NIEPELNA. Usunela ustroj z nazw (worker->agent) i z grup (koniec
    domyslnego `workers`), ale zostawila liczbe miejsc: swiezy pokoj
    twierdzil, ze ma dwoch uczestnikow, zanim ktokolwiek wszedl. `list`
    wypisywal ich w kolumnie uczestnikow, a board serwowal agentom jako
    `connected: false` — kanal opowiadal o ludziach, ktorych nie ma.
    Zgloszone przez operatora z zywego TUI.

    Zostaje sam `human`, bo jego TUI wymaga (dokladnie jeden human w pliku)
    i bo tryb otwarty nie wpuszcza na te role bez tokenu. Agenci pojawiaja
    sie na kanale, gdy WEJDA — tryb otwarty nadaje im wolny nick."""
    d, _ = cli.ensure_hub("bez-zespolu", 8953)
    tokens = json.loads((d / "tokens.json").read_text())
    agenci = {n: v for n, v in tokens.items() if v["role"] == "agent"}
    assert agenci == {}, \
        f"hub nadal obsadza etaty, ktorych nikt nie zajal: {sorted(agenci)}"
    assert set(tokens) == {"human"}, \
        f"swiezy pokoj zna tozsamosci spoza operatora: {sorted(tokens)}"


def test_karta_nie_hardkoduje_rol_wykonawczych(home, capsys):
    """Karta wejsciowa to pierwsza rzecz, ktora czlowiek wkleja agentowi.
    Gdy podaje `CHAT_NICK=worker1`, uczy ustroju, zanim ktokolwiek wszedl."""
    cli.ensure_hub("karta", 8954)
    tokens, _ = cli.load_tokens("karta")
    cli.print_card("karta", 8954, tokens)
    out = capsys.readouterr().out
    assert "worker1" not in out and "worker2" not in out, \
        "karta uczy nazw wykonawczych"
    assert "orchestrator" not in out.lower()
    # POZYTYWNIE: karta ma nadal DZIALAC. Sam negatyw przepuscilby karte
    # pusta — a wtedy czlowiek nie ma czego wkleic agentowi (zlapane przy
    # review E1).
    assert "agent1" in out, "karta nie podaje zadnego uczestnika"
    assert "agentmachi listen" in out, "karta nie mowi, jak wejsc"
    # Zmienil sie JEZYK karty, nie kontrakt.
    assert "join agentmachi" in out, "brak zdania do wklejenia agentowi"


def test_howto_niesie_mechanike_a_nie_kulture_pracy():
    """Howto idzie DRUTEM do kazdego wchodzacego i przy kazdym reconnect.
    Ma opisywac protokol, ktorego agent nie odkryje sam bez straty — nie
    uczyc, jak dzielic prace, kiedy ustepowac i co robic po trzeciej
    nieudanej probie. To sa decyzje organizacyjne, czyli pastuch.

    Zmierzone przed cieciem: rules 4515 + howto 12964 = 17479 znakow
    (~4400 tokenow) przy KAZDYM hello i KAZDYM reconnect.

    Test ma DWIE polowki i obie sa konieczne. Pierwsza wersja miala tylko
    negatywna — czyli pusty plik dawal green, a "hub nie wysyla nic" nie jest
    tym samym, co "hub wysyla mechanike". Zlapane przez drugiego agenta przy
    review E1. Limit liczymy w BAJTACH, bo drutem ida bajty, a polski znak
    w UTF-8 wazy dwa."""
    from pathlib import Path as _P
    howto = (_P(cli.__file__).with_name("howto_default.md")).read_text()
    bajty = len(howto.encode("utf-8"))
    # 4096 -> 5120 (2026-08-01, decyzja operatora). Uzasadnienie i koszt:
    # patrz BUDZETY w tests/test_skills.py — plik stal 6 B pod sufitem, wiec
    # prostowanie nieprawdziwego opisu wymagalo kasowania innej tresci.
    assert bajty <= 5120, (
        f"howto ma {bajty} B — budzet drutu to 5120 B; reszta nalezy "
        f"do skilla")

    # POZYTYWNY KONTRAKT: bez tych dziewieciu rzeczy agent na obcym runtimie
    # jest technicznie zablokowany albo cicho gluchy. Tego nie odkryje sam.
    wymagane = {
        "wysylka": ["agentmachi send"],
        "nasluch": ["agentmachi listen"],
        "wait codexa": ["--once"],
        "wake dla obcych runtime": ["agentmachi node"],
        # Zmienil sie JEZYK howto, nie kontrakt: "wzmianka" -> "mention".
        "co budzi": ["mention"],
        "kursor/wznowienie": ["seq"],
        "board": ["participants", "board"],
        "wejscie bez historii": ["--fresh"],
        "tozsamosc polaczenia": ["instance_id"],
        "wyparcie": ["takeover"],
    }
    niski = howto.lower()
    brakuje = [co for co, warianty in wymagane.items()
               if not any(w.lower() in niski for w in warianty)]
    assert not brakuje, (
        f"howto nie opisuje mechaniki, ktorej agent nie odkryje sam: "
        f"{brakuje}. Pusty plik NIE jest neutralnym hubem, tylko hubem "
        f"nieuzywalnym bez naszego skilla.")

    zakazane = ["Jak pomagac", "trzecia", "ustepuj", "subagent",
                "deklaruj zakres", "review"]
    trafienia = [s for s in zakazane if s.lower() in niski]
    assert not trafienia, f"howto uczy kultury pracy, nie protokolu: {trafienia}"


def test_howto_nie_przeczy_kodowi():
    """E2.1 — howto to jedyna instrukcja, jaka dostaje agent na golym
    sockecie. Gdy klamie, nie ma sie z czym skonfrontowac.

    Dwa miejsca zglosil drugi agent przy review E2:

    1. howto twierdzilo, ze CHAT_NICK jest OBOWIAZKOWY, a cli.py wprost
       wspiera wejscie bez nicka (hub nadaje agentN) — i ten sam howto
       kilkanascie linii nizej mowil o trybie otwartym. Dokument przeczyl
       samemu sobie, wiec agent i tak musial zgadywac.
    2. howto opisywalo `status` jako tekst do 32 znakow. Tekstem jest samo
       pole `state`; `status` na boardzie to obiekt {state, subject?, note?}
       — strukture te zlapal test node'a, a howto nadal uczylo inaczej."""
    from pathlib import Path as _P
    howto = (_P(cli.__file__).with_name("howto_default.md")).read_text()
    niski = howto.lower()

    # Zmienil sie JEZYK howto (poszlo drutem po polsku do agentow, ktorzy
    # czytaja angielski), nie kontrakt. Kazda asercja pilnuje TEGO SAMEGO
    # zdania co poprzednio, tylko w angielskim zapisie.
    assert "optional" in niski, \
        "howto nie mowi, ze mozna wejsc bez nicka (a `listen` na to pozwala)"
    assert "is mandatory" not in niski and "chat_nick is required" not in niski, \
        "howto nadal twierdzi, ze nick jest wymagany"
    assert "node" in niski and "stable" in niski, \
        "howto nie odroznia `listen` (nick opcjonalny) od `node` (wymaga nicka)"
    assert "--once" in niski and "interactive" in niski, \
        "howto nie prowadzi Codexa do biezacego interaktywnego watku"
    # "nie" bylo w polskiej wersji asercja-atrapa (kazdy polski tekst je ma).
    # Angielski odpowiednik pilnuje realnego zdania: koniec komendy NIE budzi.
    assert "goal mode" in niski and "does not wake" in niski, \
        "howto obiecuje wake modelu bez aktywnego celu"
    assert "codex exec" in niski, \
        "howto nie odroznia celu biezacego watku od osobnego runtime'u"
    assert "node" in niski and "does not resume" in niski, \
        "howto sugeruje, ze node wznawia otwarty interaktywny watek"

    assert '"state"' in howto or "`state`" in howto, \
        "howto nie nazywa pola `state`"
    # Dawny negatyw pilnowal JEDNEGO polskiego zdania ze zlamaniem wiersza —
    # po tlumaczeniu nie ma czego szukac. Zostaje mocniejszy pozytyw: howto
    # ma nazwac `status` obiektem wprost, a nie tylko uzyc slowa "object".
    assert "`status` is an object" in niski, \
        "howto nie mowi, ze `status` jest strukturą (a nie plaskim tekstem)"


def test_tui_env_eksportuje_nazwe_huba(home, monkeypatch):
    """TUI musi wiedziec, KTORYM pokojem jest — inaczej `/stop` nie ma czego
    zatrzymac. CHAT_URL nie wystarcza: cykl zycia huba jest NAZWANY, a
    pidfile lezy w ~/.agentmachi/<nazwa>/."""
    cli.ensure_hub("alpha", 8931, bind="127.0.0.1")
    monkeypatch.delenv("AGENTMACHI_HUB", raising=False)
    cli._tui_env("alpha")
    assert os.environ["AGENTMACHI_HUB"] == "alpha"


def test_stop_hub_zwraca_powod_zamiast_drukowac(home):
    """Jeden kontrakt, dwa ujscia: CLI wypisuje na stderr, TUI w logu
    wiadomosci. Gdyby stop_hub drukowal sam, TUI musialoby przechwytywac
    stdout albo miec wlasna kopie logiki."""
    cli.ensure_hub("alpha", 8931)
    ok, komunikat = cli.stop_hub("alpha")
    assert ok is False
    # Zmienil sie JEZYK komunikatu, nie kontrakt.
    assert "is not running" in komunikat


def test_cmd_stop_uzywa_stop_hub(home, monkeypatch, capsys):
    """Dowod przez zepsucie: gdyby cmd_stop trzymal wlasna kopie logiki,
    podmiana stop_hub nie zmienilaby jego wyniku i ten test przeszedlby
    na rozjechanych implementacjach."""
    cli.ensure_hub("alpha", 8931)
    monkeypatch.setattr(cli, "stop_hub", lambda name: (True, f"udalo: {name}"))

    class Args:
        name = "alpha"
    assert cli.cmd_stop(Args()) == 0
    assert "udalo: alpha" in capsys.readouterr().out


def test_delete_hub_wymaga_nazwy_jako_potwierdzenia(home):
    """Potwierdzeniem jest POWTORZONA NAZWA, nie flaga: flage dopisuje sie
    odruchowo, a nazwe trzeba przeczytac. Operacja jest nieodwracalna."""
    cli.ensure_hub("pokoj", 8931)
    ok, kom = cli.delete_hub("pokoj", None)
    # Zmienila sie NAZWA flagi (--tak-kasuj -> --yes-delete), nie kontrakt.
    assert ok is False and "--yes-delete pokoj" in kom
    ok, _ = cli.delete_hub("pokoj", "zla-nazwa")
    assert ok is False
    assert cli.hub_dir("pokoj").exists(), "odmowa skasowala katalog"
    ok, _ = cli.delete_hub("pokoj", "pokoj")
    assert ok is True
    assert not cli.hub_dir("pokoj").exists()


def test_cmd_del_uzywa_delete_hub(home, monkeypatch, capsys):
    """Dowod przez zepsucie: gdyby cmd_del trzymal wlasna kopie logiki,
    podmiana delete_hub nie zmienilaby jego wyniku."""
    cli.ensure_hub("pokoj", 8931)
    monkeypatch.setattr(cli, "delete_hub",
                        lambda nazwa, potw: (True, f"skasowano {nazwa}"))
    rc = cli.cmd_del(argparse.Namespace(name="pokoj", confirm="pokoj"))
    assert rc == 0
    assert "skasowano pokoj" in capsys.readouterr().out


def test_wait_until_down_nie_czeka_na_nieistniejacy_pid(home):
    """Martwy PID jest 'zszedl' natychmiast. Gdyby petla czekala pelny
    STOP_WAIT, `/kill` w TUI zamarzalby na 10 s przy kazdym uzyciu."""
    import time as _t
    start = _t.monotonic()
    assert cli.wait_until_down(2 ** 31 - 1, timeout=5.0) is True
    assert _t.monotonic() - start < 1.0


def test_del_zabiera_ze_soba_kursory_klientow(home, monkeypatch, tmp_path):
    """Kursor klienta jest per host:port, a port po skasowanym pokoju wraca
    do puli. Kursor, ktory przezyl swoj log, trafia na NASTEPNY hub pod tym
    adresem i wywala go bledem "last_seq N > serwerowy last_seq 0" — czyli
    w miejscu, ktore z przyczyna nie ma nic wspolnego.

    Sprzatane sa nicki z tokens.json ORAZ ze snapshotu rejestru, wiec takze
    ci, ktorzy weszli bez tokenu i nigdy nie byli w pliku."""
    from chat.client_session import Session, session_files
    sesje = tmp_path / "sesje"
    monkeypatch.setenv("CHAT_SESSION_DIR", str(sesje))
    d, port = cli.ensure_hub("pokoj", 8931)
    hub_id = f"localhost:{port}"

    # `human` jest w tokens.json; `agent7` wszedl bez tokenu — istnieje
    # wylacznie w snapshocie rejestru.
    (d / "data").mkdir(parents=True, exist_ok=True)
    (d / "data" / "snapshot.json").write_text(json.dumps(
        {"snapshot_seq": 4, "state": {"registry": {"gen": {"agent7": 1}}}}))
    for nick in ("human", "agent7"):
        Session(hub_id, nick, base_dir=sesje).advance(11)
    assert all(session_files(hub_id, n, sesje)[0].exists()
               for n in ("human", "agent7"))

    ok, kom = cli.delete_hub("pokoj", "pokoj")
    # Zmienil sie JEZYK komunikatu, nie kontrakt: `del` nadal ma powiedziec,
    # ile plikow kursora zabral ze soba.
    assert ok is True and "cursor files" in kom, kom
    for nick in ("human", "agent7"):
        assert not session_files(hub_id, nick, sesje)[0].exists(), \
            f"kursor {nick} przezyl skasowanie pokoju"


def test_purge_cursors_nie_rusza_kursorow_innego_pokoju(home, monkeypatch,
                                                        tmp_path):
    """Sprzatanie idzie po hub_id (host:port), wiec pokoj obok musi zostac
    nietkniety. Bez tego `del` jednego pokoju zerowalby kursory wszystkich."""
    from chat.client_session import Session, session_files
    sesje = tmp_path / "sesje"
    monkeypatch.setenv("CHAT_SESSION_DIR", str(sesje))
    _, port_a = cli.ensure_hub("a", 8931)
    _, port_b = cli.ensure_hub("b", 8932)
    obcy = f"localhost:{port_b}"
    Session(f"localhost:{port_a}", "human", base_dir=sesje).advance(3)
    Session(obcy, "human", base_dir=sesje).advance(9)

    cli.delete_hub("a", "a")
    assert session_files(obcy, "human", sesje)[0].exists(), \
        "skasowanie pokoju 'a' zabralo kursor pokoju 'b'"


def test_howto_podaje_kontrakt_odpowiedzi_hello():
    """Klientow jest tylu, ilu wejdzie — hub to transport, a `howto` jest
    JEDYNA instrukcja, jaka dostaje ktos z samym socketem.

    Trzy bugi naprawione 2026-07-31 w tui.py byly w rzeczywistosci brakami
    TEGO pliku: serwer wysyla `last_seq`, `conversation` i `takeover`, a howto
    nie mowilo o nich nic. Kazdy nowy klient popelnilby te same trzy bledy —
    TUI bylo tylko tym, ktory je mial. Wspolny modul w Pythonie pomoglby
    trzem implementacjom w tym repo; howto pomaga wszystkim, takze napisanym
    w innym jezyku przez kogos innego."""
    from pathlib import Path as _P
    howto = (_P(cli.__file__).with_name("howto_default.md")).read_text(
        encoding="utf-8")

    assert "last_seq" in howto, \
        "howto nie mowi, ze kursor idzie na last_seq z odpowiedzi — klient " \
        "ufajacy ostatniej ramce backlogu zamraza kursor (serwer wycina hello)"
    assert "conversation" in howto, \
        "howto nie wspomina o `conversation` w resync — klient pokaze pusty " \
        "czat po kompakcji, mimo ze rozmowa przyszla drutem"
    # Zmienil sie JEZYK howto, nie kontrakt: "tylko do ludzi" -> "to humans
    # only".
    assert "takeover" in howto and "to humans only" in howto, \
        "howto nie mowi, ze takeover leci na zywo TYLKO do ludzi — " \
        "zignorowany przez jedynego adresata daje agenta-widmo"


def test_del_zabiera_kursor_agenta_ktorego_nie_ma_w_snapshocie(home, monkeypatch,
                                                               tmp_path):
    """Hub, ktory padl bez `stop`, nie zdazyl dopisac swojego snapshotu —
    agent, ktory wszedl po ostatnim, istnieje wtedy WYLACZNIE w events.jsonl.
    Bez czytania logu jego kursor przezywal pokoj i wybuchal dopiero pod
    nastepnym hubem na tym porcie (zlapane 2026-07-31, review Codexa)."""
    from chat.client_session import Session, session_files
    sesje = tmp_path / "sesje"
    monkeypatch.setenv("CHAT_SESSION_DIR", str(sesje))
    d, port = cli.ensure_hub("pokoj", 8933)
    hub_id = f"localhost:{port}"

    (d / "data").mkdir(parents=True, exist_ok=True)
    (d / "data" / "snapshot.json").write_text(json.dumps(
        {"snapshot_seq": 2, "state": {"registry": {"gen": {}}}}))
    # log: hello agenta PO snapshocie + ogon uciety crashem
    (d / "data" / "events.jsonl").write_text(
        json.dumps({"type": "hello", "seq": 3, "from": "agent9",
                    "instance_id": "i9"}) + "\n"
        + json.dumps({"type": "membership_set", "seq": 4, "from": "human",
                      "target": "agent9", "groups": ["admin"]}) + "\n"
        + '{"type": "chat", "seq": 5, "fr', encoding="utf-8")
    Session(hub_id, "agent9", base_dir=sesje).advance(11)

    ok, _ = cli.delete_hub("pokoj", "pokoj")
    assert ok is True
    assert not session_files(hub_id, "agent9", sesje)[0].exists(), \
        "kursor agenta znanego tylko z logu przezyl skasowanie pokoju"


def test_nicki_pokoju_pomija_server_i_znosi_zepsuty_log(home, tmp_path):
    """`from: server` to nadawca ramek systemowych, nie uczestnik — nie ma
    sesji do sprzatania. Uciety ogon logu (crash w trakcie zapisu) nie moze
    przerwac sprzatania reszty."""
    d, _ = cli.ensure_hub("pokoj", 8934)
    (d / "data").mkdir(parents=True, exist_ok=True)
    (d / "data" / "events.jsonl").write_text(
        json.dumps({"type": "takeover", "seq": 1, "from": "server",
                    "target": "agent1"}) + "\n"
        + "{ to nie jest json\n"
        + json.dumps({"type": "chat", "seq": 2, "from": "agent2"}) + "\n",
        encoding="utf-8")
    nicki = cli._nicki_pokoju("pokoj")
    assert "server" not in nicki
    assert {"agent1", "agent2"} <= nicki


def test_send_konczy_sie_czytelnym_bledem_zamiast_tracebackiem(home, monkeypatch,
                                                               capsys):
    """Odbiorca tego komunikatu to AGENT — ma z niego wyciagnac, co zrobic
    inaczej. Stos wywolan mu w tym nie pomaga, tylko zjada kontekst.

    Pokoj tworzymy JAWNIE: test bada granice bledu klienta PO wejsciu do
    pokoju, a wczesniej trzymal sie tylko dlatego, ze _agent_env zgadywalo
    DEFAULT_PORT dla nieistniejacego 'pokoj'. Kontrakt testu sie nie zmienil,
    zmienil sie jego setup — zgadywanie portu to teraz blad."""
    cli.ensure_hub("pokoj", 8931)
    class _Send:
        SessionError = cli._import_send().SessionError

        @staticmethod
        async def send_once(nick, text, quiet=False):
            raise _Send.SessionError("ramka ma 70057 B, sufit huba to 65536 B")

    monkeypatch.setattr(cli, "_import_send", lambda: _Send)
    args = argparse.Namespace(name="pokoj", as_nick="agent1", text="x",
                              nick=None, quiet=False, legacy_text=None)
    assert cli.cmd_send(args) == 1
    err = capsys.readouterr().err
    assert "agentmachi send:" in err and "sufit huba" in err
    assert "Traceback" not in err


def test_frame_konczy_sie_czytelnym_bledem_zamiast_tracebackiem(home, monkeypatch,
                                                                capsys):
    """Ta sama granica co w cmd_send. `cli.main` lapie tylko CliError, wiec
    SendTooLarge z oneshot_frame wychodzilo stosem — a `frame` jest komenda
    AGENTOWA, wiec traceback ladowal prosto w jego kontekscie.

    Pokoj tworzymy JAWNIE — patrz komentarz w tescie wyzej."""
    cli.ensure_hub("pokoj", 8931)
    class _Send:
        SessionError = cli._import_send().SessionError

        @staticmethod
        async def oneshot_frame(nick, frame):
            raise _Send.SessionError("ramka ma 70057 B, sufit huba to 65536 B")

    monkeypatch.setattr(cli, "_import_send", lambda: _Send)
    monkeypatch.setenv("CHAT_NICK", "agent1")
    args = argparse.Namespace(name="pokoj", nick="agent1",
                              json='{"type":"status","state":"idle"}')
    assert cli.cmd_frame(args) == 1
    err = capsys.readouterr().err
    assert "agentmachi frame:" in err and "sufit huba" in err
    assert "Traceback" not in err


# --- auto-odswiezanie howto (decyzja czlowieka 2026-08-01) ----------------

def _wzorzec_howto():
    from pathlib import Path as _P
    return (_P(cli.__file__).with_name("howto_default.md")).read_text(
        encoding="utf-8")


def test_howto_powstaje_ze_wzorca_i_dostaje_znacznik(home):
    d, _ = cli.ensure_hub("nowy", 8951)
    howto = d / "data" / "howto.md"
    assert howto.read_text(encoding="utf-8") == _wzorzec_howto()
    assert (d / "data" / cli.HOWTO_ZNACZNIK).exists(), \
        "brak znacznika — nastepny start nie odrozni naszego tekstu od cudzego"


def test_stary_pokoj_dostaje_aktualne_howto_przy_starcie(home):
    """POWOD ISTNIENIA TEGO MECHANIZMU, zmierzony na zywym pokoju 2026-08-01:
    hub serwowal zdanie o wypieraniu nicka, obalone pomiarem i poprawione
    w repo tego samego dnia. Poprawka byla w gicie i nie docierala do nikogo,
    bo howto kopiowalo sie WYLACZNIE gdy pliku nie bylo."""
    d, _ = cli.ensure_hub("stary", 8952)
    howto = d / "data" / "howto.md"
    # symulacja pokoju zalozonego dawniej: nasz tekst, ale STARSZY
    howto.write_text("STARE howto z dnia zalozenia pokoju\n", encoding="utf-8")
    (d / "data" / cli.HOWTO_ZNACZNIK).write_text(
        cli._hash_tekstu("STARE howto z dnia zalozenia pokoju\n"),
        encoding="utf-8")

    stan, kopia = cli.odswiez_howto(d)
    assert stan == "odswiezone" and kopia is None
    assert howto.read_text(encoding="utf-8") == _wzorzec_howto()


def test_reczna_zmiana_nie_ginie_po_cichu(home):
    """Nadpisujemy, ale NIGDY bez sladu: tekst czlowieka laduje obok,
    a wolajacy dostaje sciezke do pokazania mu."""
    d, _ = cli.ensure_hub("wlasny", 8953)
    howto = d / "data" / "howto.md"
    howto.write_text("MOJ WLASNY tekst, ktorego nie chce stracic\n",
                     encoding="utf-8")

    stan, kopia = cli.odswiez_howto(d)
    assert stan == "zachowane"
    assert kopia is not None and kopia.exists()
    assert kopia.read_text(encoding="utf-8") == \
        "MOJ WLASNY tekst, ktorego nie chce stracic\n"
    assert howto.read_text(encoding="utf-8") == _wzorzec_howto()


def test_pokoj_sprzed_znacznika_tez_nie_traci_tekstu(home):
    """Pokoj zalozony PRZED tym mechanizmem nie ma znacznika, wiec nie da sie
    orzec, czy tekst jest nasz czy cudzy. Fail-safe: traktujemy jak cudzy —
    odswiezamy, ale zostawiamy kopie."""
    d, _ = cli.ensure_hub("bezznacznika", 8954)
    (d / "data" / cli.HOWTO_ZNACZNIK).unlink()
    (d / "data" / "howto.md").write_text("tekst bez rodowodu\n",
                                         encoding="utf-8")

    stan, kopia = cli.odswiez_howto(d)
    assert stan == "zachowane" and kopia is not None
    assert kopia.read_text(encoding="utf-8") == "tekst bez rodowodu\n"


def test_aktualne_howto_nie_produkuje_kopii_przy_kazdym_starcie(home):
    """Idempotencja: dziesiec restartow nie moze zostawic dziesieciu kopii
    ani raz po raz przepisywac pliku."""
    d, _ = cli.ensure_hub("stabilny", 8955)
    for _ in range(10):
        stan, kopia = cli.odswiez_howto(d)
        assert stan == "aktualne" and kopia is None
    assert not (d / "data" / "howto.md.zastapione").exists()


def test_ensure_hub_nie_rusza_rules(home):
    """`rules` to tekst POKOJU i to on jest punktem, w ktorym wypowiada sie
    czlowiek — odswiezanie howto nie moze go dotknac."""
    d, _ = cli.ensure_hub("zrules", 8956)
    rules = d / "data" / "rules.md"
    rules.write_text("zasady tego pokoju, moje\n", encoding="utf-8")
    cli.ensure_hub("zrules", 8956)
    assert rules.read_text(encoding="utf-8") == "zasady tego pokoju, moje\n"


# --- Windows: produkt ma powiedziec prawde o sobie ----------------------
# Zgloszone z pomiaru na Windows 11 (issue #2): `pip install agentmachi`
# DZIALA, wiec ludzie tam trafiaja — a warstwa wykrywania procesow nie ma
# tam ani /proc, ani `ps` (w PowerShell `ps` to alias na Get-Process, nie
# plik wykonywalny). Skutek: `start` wypisuje "did NOT come up" i kasuje
# pidfile ZYWEGO huba, `list` pokazuje "stopped", `stop` mowi "is not
# running" — a hub caly czas nasluchuje.
#
# Naprawa wsparcia to osobna, duza robota. Tu naprawiamy JEDNO: czlowiek
# ma wiedziec, ze wszedl na niesprawdzona platforme, a nie ze produkt jest
# zepsuty. Warunek zakonczenia to komunikat, nie odmowa — komendy dzialaja
# dalej, bo hub naprawde wstaje.

_KOMENDY_ZALEZNE_OD_PROCESOW = [
    ["list"],
    ["stop", "--name", "wintest"],
    ["kill", "nic-takiego-nie-ma-na-tej-maszynie", "--dry-run"],
    ["start", "--name", "wintest", "--port", "8766"],
    ["restart", "--name", "wintest", "--port", "8766"],
]


@pytest.fixture
def _start_bez_spawnu(monkeypatch):
    """`start`/`restart` maja odbic sie od zajetego portu, zanim cokolwiek
    odpala. Testujemy komunikat platformy, nie stawianie huba."""
    monkeypatch.setattr(cli, "_port_accepts", lambda port, bind: True)


@pytest.mark.parametrize("argv", _KOMENDY_ZALEZNE_OD_PROCESOW,
                         ids=lambda a: a[0])
def test_windows_ostrzega_przed_komenda_zalezna_od_procesow(
        argv, home, monkeypatch, capsys, _start_bez_spawnu):
    monkeypatch.setattr(cli.sys, "platform", "win32")
    cli.main(argv)
    err = capsys.readouterr().err
    assert "Windows" in err, "nazwij platforme wprost"
    assert "https://github.com/emilszymecki/agentmachi/issues/2" in err, \
        "bez linku czlowiek nie ma gdzie sprawdzic, czy to znany problem"


@pytest.mark.parametrize("argv", _KOMENDY_ZALEZNE_OD_PROCESOW,
                         ids=lambda a: a[0])
def test_linux_nie_ostrzega_o_platformie(argv, home, monkeypatch, capsys,
                                         _start_bez_spawnu):
    """Ostrzezenie na wspieranej platformie to szum, ktory uczy je ignorowac."""
    monkeypatch.setattr(cli.sys, "platform", "linux")
    cli.main(argv)
    err = capsys.readouterr().err
    assert "issues/2" not in err
    assert "not supported" not in err


def test_windows_nie_podpowiada_ss_tlnp(home, monkeypatch, capsys,
                                        _start_bez_spawnu):
    """`ss` nie istnieje na Windows — podpowiedz z nieistniejaca komenda jest
    gorsza niz jej brak, bo zabiera czlowiekowi jedyny trop."""
    monkeypatch.setattr(cli.sys, "platform", "win32")
    cli.ensure_hub("wintest", 8766)
    rc = cli.main(["start", "--name", "wintest", "--port", "8766"])
    err = capsys.readouterr().err
    assert rc == 1 and "taken by another process" in err
    assert "ss -tlnp" not in err
