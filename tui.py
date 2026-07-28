#!/usr/bin/env python3
"""Minimalne TUI human-operatora dla autorytatywnego huba agentmachi B1.

Zero konfiguracji: uruchamiane z katalogu repo, czyta jedynego humana z
hub.tokens.json i laczy sie z ws://localhost:8766. Trwaly kursor, instance_id,
lock listenera i fail-closed uszkodzonej sesji zapewnia chat.client_session.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

import websockets
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Label, RichLog, Static, TextArea

from chat import protocol
from chat.client_session import ListenerLockHeld, Session, SessionError
from send import hub_id_from_url

# CLI agentmachi ustawia CHAT_PORT i AGENTMACHI_TOKENS; gołe `python3
# tui.py` w repo zachowuje stare defaulty (hub.tokens.json + 8766)
_PORT = os.environ.get("CHAT_PORT", "8766")
HUB_URI = os.environ.get("CHAT_URL", f"ws://localhost:{_PORT}")
HUB_ID = hub_id_from_url(HUB_URI)
TOKENS_PATH = Path(os.environ.get("AGENTMACHI_TOKENS", "hub.tokens.json"))
LEGACY_SESSION_FILE = Path(__file__).with_name(".chat-session.json")
HELLO_TIMEOUT = 10.0
BACKOFF_START = 1.0
BACKOFF_MAX = 30.0


class TuiError(Exception):
    """Blad kontraktu klienta widoczny dla humana, bez sekretow."""


class FatalHubError(TuiError):
    """Blad wymagajacy swiadomej naprawy, bez automatycznego resetu."""


@dataclass(frozen=True)
class HumanIdentity:
    nick: str
    token: str = field(repr=False)
    role: str = "human"
    groups: tuple[str, ...] = ()


@dataclass
class Participant:
    nick: str
    role: str
    groups: list[str]
    presence: str = "known"
    status: str = ""      # wolny tekst umowny: sleeping|idle|working|blocked|
                           # review|done, ale server nie waliduje enuma ("" = nieznany)
    status_note: str = ""  # subject / note z ostatniej deklaracji
    last_seq: int = 0      # ostatnia ramka, ktora ten uczestnik WYSLAL
    status_seq: int = 0    # ramka, w ktorej powstala deklaracja statusu


def _normalized_groups(value, *, owner):
    if not isinstance(value, list) or not all(
            isinstance(group, str) and group for group in value):
        raise TuiError(f"zle groups dla {owner!r} w hub.tokens.json")
    return list(dict.fromkeys(value))


def load_human_identity(path=TOKENS_PATH):
    """Wczytaj jedynego humana i bezsekretowy roster; brak/corrupt = fail-closed."""
    path = Path(path)
    try:
        raw = path.read_text()
    except OSError as exc:
        raise TuiError(
            f"brak czytelnego {path}; TUI nie wysle pustego tokenu") from exc
    try:
        tokens = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TuiError(f"{path} ma uszkodzony JSON; fail-closed") from exc
    if not isinstance(tokens, dict) or not tokens:
        raise TuiError(f"{path} musi zawierac niepusta mape tokenow")

    humans = []
    roster = {}
    for nick, entry in tokens.items():
        if not isinstance(nick, str) or not nick:
            raise TuiError(f"zly nick w {path}")
        if isinstance(entry, str):
            token, role, groups = entry, "agent", []
        elif isinstance(entry, dict):
            token = entry.get("token")
            role = entry.get("role", "agent")
            groups = _normalized_groups(entry.get("groups", []), owner=nick)
        else:
            raise TuiError(f"zly wpis tokenu dla {nick!r}")
        if not isinstance(token, str) or not token:
            raise TuiError(f"brak niepustego tokenu dla {nick!r}")
        if role not in {"agent", "human"}:
            raise TuiError(f"zla rola dla {nick!r}: {role!r}")
        roster[nick] = Participant(nick, role, list(groups))
        if role == "human":
            humans.append(HumanIdentity(nick, token, role, tuple(groups)))

    if len(humans) != 1:
        raise TuiError(
            f"{path} musi zawierac dokladnie jednego humana; jest {len(humans)}")
    return humans[0], roster


def parse_user_input(value):
    """Zamien pojedynczy input na minimalna ramke chat albo membership_set."""
    text = value.strip()
    if not text:
        raise TuiError("pusta wiadomosc")
    if not text.startswith("/"):
        return {"type": "chat", "text": text}
    if text.startswith("/kick"):
        # B6: wyrzucenie uczestnika. Uprawnienie WYLACZNIE humana — serwer
        # i tak to egzekwuje, ale nie udajemy tu, ze to zwykla komenda.
        parts = text.split()
        if len(parts) != 2 or not parts[1]:
            raise TuiError("uzycie: /kick <nick>")
        return {"type": "kick", "target": parts[1]}
    if not text.startswith("/groups"):
        raise TuiError("nieznana komenda; dostepne: /groups <nick> <g1,g2>, "
                       "/kick <nick>")
    parts = text.split(maxsplit=2)
    if len(parts) != 3 or parts[0] != "/groups":
        raise TuiError("uzycie: /groups <nick> <g1,g2>; '-' usuwa wszystkie")
    target, raw_groups = parts[1], parts[2]
    if not target:
        raise TuiError("groups: nick nie moze byc pusty")
    if raw_groups == "-":
        groups = []
    else:
        split = [group.strip() for group in raw_groups.split(",")]
        if not split or any(not group for group in split):
            raise TuiError("groups: podaj niepuste nazwy oddzielone przecinkami")
        groups = list(dict.fromkeys(split))
    return {"type": "membership_set", "target": target, "groups": groups}


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def apply_resumable_frame(session, frame, apply):
    """Apply -> mark activation -> advance cursor, identyczny kontrakt jak CLI."""
    if not isinstance(frame, dict):
        await _maybe_await(apply(frame))
        return True
    seq = frame.get("seq")
    has_seq = (not isinstance(seq, bool)
               and isinstance(seq, int) and seq >= 1)
    if has_seq and seq <= session.last_applied_seq:
        return False
    activation_id = frame.get("activation_id")
    has_activation = isinstance(activation_id, str) and bool(activation_id)
    if has_activation and session.is_activation_applied(activation_id):
        if has_seq:
            session.advance(seq)
        return False
    await _maybe_await(apply(frame))
    if has_activation:
        session.mark_activation(activation_id)
    if has_seq:
        session.advance(seq)
    return True


class HubAdapter:
    """Cienki transport UI; stan sesji i idempotencja pozostaja w Session."""

    def __init__(self, identity, *, session=None, uri=HUB_URI, connector=None):
        self.identity = identity
        self.uri = uri
        self.session = session or Session(
            HUB_ID, identity.nick, legacy_instance_file=LEGACY_SESSION_FILE)
        self._connector = connector or websockets.connect
        self._ws = None
        self._send_lock = asyncio.Lock()
        self._closing = False

    async def _hello(self, ws):
        await ws.send(json.dumps({
            "type": "hello",
            "from": self.identity.nick,
            "ts": 0.0,
            "instance_id": self.session.instance_id,
            "token": self.identity.token,
            "last_seq": self.session.last_applied_seq,
            "role": "human",
        }))
        try:
            raw = await asyncio.wait_for(ws.recv(), HELLO_TIMEOUT)
            reply = json.loads(raw)
        except asyncio.TimeoutError as exc:
            raise FatalHubError("hello: hub nie odpowiedzial w terminie") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise FatalHubError("hello: hub zwrocil niepoprawny JSON") from exc
        if not isinstance(reply, dict):
            raise FatalHubError("hello: odpowiedz huba nie jest obiektem")
        if reply.get("type") == "error":
            # Sciezke pliku sesji zna WYLACZNIE klient — serwer moze co
            # najwyzej podac wzorzec. Doklejamy ja do kazdej odmowy hello,
            # bo najczestsza przyczyna (kursor z poprzedniego huba na tym
            # samym porcie) naprawia sie kasowaniem dokladnie tego pliku.
            raise FatalHubError(
                f"hello odrzucone: {reply.get('text', 'nieznany blad')} "
                f"[twoj plik sesji: {self.session.path}]")
        if reply.get("type") not in {"ok", "resync_required"}:
            raise FatalHubError(f"hello: nieoczekiwany typ {reply.get('type')!r}")
        return reply

    @staticmethod
    def _metadata(reply):
        return {key: reply[key] for key in (
            "rules", "rules_hash", "role", "groups", "generation")
                if key in reply}

    async def _apply_hello(self, reply, on_frame, on_metadata):
        await _maybe_await(on_metadata(self._metadata(reply)))
        participants = reply.get("participants")
        if isinstance(participants, list):
            # autorytatywny roster PRZED backlogiem/stanem — panel nie
            # zgaduje z configu, tylko odzwierciedla serwer (cursor-coherent)
            await _maybe_await(on_frame({
                "type": "participants_snapshot",
                "participants": participants}))
        if reply["type"] == "ok":
            backlog = reply.get("backlog", [])
            if not isinstance(backlog, list):
                raise FatalHubError("hello ok: backlog nie jest lista")
            for frame in backlog:
                await apply_resumable_frame(self.session, frame, on_frame)
            return
        state = reply.get("state")
        snapshot_seq = reply.get("snapshot_seq")
        if not isinstance(state, dict):
            raise FatalHubError(
                "resync_required bez poprawnego state; kursor nieprzesuniety")
        if (isinstance(snapshot_seq, bool)
                or not isinstance(snapshot_seq, int) or snapshot_seq < 1):
            raise FatalHubError("resync_required ma zly snapshot_seq")
        await _maybe_await(on_frame({"type": "resync_state", "state": state}))
        self.session.advance(snapshot_seq)

    async def run(self, on_frame, on_metadata, on_status):
        # Lock listenera moze byc chwilowo zajety (np. inny klient na tym
        # samym nicku wlasnie pada) — TUI to fotel czlowieka, wiec zamiast
        # fail-closed na stale ponawiamy z backoffem az do zwolnienia.
        backoff = BACKOFF_START
        while not self._closing:
            try:
                self.session.acquire_listener_lock()
                break
            except ListenerLockHeld as exc:
                await _maybe_await(on_status(
                    f"{exc} — ponawiam za {backoff:.0f}s", False))
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX)
        if self._closing:
            return
        backoff = BACKOFF_START
        try:
            while not self._closing:
                try:
                    await _maybe_await(on_status(
                        f"laczenie z hubem {self.uri}...", False))
                    async with self._connector(self.uri) as ws:
                        self._ws = ws
                        reply = await self._hello(ws)
                        await self._apply_hello(reply, on_frame, on_metadata)
                        await _maybe_await(on_status(
                            f"polaczono jako {self.identity.nick}", True))
                        backoff = BACKOFF_START
                        async for raw in ws:
                            try:
                                frame = json.loads(raw)
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                await _maybe_await(on_frame({
                                    "type": "error", "from": "client",
                                    "text": "hub wyslal niepoprawny JSON"}))
                                continue
                            await apply_resumable_frame(
                                self.session, frame, on_frame)
                except asyncio.CancelledError:
                    raise
                except (FatalHubError, SessionError) as exc:
                    # Pasek statusu to JEDNA linia — dluzszy powod odmowy
                    # zostaje w nim uciety i czlowiek widzi "hello odrzucone:"
                    # bez tresci. Ten sam tekst leci wiec do logu wiadomosci,
                    # ktory zawija. Zlapane na zywym pokoju 2026-07-26:
                    # operator widzial pusty pokoj i zadnej przyczyny.
                    await _maybe_await(on_frame({
                        "type": "error", "from": "client",
                        "text": f"FAIL-CLOSED: {exc}"}))
                    await _maybe_await(on_status(f"FAIL-CLOSED: {exc}", False))
                    return
                except (OSError, websockets.exceptions.ConnectionClosed) as exc:
                    if self._closing:
                        break
                    await _maybe_await(on_status(
                        f"rozlaczono ({type(exc).__name__}); retry za "
                        f"{backoff:.0f}s", False))
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, BACKOFF_MAX)
                finally:
                    self._ws = None
        finally:
            self.session.release_listener_lock()

    async def send(self, frame):
        if self._ws is None:
            raise TuiError("brak polaczenia z hubem")
        wire = {"from": self.identity.nick, "ts": 0.0, **frame}
        async with self._send_lock:
            try:
                await self._ws.send(json.dumps(wire, ensure_ascii=False))
            except (OSError, websockets.exceptions.ConnectionClosed) as exc:
                raise TuiError("wysylka nieudana: hub rozlaczony") from exc

    async def close(self):
        self._closing = True
        if self._ws is not None:
            await self._ws.close()


class MessageInput(TextArea):
    """Wieloliniowy input operatora (czat + komendy slash).

    TextArea zamiast jednoliniowego Input: Emil moze wkleic tekst z
    newline'ami i komponowac w wielu liniach. Enter wstawia nowa linie
    (kontrakt TextArea), a wysylka jest JAWNA pod Ctrl+S — inaczej Enter
    wysylalby wpol-napisana wiadomosc przy pierwszym zawinieciu. Emituje
    wlasna ramke Submitted z pelnym tekstem, zeby App nie znala szczegolow
    edytora (ta sama sciezka wysylki co dawny Input.Submitted)."""

    # Ctrl+S jest nieprintowalny i spoza insert_values TextArea, wiec jej
    # _on_key go nie polyka i binding odpala normalnie. Ctrl+Enter to bonus
    # dla terminali z protokolem kitty; tam gdzie go nie ma, klawisz wchodzi
    # po prostu jako Enter (nowa linia) i nic sie nie psuje.
    BINDINGS = [
        Binding("ctrl+s", "submit", "wyslij", show=False),
        Binding("ctrl+enter", "submit", "wyslij", show=False),
    ]

    class Submitted(Message):
        """Operator zatwierdzil tekst (Ctrl+S) — do wyslania na hub."""

        def __init__(self, input: "MessageInput", text: str) -> None:
            self.input = input
            self.text = text
            super().__init__()

    def action_submit(self) -> None:
        self.post_message(self.Submitted(self, self.text))


class AgentmachiApp(App):
    TITLE = "agentmachi"
    SUB_TITLE = "human operator"
    CSS = """
    Screen {
        background: $surface;
    }
    #workspace {
        height: 1fr;
    }
    .panel {
        border: round $accent;
        padding: 0 1;
        margin: 0 1 0 0;
    }
    #chat-panel {
        width: 2fr;
    }
    #participants-panel, #rules-panel {
        width: 1fr;
    }
    .panel-title {
        height: 1;
        text-style: bold;
        color: $accent;
    }
    #chat-log {
        height: 1fr;
    }
    #message-input {
        height: 6;
        border: tall $accent;
    }
    #participants, #rules {
        height: auto;
    }
    #connection-status, #rules-hash {
        height: auto;
        color: $text-muted;
    }
    """

    def __init__(self, adapter, roster):
        super().__init__()
        self.adapter = adapter
        self.roster = {
            nick: Participant(item.nick, item.role, list(item.groups),
                              item.presence)
            for nick, item in roster.items()
        }
        self.rules_text = ""
        self.history = []
        self.connected = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="workspace"):
            with Vertical(id="chat-panel", classes="panel"):
                yield Label("Czat", classes="panel-title")
                yield RichLog(id="chat-log", wrap=True, max_lines=500,
                              auto_scroll=True)
                yield MessageInput(
                    id="message-input",
                    placeholder="wiadomosc lub /groups <nick> <g1,g2> — "
                                "Ctrl+S wysyla, Enter = nowa linia")
            with VerticalScroll(id="participants-panel", classes="panel"):
                yield Label("Uczestnicy / grupy", classes="panel-title")
                yield Static("", id="participants")
            with VerticalScroll(id="rules-panel", classes="panel"):
                yield Label("Rules / stan", classes="panel-title")
                yield Static("laczenie...", id="connection-status")
                yield Static("", id="rules-hash")
                yield Static("", id="rules")

    def on_mount(self):
        self.query_one("#message-input", MessageInput).disabled = True
        self._render_participants()
        self.run_worker(
            self.adapter.run(
                self.apply_hub_frame, self.apply_metadata, self.apply_status),
            name="hub-listener", group="hub", exclusive=True)

    async def on_unmount(self):
        await self.adapter.close()

    def _log(self, sender, message, *, style=""):
        line = Text()
        line.append(f"{sender}: ", style=style or "bold cyan")
        line.append(str(message))
        self.history.append((sender, str(message)))
        self.query_one("#chat-log", RichLog).write(line)

    def _render_participants(self):
        """Lista jak online-lista czatu: TYLKO podlaczeni (presence ==
        connected). Odlaczony znika; wraca przy nastepnym hello/presence."""
        lines = Text()
        online = [n for n in sorted(self.roster, key=str.casefold)
                  if self.roster[n].presence == "connected"]
        if not online:
            lines.append("(nikt nie jest online)", style="dim")
        for index, nick in enumerate(online):
            participant = self.roster[nick]
            if index:
                lines.append("\n")
            groups = ",".join(participant.groups) or "—"
            lines.append(f"● {nick}", style="bold")
            lines.append(f"  {participant.role}  [{groups}]")
            # "cicho od N" odroznia siedzacego cicho od tego, kto oglochl.
            # `connected` mowi tylko, ze gniazdo jest otwarte — a proces
            # potrafi zyc godzinami, nie dostarczajac modelowi ani jednej
            # ramki (zmierzone w dogfoodzie kinas-machine).
            biezacy = max((self.roster[n].last_seq for n in self.roster),
                          default=0)
            zaleglosc = max(0, biezacy - participant.last_seq)
            if participant.last_seq and zaleglosc >= 20:
                lines.append(f"  cicho od {zaleglosc}", style="dim yellow")
            if participant.status:
                style = {"idle": "green", "working": "yellow",
                         "blocked": "bold red", "review": "cyan"}.get(
                    participant.status, "")
                note = f" ({participant.status_note})" \
                    if participant.status_note else ""
                lines.append(f"  {participant.status}{note}", style=style)
                # Wiek deklaracji. Bez tego board KLAMIE zamiast milczec:
                # po dogfoodzie kinas-machine pokazywal "worker1: idle"
                # (pracowal bez przerwy) i "worker2: working, buduje polowe
                # A" (skonczyl ja godziny wczesniej). Prog 20 ramek jest
                # ten sam co przy "cicho od" — ponizej niego status jest
                # na tyle swiezy, ze liczba tylko zaszumia widok.
                wiek = max(0, biezacy - participant.status_seq)
                if participant.status_seq and wiek >= 20:
                    lines.append(f"  (deklaracja sprzed {wiek} ramek)",
                                 style="dim yellow")
        self.query_one("#participants", Static).update(lines)

    async def apply_status(self, message, connected):
        self.connected = bool(connected)
        self.query_one("#connection-status", Static).update(Text(str(message)))
        self.query_one("#message-input", MessageInput).disabled = not self.connected
        own = self.roster.get(self.adapter.identity.nick)
        if own is not None:
            own.presence = "connected" if connected else "known"
            self._render_participants()

    async def apply_metadata(self, metadata):
        role = metadata.get("role", self.adapter.identity.role)
        groups = metadata.get("groups", list(self.adapter.identity.groups))
        own = self.roster.setdefault(
            self.adapter.identity.nick,
            Participant(self.adapter.identity.nick, role, []))
        own.role = role
        if isinstance(groups, list):
            own.groups = list(groups)
        rules = metadata.get("rules")
        self.rules_text = rules if isinstance(rules, str) else "brak rules.md"
        self.query_one("#rules", Static).update(Text(self.rules_text))
        rules_hash = metadata.get("rules_hash")
        label = f"rules_hash: {rules_hash}" if rules_hash else "rules_hash: brak"
        self.query_one("#rules-hash", Static).update(Text(label))
        self._render_participants()

    def _apply_registry_state(self, state):
        registry = state.get("registry", {})
        groups = registry.get("groups", {}) if isinstance(registry, dict) else {}
        if not isinstance(groups, dict):
            return
        for nick, value in groups.items():
            if not isinstance(nick, str) or not isinstance(value, list):
                continue
            participant = self.roster.setdefault(
                nick, Participant(nick, "agent", []))
            participant.groups = [
                group for group in value if isinstance(group, str) and group]
        self._render_participants()

    async def apply_hub_frame(self, frame):
        if not isinstance(frame, dict):
            self._log("client", "hub wyslal ramke niebedaca obiektem",
                      style="bold red")
            return
        kind = frame.get("type")
        if kind in {"chat", "fyi"}:
            self._log(frame.get("from", "?"), frame.get("text", ""))
        elif kind == "hello":
            nick = frame.get("from")
            if isinstance(nick, str) and nick:
                participant = self.roster.setdefault(
                    nick, Participant(nick, frame.get("role", "agent"), []))
                if frame.get("role") in {"agent", "human"}:
                    participant.role = frame["role"]
                if isinstance(frame.get("groups"), list):
                    participant.groups = list(frame["groups"])
                if nick != self.adapter.identity.nick:
                    participant.presence = "seen"
                self._render_participants()
        elif kind == "presence":
            nick = frame.get("nick")
            if isinstance(nick, str) and nick:
                participant = self.roster.setdefault(
                    nick, Participant(nick, "agent", []))
                participant.presence = ("connected" if frame.get("connected")
                                        else "known")
                status = frame.get("status")
                if isinstance(status, dict):
                    raw = status.get("state")
                    participant.status = raw if isinstance(raw, str) else ""
                    raw_note = status.get("subject") or status.get("note")
                    participant.status_note = raw_note \
                        if isinstance(raw_note, str) else ""
                self._render_participants()
        elif kind == "status":
            # `target` jest autorytatywny (server-side default = nadawca);
            # aktualizujemy WIERSZ target, nie koniecznie nadawce (human albo
            # agent z grupy admin moze ustawic cudzy status). Stan spoza
            # znanych kolorow ma po prostu brak koloru
            # w _render_participants — nie jest to blad.
            nick = frame.get("target") or frame.get("from")
            state = frame.get("state")
            if (isinstance(nick, str) and nick
                    and isinstance(state, str) and state):
                participant = self.roster.setdefault(
                    nick, Participant(nick, "agent", []))
                participant.status = state
                raw_note = frame.get("subject") or frame.get("note")
                participant.status_note = raw_note \
                    if isinstance(raw_note, str) else ""
                self._render_participants()
        elif kind == "kick":
            # Trwaly slad wyrzucenia — jedyna ramka poza wzmianka, ktora
            # dochodzi do wszystkich: zmienia SKLAD zespolu, nie tresc
            # rozmowy, wiec kazdy musi wiedziec bez pytania.
            target = frame.get("target")
            by = frame.get("by")
            if isinstance(target, str) and target:
                self.roster.pop(target, None)
                self._render_participants()
                self._log("server", f"{target} wyrzucony przez {by or '?'}",
                          style="bold red")
        elif kind == "membership_set":
            self._apply_groups(frame.get("target"), frame.get("groups"))
        elif kind == "ok" and "target" in frame and "groups" not in frame:
            self._log("server", f"wyrzucam {frame.get('target')}...",
                      style="yellow")
        elif kind == "ok" and "target" in frame and "groups" in frame:
            self._apply_groups(frame.get("target"), frame.get("groups"))
            self._log("server", f"groups {frame.get('target')} = "
                      f"{','.join(frame.get('groups', [])) or '—'}",
                      style="bold green")
        elif kind == "participants_snapshot":
            self._apply_participants_snapshot(frame.get("participants"))
        elif kind == "resync_state":
            state = frame.get("state")
            if isinstance(state, dict):
                self._apply_registry_state(state)
        elif kind == "error":
            self._log("server", frame.get("text", "blad"),
                      style="bold red")

    def _apply_participants_snapshot(self, participants):
        if not isinstance(participants, list):
            return
        fresh = {}
        for item in participants:
            if not isinstance(item, dict):
                continue
            nick = item.get("nick")
            if not isinstance(nick, str) or not nick:
                continue
            role = item.get("role")
            groups = item.get("groups")
            status = item.get("status")
            state, note = "", ""
            if isinstance(status, dict):
                raw_state = status.get("state")
                state = raw_state if isinstance(raw_state, str) else ""
                raw_note = status.get("subject") or status.get("note")
                note = raw_note if isinstance(raw_note, str) else ""
            fresh[nick] = Participant(
                nick,
                role if role in {"agent", "human"} else "agent",
                [g for g in groups if isinstance(g, str) and g]
                if isinstance(groups, list) else [],
                "connected" if item.get("connected") else "known",
                state, note,
                item.get("last_seq") if isinstance(item.get("last_seq"), int)
                and not isinstance(item.get("last_seq"), bool) else 0,
                item.get("status_seq")
                if isinstance(item.get("status_seq"), int)
                and not isinstance(item.get("status_seq"), bool) else 0)
        if fresh:
            self.roster = fresh  # snapshot AUTORYTATYWNY — zastepuje zgadywanie
            self._render_participants()

    def _apply_groups(self, target, groups):
        if not isinstance(target, str) or not isinstance(groups, list):
            return
        participant = self.roster.setdefault(
            target, Participant(target, "agent", []))
        participant.groups = [
            group for group in groups if isinstance(group, str) and group]
        self._render_participants()

    @on(MessageInput.Submitted)
    async def on_message_submitted(self, event: MessageInput.Submitted):
        # Nazwa metody celowo NIE pasuje do konwencji on_message_input_submitted
        # — dyspozycja idzie wylacznie przez @on, wiec handler nie odpali dwa razy.
        try:
            frame = parse_user_input(event.text)
            await self.adapter.send(frame)
        except TuiError as exc:
            self._log("client", str(exc), style="bold red")
            return
        event.input.clear()
        if frame["type"] == "chat":
            self._log(self.adapter.identity.nick, frame["text"],
                      style="bold green")
            # Fizyka kanalu: chat bez wzmianki trafia wylacznie do humanow
            # (sen agenta jest darmowy) — czlowiek piszacy do agentow bez
            # @nicka dostalby cisze i nie wiedzialby dlaczego (dogfood B3).
            if not (protocol.parse_mentions(frame["text"])
                    or protocol.parse_groups(frame["text"])):
                self._log("client",
                          "(bez wzmianki — agenci tego nie dostana; "
                          "uzyj @nick, $grupa albo @all)", style="dim")
        else:
            groups = ",".join(frame["groups"]) or "—"
            self._log("client", f"wyslano groups {frame['target']} = {groups}",
                      style="bold yellow")


def build_app(tokens_path=TOKENS_PATH, *, session_dir=None):
    identity, roster = load_human_identity(tokens_path)
    session = Session(
        HUB_ID, identity.nick, base_dir=session_dir,
        legacy_instance_file=LEGACY_SESSION_FILE)
    return AgentmachiApp(HubAdapter(identity, session=session), roster)


def main():
    try:
        app = build_app()
    except (TuiError, SessionError) as exc:
        print(f"agentmachi TUI: {exc}", file=sys.stderr)
        return 2
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
