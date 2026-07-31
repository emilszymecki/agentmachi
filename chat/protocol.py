"""Ramki i wzmianki. Zero I/O."""
import json
import math
import re
import sys

# Sufit JEDNEJ ramki na drucie, w bajtach UTF-8. Mieszka TUTAJ, bo obie
# strony musza mierzyc to samo: serwer egzekwuje go jako `max_size` (obrona
# pamieci huba przed jednym uczestnikiem), a klient sprawdza go PRZED
# wyslaniem. Bez sprawdzenia u klienta `chat` ginie po cichu: chat nie ma
# ACK, serwer zamyka polaczenie kodem 1009, a menedzer kontekstu websockets
# polyka wyjatek — komenda konczy sie zerem, wiadomosci nie ma nigdzie.
MAX_FRAME_BYTES = 64 * 1024


def utf8_safe(obj):
    """Czy ta struktura da sie w ogole zapisac jako UTF-8?

    `\\ud800` (osamotniony surogat) jest POPRAWNYM JSON-em i `json.loads`
    zwraca go jako zwykly znak w stringu — ale UTF-8 takiego znaku nie ma,
    wiec `.encode("utf-8")` rzuca. Pytamy o to PRZED wpuszczeniem ramki,
    bo `chat` jest trwaly PRZED publikacja: raz zapisana taka ramka zostaje
    w events.jsonl i wywala handler przy KAZDYM nastepnym hello, ktorego
    backlog ja obejmuje. Zmierzone: pokoj po jednej takiej ramce oddawal
    1011 kazdemu wznawiajacemu sie — dowolny uczestnik mogl go trwale zabic
    (osme review Codexa)."""
    try:
        json.dumps(obj, ensure_ascii=False).encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def dumps(obj):
    """Serializacja ramki NA DRUT. Zawsze `ensure_ascii=False`.

    Nie jest to kosmetyka, tylko warunek spojnosci sufitow. `max_size`
    websockets liczy bajty UTF-8, a domyslny `json.dumps` rozpisuje kazdy
    znak spoza ASCII na `\\uXXXX` — emoji puchnie z 4 bajtow do 12. Ramka,
    ktora przeszla sufit WEJSCIA jako 65 252 B, wracala w odpowiedzi jako
    195 652 B (zmierzone: 3.0x). Przy oknie rozmowy 200 ramek dawalo to
    37 MB odpowiedzi i klient znow nie mogl sie wznowic — sufit wyjscia
    goniby wejscie w nieskonczonosc. Z `ensure_ascii=False` wyjscie ma ten
    sam rzad co wejscie i arytmetyka sufitow sie domyka.

    NIGDY nie rzuca. Osamotniony surogat nie ma reprezentacji w UTF-8, wiec
    dla takiej ramki wracamy do escapowania — brzydziej i trzy razy wiecej
    bajtow, ale ramka WYCHODZI. To nie jest zapasowa sciezka dla nowych
    danych (te odbija walidacja wejscia), tylko warunek WYLECZALNOSCI pokoju,
    ktory taka ramke juz ma w logu: bez tego zostawalby zatruty na zawsze,
    a naprawa wymagalaby recznej edycji events.jsonl."""
    try:
        tekst = json.dumps(obj, ensure_ascii=False)
        tekst.encode("utf-8")
    except UnicodeEncodeError:
        return json.dumps(obj)
    return tekst


def frame_bytes(obj):
    """Ile ta ramka zajmie na drucie (dokladnie tak, jak liczy max_size)."""
    return len(dumps(obj).encode("utf-8"))


TRUNCATION_MARK = " […ramka przycieta — calosc w events.jsonl]"


_RDZEN = ("type", "from", "ts", "seq")
_MARKERY = ("truncated", "dropped")


