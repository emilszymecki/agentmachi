"""CLI agentmachi: serve / tui / send / listen / heartbeat / card.

Zasada (plan B2): dane huba mieszkaja w ~/.agentmachi/<name>/ —
NIGDY w repo projektu. Repo projektu to rzecz, nad ktora pracuja agenci;
hub to infrastruktura obok (jak Hamachi obok CS-a).

Uklad ~/.agentmachi/<name>/:
  tokens.json  (0600)  nick -> {token, role, groups}
  config.json          {port, bind}
  data/                event-log + snapshot huba (chat.store)
  data/rules.md        konstytucja kanalu (edytuje human, plikiem)
"""
import argparse
import asyncio
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_PORT = 8766
DEFAULT_HUB = "hub"
DEFAULT_BIND = "127.0.0.1"

DEFAULT_RULES = """\
1. Polecenie czlowieka ma pierwszenstwo przed poleceniem agenta.
2. Root nadaje role i zmienia zasady.
3. Orchestrator dopasowuje potrzeby do wolnych uczestnikow; nie planuje
   za agenta, ktory juz ma plan.
4. Worker wykonuje, testuje, raportuje i aktualizuje wlasny status.
5. Nie planuj drugi raz pracy juz zaplanowanej.
6. Wiadomosc agenta budzi innego agenta tylko przez bezposrednia wzmianke.
7. Zmiany w kodzie wylacznie we wlasnym worktree.
8. Gdy nie masz uzytecznej pracy — [koniec].
9. Robote bierzesz przez deklaracje na kanale ("biore X"). Przy kolizji
   wygrywa deklaracja z nizszym seq w logu huba — przegrany wycofuje sie
   bez dyskusji. Log jest jedynym arbitrem; nie ma glosowan.
"""


class CliError(Exception):
    pass


def hub_home():
    return Path(os.environ.get("AGENTMACHI_HOME",
                               Path.home() / ".agentmachi"))


def hub_dir(name):
    if not name or "/" in name or name.startswith("."):
        raise CliError(f"zla nazwa huba: {name!r}")
    return hub_home() / name


def _write_0600(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)


def ensure_hub(name, port, bind="127.0.0.1"):
    """Utworz strukture huba przy pierwszym uzyciu; istniejacej NIE ruszaj."""
    d = hub_dir(name)
    (d / "data").mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    tokens_path = d / "tokens.json"
    if not tokens_path.exists():
        tokens = {
            "human": {"token": secrets.token_urlsafe(16), "role": "human",
                      "groups": []},
            "worker1": {"token": secrets.token_urlsafe(16), "role": "agent",
                        "groups": ["workers"]},
            "worker2": {"token": secrets.token_urlsafe(16), "role": "agent",
                        "groups": ["workers"]},
        }
        _write_0600(tokens_path, json.dumps(tokens, indent=2))
    rules_path = d / "data" / "rules.md"
    if not rules_path.exists():
        rules_path.write_text(DEFAULT_RULES)
    # F5 (B5): howto ma dojsc do agenta PROTOKOLEM (hub czyta ten plik i
    # doklada do hello) — plik w repo jest bezuzyteczny dla klienta, ktory
    # ma tylko socket. Szablon idzie z pakietu; human moze go nadpisac.
    howto_path = d / "data" / "howto.md"
    if not howto_path.exists():
        howto_path.write_text(
            (Path(__file__).with_name("howto_default.md")).read_text())
    config_path = d / "config.json"
    if config_path.exists():
        port = json.loads(config_path.read_text()).get("port", port)
    else:
        config_path.write_text(json.dumps({"port": port, "bind": bind}))
    return d, port


def load_tokens(name):
    d = hub_dir(name)
    tokens_path = d / "tokens.json"
    if not tokens_path.exists():
        raise CliError(f"hub {name!r} nie istnieje (brak {tokens_path}); "
                       f"najpierw: agentmachi serve --name {name}")
    return json.loads(tokens_path.read_text()), d


def hub_port(name, fallback=DEFAULT_PORT):
    config = hub_dir(name) / "config.json"
    if config.exists():
        return json.loads(config.read_text()).get("port", fallback)
    return fallback


