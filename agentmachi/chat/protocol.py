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
    backlog ja obejmuje: pokoj oddaje 1011 kazdemu wznawiajacemu sie, wiec
    dowolny uczestnik moze go trwale zabic jedna ramka."""
    try:
        json.dumps(obj, ensure_ascii=False).encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def dumps(obj):
    """Serializacja ramki NA DRUT. Zawsze `ensure_ascii=False`.

    Nie jest to kosmetyka, tylko warunek spojnosci sufitow. `max_size`
    websockets liczy bajty UTF-8, a domyslny `json.dumps` rozpisuje kazdy
    znak spoza ASCII na `\\uXXXX` — emoji puchnie z 4 bajtow do 12. Ramka
    tuz pod sufitem WEJSCIA wraca wtedy ~3x wieksza; przy oknie rozmowy 200
    ramek to 37 MB odpowiedzi i klient nie moze sie wznowic — sufit wyjscia
    gonilby wejscie w nieskonczonosc. Z `ensure_ascii=False` wyjscie ma ten
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


TRUNCATION_MARK = " […frame truncated — full text in events.jsonl]"


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
       60 takich ramek zostaje 55 MB po przycieciu samego `text`.

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
    kandydaci = [k for k in out if k not in _RDZEN and k not in _MARKERY]
    # Koszt liczony RAZ na klucz, i to DOKLADNIE: `"klucz":wartosc` plus
    # dwa separatory. Dwie rzeczy, ktore trzeba tu zrobic dobrze:
    #
    # (a) NAZWA klucza wchodzi do kosztu. Ranking po samych wartosciach
    #     stawia 100 KiB w nazwie klucza z pusta wartoscia za krotkim
    #     `text` — kasujemy wtedy TRESC WIADOMOSCI, zostawiajac winowajce.
    # (b) Odejmujemy koszt od biezacego rozmiaru zamiast serializowac cala
    #     ramke po KAZDYM usunieciu. Tamto jest kwadratowe i SYNCHRONICZNE
    #     w petli zdarzeń: legalna ramka sprzed sufitu (8000 malych pol,
    #     905 KiB) zamraza CALY hub na 18,7 s przy czyimkolwiek hello.
    #     Nie "jeden klient sie nie wznowi" — wszyscy stoja.
    koszt = {k: len(dumps(k).encode("utf-8"))
                + len(dumps(out[k]).encode("utf-8")) + 2 for k in kandydaci}
    kandydaci.sort(key=lambda k: koszt[k], reverse=True)
    biezacy = frame_bytes(out)
    for klucz in kandydaci:
        if biezacy <= MAX_FRAME_BYTES:
            break
        del out[klucz]
        biezacy -= koszt[klucz]
        usuniete.append(klucz)
    # Koszt jest dokladny (dla ostatniego klucza zawyzony o przecinek), wiec
    # ta petla to straznik, nie sciezka robocza — ma nie dac gwarancji upasc,
    # gdyby ktos kiedys zmienil serializacje.
    for klucz in [k for k in out if k not in _RDZEN and k not in _MARKERY]:
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
    # niz cala dzisiejsza ramka — i wtedy KAZDY jego wpis w logu jest ponad
    # sufitem. Przycinamy `from`/`type` na koncu,
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
    tej kontroli ramka z krotkim `text` i wielkim obcym polem traci `text`
    do zera, zanim ktokolwiek tknie winowajce.

    `wymus=True` te kontrole wylacza i jest konieczne w kroku 4, gdzie
    rozdyma nas KILKA pol rdzenia naraz: przy wielkim `type` I wielkim
    `from` kontrola odpowiada "to nie ja" dla obu, wiec zadne nie zostaje
    przyciete i gwarancja pada."""
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

# INBOUND to jedyne typy, ktore klient moze przyslac. OUTBOUND to typy
# WYLACZNIE serwerowe, generowane w locie (backlog/resync_required/error/ok).
# Serwer nie planuje pracy — typy zadaniowe (task_*, heartbeat, oferty)
# wycofano celowo; board to state/subject/note.
INBOUND_FRAME_TYPES = {
    "hello", "chat", "fyi", "status", "membership_set", "kick",
    "workspace",  # efemeryczny (bez seq): gdzie pracuje klient — patrz _validate_body
}
OUTBOUND_FRAME_TYPES = {
    "backlog", "resync_required", "error", "ok",
    "presence",  # efemeryczny (bez seq): nick wszedl/wypadl z polaczenia
    "takeover",  # TRWALY slad wyparcia nicka przez nowsze hello
}
# `kick` jest jedynym typem, ktory wystepuje w OBU kierunkach: klient
# (human) prosi o wyrzucenie, serwer publikuje TRWALY fakt z polami
# target/by. Rozroznia je zrodlo — inbound niesie tylko `target`.
FRAME_TYPES = INBOUND_FRAME_TYPES | OUTBOUND_FRAME_TYPES

# Kanon statusow agenta (deklarowane ramka `status`; presence
# connected/offline nadaje serwer z zywych polaczen, NIE deklaracja).
# `state` to WOLNY TEKST (niepusty str, maks 32 znaki) — ponizszy zbior
# to WYLACZNIE dokumentacja stanow umownych, walidacja schematu go nie
# egzekwuje (patrz _validate_body):
#   sleeping — spie, czekam na wzmianke (node/agent jeszcze nie obudzony)
#   idle    — czekam na przydzial pracy (deklaruje sie na kanale)
#   working — robie cos (opcjonalnie subject = nad czym, + note co dokladnie)
#   blocked — stoje, czekam na odpowiedz/decyzje (subject/note = na co)
#   review  — skonczylem, czekam na review mojej pracy (subject = czego)
#   done    — task zamkniety (deklaracja koncowa, opcjonalna)
STATUS_STATES = frozenset(
    {"sleeping", "idle", "working", "blocked", "review", "done"})

# Myslnik NALEZY do nicka. Hub przyjmuje kazdy niepusty string jako nick
# (identity.py), a nicki pomocnicze bywaja prefiksowane — "tester-worker3".
# Przy samym \w takie wzmianki rozpadaja sie cicho: "@tester-worker3"
# parsuje sie do "tester", ktorego nikt nie trzyma, wiec adresat NIE JEST
# budzony, a nadawca nie dostaje zadnego bledu.
#
# Myslnik tylko MIEDZY segmentami: "@nick-" na koncu zdania albo "@nick-,"
# ma dac "nick", nie "nick-". Ta sama zasada dla grup.
_MENTION = re.compile(r"(?:^|\s)@(\w+(?:-\w+)*)")
_GROUP = re.compile(r"(?:^|\s)\$(\w+(?:-\w+)*)")


def parse_mentions(text):
    return set(_MENTION.findall(text or ""))


def parse_groups(text):
    # Group names are lowercase by channel convention; all-caps tokens like
    # $HOME / $PATH are shell variables in ordinary technical talk, not groups.
    return {g for g in _GROUP.findall(text or "") if not g.isupper()}


def make_frame(ftype, frm, ts, **fields):
    return {"type": ftype, "from": frm, "ts": ts, **fields}


def validate(frame):
    # Walidacja INBOUND ze SCHEMATEM PER TYP: wspolne pola + per-typ.
    # Wejscie klienckie musi przejsc tu ZANIM dotknie logu/kolejki.
    if "type" not in frame:
        return "missing type"
    ftype = frame["type"]
    # type MUSI byc niepustym stringiem ZANIM sprawdzimy przynaleznosc do
    # FRAME_TYPES: type=[]/{} to unhashable, a `in FRAME_TYPES` rzuca
    # TypeError, wywalajac cala walidacje zanim zwroci czytelny blad.
    if not isinstance(ftype, str) or not ftype:
        return "type required (non-empty string)"
    if ftype not in FRAME_TYPES:
        return f"unknown type: {ftype}"
    if ftype not in INBOUND_FRAME_TYPES:
        # znany typ, ale wylacznie wyjsciowy/trwaly — klient nie moze go przyslac
        return f"{ftype}: outbound/persisted-only type, a client cannot send it"
    # Kontrola `context` MUSI stac PRZED galezia nickless hello ponizej —
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
        # `peek` = podglad bez sladu (board/read). Nie-bool odrzucony, nie
        # potraktowany jak False: klient, ktory prosil o podglad i dostal
        # pelne wejscie, zostawilby w pokoju nick-ducha nie wiedzac o tym.
        if "peek" in frame and not isinstance(frame["peek"], bool):
            return "peek must be true or false"
    # wspolne: from niepusty string, ts liczba SKONCZONA (bool wykluczony)
    if "from" not in frame:
        # Hello w trybie otwartym moze NIE niesc nicka — agent prosi
        # wtedy o dowolny wolny, a serwer odsyla przydzielony w polu `nick`.
        # Kazda inna ramka nadal wymaga tozsamosci.
        if frame.get("type") == "hello":
            return None
        return "missing from"
    if not isinstance(frame["from"], str) or not frame["from"]:
        return "from required (non-empty string)"
    if "ts" not in frame:
        return "missing ts"
    ts = frame["ts"]
    # ts musi byc liczba SKONCZONA — NaN/inf przechodza isinstance(float)
    # i trafilyby do logu jako niestandardowy JSON.
    # math.isfinite wolamy TYLKO dla float: math.isfinite(10**400) rzuca
    # OverflowError (int za duzy na konwersje do float) i wysypuje cala
    # walidacje. int sprawdzamy zakresowo BEZ konwersji (porownanie int<->float
    # jest w Pythonie dokladne, nie przepelnia): int poza zakresem float to
    # bezsensowny timestamp — odrzucony komunikatem, nie wyjatkiem.
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return "ts required (finite number)"
    if isinstance(ts, float):
        if not math.isfinite(ts):
            return "ts required (finite number)"
    elif abs(ts) > sys.float_info.max:
        return "ts required (finite number)"
    return _validate_body(frame, ftype)


def _validate_body(frame, ftype):
    if ftype in ("chat", "fyi"):
        # ani chat, ani fyi bez sensownego text nie moga trafic do logu/humana
        text = frame.get("text")
        if not isinstance(text, str) or not text:
            return f"{ftype}: text required (non-empty string)"
        return None
    if ftype == "status":
        state = frame.get("state")
        if not isinstance(state, str) or not state or len(state) > 32:
            return ("status: state required (non-empty string, "
                    "max 32 characters)")
        # task_id (zastapione przez subject) odrzucamy JAWNIE, z podpowiedzia:
        # handler _append(frame) utrwalilby cala ramke do logu i broadcastu
        # do ludzi, zanim board-projekcja by je odsiala.
        if "task_id" in frame:
            return "status: task_id is retired; use subject"
        # Nieznany klucz odbity, nie zgubiony: handler utrwala cala ramke,
        # a board projektuje tylko state/subject/note — agent dostaje
        # "(sent)" i mysli, ze zadeklarowal cos (np. `text` zamiast
        # `subject`), czego nikt nie zobaczy.
        nieznane = set(frame) - {"type", "from", "ts", "state", "subject",
                                 "note", "target"}
        if nieznane:
            return (f"status: unknown field(s): {', '.join(sorted(nieznane))}"
                    f" — the board shows only state, subject and note")
        for opt in ("note", "subject"):
            if opt in frame and (not isinstance(frame[opt], str)
                                 or not frame[opt]):
                return f"status: {opt} if given must be a non-empty string"
        if "target" in frame and (not isinstance(frame["target"], str)
                                  or not frame["target"]):
            return "status: target if given must be a non-empty string"
        return None
    if ftype == "workspace":
        # Gdzie pracuje agent — fakt, ktory klient zna, a ktorego agent nie
        # aktualizuje recznie. Bez absolutnych sciezek: `worktree` to
        # nazwa katalogu, nie sciezka. Brak `branch` = detached HEAD.
        nieznane = set(frame) - {"type", "from", "ts", "worktree", "branch",
                                 "head"}
        if nieznane:
            return f"workspace: unknown field(s): {', '.join(sorted(nieznane))}"
        if not set(frame) - {"type", "from", "ts"}:
            return None   # pusta ramka = listener odwoluje swoj workspace
        worktree, head = frame.get("worktree"), frame.get("head")
        if (not isinstance(worktree, str) or not worktree
                or len(worktree) > 100 or "/" in worktree or "\\" in worktree):
            return "workspace: worktree required (directory name, max 100)"
        if (not isinstance(head, str) or not 4 <= len(head) <= 40
                or any(c not in "0123456789abcdef" for c in head)):
            return "workspace: head required (hex commit, 4-40)"
        if "branch" in frame and (not isinstance(frame["branch"], str)
                                  or not frame["branch"]
                                  or len(frame["branch"]) > 100):
            return "workspace: branch if given must be a non-empty string (max 100)"
        return None
    if ftype == "kick":
        # Moderacja czlowieka. Zadnych pol poza target — powod, ban,
        # czas trwania to stan, ktorego nie potrzebujemy (kick nie jest
        # banem: wyrzucony moze wrocic, a moderator moze go wyrzucic znowu).
        target = frame.get("target")
        if not isinstance(target, str) or not target:
            return "kick: target required (non-empty string)"
        return None
    if ftype == "membership_set":
        target = frame.get("target")
        groups = frame.get("groups")
        if not isinstance(target, str) or not target:
            return "membership_set: target required (non-empty string)"
        if not isinstance(groups, list) or not all(
                isinstance(group, str) and group for group in groups):
            return "membership_set: groups required (list of non-empty strings)"
        return None
    # hello: token/instance_id/last_seq/groups/role waliduje serwer (identity)
    return None
