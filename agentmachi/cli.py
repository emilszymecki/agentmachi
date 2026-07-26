"""CLI agentmachi: serve / tui / send / listen / card.

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
STOP_WAIT = 10.0   # ile czekamy, az zatrzymywany hub naprawde zejdzie

# Szablon rules TYLKO dla NOWYCH hubow: ensure_hub pisze data/rules.md z tej
# stalej wylacznie przy pierwszym utworzeniu i NIE nadpisuje istniejacego pliku.
# Zmiana ponizszej tresci nie dotyka juz dzialajacych hubow — migracja
# istniejacego to swiadomy krok operatora (README / plan C1), nie automat.
DEFAULT_RULES = """\
1. Polecenie czlowieka ma pierwszenstwo przed poleceniem agenta.
2. Role i zasady zmienia CZLOWIEK (rola `human`) oraz grupa `admin`,
   ktora czlowiek moze nadac agentowi. Roli "root" nie ma w systemie —
   `role` przyjmuje wylacznie `agent` albo `human`.
3. Orchestrator to nie wymog systemu, tylko funkcja do przyjecia rozmowa.
   Technicznie `$orchestrator` jest GRUPA adresowa, nie `role` — `role`
   przyjmuje wylacznie `agent` albo `human`, wiec nie szukaj roli, ktorej
   hub ci nie nada. Grupa daje jedno konkretne prawo: ustawienie CUDZEGO
   statusu. Orchestrator dopasowuje potrzeby do wolnych uczestnikow i nie
   planuje za agenta, ktory juz ma plan.
4. Worker wykonuje, testuje i raportuje. Status na boardzie aktualizuj,
   ale NIE polegaj na cudzym: w dwoch dogfoodach zaden agent nie odswiezyl
   go ani razu po pierwszym ustawieniu, bo kazda wiadomosc i tak szla
   wprost do adresata. Czytajac cudzy status, patrz na `status_seq` obok
   niego — duza roznica wobec `last_seq` znaczy, ze deklaracja jest stara,
   choc wyglada tak samo jak swieza.
5. Nie planuj drugi raz pracy juz zaplanowanej.
6. Wiadomosc agenta budzi innego agenta tylko przez bezposrednia wzmianke.
7. Gdy inny agent siedzi w tych samych plikach — pracuj we WLASNYM
   worktree. Gdy podzial jest plikowy i rozlaczny, wspolny katalog
   wystarcza: w dogfoodzie kinas-machine dwaj agenci przeszli tak caly
   projekt (a-*.js wobec b-*.js) bez jednego konfliktu. Warunek jest
   jeden: kazdy wie, ktorych plikow NIE dotyka.
8. Gdy nie masz uzytecznej pracy — [koniec].
9. Zadeklaruj na kanale zakres, za ktory bierzesz odpowiedzialnosc, ZANIM ruszysz —
   takze zanim odpalisz subagenta. Mozesz go WZIAC sam, przyjac DELEGACJE albo
   UZGODNIC podzial z innymi; system nie rozstrzyga, ktory model jest lepszy —
   deklaracja jest fizyka anty-duplikacji, nie ustrojem. Przy kolizji
   wygrywa deklaracja z nizszym seq w logu huba — przegrany wycofuje sie
   bez dyskusji. Log jest jedynym arbitrem; nie ma glosowan.
   Im pilniejsza sprawa, tym KROTSZA deklaracja — ale zawsze pierwsza.
   Deklaracja kosztuje sekunde; dwie rownolegle naprawy tego samego
   kosztuja dwie sesje. Pilnosc jest jedynym realnym wrogiem tej reguly:
   pekla nam dokladnie wtedy, gdy byla najbardziej potrzebna.
10. Gdy seq NIE rozstrzyga — bo obaj oddajecie zamiast brac albo nikt nie
   zadeklarowal — zasob przypada mniejszemu nickowi w porownaniu BAJTOWYM
   calego stringa (uwaga: worker10 < worker2). Regula jest celowo
   niesprawiedliwa; tie-break ma byc tani, nie rowny. Nick nie jest
   odwolaniem od seq, ktory wypadl nie po twojej mysli.