def hub_bind(name, fallback=DEFAULT_BIND):
    config = hub_dir(name) / "config.json"
    if config.exists():
        return json.loads(config.read_text()).get("bind", fallback)
    return fallback


# --- cykl zycia huba (F6 UX + F7 split-brain) ---------------------------
# Jeden komputer = wiele kanalow (projektow) na wielu portach. Bez listingu
# i bez blokady podwojnego startu operator nie ma jak stwierdzic, co u niego
# dziala — zmierzone bolesnie: pkill nie ubil starego huba, `serve` postawil
# drugi obok, dwa procesy pisaly do jednego katalogu (split-brain).

def _cmdline_of(pid):
    """Linia polecen procesu albo None, gdy go nie ma. Wydzielone, zeby
    test mogl podstawic cudzy proces bez zabawy w prawdziwe PID-y."""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return None
    return raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()


def _pid_is_our_hub(pid, name):
    """Czy PID to NA PEWNO hub tego kanalu? Pidfile bywa nieaktualny, a PID-y
    sa recyklowane — bez tej kontroli `stop` moglby ubic cudzy proces."""
    cmd = _cmdline_of(pid)
    if not cmd:
        return False
    return ("agentmachi" in cmd or "chat.server" in cmd) and name in cmd


_SHELLS = ("zsh", "bash", "sh", "dash", "fish", "setsid", "nohup", "timeout", "env")


def _ancestor_pids():
    """My i wszyscy nasi przodkowie. Skaner nie ma prawa uznac zadnego z nich
    za "juz dzialajacy hub" — to nie inny serwer, to my w drodze do startu."""
    out = set()
    cur = os.getpid()
    while cur and cur > 1 and cur not in out:
        out.add(cur)
        try:
            status = Path(f"/proc/{cur}/status").read_text()
        except OSError:
            break
        ppid = next((l.split()[1] for l in status.splitlines()
                     if l.startswith("PPid:")), None)
        cur = int(ppid) if ppid and ppid.isdigit() else 0
    return out


def _is_shell_wrapper(pid):
    """Czy proces to powloka/opakowanie odpalajace polecenie, a nie sam hub?

    `zsh -c "... agentmachi serve --name X"` ma cale polecenie we wlasnym
    argv, wiec kazdy wzorzec tekstowy trafia w niego tak samo jak w prawdziwy
    serwer. Rozstrzygamy po PLIKU WYKONYWALNYM, nie po tresci argumentow —
    argv klamie, exe nie."""
    try:
        exe = os.path.basename(os.readlink(f"/proc/{pid}/exe"))
    except OSError:
        return False           # brak dostepu: nie zgadujemy, decyduje wzorzec
    return any(exe == s or exe.startswith(s) for s in _SHELLS)


def _scan_hub_pid(name):
    """Znajdz zywy hub tego kanalu po procesach, bez pidfile.

    F8 (B5): pidfile nie jest zrodlem prawdy o tym, czy hub zyje. Nie ma go
    dla hubow wystartowanych przed F6, znika przy recznym sprzataniu katalogu
    i nie powstaje, gdy ktos odpali serwer inaczej niz przez `serve`. Sam brak
    pliku raportowany jako "zatrzymany" jest grozny w JEDNA strone: kusi, zeby
    postawic drugi hub na tym samym katalogu — czyli split-brain z F7, ktory
    16:05 zzarl nam rozmowe. Dlatego przy braku pidfile pytamy system.
    """
    proc = Path("/proc")
    if not proc.is_dir():          # nie-Linux: zostajemy przy pidfile
        return None
    # REGRESJA z produkcji: startujacy hub pytal "czy juz dzialam?", skaner
    # znajdowal JEGO WLASNY proces (cmdline pasuje idealnie) i serve odmawial
    # startu — hub nie mogl wstac w ogole. Ten sam wzorzec, co pkill -f
    # trafiajacy we wlasny wrapper powloki. Wlasny PID jest zawsze wykluczony.
    # ...a razem z nim CALE nasze drzewo przodkow. Wrapper powloki
    # (`zsh -c "... serve --name X"`, setsid, nohup) trzyma cale polecenie
    # we WLASNYM argv, wiec pasuje do wzorca rownie dobrze jak prawdziwy hub.
    # Bez tego startujacy przez powloke hub znajduje swojego rodzica i znow
    # odmawia startu — ta sama pulapka, tylko o jedno pietro wyzej.
    mine = _ancestor_pids()
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid in mine or _is_shell_wrapper(pid):
            continue
        cmd = _cmdline_of(pid)
        if not cmd or "serve" not in cmd:
            continue
        if _pid_is_our_hub(pid, name):
            return pid
    return None


