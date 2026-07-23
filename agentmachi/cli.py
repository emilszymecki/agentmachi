"""CLI agentmachi: serve / tui / send / listen / heartbeat / card.

Zasada (plan B2): dane huba mieszkaja w ~/.agentmachi/<name>/ —
NIGDY w repo projektu. Repo projektu to rzecz, nad ktora pracuja agenci;
hub to infrastruktura obok (jak Hamachi obok CS-a).

Uklad ~/.agentmachi/<name>/:
  tokens.json  (0600)  nick -> {token, role, groups}
  config.json          {port}
  data/                event-log + snapshot huba (chat.store)
  data/rules.md        konstytucja kanalu (edytuje human, plikiem)
"""
import argparse
import asyncio
import json
import os
import secrets
import sys
from pathlib import Path

DEFAULT_PORT = 8766
DEFAULT_HUB = "hub"
DEFAULT_BIND = "127.0.0.1"

DEFAULT_RULES = """\
1. Zanim wezmiesz taska, sprawdz czy nikt inny juz go nie robi.
2. Decyzje i pytania architektoniczne przez `@all` albo `$workers`.
3. Blokera zglaszaj (`task_blocked`) od razu.
4. Nie zatwierdzaj (`task_approve`) wlasnej pracy — review robi ktos inny.
5. Statusy: idle/working/blocked/review — deklaruj przy zmianie fazy.
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

zdanie dla agenta (skill join):
  "dolacz do agentmachi '{name}' ({addr}) jako worker1"
""")


def _agent_env(args):
    """Zloz srodowisko klienta: hub z --name/AGENTMACHI_HUB, nick+token
    z tokens.json huba (CHAT_TOKEN z env wygrywa — nie wymuszamy pliku).
    CHAT_URL wygrywa nad CHAT_PORT w send.py; adres to connect_host(bind)
    (NIE surowy bind — patrz connect_host: loopback/wildcard -> localhost,
    zeby hub_id agenta nie zmienial sie przy kazdym upgradzie/bindzie)."""
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
    os.environ["CHAT_URL"] = f"ws://{connect_host(bind)}:{port}"
    os.environ["CHAT_TOKEN"] = token
    os.environ["CHAT_NICK"] = nick or "listener"
    return nick


def _import_send():
    # send.py liczy URI z env przy imporcie — env MUSI byc ustawione wczesniej
    import send
    return send


def cmd_serve(args):
    d, port = ensure_hub(args.name, args.port, bind=args.bind)
    bind = hub_bind(args.name, fallback=args.bind)
    tokens = json.loads((d / "tokens.json").read_text())
    print_card(args.name, port, tokens, bind=bind)
    os.environ["CHAT_TOKENS"] = str(d / "tokens.json")
    os.environ["CHAT_DATA"] = str(d / "data")
    os.environ["CHAT_PORT"] = str(port)
    os.environ["CHAT_BIND"] = bind
    from chat.server import main as server_main
    server_main()
    return 0


def cmd_card(args):
    name = args.name or os.environ.get("AGENTMACHI_HUB", DEFAULT_HUB)
    tokens, d = load_tokens(name)
    print_card(name, hub_port(name), tokens, bind=hub_bind(name))
    return 0


def cmd_tui(args):
    name = args.name or os.environ.get("AGENTMACHI_HUB", DEFAULT_HUB)
    tokens_path = hub_dir(name) / "tokens.json"
    if not tokens_path.exists():
        raise CliError(f"hub {name!r} nie istnieje; najpierw: "
                       f"agentmachi serve --name {name}")
    os.environ["AGENTMACHI_TOKENS"] = str(tokens_path)
    os.environ["CHAT_PORT"] = str(hub_port(name))
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