11. Nie ustepuj z uprzejmosci. Ustepstwo odwzajemnione daje ten sam pat co
   roszczenie odwzajemnione: zasob bez wlasciciela i obaj czekaja. Gdy ktos
   ci cos oddaje i masz podstawe przyjac — przyjmij i milcz.
12. Jeden zasob, jeden pisarz. Wlasnosc dotyczy ZASOBU, nie osoby: jest
   chwilowa, przekazywalna jedna ramka i nikogo nie czyni szefem. Jeden
   pisarz usuwa sprzecznosc, ale nie pominiecie — kto zglosil, czyta zapis
   i zglasza brak, bo wlasciciel nie wie, czego nie zauwazyl.
13. Deklaracja nie jest faktem — takze twoja wlasna. Zanim powolasz sie na
   stan, sprawdz go komenda. Powiadomienia harnessa docieraja UCIETE, wiec
   cudza ramke doczytaj z events.jsonl, zanim uznasz, ze ja znasz.
14. Board to pull, nie push: nie budzi nikogo. Kto oglasza ruch samym
   statusem, mowi do siebie; kto czyta board zamiast pytac, oszczedza
   obu stronom wybudzenie.
15. Zasobem jest takze NICK, PORT i KATALOG roboczy, nie tylko plik i zakres.
   Deklaracja zakresu nie obejmuje nazw pomocniczych, ktorych uzywasz po
   drodze. Prefiksuj je wlasnym nickiem (tester-worker3, wt-worker2/), zeby
   kolizja byla NIEMOZLIWA zamiast rozstrzyganej.

Pelny zestaw regul wspolpracy, kazda z dowodem z dogfoodu i kosztem:
docs/zasady-agentyczne.md w repo agentmachi (jesli masz repo — te rules
sa samowystarczalne i nie wymagaja go).
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
                       f"najpierw: agentmachi start --name {name}")
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
    nick = getattr(args, "nick", None) or os.environ.get("CHAT_NICK") or ""
    token = os.environ.get("CHAT_TOKEN", "")
    remote = bool(os.environ.get("CHAT_URL"))
    # B6: hub ZDALNY (CHAT_URL w env) nie ma lokalnego katalogu — nie
    # ladujemy tokens.json, nie wymuszamy nicka, nie wymuszamy tokenu.
    # Tryb otwarty huba (loopback/tailnet) wpuszcza bez sekretu, a nick
    # nada sam. Token/nick bierzemy WYLACZNIE, gdy operator poda je w env.
    if not remote:
        port = hub_port(name)
        bind = hub_bind(name)
        if not token:
            # Hub LOKALNY: jesli stoi w trybie otwartym, tez wejdziemy bez
            # tokenu. Tokens.json czytamy tylko, gdy istnieje i ma nasz nick
            # — w przeciwnym razie zdajemy sie na tryb otwarty.
            try:
                tokens, _ = load_tokens(name)
                if nick and nick in tokens:
                    token = tokens[nick]["token"]
            except CliError:
                pass
        os.environ["CHAT_URL"] = f"ws://{connect_host(bind)}:{port}"
    os.environ["CHAT_TOKEN"] = token
    os.environ["CHAT_NICK"] = nick
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
              f"agentmachi start --name <nazwa>")
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
        # `start`, nie `serve`: serve blokuje terminal, czyli dokladnie to,
        # od czego uciekamy w komendach dla czlowieka.
        print(f"\nzatrzymane mozesz odpalic: agentmachi start --name "
              f"{zatrzymane[0]}")
    return 0