def hub_pid(name):
    """PID zywego huba albo None. Martwy pidfile sprzatamy od razu — inaczej
    `list` klamie, ze kanal dziala. Gdy pidfile nie ma, a proces jest,
    dowiadujemy sie tego ze skanu (patrz _scan_hub_pid): lepiej powiedziec
    'dziala' bez pliku niz 'zatrzymany' o zywym hubie."""
    path = hub_dir(name) / "hub.pid"
    if not path.exists():
        return _scan_hub_pid(name)
    try:
        pid = int(path.read_text().strip())
    except (ValueError, OSError):
        path.unlink(missing_ok=True)
        return _scan_hub_pid(name)
    if _cmdline_of(pid) is None:
        path.unlink(missing_ok=True)
        return _scan_hub_pid(name)
    # UWAGA (poza zakresem F8, zgloszone osobno): nie sprawdzamy tu, czy PID
    # to NA PEWNO nasz hub. PID-y sa recyklowane, wiec nieaktualny pidfile
    # wskazujacy na cudzy zywy proces daje falszywe "dziala". `stop` jest
    # na to odporny (_pid_is_our_hub przed zabiciem), `list` jeszcze nie.
    return pid


def write_hub_pid(name):
    (hub_dir(name) / "hub.pid").write_text(str(os.getpid()))


def hub_rows():
    """Stan wszystkich kanalow tego uzytkownika — zrodlo dla `list`."""
    home = hub_home()
    if not home.exists():
        return []
    rows = []
    for d in sorted(p for p in home.iterdir() if p.is_dir()):
        name = d.name
        if not (d / "tokens.json").exists():
            continue
        pid = hub_pid(name)
        try:
            tokens = json.loads((d / "tokens.json").read_text())
            nicks = sorted(tokens)
        except (json.JSONDecodeError, OSError):
            nicks = []
        rows.append({"name": name, "port": hub_port(name),
                     "bind": hub_bind(name), "pid": pid,
                     "running": pid is not None,
                     # hub bez pidfile dziala, ale `stop` nie zostawi po sobie
                     # sladu w katalogu — user ma to widziec, a nie zgadywac
                     "pidfile": (d / "hub.pid").exists(),
                     "nicks": nicks, "dir": d})
    return rows


def connect_host(bind):
    """Adres POLACZENIOWY != bind: bind loopback/wildcard laczy sie lokalnie
    po 'localhost' (a) zachowuje dotychczasowy hub_id 'localhost:<port>' —
    kursory zywych sesji w ~/.chat-sessions/ przezywaja upgrade (hub sprzed
    B3 ma config bez 'bind' i dostaje fallback loopback tutaj), (b) nie
    drukuje na karcie nieroutowalnego ws://0.0.0.0:... . Prawdziwy adres
    tailnetu/publiczny (np. 100.x.y.z) zostaje bez zmian."""
    return "localhost" if bind in ("127.0.0.1", "0.0.0.0", "localhost") else bind