def clamp_frame(frame):
    """Przytnij ramke Z LOGU do sufitu drutu. Zwraca ramke albo jej KOPIE.

    GWARANCJA BEZWARUNKOWA: wynik ma <= MAX_FRAME_BYTES. Bez niej cala
    arytmetyka sufitow jest zyczeniem — a to ona decyduje, czy agent zdola
    sie wznowic.

    Po co w ogole: sufit wejscia dotyczy tylko tego, co przychodzi OD TERAZ,
    i nie przepisuje historii. Log zalozony pod poprzednim domyslnym sufitem
    websockets moze trzymac ramki blisko 1 MiB — dosc, by przekroczyc sufit
    odbioru klienta i zablokowac wznowienie PO UPGRADZIE huba, czyli tam,
    gdzie nikt nie szuka przyczyny.

    Trzy kroki, od najmniej do najbardziej niszczacego:

    1. `text` — przycinany, bo to zwykle on rozdyma ramke. ZBIOR WZMIANEK
       jest niezmiennikiem: `@nick` i `$grupa` przenosza sie za znacznik.
       Wzmianka to jedyny mechanizm budzenia (`node._should_wake` parsuje
       dostarczony tekst), wiec zgubiona znaczy, ze adresat sie nie obudzi.
       Rozciety token urywamy dopiero, gdy porownanie zbiorow pokaze, ze
       zmyslil wzmianke — `@beta-dwa` -> `@beta` budzi NIE TEGO agenta.
    2. `note` — to samo, bez wzmianek.
    3. pola spoza rdzenia, od najwiekszego — usuwane, nazwy trafiaja do
       `dropped`. Krok istnieje, bo ramke moze rozdymac pole, o ktorym ten
       kod nie wie: stary log przepuszczal dowolne dodatkowe pola do 1 MiB.
       60 takich ramek zostawalo 55 MB po przycieciu samego `text`
       (dziesiate review Codexa).

    Miara to `frame_bytes` GOTOWEJ ramki, nie dlugosc prefiksu: `dumps`
    escapuje znaki sterujace, wiec NUL rosnie z 1 bajtu do szesciu.
    Ciecie po ZNAKACH nie rozlupie znaku wielobajtowego — indeksowanie str
    idzie po punktach kodowych.
    """
    if frame_bytes(frame) <= MAX_FRAME_BYTES:
        return frame
    out = dict(frame)

    for pole in ("text", "note"):
        if frame_bytes(out) <= MAX_FRAME_BYTES:
            break
        wartosc = out.get(pole)
        if isinstance(wartosc, str) and wartosc:
            _przytnij_pole(out, pole, wartosc)

    if frame_bytes(out) <= MAX_FRAME_BYTES:
        return out

    # Krok 3: ramke rozdyma cos, czego ten kod nie zna z nazwy.
    usuniete = []
    kandydaci = sorted(
        (k for k in out if k not in _RDZEN and k not in _MARKERY),
        key=lambda k: len(dumps(out[k])), reverse=True)
    for klucz in kandydaci:
        if frame_bytes(out) <= MAX_FRAME_BYTES:
            break
        del out[klucz]
        usuniete.append(klucz)
    if usuniete:
        out["dropped"] = usuniete
        # sam spis nazw tez moze nie wejsc (setki pol) — wtedy tylko liczba
        if frame_bytes(out) > MAX_FRAME_BYTES:
            out["dropped"] = len(usuniete)
    if frame_bytes(out) <= MAX_FRAME_BYTES:
        return out

    # Krok 4: rozdyma nas SAM RDZEN. Nick nie ma limitu dlugosci, wiec pokoj
    # zalozony pod starym sufitem 1 MiB mogl miec uczestnika o nicku wiekszym
    # niz cala dzisiejsza ramka — i wtedy KAZDY jego wpis w logu byl ponad
    # sufitem (jedenaste review Codexa). Przycinamy `from`/`type` na koncu,
    # bo to psuje rozpoznanie nadawcy — ale ramka ponad sufitem psuje
    # wznowienie WSZYSTKIM, wiec wybor jest miedzy zla a gorsza opcja.
    # `ts` i `seq` zostaja nietkniete: na `seq` stoi kursor.
    for pole in ("from", "type"):
        if frame_bytes(out) <= MAX_FRAME_BYTES:
            break
        wartosc = out.get(pole)
        if isinstance(wartosc, str) and wartosc:
            _przytnij_pole(out, pole, wartosc, wymus=True)
    return out