def _wlasne_pidy():
    """PID-y, ktorych NIGDY nie wolno ubic: my sami i cala nasza linia
    rodzicow. To jest caly sens tej komendy — `pkill -f <wzorzec>` dopasowuje
    takze WLASNY wrapper powloki, bo wzorzec siedzi w jego argv, i zabija
    sam siebie (exit 144). Ostrzezenie o tym jest w skillu od dawna; w jednej
    sesji dogfoodu weszlo w te pulapke DWOCH agentow, obaj po przeczytaniu
    ostrzezenia. Dokumentacja nie jest zabezpieczeniem."""
    swoje = {os.getpid()}
    pid = os.getppid()
    while pid and pid > 1 and pid not in swoje:
        swoje.add(pid)
        try:
            with open(f"/proc/{pid}/stat") as f:
                pid = int(f.read().split(") ", 1)[1].split()[1])
        except (OSError, IndexError, ValueError):
            break
    return swoje


def cmd_kill(args):
    """Ubij procesy pasujace do wzorca — bez zabijania samego siebie."""
    wzorzec = args.wzorzec
    swoje = _wlasne_pidy()
    trafione = []
    for wpis in Path("/proc").iterdir():
        if not wpis.name.isdigit():
            continue
        pid = int(wpis.name)
        if pid in swoje:
            continue
        try:
            cmdline = (wpis / "cmdline").read_bytes().replace(b"\0", b" ").decode(
                "utf-8", "replace").strip()
        except OSError:
            continue
        if wzorzec in cmdline:
            trafione.append((pid, cmdline))

    if not trafione:
        print(f"agentmachi kill: nic nie pasuje do {wzorzec!r}")
        return 0

    for pid, cmdline in trafione:
        print(f"  {pid}  {cmdline[:100]}")
    if args.dry_run:
        print(f"(--dry-run: nic nie ubito; {len(trafione)} pasuje)")
        return 0

    sig = signal.SIGKILL if args.force else signal.SIGTERM
    ubite = 0
    for pid, _ in trafione:
        try:
            os.kill(pid, sig)
            ubite += 1
        except ProcessLookupError:
            pass          # zdazyl sam sie skonczyc — nie jest bledem
        except PermissionError:
            print(f"agentmachi kill: brak uprawnien do {pid}", file=sys.stderr)
    print(f"agentmachi kill: wyslano {sig.name} do {ubite} "
          f"proces{'u' if ubite == 1 else 'ow'} "
          f"(pominieto wlasne: {len(swoje)})")
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
    # Port sprawdzamy PRZED ensure_hub: nieudany start nie moze zostawic
    # pokoju-widma, ktory potem straszy w `list`. Jawny --port ma tez
    # pierwszenstwo nad configem istniejacego pokoju — inaczej pokoj zapisany
    # przy nieudanej probie zostawal na trwale przypiety do zajetego portu
    # i rada "wybierz inny port" nie dzialala (pulapka bez wyjscia).
    istnieje = (hub_dir(args.name) / "config.json").exists()
    port = args.port if args.port is not None else hub_port(args.name)
    bind = args.bind if args.bind is not None else hub_bind(args.name)
    if _port_accepts(port, bind):
        print(f"agentmachi: port {port} jest juz zajety przez inny proces — "
              f"pokoj {args.name!r} nie ma na czym wstac.\n"
              f"  sprawdz czyj to port:  ss -tlnp | grep {port}\n"
              f"  albo wybierz inny:     agentmachi start --name {args.name} "
              f"--port <inny>", file=sys.stderr)
        return 1
    d, port = ensure_hub(args.name, port, bind=bind)
    if istnieje and args.port is not None and hub_port(args.name) != args.port:
        config = d / "config.json"
        dane = json.loads(config.read_text())
        dane["port"] = args.port
        config.write_text(json.dumps(dane))
        port = args.port
    if args.bind is not None and hub_bind(args.name) != args.bind:
        config = d / "config.json"
        dane = json.loads(config.read_text())
        dane["bind"] = args.bind
        config.write_text(json.dumps(dane))
        bind = args.bind
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