def print_card(name, port, tokens, participants=None, bind=DEFAULT_BIND):
    """Karta wejsciowa: wszystko, czego potrzebuje czlowiek i agenci."""
    d = hub_dir(name)
    addr = f"ws://{connect_host(bind)}:{port}"
    print(f"""
=== agentmachi: hub '{name}' ===
adres:   {addr}
tokeny:  {d / 'tokens.json'}  (0600 — nie commituj!)
rules:   {d / 'data' / 'rules.md'}
dane:    {d / 'data'}
""")
    if bind == "0.0.0.0":
        print("uwaga: bind na wszystkie interfejsy — z innego hosta uzyj "
              "adresu maszyny w tailnecie (patrz README: Zdalny hub)\n")
    print("uczestnicy (config):")
    for nick, entry in tokens.items():
        role = entry.get("role", "agent")
        groups = ",".join(entry.get("groups", [])) or "-"
        line = f"  {nick}  {role}  [{groups}]"
        if participants:
            live = {p["nick"]: p for p in participants}
            if live.get(nick, {}).get("connected"):
                status = (live[nick].get("status") or {}).get("state", "")
                line += f"  ONLINE {status}".rstrip()
        print(line)
    print(f"""
czlowiek (TUI):
  agentmachi tui --name {name}

agent dolacza (nasluch + wysylka; wklej agentowi jedno z ponizszych):
  AGENTMACHI_HUB={name} CHAT_URL={addr} CHAT_NICK=worker1 agentmachi listen
  AGENTMACHI_HUB={name} CHAT_URL={addr} agentmachi send worker1 "czesc"
  na zdalnej maszynie dodaj CHAT_TOKEN=<token z tokens.json> (hub nie
  musi tam istniec lokalnie — patrz README: Node na zdalnej maszynie)

zdanie dla agenta (skill join):
  "dolacz do agentmachi '{name}' ({addr}) jako worker1"
""")


def _agent_env(args):
    """Zloz srodowisko klienta: hub z --name/AGENTMACHI_HUB, nick+token
    z tokens.json huba (CHAT_TOKEN z env wygrywa — nie wymuszamy pliku).
    CHAT_URL z env WYGRYWA NAD configiem lokalnym (fix C1 — na maszynie
    zdalnej, bez ~/.agentmachi/<hub>, ustawiamy tylko gdy env pusty;
    inaczej agent na VPS dostalby CHAT_URL z lokalnego configu i celowal
    w localhost zamiast w adres operatora). Gdy ustawiamy sami, adres to
    connect_host(bind) (NIE surowy bind — patrz connect_host:
    loopback/wildcard -> localhost, zeby hub_id agenta nie zmienial sie
    przy kazdym upgradzie/bindzie)."""
    name = args.name or os.environ.get("AGENTMACHI_HUB", DEFAULT_HUB)
    nick = getattr(args, "nick", None) or os.environ.get("CHAT_NICK")
    port = hub_port(name)
    bind = hub_bind(name)
    token = os.environ.get("CHAT_TOKEN", "")
    if not token:
        tokens, _ = load_tokens(name)
        if not nick or nick not in tokens:
            raise CliError(
                f"podaj nick z {hub_dir(name) / 'tokens.json'} "
                f"(--nick albo CHAT_NICK); znane: {', '.join(tokens)}")
        token = tokens[nick]["token"]
    if not os.environ.get("CHAT_URL"):
        os.environ["CHAT_URL"] = f"ws://{connect_host(bind)}:{port}"
    os.environ["CHAT_TOKEN"] = token
    os.environ["CHAT_NICK"] = nick or "listener"
    return nick


def _import_send():
    # send.py liczy URI z env przy imporcie — env MUSI byc ustawione wczesniej
    import send
    return send