def _przytnij_pole(out, pole, wartosc, wymus=False):
    """Najdluzszy prefiks `wartosc`, przy ktorym cala ramka wchodzi w sufit.

    Domyslnie sprawdzamy najpierw, czy to pole W OGOLE jest problemem: gdy
    ramka nie miesci sie nawet z PUSTYM tym polem, rozdyma ja co innego —
    wtedy zostawiamy je nietkniete i oddajemy robote nastepnemu krokowi. Bez
    tej kontroli ramka z krotkim `text` i wielkim obcym polem tracila `text`
    do zera, zanim ktokolwiek tknal winowajce.

    `wymus=True` te kontrole wylacza i jest konieczne w kroku 4, gdzie
    rozdyma nas KILKA pol rdzenia naraz: przy wielkim `type` I wielkim
    `from` kontrola odpowiada "to nie ja" dla obu, wiec zadne nie zostaje
    przyciete i gwarancja pada. Zlapane fuzzem, nie przemysleniem."""
    oryginal = out[pole]
    out[pole] = ""
    if not wymus and frame_bytes(out) > MAX_FRAME_BYTES:
        out[pole] = oryginal
        return
    out["truncated"] = len(wartosc)
    if pole == "text":
        wzmianki, grupy = parse_mentions(wartosc), parse_groups(wartosc)
    else:
        wzmianki, grupy = set(), set()
    etykiety = ([f"@{n}" for n in sorted(wzmianki)]
                + [f"${g}" for g in sorted(grupy)])
    ogon = TRUNCATION_MARK + (" " + " ".join(etykiety) if etykiety else "")

    def _bez_rozcietego_tokenu(prefiks):
        if (parse_mentions(prefiks) <= wzmianki
                and parse_groups(prefiks) <= grupy):
            return prefiks
        i = len(prefiks)
        while i > 0 and not prefiks[i - 1].isspace():
            i -= 1
        return prefiks[:i]

    def _miesci(dlugosc, sufiks):
        out[pole] = _bez_rozcietego_tokenu(wartosc[:dlugosc]) + sufiks
        return frame_bytes(out) <= MAX_FRAME_BYTES

    if not _miesci(0, ogon):
        out[pole] = TRUNCATION_MARK if _miesci(0, TRUNCATION_MARK) else ""
        return

    lo, hi = 0, len(wartosc)
    while lo < hi:
        srodek = (lo + hi + 1) // 2
        if _miesci(srodek, ogon):
            lo = srodek
        else:
            hi = srodek - 1
    _miesci(lo, ogon)

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

# Myslnik NALEZY do nicka. Hub przyjmuje kazdy niepusty string jako nick
# (identity.py), a rules kanalu pkt 15 wprost kaza prefiksowac nazwy
# pomocnicze wlasnym nickiem — "tester-worker3", "wt-worker2". Przy samym
# \w takie wzmianki rozpadaly sie cicho: "@tester-worker3" parsowalo sie do
# "tester", ktorego nikt nie trzyma, wiec adresat NIE BYL budzony, a nadawca
# nie dostawal zadnego bledu.
#
# Zmierzone na zywym kanale: agent 'tester-claude' wszedl poprawnie
# (hello seq 116), ramka "@tester-claude ..." wyladowala w logu (seq 118)
# i nie dotarla do niego wcale. Regula kanalu instruowala wiec agentow, zeby
# nadawali sobie nazwy, ktorych nikt nie moze zawolac.
#
# Myslnik tylko MIEDZY segmentami: "@nick-" na koncu zdania albo "@nick-,"
# ma dac "nick", nie "nick-". Ta sama zasada dla grup.
_MENTION = re.compile(r"(?:^|\s)@(\w+(?:-\w+)*)")
_GROUP = re.compile(r"(?:^|\s)\$(\w+(?:-\w+)*)")


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
    # C2: kontrola `context` MUSI stac PRZED galezia nickless hello ponizej —
    # tamta konczy walidacje returnem, wiec kontrola w _validate_body nigdy
    # by sie nie wykonala dla wejscia bez nicka. A to wlasnie ta sciezka jest
    # tu krytyczna: agent wpuszczany po niezalezna perspektywe czesto nie ma
    # jeszcze nicka i prosi hub o dowolny wolny. Cichy fallback do "full"
    # znaczylby, ze prosil o wejscie bez kotwicy, dostal ja i nigdy sie
    # o tym nie dowiedzial.
    if ftype == "hello":
        ctx = frame.get("context")
        if ctx is not None and ctx not in ("full", "fresh"):
            return "context must be 'full' or 'fresh'"
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
