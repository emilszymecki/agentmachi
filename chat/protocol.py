"""Ramki i wzmianki. Zero I/O."""
import math
import re
import sys

# (Runda 4 #5 / laka-nie-obora A2/A3/A4) Rozdzial typow: INBOUND to jedyne
# typy, ktore klient moze przyslac. OUTBOUND to typy WYLACZNIE serwerowe,
# generowane w locie (backlog/resync_required/error/ok). Cala obora wycieta —
# juz nie istnieja: inbound task_*/heartbeat (A2, teraz unknown type), offer
# machinery task_offer/offer_resolved (A3), kolejka zadaniowa task_expired/
# task_expired_batch (A4). Serwer nie planuje pracy; board = state/subject/note.
INBOUND_FRAME_TYPES = {
    "hello", "chat", "fyi", "status", "membership_set", "kick",
}
OUTBOUND_FRAME_TYPES = {
    "backlog", "resync_required", "error", "ok",
    "presence",  # efemeryczny (bez seq): nick wszedl/wypadl z polaczenia
    "takeover",  # F3: TRWALY slad wyparcia nicka przez nowsze hello
}
# `kick` jest jedynym typem, ktory wystepuje w OBU kierunkach: klient
# (human) prosi o wyrzucenie, serwer publikuje TRWALY fakt z polami
# target/by. Rozroznia je zrodlo — inbound niesie tylko `target`.
FRAME_TYPES = INBOUND_FRAME_TYPES | OUTBOUND_FRAME_TYPES

# Kanon statusow agenta (deklarowane ramka `status`; presence
# connected/offline nadaje serwer z zywych polaczen, NIE deklaracja).
# Od tego zadania `state` to WOLNY TEKST (niepusty str, maks 32 znaki) —
# ponizszy zbior to WYLACZNIE dokumentacja stanow umownych, walidacja
# schematu juz go nie egzekwuje (patrz _validate_body):
#   sleeping — smiem czekam na wzmianke (node/agent jeszcze nie obudzony)
#   idle    — czekam na przydzial pracy (deklaruje sie na kanale)
#   working — robie cos (opcjonalnie subject = nad czym, + note co dokladnie)
#   blocked — stoje, czekam na odpowiedz/decyzje (subject/note = na co)
#   review  — skonczylem, czekam na review mojej pracy (subject = czego)
#   done    — task zamkniety (deklaracja koncowa, opcjonalna)
STATUS_STATES = frozenset(
    {"sleeping", "idle", "working", "blocked", "review", "done"})

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
    # (Runda 5 C1) type MUSI byc niepustym stringiem ZANIM sprawdzimy
    # przynaleznosc do FRAME_TYPES: type=[]/{} to unhashable, a `in FRAME_TYPES`
    # (membership po secie) rzucalo TypeError, wywalajac cala walidacje zanim
    # zdazyla zwrocic czytelny blad.
    if not isinstance(ftype, str) or not ftype:
        return "type wymagany (niepusty string)"
    if ftype not in FRAME_TYPES:
        return f"unknown type: {ftype}"
    if ftype not in INBOUND_FRAME_TYPES:
        # znany typ, ale wylacznie wyjsciowy/trwaly — klient nie moze go przyslac
        return f"{ftype}: typ wylacznie wyjsciowy/trwaly, nie moze przyjsc od klienta"
    # wspolne: from niepusty string, ts liczba SKONCZONA (bool wykluczony)
    if "from" not in frame:
        # B6: hello w trybie otwartym moze NIE niesc nicka — agent prosi
        # wtedy o dowolny wolny, a serwer odsyla przydzielony w polu `nick`.
        # Kazda inna ramka nadal wymaga tozsamosci.
        if frame.get("type") == "hello":
            return None
        return "missing from"
    if not isinstance(frame["from"], str) or not frame["from"]:
        return "from wymagany (niepusty string)"
    if "ts" not in frame:
        return "missing ts"
    ts = frame["ts"]
    # (Runda 5 C2) ts musi byc liczba SKONCZONA — NaN/inf przechodzily
    # (isinstance float True) i trafialy do logu jako niestandardowy JSON.
    # (Runda 6 #3) math.isfinite wolamy TYLKO dla float: math.isfinite(10**400)
    # rzuca OverflowError (int za duzy na konwersje do float) i wysypywal cala
    # walidacje. int sprawdzamy zakresowo BEZ konwersji (porownanie int<->float
    # jest w Pythonie dokladne, nie przepelnia): int poza zakresem float to
    # bezsensowny timestamp — odrzucony komunikatem, nie wyjatkiem.
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return "ts wymagany (liczba skonczona)"
    if isinstance(ts, float):
        if not math.isfinite(ts):
            return "ts wymagany (liczba skonczona)"
    elif abs(ts) > sys.float_info.max:
        return "ts wymagany (liczba skonczona)"
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
        if not isinstance(state, str) or not state or len(state) > 32:
            return ("status: state wymagany (niepusty string, "
                    "maks 32 znaki)")
        # B1 retire: task_id wycofane — subject je zastapil. Odrzucamy JAWNIE
        # (nie jako ciche unknown pole), bo handler _append(frame) utrwalilby
        # cala ramke do logu i broadcastu do ludzi zanim board-projekcja by je
        # odsiala; sam drop na boardzie nie wystarcza, zeby task_id nie wyciekl.
        if "task_id" in frame:
            return "status: task_id wycofane; uzyj subject"
        for opt in ("note", "subject"):
            if opt in frame and (not isinstance(frame[opt], str)
                                 or not frame[opt]):
                return f"status: {opt} jesli podany musi byc niepustym stringiem"
        if "target" in frame and (not isinstance(frame["target"], str)
                                  or not frame["target"]):
            return "status: target jesli podany musi byc niepustym stringiem"
        return None
    if ftype == "kick":
        # B6: moderacja czlowieka. Zadnych pol poza target — powod, ban,
        # czas trwania to stan, ktorego nie potrzebujemy (kick nie jest
        # banem: wyrzucony moze wrocic, a moderator moze go wyrzucic znowu).
        target = frame.get("target")
        if not isinstance(target, str) or not target:
            return "kick: target wymagany (niepusty string)"
        return None
    if ftype == "membership_set":
        target = frame.get("target")
        groups = frame.get("groups")
        if not isinstance(target, str) or not target:
            return "membership_set: target wymagany (niepusty string)"
        if not isinstance(groups, list) or not all(
                isinstance(group, str) and group for group in groups):
            return "membership_set: groups wymagane (lista niepustych stringow)"
        return None
    # hello: token/instance_id/last_seq/groups/role waliduje serwer (identity)
    return None