def cmd_serve(args):
    # F7: fail-fast zamiast split-brain. Drugi `serve` na tej samej nazwie
    # nie dostanie portu (bind zawiedzie), ale ZDAZY otworzyc ten sam
    # katalog danych i pisac do tego samego events.jsonl — dwa procesy,
    # jeden log. Sprawdzamy PRZED czymkolwiek innym.
    running = hub_pid(args.name)
    # `agentmachi start` zapisuje hub.pid z PID-em procesu, ktory WLASNIE
    # tu jestesmy — wiec wlasny PID w pidfile nie oznacza "inny hub juz
    # dziala". Trzeci wariant tej samej pulapki w jednym dniu: dopasowanie
    # po argv (pkill), skan procesow, teraz pidfile.
    if running == os.getpid():
        running = None
    if running is not None and _pid_is_our_hub(running, args.name):
        print(f"agentmachi: hub {args.name!r} juz dziala (PID {running}). "
              f"Zatrzymaj go: agentmachi stop --name {args.name}",
              file=sys.stderr)
        return 1
    d, port = ensure_hub(args.name, args.port, bind=args.bind)
    bind = hub_bind(args.name, fallback=args.bind)
    write_hub_pid(args.name)
    tokens = json.loads((d / "tokens.json").read_text())
    print_card(args.name, port, tokens, bind=bind)
    os.environ["CHAT_TOKENS"] = str(d / "tokens.json")
    os.environ["CHAT_DATA"] = str(d / "data")
    os.environ["CHAT_PORT"] = str(port)
    os.environ["CHAT_BIND"] = bind
    from chat.server import main as server_main
    server_main()
    return 0


def cmd_list(args):
    """Co u mnie dziala? Jeden komputer = wiele kanalow na wielu portach."""
    rows = hub_rows()
    if not rows:
        print(f"brak kanalow w {hub_home()} — zaloz pierwszy: "
              f"agentmachi serve --name <nazwa>")
        return 0
    print(f"{'KANAL':<16} {'ADRES':<28} {'STAN':<24} UCZESTNICY")
    for r in rows:
        addr = f"ws://{connect_host(r['bind'])}:{r['port']}"
        if not r["running"]:
            stan = "zatrzymany"
        elif r["pidfile"]:
            stan = f"dziala (PID {r['pid']})"
        else:
            stan = f"dziala (PID {r['pid']}, bez pidfile)"
        print(f"{r['name']:<16} {addr:<28} {stan:<24} {', '.join(r['nicks'])}")
    zatrzymane = [r["name"] for r in rows if not r["running"]]
    if zatrzymane:
        print(f"\nzatrzymane mozesz odpalic: agentmachi serve --name "
              f"{zatrzymane[0]}")
    return 0


def cmd_stop(args):
    pid = hub_pid(args.name)
    if pid is None:
        print(f"agentmachi: hub {args.name!r} nie dziala", file=sys.stderr)
        return 1
    if not _pid_is_our_hub(pid, args.name):
        # Pidfile moze byc nieaktualny, a PID-y sa recyklowane przez system.
        # Lepiej odmowic i zostawic decyzje czlowiekowi niz ubic cudzy proces.
        print(f"agentmachi: PID {pid} z hub.pid NIE wyglada na hub "
              f"{args.name!r} (cmdline: {_cmdline_of(pid)!r}) — nie ubijam. "
              f"Sprawdz sam i usun {hub_dir(args.name) / 'hub.pid'}",
              file=sys.stderr)
        return 1
    os.kill(pid, signal.SIGTERM)
    print(f"agentmachi: wyslano SIGTERM do huba {args.name!r} (PID {pid})")
    return 0


# --- cykl zycia dla operatora: start / stop / list / del ----------------
# Czlowiek ma odpalac i moderowac pokoje, a nie pamietac zaklec powloki.
# Do dzis start w tle wymagal recznego `setsid nohup ... & disown` — cztery
# razy dyktowanego przez czat, raz wklejonego w zlej kolejnosci (skonczylo
# sie split-brainem). Prompt musi wrocic do czlowieka, a adres ma byc na
# ekranie.

def _spawn_detached(argv, log_path):
    """Odpal proces w tle, odpiety od terminala. Zwraca PID."""
    with open(log_path, "a") as log:
        proc = subprocess.Popen(
            argv, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
            start_new_session=True)
    return proc.pid


def _port_accepts(port, bind):
    """Czy cokolwiek przyjmuje polaczenia na tym porcie."""
    try:
        with socket.create_connection((connect_host(bind), port), timeout=0.5):
            return True
    except OSError:
        return False


READY_MARK = "chat server on"     # linia, ktora wypisuje NASZ serwer