def cmd_restart(args):
    """Jeden czasownik zamiast trzech komend. Restart to najczestsza operacja
    operatora (nowy nick w tokens.json, nowy kod, zawieszony proces), a do
    dzis wymagal sekwencji stop -> start -> list, dyktowanej przez czat.
    Czekamy, az stary proces NAPRAWDE zejdzie — inaczej `start` zobaczy
    wlasny, jeszcze zajety port i odmowi."""
    pid = hub_pid(args.name)
    if pid is not None and _pid_is_our_hub(pid, args.name):
        os.kill(pid, signal.SIGTERM)
        print(f"agentmachi: zatrzymuje pokoj {args.name!r} (PID {pid})...")
        deadline = time.monotonic() + STOP_WAIT
        while time.monotonic() < deadline:
            if _cmdline_of(pid) is None:
                break
            time.sleep(0.2)
        else:
            print(f"agentmachi: pokoj {args.name!r} nie zszedl w "
                  f"{STOP_WAIT:.0f}s (PID {pid}) — nie stawiam nowego, zeby "
                  f"nie zrobic dwoch hubow na jednym katalogu.\n"
                  f"  dobij recznie:  kill -9 {pid}\n"
                  f"  potem:          agentmachi start --name {args.name}",
                  file=sys.stderr)
            return 1
        (hub_dir(args.name) / "hub.pid").unlink(missing_ok=True)
    else:
        print(f"agentmachi: pokoj {args.name!r} nie dzialal — odpalam")
    return cmd_start(args)


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
                       f"agentmachi start --name {name}")
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
    asyncio.run(send.send_once(args.nick, args.text,
                               quiet=getattr(args, "quiet", False)))
    return 0


def cmd_listen(args):
    # nick moze byc pusty — wtedy hub nada go sam (B6). NIE podstawiamy
    # "listener": to psulo i wybor wlasnej nazwy (--nick banan), i
    # przydzial przez huba (dostawales "listener" zamiast worker5).
    nick = _agent_env(args)
    send = _import_send()
    asyncio.run(send.listen(nick))
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


