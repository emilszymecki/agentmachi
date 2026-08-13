#!/usr/bin/env python3
"""Minimalne TUI human-operatora dla autorytatywnego huba agentmachi B1.

Zero konfiguracji: uruchamiane z katalogu repo, czyta jedynego humana z
hub.tokens.json i laczy sie z ws://localhost:8766. Trwaly kursor, instance_id,
lock listenera i fail-closed uszkodzonej sesji zapewnia chat.client_session.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

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
from send import MAX_HUB_FRAME, hub_id_from_url

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


def _opis_deklaracji(zrodlo):
    """`subject` I `note` razem, tym samym separatorem co `board`.

    Bylo `subject or note`, czyli JEDNO z dwoch pol — a `_opis_statusu`
    w send.py doklada oba. Agent deklarowal trzy pola, board pokazywal trzy,
    czlowiek widzial dwa i nie mial jak zauwazyc, ze trzeciego brakuje.
    Zgloszone przez operatora przy TUI 2026-08-13 zdaniem "to, co macie na
    boardzie, powinno byc 1:1 z tym, co widze", zmierzone na zywych statusach:
    board mowil `idle — poligon zamkniety — czekam na sonde Dowodu B`, TUI
    `idle (poligon zamkniety)`.

    Ginelo `note` — wolny tekst, jedyne miejsce, w ktorym agent mowi czlowiekowi
    cos, czego nie da sie zakodowac w stanie. I ginelo akurat u tego odbiorcy,
    ktory nie ma alternatywy: agent doczyta sobie `board`, czlowiek ma TUI.
    """
    czesci = []
    for pole in ("subject", "note"):
        wartosc = zrodlo.get(pole)
        if isinstance(wartosc, str) and wartosc.strip():
            czesci.append(wartosc.strip())
    return " — ".join(czesci)


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
        raise TuiError(f"bad groups for {owner!r} in hub.tokens.json")
    return list(dict.fromkeys(value))


def load_human_identity(path=TOKENS_PATH):
    """Wczytaj jedynego humana i bezsekretowy roster; brak/corrupt = fail-closed."""
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TuiError(
            f"cannot read {path}; the TUI will not send an empty token"
        ) from exc
    try:
        tokens = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TuiError(f"{path} has corrupted JSON; fail-closed") from exc
    if not isinstance(tokens, dict) or not tokens:
        raise TuiError(f"{path} must contain a non-empty token map")

    humans = []
    roster = {}
    for nick, entry in tokens.items():
        if not isinstance(nick, str) or not nick:
            raise TuiError(f"bad nick in {path}")
        if isinstance(entry, str):
            token, role, groups = entry, "agent", []
        elif isinstance(entry, dict):
            token = entry.get("token")
            role = entry.get("role", "agent")
            groups = _normalized_groups(entry.get("groups", []), owner=nick)
        else:
            raise TuiError(f"bad token entry for {nick!r}")
        if not isinstance(token, str) or not token:
            raise TuiError(f"no non-empty token for {nick!r}")
        if role not in {"agent", "human"}:
            raise TuiError(f"bad role for {nick!r}: {role!r}")
        roster[nick] = Participant(nick, role, list(groups))
        if role == "human":
            humans.append(HumanIdentity(nick, token, role, tuple(groups)))

    if len(humans) != 1:
        raise TuiError(
            f"{path} must contain exactly one human; there are {len(humans)}")
    return humans[0], roster


def history_pick(history, pos, direction):
    """Wybierz wpis z historii wysylek. Zwraca (nowy_pos, tekst albo None).

    Kontrakt jak w powloce. `pos == len(history)` znaczy „nie przegladam,
    jestem w swiezym szkicu". W gore cofa sie do najstarszego i TAM ZOSTAJE
    (nie zawija — zawijanie gubi to, co wlasnie chciales znalezc).
    None = nie ma czego podstawic Z HISTORII, nie dotykaj pola.

    W DOL NIE ZWRACA JUZ `""` i to jest zmiana kontraktu, nie poprawka
    literowki. Zgloszone przez operatora przy zywym TUI 2026-08-13: pisal
    wiadomosc, nacisnal strzalke w dol i pole sie WYCZYSCILO. Stary kontrakt
    mowil „w dol wraca do pustego szkicu" i mylil dwie rozne rzeczy — „wroc
    do szkicu" z „szkic jest pusty". Szkic nie jest pusty; szkic to jest to,
    co czlowiek wlasnie pisze, a czego jeszcze nie ma w historii. `""`
    kasowalo mu to bez odwolania.

    Rozdzial odpowiedzialnosci: ta funkcja wie tylko o historii, wiec przy
    powrocie do szkicu mowi None. Tekst szkicu zna wylacznie widget, ktory go
    trzyma — i on go odtwarza.
    """
    if not history:
        return pos, None
    if direction < 0:
        nowy = max(0, min(pos, len(history)) - 1)
        return nowy, history[nowy]
    if pos >= len(history):
        # Juz w szkicu. Przyszlosci nie ma i nie wolno niczego podstawiac —
        # to jest dokladnie ten przypadek, ktory kasowal wpisywana wiadomosc.
        return len(history), None
    nowy = pos + 1
    if nowy >= len(history):
        return len(history), None
    return nowy, history[nowy]


def parse_user_input(value):
    """Zamien pojedynczy input na ramke do wyslania albo akcje lokalna.

    Typ `local` NIE idzie na drut — to komendy operatora wykonywane po
    stronie klienta (cykl zycia huba, kursor sesji). Rozdzielone jawnie,
    zeby nikt nie dopisal ich kiedys do INBOUND_FRAME_TYPES: zatrzymanie
    huba jest domena czlowieka przy maszynie, nie ramka w protokole.
    """
    text = value.strip()
    if not text:
        raise TuiError("empty message")
    if not text.startswith("/"):
        return {"type": "chat", "text": text}
    if text.split()[0] == "/stop":
        if text.split() != ["/stop"]:
            raise TuiError("usage: /stop (no arguments)")
        return {"type": "local", "action": "stop"}
    if text.split()[0] == "/kill":
        czesci = text.split()
        if len(czesci) != 2 or not czesci[1]:
            raise TuiError(
                "usage: /kill <room-name>. The confirmation is the NAME "
                "(not /force, not /yes), because this deletes the whole "
                "history FOREVER")
        return {"type": "local", "action": "kill", "target": czesci[1]}
    if text.split()[0] == "/reset-cursor":
        if text.split() != ["/reset-cursor"]:
            raise TuiError("usage: /reset-cursor (no arguments)")
        return {"type": "local", "action": "reset-cursor"}
    if text.startswith("/kick"):
        # B6: wyrzucenie uczestnika. Uprawnienie WYLACZNIE humana — serwer
        # i tak to egzekwuje, ale nie udajemy tu, ze to zwykla komenda.
        parts = text.split()
        if len(parts) != 2 or not parts[1]:
            raise TuiError("usage: /kick <nick>")
        return {"type": "kick", "target": parts[1]}
    if not text.startswith("/groups"):
        raise TuiError("unknown command; available: /groups <nick> <g1,g2>, "
                       "/kick <nick>, /stop, /kill <room>, /reset-cursor")
    parts = text.split(maxsplit=2)
    if len(parts) != 3 or parts[0] != "/groups":
        raise TuiError("usage: /groups <nick> <g1,g2>; '-' removes all")
    target, raw_groups = parts[1], parts[2]
    if not target:
        raise TuiError("groups: nick must not be empty")
    if raw_groups == "-":
        groups = []
    else:
        split = [group.strip() for group in raw_groups.split(",")]
        if not split or any(not group for group in split):
            raise TuiError("groups: pass non-empty names separated by commas")
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
        # max_size wpiety w KONSTRUKTOR connectora, nie w miejsce wywolania:
        # limit jest wlasciwoscia prawdziwego polaczenia, a wstrzykiwane
        # atrapy (testy) maja zostac przy swojej prostej sygnaturze.
        # Po co w ogole: patrz send.MAX_HUB_FRAME — hub wysyla backlog
        # w jednej ramce i domyslny 1 MiB bywa za maly.
        self._connector = connector or functools.partial(
            websockets.connect, max_size=MAX_HUB_FRAME)
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
            raise FatalHubError("hello: the hub did not reply in time") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise FatalHubError("hello: the hub returned invalid JSON") from exc
        if not isinstance(reply, dict):
            raise FatalHubError("hello: the hub reply is not an object")
        if reply.get("type") == "error":
            # Sciezke pliku sesji zna WYLACZNIE klient — serwer moze co
            # najwyzej podac wzorzec. Doklejamy ja do kazdej odmowy hello,
            # bo najczestsza przyczyna (kursor z poprzedniego huba na tym
            # samym porcie) naprawia sie kasowaniem dokladnie tego pliku.
            raise FatalHubError(
                f"hello rejected: {reply.get('text', 'unknown error')} "
                f"[your session file: {self.session.path}]")
        if reply.get("type") not in {"ok", "resync_required"}:
            raise FatalHubError(
                f"hello: unexpected type {reply.get('type')!r}")
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
                raise FatalHubError("hello ok: backlog is not a list")
            for frame in backlog:
                await apply_resumable_frame(self.session, frame, on_frame)
            # Kursor konczy na AUTORYTATYWNYM koncu logu, nie na ostatniej
            # ramce z drutu: serwer wycina z backlogu ramki `hello` (54%
            # backlogu w pomiarze B5), wiec klient ufajacy tylko ramkom
            # zostaje z kursorem sprzed filtra i przy kazdym reconnekcie
            # zjezdza na sciezke resync. `send.py` ma to od dawna; TUI nie
            # czytalo `last_seq` w ogole (zlapane 2026-07-31).
            wire_last_seq = reply.get("last_seq")
            if (isinstance(wire_last_seq, bool)
                    or not isinstance(wire_last_seq, int)
                    or wire_last_seq < 0):
                raise FatalHubError(
                    f"hello ok without a valid last_seq (got: "
                    f"{wire_last_seq!r}) — cursor NOT advanced")
            if wire_last_seq > 0:      # 0 = pusty log, nie ma czego przesuwac
                self.session.advance(wire_last_seq)
            return
        state = reply.get("state")
        snapshot_seq = reply.get("snapshot_seq")
        if not isinstance(state, dict):
            raise FatalHubError(
                "resync_required without a valid state; cursor not advanced")
        if (isinstance(snapshot_seq, bool)
                or not isinstance(snapshot_seq, int) or snapshot_seq < 1):
            raise FatalHubError("resync_required has a bad snapshot_seq")
        await _maybe_await(on_frame({"type": "resync_state", "state": state}))
        # PAMIEC KANALU. Serwer dokleja do resync do 200 ramek rozmowy, bo
        # `state` odtwarza rejestr i board, ale rozmowy nie odtworzy nic.
        # send.py i node.py to czytaja; TUI nie czytalo, wiec operator po
        # kompakcji dostawal PUSTY panel czatu mimo dostarczonej rozmowy.
        # SUROWO, nie przez apply_resumable_frame: te ramki maja seq NIZSZE
        # niz snapshot_seq, wiec dedup by je wyciol (tak samo send.py:280).
        rozmowa = reply.get("conversation")
        if isinstance(rozmowa, list):
            for ramka in rozmowa:
                await _maybe_await(on_frame(ramka))
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
                    f"{exc} — retrying in {backoff:.0f}s", False))
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX)
        if self._closing:
            return
        backoff = BACKOFF_START
        try:
            while not self._closing:
                try:
                    await _maybe_await(on_status(
                        f"connecting to hub {self.uri}...", False))
                    async with self._connector(self.uri) as ws:
                        self._ws = ws
                        reply = await self._hello(ws)
                        await self._apply_hello(reply, on_frame, on_metadata)
                        await _maybe_await(on_status(
                            f"connected as {self.identity.nick}", True))
                        backoff = BACKOFF_START
                        async for raw in ws:
                            try:
                                frame = json.loads(raw)
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                await _maybe_await(on_frame({
                                    "type": "error", "from": "client",
                                    "text": "the hub sent invalid JSON"}))
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
                        f"disconnected ({type(exc).__name__}); retry in "
                        f"{backoff:.0f}s", False))
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, BACKOFF_MAX)
                finally:
                    self._ws = None
        finally:
            self.session.release_listener_lock()

    async def send(self, frame):
        if self._ws is None:
            raise TuiError("no connection to the hub")
        wire = {"from": self.identity.nick, "ts": 0.0, **frame}
        # Sufit sprawdzamy TUTAJ, bo `chat` nie ma ACK: hub zamknie
        # polaczenie kodem 1009, a operator zobaczylby tylko "hub
        # rozlaczony" — nigdy powodu. Patrz protocol.MAX_FRAME_BYTES.
        rozmiar = protocol.frame_bytes(wire)
        if rozmiar > protocol.MAX_FRAME_BYTES:
            raise TuiError(
                f"the message is {rozmiar // 1024} KiB, the hub limit is "
                f"{protocol.MAX_FRAME_BYTES // 1024} KiB — the hub will drop "
                f"it without explaining. Split it or pass a file path.")
        async with self._send_lock:
            try:
                await self._ws.send(protocol.dumps(wire))
            except (OSError, websockets.exceptions.ConnectionClosed) as exc:
                raise TuiError("send failed: hub disconnected") from exc

    async def close(self):
        self._closing = True
        if self._ws is not None:
            await self._ws.close()


class MessageInput(TextArea):
    """Wieloliniowy input operatora (czat + komendy slash).

    TextArea zamiast jednoliniowego Input: Emil moze wkleic tekst z
    newline'ami i komponowac w wielu liniach. Uklad klawiszy jak w Claude
    Code — Enter wysyla, Shift+Enter lamie linie. Emituje wlasna ramke
    Submitted z pelnym tekstem, zeby App nie znala szczegolow edytora
    (ta sama sciezka wysylki co dawny Input.Submitted)."""

    # UKLAD JAK W CLAUDE CODE: Enter wysyla, Shift+Enter lamie linie.
    #
    # `enter` MUSI miec priority=True. Bez tego binding nie odpala WCALE:
    # Enter jest w insert_values TextArei, wiec jej `_on_key` polyka go przed
    # rozwiazaniem bindingow (zmierzone sonda przez pilot: submit=0, w polu
    # ladowal "\n"). Priorytet odwraca kolejnosc i znak nie jest wstawiany.
    #
    # NOWA LINIA ma trzy nazwy, bo to jeden klawisz kodowany roznie:
    #   `ctrl+j`     — goly LF (\n). W Textualu ODREBNY klawisz (alias
    #                  `newline`), bo Enter to CR (\r) = `enter`/`ctrl+m`
    #                  (patrz keys.KEY_ALIASES). Tu trafia Shift+Enter
    #                  w Windows Terminal / WSL — ZMIERZONE na zywym TUI.
    #   `shift+enter`— terminale z protokolem kitty/CSI-u (kitty, WezTerm,
    #                  foot, Ghostty) nazywaja go wprost.
    #   `ctrl+o`     — bezpiecznik. Sa terminale, ktore Shift+Enter wysylaja
    #                  bajt w bajt jak Enter; tam OBIE powyzsze drogi znikaja
    #                  i bez trzeciej nie dalo by sie napisac drugiej linii
    #                  w ogole. Ctrl+O jest nieprintowalny i wolny w TextArea.
    #
    # Dlaczego Enter=wysylka jest tu BEZPIECZNE mimo wieloliniowosci:
    # wklejanie idzie przez `TextArea._on_paste` (bracketed paste), czyli
    # jednym zdarzeniem Paste, a NIE seria Enterow. Wklejenie trzydziestu
    # linii wstawia trzydziesci linii i nie wysyla niczego.
    #
    # Ctrl+S usuniety swiadomie: to historyczny XOFF (programowe wstrzymanie
    # terminala) — przy wlaczonym flow control zamrazalby ekran zamiast wyslac.
    #
    # Gora/dol: historia wysylek, ale DOPIERO z brzegu tekstu. W srodku
    # wieloliniowego wpisu strzalki musza ruszac kursor — inaczej wklejenie
    # trzech linii i poprawka w drugiej przestaje byc mozliwe, a to jest
    # powod, dla ktorego ten input w ogole jest TextArea.
    BINDINGS = [
        Binding("enter", "submit", "send", show=False, priority=True),
        Binding("ctrl+j", "newline", "new line", show=False),
        Binding("shift+enter", "newline", "new line", show=False),
        Binding("ctrl+o", "newline", "new line", show=False),
        Binding("up", "history_prev", "previous", show=False),
        Binding("down", "history_next", "next", show=False),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._history = []
        self._history_pos = 0
        self._szkic = ""      # to, co czlowiek pisal, zanim wszedl w historie

    class Submitted(Message):
        """Operator zatwierdzil tekst (Enter) — do wyslania na hub."""

        def __init__(self, input: "MessageInput", text: str) -> None:
            self.input = input
            self.text = text
            super().__init__()

    def action_submit(self) -> None:
        # Straz na fokusie, bo `enter` jest bindingiem PRIORYTETOWYM, a
        # priorytet jest rozwiazywany PRZED fokusem. Bez niej Enter wcisniety
        # przy zaznaczonym innym panelu wysylalby zawartosc pola.
        if not self.has_focus:
            return
        self.post_message(self.Submitted(self, self.text))

    def action_newline(self) -> None:
        if not self.has_focus:
            return
        self.insert("\n")

    def remember(self, text) -> None:
        """Zapamietaj wyslany tekst i wroc na koniec historii.

        Powtorzenie tej samej tresci pod rzad NIE dubluje wpisu — inaczej
        trzy razy wyslane `/stop` wymagaja trzech nacisniec, zeby przewinac
        sie za nie."""
        text = (text or "").strip()
        if text and (not self._history or self._history[-1] != text):
            self._history.append(text)
        self._history_pos = len(self._history)
        # Szkic zostal wyslany, wiec przestaje istniec. Bez tego strzalka
        # w dol po wyslaniu wskrzeszalaby tresc sprzed wysylki.
        self._szkic = ""

    def action_history_prev(self) -> None:
        row, _ = self.cursor_location
        if row > 0:
            self.action_cursor_up()
            return
        self._history_step(-1)

    def action_history_next(self) -> None:
        if self.cursor_location[0] < self.document.line_count - 1:
            self.action_cursor_down()
            return
        self._history_step(1)

    def _history_step(self, direction) -> None:
        # Szkic zapamietujemy w MOMENCIE WEJSCIA w historie, nie przy kazdym
        # kroku — inaczej pierwsza strzalka w gore nadpisalaby go wpisem
        # z historii i powrot w dol oddawalby nie to, co czlowiek pisal.
        w_szkicu = self._history_pos >= len(self._history)
        if w_szkicu and direction < 0:
            self._szkic = self.text
        pos, tekst = history_pick(self._history, self._history_pos, direction)
        wracamy_do_szkicu = pos >= len(self._history)
        self._history_pos = pos
        if tekst is not None:
            self.text = tekst
            self.move_cursor(self.document.end)
            return
        # None z historii ma dwa znaczenia i tylko jedno z nich cos robi:
        # powrot z przegladania do szkicu odtwarza szkic, a strzalka w dol
        # w samym szkicu NIE RUSZA POLA (nie ma przyszlosci do pokazania).
        if direction > 0 and wracamy_do_szkicu and not w_szkicu:
            self.text = self._szkic
            self.move_cursor(self.document.end)


class AgentmachiApp(App):
    TITLE = "agentmachi"
    SUB_TITLE = "human operator"
    BINDINGS = [
        # Rules to zwykle kilka zdan albo nic (swiezy pokoj ma je puste),
        # a zabieraja stala kolumne. Chowanie oddaje szerokosc czatowi —
        # Horizontal przelicza `fr` sam, gdy panel znika.
        Binding("ctrl+r", "toggle_rules", "rules on/off", show=False),
        # Wyjscie pod Ctrl+Q obok wbudowanego Ctrl+C. `priority=True`, bo
        # fokus siedzi w TextArea przez wieksza czesc sesji, a widget ma
        # pierwszenstwo przed App — bez tego skrot dzialalby tylko wtedy,
        # gdy akurat nie piszesz.
        Binding("ctrl+q", "quit", "quit", show=False, priority=True),
    ]
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
        # Czytane przez tests/test_tui.py — punkt obserwacyjny na to, co
        # naprawde trafilo do czatu. RichLog nie daje sie odpytac o tresc,
        # wiec bez tego nie da sie zweryfikowac renderowania ramki. Audyt
        # 2026-07-31 wzial to za martwy kod (grep tylko po tui.py) — NIE JEST.
        self.history = []
        self.connected = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="workspace"):
            with Vertical(id="chat-panel", classes="panel"):
                yield Label("Chat", classes="panel-title")
                yield RichLog(id="chat-log", wrap=True, max_lines=500,
                              auto_scroll=True)
                yield MessageInput(
                    id="message-input",
                    placeholder="message or /stop /kick /groups — "
                                "Enter sends, Shift+Enter = new line, "
                                "arrows = history, Ctrl+Q quits")
            with VerticalScroll(id="participants-panel", classes="panel"):
                yield Label("Participants / groups", classes="panel-title")
                yield Static("", id="participants")
            with VerticalScroll(id="rules-panel", classes="panel"):
                yield Label("Rules / state  (Ctrl+R hides)",
                            classes="panel-title")
                yield Static("connecting...", id="connection-status")
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
            lines.append("(nobody is online)", style="dim")
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
                lines.append(f"  silent for {zaleglosc}", style="dim yellow")
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
                    lines.append(f"  (declared {wiek} frames ago)",
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
        self.rules_text = rules if isinstance(rules, str) else "no rules.md"
        self.query_one("#rules", Static).update(Text(self.rules_text))
        rules_hash = metadata.get("rules_hash")
        label = f"rules_hash: {rules_hash}" if rules_hash else "rules_hash: none"
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
            self._log("client", "the hub sent a frame that is not an object",
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
                    participant.status_note = _opis_deklaracji(status)
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
                participant.status_note = _opis_deklaracji(frame)
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
                self._log("server", f"{target} kicked by {by or '?'}",
                          style="bold red")
        elif kind == "membership_set":
            self._apply_groups(frame.get("target"), frame.get("groups"))
        elif kind == "ok" and "target" in frame and "groups" not in frame:
            self._log("server", f"kicking {frame.get('target')}...",
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
        elif kind == "takeover":
            # Serwer pushuje te ramke NA ZYWO WYLACZNIE do ludzi — bo to oni
            # reaguja na widmo (restart, ubicie klienta). Jedyny adresat, do
            # ktorego celuje, zjadal ja bez sladu (zlapane 2026-07-31).
            self._log("server", frame.get(
                "text", f"{frame.get('nick')}: taken over by a newer hello"),
                style="bold red")
        elif kind == "error":
            self._log("server", frame.get("text", "error"),
                      style="bold red")
        else:
            # Bez tego `else` KAZDY nowy typ OUTBOUND znika po cichu — tak
            # wlasnie zgubil sie `takeover`. Lepiej pokazac czlowiekowi ramke,
            # ktorej nie rozumiemy, niz udawac, ze nie przyszla.
            self._log("server", f"unhandled frame {kind!r}: {frame}",
                      style="dim yellow")

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
                note = _opis_deklaracji(status)
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

    def action_toggle_rules(self) -> None:
        panel = self.query_one("#rules-panel")
        panel.display = not panel.display

    async def _stop_hub(self):
        """Zatrzymaj WLASNY pokoj. Agentow nie ubijamy pojedynczo — hub
        zamyka sockety przy zejsciu, a ich klienty same wchodza w backoff.
        Jedna akcja, nie lista uczestnikow do odklikania."""
        name = os.environ.get("AGENTMACHI_HUB")
        if not name:
            self._log("client",
                      "I do not know which room I am (no AGENTMACHI_HUB) "
                      "— start the TUI with `agentmachi tui --name <room>`",
                      style="bold red")
            return
        # Lazy: agentmachi.cli importuje tui w cmd_tui, wiec import na
        # poziomie modulu zamknalby cykl.
        from agentmachi.cli import stop_hub
        ok, komunikat = stop_hub(name)
        self._log("server" if ok else "client", komunikat,
                  style="bold yellow" if ok else "bold red")
        if ok:
            self._log("client",
                      "agents disconnect on their own and go into backoff. "
                      "History and tokens STAY — `agentmachi start --name "
                      f"{name}` returns to the same log and the same "
                      "cursors (none of them needs a reset).", style="dim")

    def _reset_cursor(self):
        """Ostatnia deska: kursor z poprzedniego huba na tym samym porcie.
        Zdarza sie po `del` + `start`, nie po `stop` + `start`."""
        try:
            self.adapter.session.reset_cursor()
        except (SessionError, OSError) as exc:
            self._log("client", f"cursor reset failed: {exc}",
                      style="bold red")
            return
        self._log("client",
                  "cursor zeroed. On the next entry you get the history from "
                  "the beginning — restart the TUI.",
                  style="bold yellow")

    async def _kill_hub(self, potwierdzenie):
        """Zatrzymaj i SKASUJ pokoj — z historia, tokenami i katalogiem.
        Po tym nie ma go nawet w `agentmachi list`. Nieodwracalne."""
        name = os.environ.get("AGENTMACHI_HUB")
        if not name:
            self._log("client",
                      "I do not know which room I am (no AGENTMACHI_HUB) "
                      "— start the TUI with `agentmachi tui --name <room>`",
                      style="bold red")
            return
        if potwierdzenie != name:
            self._log("client",
                      f"/kill needs the NAME of this room as confirmation: "
                      f"/kill {name}", style="bold red")
            return
        from agentmachi.cli import (delete_hub, hub_pid, stop_hub,
                                    wait_until_down)
        pid = hub_pid(name)
        if pid is not None:
            ok, komunikat = stop_hub(name)
            self._log("server" if ok else "client", komunikat,
                      style="bold yellow" if ok else "bold red")
            # to_thread, bo wait_until_down spi w petli — na golym await
            # zamrozilby cale TUI na te dziesiec sekund.
            if ok and not await asyncio.to_thread(wait_until_down, pid):
                self._log("client",
                          f"room {name!r} did not go down (PID {pid}) — NOT "
                          f"deleting the directory under a live process, "
                          f"that would leave a hub without data. Finish it "
                          f"off by hand: kill -9 {pid}",
                          style="bold red")
                return
        ok, komunikat = delete_hub(name, name)
        if not ok:
            self._log("client", komunikat, style="bold red")
            return
        # Kursorow NIE sprzatamy tutaj: robi to `delete_hub` dla WSZYSTKICH
        # nickow pokoju, nie tylko dla naszego. Druga implementacja obok
        # tamtej rozjechalaby sie przy pierwszej zmianie — a objawem byloby
        # to, ze kursor agenta przezywa pokoj, choc kursor czlowieka nie.
        self.exit(message=f"agentmachi: {komunikat}")

    async def _run_local(self, frame):
        action = frame["action"]
        if action == "stop":
            await self._stop_hub()
        elif action == "kill":
            await self._kill_hub(frame["target"])
        elif action == "reset-cursor":
            self._reset_cursor()

    @on(MessageInput.Submitted)
    async def on_message_submitted(self, event: MessageInput.Submitted):
        # Nazwa metody celowo NIE pasuje do konwencji on_message_input_submitted
        # — dyspozycja idzie wylacznie przez @on, wiec handler nie odpali dwa razy.
        try:
            frame = parse_user_input(event.text)
        except TuiError as exc:
            self._log("client", str(exc), style="bold red")
            return
        if frame["type"] == "local":
            # Komenda operatora — NIE idzie na drut. Historia i czyszczenie
            # pola PRZED wykonaniem: /stop zrywa polaczenie, wiec po nim nie
            # ma pewnosci, ze doszlibysmy tutaj.
            event.input.remember(event.text)
            event.input.clear()
            await self._run_local(frame)
            return
        try:
            await self.adapter.send(frame)
        except TuiError as exc:
            self._log("client", str(exc), style="bold red")
            return
        event.input.remember(event.text)
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
                          "(no mention — agents will not get this; "
                          "use @nick, $group or @all)", style="dim")
        elif frame["type"] == "membership_set":
            groups = ",".join(frame["groups"]) or "—"
            self._log("client", f"sent groups {frame['target']} = {groups}",
                      style="bold yellow")
        else:
            # `/kick` wpadal tu do galezi membership_set i wywalal handler na
            # KeyError('groups') — ramka kick pola groups nie ma. Skutek byl
            # gorszy, niz wyglada: ekran moderatora gasl (return_code 1)
            # DOKLADNIE w sekundzie moderowania, jego socket sie zamykal,
            # a serwer w `_on_kick` ma ACK do moderatora PRZED wyrzuceniem
            # celu — wiec kick zostawal w logu jako trwaly, a wyrzucany
            # siedzial dalej na kanale. Zlapane E2E 2026-08-01 (kick nigdy
            # nie przeszedl przez ten handler w zadnym tescie: test_parse_kick
            # sprawdza PARSOWANIE, a testy aplikacji jada na atrapie adaptera).
            #
            # Fallback, a nie `elif` na sam kick — z tego samego powodu, dla
            # ktorego `apply_hub_frame` ma na koncu `else`: nowa komenda ma
            # zostawic linijke, nie zabic aplikacji czlowieka. Potwierdzenie
            # i tak przychodzi z serwera osobna ramka `ok`.
            cel = frame.get("target", "")
            self._log("client", f"sent {frame['type']} {cel}".rstrip(),
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
