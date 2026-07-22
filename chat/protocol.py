"""Ramki, wzmianki i activation envelope. Zero I/O."""
import re

# (Runda 4 #5) Rozdzial typow: INBOUND to jedyne typy, ktore klient moze
# przyslac. OUTBOUND to typy WYLACZNIE serwerowe — albo generowane w locie
# (task_offer/backlog/resync_required/error/ok), albo trwale eventy stanu
# zapisywane przez serwer (task_expired/offer_resolved). validate odrzuca
# inbound-em kazda ramke typu outbound-only (znany typ, ale nie od klienta).
INBOUND_FRAME_TYPES = {
    "hello", "chat", "fyi", "status",
    "task_new", "task_claim", "task_done", "task_blocked",
    "review_changes", "task_approve", "task_unblock",
}
OUTBOUND_FRAME_TYPES = {
    "task_offer", "backlog", "resync_required", "error", "ok",
    "task_expired", "offer_resolved",
}
FRAME_TYPES = INBOUND_FRAME_TYPES | OUTBOUND_FRAME_TYPES

# task_* inbound wymagaja command_id (wszystkie) i task_id (poza task_new,
# ktory taska dopiero tworzy). Glebsza walidacja (card/expected_task_version/
# CAS/WIP/lease) nalezy do TaskQueue — validate to tylko schemat framingu.
_TASK_INBOUND = INBOUND_FRAME_TYPES & {
    "task_new", "task_claim", "task_done", "task_blocked",
    "review_changes", "task_approve", "task_unblock",
}
_MENTION = re.compile(r"(?:^|\s)@(\w+)")
_GROUP = re.compile(r"(?:^|\s)\$(\w+)")


def parse_mentions(text):
    return set(_MENTION.findall(text or ""))


def parse_groups(text):
    return set(_GROUP.findall(text or ""))


def make_frame(ftype, frm, ts, **fields):
    return {"type": ftype, "from": frm, "ts": ts, **fields}


def validate(frame):
    # (Runda 4 #5) walidacja INBOUND ze SCHEMATEM PER TYP: wspolne pola +
    # per-typ. Wejscie klienckie musi przejsc tu ZANIM dotknie logu/kolejki.
    if "type" not in frame:
        return "missing type"
    ftype = frame["type"]
    if ftype not in FRAME_TYPES:
        return f"unknown type: {ftype}"
    if ftype not in INBOUND_FRAME_TYPES:
        # znany typ, ale wylacznie wyjsciowy/trwaly — klient nie moze go przyslac
        return f"{ftype}: typ wylacznie wyjsciowy/trwaly, nie moze przyjsc od klienta"
    # wspolne: from niepusty string, ts liczba (bool wykluczony)
    if "from" not in frame:
        return "missing from"
    if not isinstance(frame["from"], str) or not frame["from"]:
        return "from wymagany (niepusty string)"
    if "ts" not in frame:
        return "missing ts"
    ts = frame["ts"]
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return "ts wymagany (liczba)"
    return _validate_body(frame, ftype)


def _validate_body(frame, ftype):
    if ftype in ("chat", "fyi"):
        # ani chat, ani fyi bez sensownego text nie moga trafic do logu/humana
        text = frame.get("text")
        if not isinstance(text, str) or not text:
            return f"{ftype}: text wymagany (niepusty string)"
        return None
    if ftype == "status":
        state = frame.get("state")
        if not isinstance(state, str) or not state:
            return "status: state wymagany (niepusty string)"
        return None
    if ftype in _TASK_INBOUND:
        command_id = frame.get("command_id")
        if not isinstance(command_id, str) or not command_id:
            return f"{ftype}: command_id wymagany (niepusty string)"
        if ftype != "task_new":
            task_id = frame.get("task_id")
            if not isinstance(task_id, str) or not task_id:
                return f"{ftype}: task_id wymagany (niepusty string)"
        return None
    # hello: token/instance_id/last_seq/groups/role waliduje serwer (identity)
    return None


def make_envelope(nick, frames, seq_from, seq_to):
    return {
        "activation_id": f"{nick}:{seq_from}-{seq_to}",
        "nick": nick,
        "seq_from": seq_from,
        "seq_to": seq_to,
        "backlog": frames,
    }