def _wait_until_listening(port, bind, timeout=10.0, pid=None,
                          log_path=None, log_from=0):
    """Czekaj, az NASZ hub potwierdzi start WLASNYM glosem.

    KRYTYCZNE: fakt, ze port odpowiada, NIC nie dowodzi — moze go trzymac
    cudzy proces. Zdarzylo sie naprawde: nowy pokoj dostal domyslny port
    zajety przez inny serwer, nasze dziecko padlo z 'Address already in use',
    a `start` zameldowal sukces, bo polaczyl sie z TAMTYM nasluchem i wypisal
    PID trupa. Sprawdzanie samego zycia procesu tez nie wystarcza: dziecko
    zyje jeszcze przez chwile po spawnie, wiec wyscig wraca.

    Dowodem startu jest wiec linia w NASZYM logu (`chat server on ...`),
    ktora wypisuje wylacznie nasz proces po udanym bindzie.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if log_path is not None and Path(log_path).exists():
            with open(log_path) as f:
                f.seek(log_from)
                if READY_MARK in f.read():
                    return True
        if pid is not None and _cmdline_of(pid) is None:
            return False           # dziecko padlo, a linii nie ma
        time.sleep(0.15)
    return False


def cmd_start(args):
    running = hub_pid(args.name)
    if running is not None and _pid_is_our_hub(running, args.name):
        print(f"agentmachi: pokoj {args.name!r} juz dziala (PID {running}).\n"
              f"  zatrzymac:  agentmachi stop --name {args.name}\n"
              f"  zobaczyc:   agentmachi card --name {args.name}",
              file=sys.stderr)
        return 1
    d, port = ensure_hub(args.name, args.port, bind=args.bind)
    bind = hub_bind(args.name, fallback=args.bind)
    # Fail-fast na zajety port: bez tego dziecko padnie z "Address already in
    # use", a czlowiek dostanie komunikat o naszym pokoju zamiast o kolizji.
    if _port_accepts(port, bind):
        print(f"agentmachi: port {port} jest juz zajety przez inny proces — "
              f"pokoj {args.name!r} nie ma na czym wstac.\n"
              f"  sprawdz czyj to port:  ss -tlnp | grep {port}\n"
              f"  albo wybierz inny:     agentmachi start --name {args.name} "
              f"--port <inny>", file=sys.stderr)
        return 1
    log_path = d / "serve.log"
    argv = [sys.executable, "-m", "agentmachi.cli", "serve",
            "--name", args.name, "--port", str(port), "--bind", bind]
    log_before = log_path.stat().st_size if log_path.exists() else 0
    pid = _spawn_detached(argv, log_path)
    if not _wait_until_listening(port, bind, 10.0, pid=pid,
                                 log_path=log_path, log_from=log_before):
        # pidfile NIE powstaje przy nieudanym starcie — martwy plik klamalby
        # potem `list` i `stop`.
        powod = ""
        if log_path.exists():
            with log_path.open() as f:
                f.seek(log_before)
                ogon = f.read().strip().splitlines()
            if ogon:
                powod = "\n  powod: " + "\n         ".join(ogon[-3:])
        print(f"agentmachi: pokoj {args.name!r} NIE wstal.{powod}\n"
              f"  pelny log: {log_path}\n"
              f"  czy port {port} jest wolny:  agentmachi list", file=sys.stderr)
        return 1
    (d / "hub.pid").write_text(str(pid))
    tokens = json.loads((d / "tokens.json").read_text())
    print_card(args.name, port, tokens, bind=bind)
    print(f"pokoj dziala w tle (PID {pid}), log: {log_path}\n"
          f"  kto jest w srodku:  agentmachi list\n"
          f"  zatrzymac:          agentmachi stop --name {args.name}")
    return 0


def cmd_del(args):
    """Skasuj pokoj. Nieodwracalne: znikaja tokeny, rules, howto i log."""
    d = hub_dir(args.name)
    if not d.exists():
        print(f"agentmachi: pokoj {args.name!r} nie istnieje", file=sys.stderr)
        return 1
    running = hub_pid(args.name)
    if running is not None and _pid_is_our_hub(running, args.name):
        print(f"agentmachi: pokoj {args.name!r} DZIALA (PID {running}) — "
              f"najpierw: agentmachi stop --name {args.name}", file=sys.stderr)
        return 1
    if args.confirm != args.name:
        print(f"agentmachi: to skasuje pokoj {args.name!r} NA ZAWSZE "
              f"(tokeny, rules, howto, cala historia rozmowy).\n"
              f"  jesli na pewno:  agentmachi del --name {args.name} "
              f"--tak-kasuj {args.name}", file=sys.stderr)
        return 1
    shutil.rmtree(d)
    print(f"agentmachi: pokoj {args.name!r} skasowany")
    return 0


def cmd_card(args):
    name = args.name or os.environ.get("AGENTMACHI_HUB", DEFAULT_HUB)
    tokens, d = load_tokens(name)
    print_card(name, hub_port(name), tokens, bind=hub_bind(name))
    return 0


def _tui_env(name):
    """Zloz srodowisko TUI (wydzielone z cmd_tui — testowalne bez Textuala).
    I3 fix: CHAT_URL musi isc z bindu huba (connect_host(hub_bind(name))),
    nie tylko CHAT_PORT — inaczej tui.py fallbackuje do ws://localhost i
    nie polaczy sie z hubem bindowanym na adres tailnetowy. Env CHAT_URL
    WYGRYWA nad configiem lokalnym (symetrycznie do C1 w _agent_env)."""
    tokens_path = hub_dir(name) / "tokens.json"
    if not tokens_path.exists():
        raise CliError(f"hub {name!r} nie istnieje; najpierw: "
                       f"agentmachi serve --name {name}")
    os.environ["AGENTMACHI_TOKENS"] = str(tokens_path)
    port = hub_port(name)
    os.environ["CHAT_PORT"] = str(port)
    if not os.environ.get("CHAT_URL"):
        os.environ["CHAT_URL"] = f"ws://{connect_host(hub_bind(name))}:{port}"
    return tokens_path


def cmd_tui(args):
    name = args.name or os.environ.get("AGENTMACHI_HUB", DEFAULT_HUB)
    _tui_env(name)
    import tui
    return tui.main()


def cmd_send(args):
    _agent_env(args)
    send = _import_send()
    asyncio.run(send.send_once(args.nick, args.text))
    return 0


def cmd_listen(args):
    nick = _agent_env(args)
    send = _import_send()
    asyncio.run(send.listen(nick or "listener"))
    return 0


def cmd_frame(args):
    nick = _agent_env(args)
    if not nick:
        raise CliError("frame wymaga nicka (--nick albo CHAT_NICK)")
    try:
        frame = json.loads(args.json)
    except json.JSONDecodeError as e:
        raise CliError(f"zly JSON ramki: {e}")
    if not isinstance(frame, dict) or not frame.get("type"):
        raise CliError("ramka musi byc obiektem z polem type")
    send = _import_send()
    reply = asyncio.run(send.oneshot_frame(nick, frame))
    if reply is None:
        print("(wyslane; serwer nie odsyla ACK dla tego typu)")
        return 0
    print(json.dumps(reply, ensure_ascii=False))
    return 1 if reply.get("type") == "error" else 0


def cmd_heartbeat(args):
    nick = _agent_env(args)
    send = _import_send()
    return asyncio.run(send.heartbeat_loop(nick or "listener",
                                           args.task_id, args.interval)) or 0


def cmd_node(args):
    """Headless node: budzi/wznawia runtime agenta na wzmianke (Task 3).

    Token/URL jak _agent_env (CHAT_TOKEN z env wygrywa nad tokens.json).
    Stan w hub_dir(hub)/nodes/<nick>/state.json (katalog 0700). Adapter
    Codexa swiadomie poza zakresem (po dogfoodzie jednego runtime'u)."""
    args.name = args.hub
    nick = _agent_env(args)
    humans = {h.strip() for h in args.humans.split(",") if h.strip()}
    state_dir = hub_dir(args.hub) / "nodes" / nick
    state_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(state_dir, 0o700)
    state_path = state_dir / "state.json"
    from agentmachi.node import ClaudeRuntime, RateLimiter, node_loop
    runtime = ClaudeRuntime(args.workspace, max_duration=args.max_wake_duration)
    limiter = RateLimiter(max_wakes_per_hour=args.max_wakes_per_hour,
                          cooldown_after_agent_wake=args.cooldown)
    asyncio.run(node_loop(os.environ["CHAT_URL"], nick, os.environ["CHAT_TOKEN"],
                         state_path, runtime, humans, limiter=limiter))
    return 0


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="agentmachi",
        description="serwer Hamachi dla agentow — hub czatu i taskow")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("serve", help="odpal hub (tworzy ~/.agentmachi/<name>)")
    p.add_argument("--name", default=DEFAULT_HUB)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--bind", default=DEFAULT_BIND,
                  help="interfejs do bindowania (0.0.0.0 = wszystkie; "
                       "domyslnie 127.0.0.1 — tylko lokalnie)")
    p.set_defaults(fn=cmd_serve)

    p = sub.add_parser("start", help="odpal pokoj W TLE i pokaz adres")
    p.add_argument("--name", default=DEFAULT_HUB)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--bind", default=DEFAULT_BIND,
                   help="0.0.0.0 = widoczny w sieci; domyslnie tylko lokalnie")
    p.set_defaults(fn=cmd_start)

    p = sub.add_parser("del", help="skasuj pokoj (nieodwracalne)")
    p.add_argument("--name", default=DEFAULT_HUB)
    p.add_argument("--tak-kasuj", dest="confirm", default=None,
                   help="wpisz nazwe pokoju, zeby potwierdzic")
    p.set_defaults(fn=cmd_del)

    p = sub.add_parser("list", help="jakie kanaly istnieja i ktore dzialaja")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("stop", help="zatrzymaj hub (SIGTERM po PID z hub.pid)")
    p.add_argument("--name", default=DEFAULT_HUB)
    p.set_defaults(fn=cmd_stop)

    p = sub.add_parser("card", help="pokaz karte wejsciowa huba")
    p.add_argument("--name", default=None)
    p.set_defaults(fn=cmd_card)

    p = sub.add_parser("tui", help="TUI human-operatora")
    p.add_argument("--name", default=None)
    p.set_defaults(fn=cmd_tui)

    p = sub.add_parser("send", help="wyslij wiadomosc jako <nick>")
    p.add_argument("nick")
    p.add_argument("text")
    p.add_argument("--name", default=None)
    p.set_defaults(fn=cmd_send)

    p = sub.add_parser("listen", help="resumowalny nasluch (kursor+lock)")
    p.add_argument("--nick", default=None)
    p.add_argument("--name", default=None)
    p.set_defaults(fn=cmd_listen)

    p = sub.add_parser("frame", help="jednorazowa ramka status/task_* "
                       "(tozsamosc sesji — zero takeoveru)")
    p.add_argument("json", help='np. \'{"type":"status","state":"idle"}\'')
    p.add_argument("--nick", default=None)
    p.add_argument("--name", default=None)
    p.set_defaults(fn=cmd_frame)

    p = sub.add_parser("heartbeat", help="procesik lease dla taska")
    p.add_argument("task_id")
    p.add_argument("interval", nargs="?", type=float, default=45.0)
    p.add_argument("--nick", default=None)
    p.add_argument("--name", default=None)
    p.set_defaults(fn=cmd_heartbeat)

    p = sub.add_parser("node", help="headless node: budzi agenta na wzmianke")
    p.add_argument("hub")
    p.add_argument("--nick", required=True)
    p.add_argument("--workspace", required=True)
    p.add_argument("--humans", default="human",
                   help="nicki ludzi (przecinki) — cooldown nie dotyczy ich wzmianek")
    p.add_argument("--max-wakes-per-hour", type=int, default=6)
    p.add_argument("--cooldown", type=float, default=60.0)
    p.add_argument("--max-wake-duration", type=float, default=1200.0)
    p.set_defaults(fn=cmd_node)

    return parser


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except CliError as e:
        print(f"agentmachi: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