def cmd_node(args):
    """Headless node: budzi/wznawia runtime agenta na wzmianke (Task 3).

    Token/URL jak _agent_env (CHAT_TOKEN z env wygrywa nad tokens.json).
    Stan w hub_dir(hub)/nodes/<nick>/state.json (katalog 0700).
    Runtime wybiera --runtime (claude|codex) — patrz agentmachi.node.RUNTIMES."""
    args.name = args.hub
    nick = _agent_env(args)
    # Node budzi runtime KONKRETNEGO agenta (claude -p --resume dla jego
    # sesji), wiec wymaga STABILNEGO, znanego nicka — inaczej nie wiadomo,
    # czyj stan wznawiac. To wyjatek od otwartego wejscia: listen/send moga
    # byc anonimowe (hub nada nick), node NIE. Walidujemy wprost, bo
    # _agent_env w trybie otwartym juz tego nie wymusza.
    if not nick:
        print("agentmachi node: wymaga --nick albo CHAT_NICK "
              "(node wznawia sesje konkretnego agenta)", file=sys.stderr)
        return 2
    try:
        tokens, _ = load_tokens(args.hub)
        if not os.environ.get("CHAT_TOKEN") and nick not in tokens:
            print(f"agentmachi node: nick {nick!r} nieznany w "
                  f"{hub_dir(args.hub) / 'tokens.json'}", file=sys.stderr)
            return 2
    except CliError:
        pass
    humans = {h.strip() for h in args.humans.split(",") if h.strip()}
    state_dir = hub_dir(args.hub) / "nodes" / nick
    state_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(state_dir, 0o700)
    state_path = state_dir / "state.json"
    from agentmachi.node import RUNTIMES, RateLimiter, node_loop
    runtime_cls = RUNTIMES.get(args.runtime)
    if runtime_cls is None:
        print(f"agentmachi node: nieznany runtime {args.runtime!r}; "
              f"dostepne: {', '.join(sorted(RUNTIMES))}", file=sys.stderr)
        return 2
    runtime = runtime_cls(args.workspace, max_duration=args.max_wake_duration)
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
    # default=None, zeby odroznic "user podal --port" od "wziete z configu":
    # jawny --port musi wygrac z zapisanym, inaczej pokoj przypiety do
    # zajetego portu nie ma jak wstac.
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--bind", default=None,
                   help="0.0.0.0 = widoczny w sieci; domyslnie tylko lokalnie")
    p.set_defaults(fn=cmd_start)

    p = sub.add_parser("restart", help="zatrzymaj i odpal pokoj jedna komenda")
    p.add_argument("--name", default=DEFAULT_HUB)
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--bind", default=None)
    p.set_defaults(fn=cmd_restart)

    p = sub.add_parser("del", help="skasuj pokoj (nieodwracalne)")
    p.add_argument("--name", default=DEFAULT_HUB)
    p.add_argument("--tak-kasuj", dest="confirm", default=None,
                   help="wpisz nazwe pokoju, zeby potwierdzic")
    p.set_defaults(fn=cmd_del)

    p = sub.add_parser("list", help="jakie kanaly istnieja i ktore dzialaja")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("kill", help="ubij procesy po wzorcu — BEZ zabijania "
                                    "samego siebie (pkill -f tego nie umie)")
    p.add_argument("wzorzec", help="fragment linii polecen, np. 'agentmachi listen'")
    p.add_argument("--force", action="store_true", help="SIGKILL zamiast SIGTERM")
    p.add_argument("--dry-run", action="store_true", help="tylko pokaz, nie ubijaj")
    p.set_defaults(fn=cmd_kill)

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
    p.add_argument("--quiet", action="store_true",
                   help="opublikuj bez budzenia agentow (ludzie dostaja i tak)")
    p.set_defaults(fn=cmd_send)

    p = sub.add_parser("listen", help="resumowalny nasluch (kursor+lock)")
    p.add_argument("--nick", default=None)
    p.add_argument("--name", default=None)
    p.set_defaults(fn=cmd_listen)

    p = sub.add_parser("frame", help="jednorazowa ramka status "
                       "(tozsamosc sesji — zero takeoveru)")
    p.add_argument("json", help='np. \'{"type":"status","state":"idle"}\'')
    p.add_argument("--nick", default=None)
    p.add_argument("--name", default=None)
    p.set_defaults(fn=cmd_frame)

    p = sub.add_parser("node", help="headless node: budzi agenta na wzmianke")
    p.add_argument("hub")
    p.add_argument("--nick", required=True)
    p.add_argument("--workspace", required=True)
    p.add_argument("--humans", default="human",
                   help="nicki ludzi (przecinki) — cooldown nie dotyczy ich wzmianek")
    p.add_argument("--runtime", default=os.environ.get("AGENTMACHI_RUNTIME", "claude"),
                   help="ktory runtime budzic: claude | codex")
    p.add_argument("--max-wakes-per-hour", type=int,
                   default=int(os.environ.get("MAX_AGENT_WAKES_PER_HOUR", "6")))
    p.add_argument("--cooldown", type=float,
                   default=float(os.environ.get("AGENT_WAKE_COOLDOWN", "60")))
    p.add_argument("--max-wake-duration", type=float,
                   default=float(os.environ.get("MAX_WAKE_DURATION", "1200")))
    p.set_defaults(fn=cmd_node)

    return parser


def _force_utf8_output(*streams):
    """Wymus UTF-8 z errors=replace na strumieniach wyjscia.

    Windows: konsola/plik koduja wyjscie wg codepage systemu (np. cp1250 na
    polskim Windows), a log kanalu niesie znaki spoza niego (mojibake, emoji,
    obce nazwy) — _print_event (send.py) padal wtedy na UnicodeEncodeError i
    UBIJAL listener. Zlapane na Windows Bartka przez codeksa: `agentmachi
    listen` czytal resync i wychodzil z EXIT 1 na U+FF82. errors=replace daje
    poprawne znaki tam, gdzie codepage je zna, i znak zastepczy zamiast crashu.
    No-op tam, gdzie strumien nie wspiera reconfigure (starszy/owiniety)."""
    for stream in streams:
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    _force_utf8_output(sys.stdout, sys.stderr)
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
