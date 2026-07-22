"""Ramki, wzmianki i activation envelope. Zero I/O."""
import re

FRAME_TYPES = {
    "hello", "chat", "fyi", "status", "backlog", "resync_required",
    "task_new", "task_offer", "task_claim", "task_done", "task_blocked",
    "review_changes", "task_approve", "task_unblock", "error", "ok",
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
    if "type" not in frame:
        return "missing type"
    if frame["type"] not in FRAME_TYPES:
        return f"unknown type: {frame['type']}"
    if "from" not in frame:
        return "missing from"
    if "ts" not in frame:
        return "missing ts"
    if frame["type"] == "chat":
        # domkniecie kontraktu wejscia: chat bez sensownego text nie moze
        # trafic ani do logu, ani do humana — twardy blad do nadawcy
        text = frame.get("text")
        if not isinstance(text, str) or not text:
            return "chat: text wymagany (niepusty string)"
    return None


def make_envelope(nick, frames, seq_from, seq_to):
    return {
        "activation_id": f"{nick}:{seq_from}-{seq_to}",
        "nick": nick,
        "seq_from": seq_from,
        "seq_to": seq_to,
        "backlog": frames,
    }
