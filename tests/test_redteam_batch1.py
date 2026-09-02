"""Red-team, batch 1 — regresje na GRANICE, które trzymają.

Eksperyment 2 (red team na kopii), 2026-09-01, pokój `redteam` na izolowanym
HOME. agent1 (atak) zgłosił wektory, agent2 (triage) odtworzył je na
izolowanym `ChatServer` i potwierdził, CO hub broni. Te testy pilnują tego,
co się obroniło — żeby przyszła zmiana nie odsłoniła tego po cichu.

Raport wymieniał DWIE DZIURY, które świadomie zostawiono bez czerwonego
testu, bo ich naprawa przesądzałaby kierunek za właściciela. **2026-09-03
właściciel zwolnił obie do naprawy** i pierwsza z nich jest już zamknięta:
`target` z ramki chat nie dociera ani do logu, ani do odbiorcy
(`test_target_z_ramki_chat_nie_dociera_ani_do_logu_ani_do_odbiorcy`) — to
było dowiezienie inwariantu, który `CLAUDE.md` już deklarował, nie nowy
mechanizm. Druga — hub przyjmuje nick ze znakami kontrolnymi
(`protocol.py:264` celowo dozwala myślnik i unicode) — jest w robocie
u drugiego agenta i tutaj jej nie ma.

Wzorzec repo: sync + asyncio.run + _free_port, bez pytest-asyncio.
"""
import asyncio
import json
import socket

import websockets

from chat.server import ChatServer

TOKENS = {"human": {"token": "h", "role": "human"}}


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _run(scenario):
    """Postaw izolowany hub w open_mode i przepuść przez niego scenariusz."""
    async def go():
        import tempfile
        import pathlib
        port = _free_port()
        tmp = pathlib.Path(tempfile.mkdtemp())
        srv = ChatServer(data_dir=tmp, tokens=TOKENS, port=port,
                         open_mode=True)
        await srv.start()
        try:
            return await asyncio.wait_for(scenario(srv, port), timeout=10)
        finally:
            await srv.stop()
    asyncio.run(go())


async def _hello(port, nick, inst="i1"):
    ws = await websockets.connect(f"ws://127.0.0.1:{port}")
    await ws.send(json.dumps({"type": "hello", "from": nick, "ts": 0.0,
                              "instance_id": inst, "last_seq": 0,
                              "role": "agent", "groups": []}))
    reply = json.loads(await asyncio.wait_for(ws.recv(), 2))
    return ws, reply


async def _recv(ws, timeout=1.0):
    """Następna ramka pomijając efemeryczne presence; None przy ciszy."""
    try:
        while True:
            f = json.loads(await asyncio.wait_for(ws.recv(), timeout))
            if f.get("type") == "presence":
                continue
            return f
    except asyncio.TimeoutError:
        return None


async def _drain(ws):
    try:
        while True:
            await asyncio.wait_for(ws.recv(), 0.15)
    except asyncio.TimeoutError:
        pass


def test_target_z_ramki_chat_nie_wplywa_na_routing():
    r"""`target` sfałszowany na ramce chat NIE kieruje jej do celu.

    Inwariant huba: chat bez wzmianki w TEKŚCIE nie budzi agentów. Napastnik
    próbuje obejść to polem `target` (jest na liście autorytatywnej). Routing
    (`_publish_chat`) czyta wyłącznie `mentions` z tekstu — więc ofiara, nie
    wzmiankowana w treści, NIE dostaje ramki, choć `target` na nią wskazuje.
    Kontrola w tym samym teście dowodzi, że routing DZIAŁA (wzmianka w tekście
    dociera) — bez niej zielony wynik mógłby znaczyć „nic nie działa", nie
    „target nie routuje". Ta kontrola złapała trzy błędy harnessu przy triage.
    """
    async def scenario(srv, port):
        wsA, _ = await _hello(port, "napastnik")
        wsV, _ = await _hello(port, "ofiara")
        for w in (wsA, wsV):
            await _drain(w)

        # target=ofiara, ale BEZ @ofiara w tekście
        await wsA.send(json.dumps({"type": "chat", "from": "napastnik",
                                   "ts": 1.0, "target": "ofiara",
                                   "text": "przez-target"}))
        assert await _recv(wsV, 0.8) is None, \
            "target skierował chat do ofiary — routing czyta pole klienta"

        # kontrola: wzmianka W TEKŚCIE dociera (dowód, że routing żyje)
        await wsA.send(json.dumps({"type": "chat", "from": "napastnik",
                                   "ts": 2.0, "text": "@ofiara przez-mention"}))
        got = await _recv(wsV, 0.8)
        assert got and "przez-mention" in got.get("text", ""), \
            "kontrola: wzmianka w tekście NIE dotarła — harness zepsuty, " \
            "wynik wyżej nieważny"
    _run(scenario)


def test_target_z_ramki_chat_nie_dociera_ani_do_logu_ani_do_odbiorcy():
    r"""`target` podany przez klienta na ramce chat ZNIKA — z logu i z drutu.

    Dziura 1 z red-teamu (2026-09-01), naprawiona 2026-09-03. Wcześniej wartość
    z klienta przechodziła nietknięta: routing jej nie czytał (pilnuje tego
    `test_target_z_ramki_chat_nie_wplywa_na_routing`), więc nie był to exploit
    — ale ramka w logu **kłamała o adresacie**, a `read` i `listen --json`
    oddają ją wiernie każdemu, kto po nią sięgnie. `target` jest na liście pól
    autorytatywnych w `CLAUDE.md`, a dla chatu wartość autorytatywna to BRAK:
    adresatów wyznacza wyłącznie wzmianka w treści.

    Sprawdzamy OBA końce, bo naprawa tylko na drucie zostawiłaby kłamstwo tam,
    gdzie przeżyje pokój — w logu.

    Falsyfikacja w drugą stronę jest w tym samym teście: `status` dostaje
    `target` NADANY PRZEZ SERWER. Bez tego członu zielony wynik znaczyłby
    równie dobrze „hub zgubił pole target wszędzie", a to byłaby inna wada,
    nie ta naprawa.
    """
    async def scenario(srv, port):
        wsA, _ = await _hello(port, "napastnik")
        wsV, _ = await _hello(port, "ofiara")
        for w in (wsA, wsV):
            await _drain(w)

        # wzmianka W TEKSCIE, zeby ramka dotarla — i target sfalszowany obok
        await wsA.send(json.dumps({"type": "chat", "from": "napastnik",
                                   "ts": 1.0, "target": "ktos-inny",
                                   "text": "@ofiara tresc"}))
        got = await _recv(wsV, 1.0)
        assert got and "tresc" in got.get("text", ""), \
            "kontrola: ramka nie dotarla — harness zepsuty, wynik nizej niewazny"
        assert "target" not in got, \
            f"target z klienta dotarl na drucie do odbiorcy: {got.get('target')!r}"

        # log przezyje pokoj — tam klamstwo boli najdluzej
        czaty = [e for e in srv.log.replay() if e.get("type") == "chat"]
        assert czaty, "kontrola: w logu nie ma ramki chat — nie ma czego sprawdzac"
        assert all("target" not in e for e in czaty), \
            "target z klienta zostal zapisany w logu"

        # falsyfikacja w druga strone: dla `status` target NADAJE serwer
        await wsA.send(json.dumps({"type": "status", "from": "napastnik",
                                   "ts": 2.0, "state": "idle"}))
        await asyncio.sleep(0.3)
        statusy = [e for e in srv.log.replay() if e.get("type") == "status"]
        assert statusy and statusy[-1].get("target") == "napastnik", \
            "status stracil serwerowy target — naprawa zabrala za duzo"
    _run(scenario)


def test_from_role_seq_spoofowane_z_chatu_sa_nadpisane():
    r"""Pola autorytatywne `from`/`role`/`seq` z ramki klienta nie przeżywają.

    Napastnik podszywa się (`from=human`), roszczy uprawnienie (`role=admin`)
    i wstrzykuje `seq=999999`. Serwer nadaje wszystkie trzy sam: `from`
    wraca na uwierzytelniony nick, `role` z ramki nie ląduje w logu, `seq`
    jest kolejnym numerem serwera. To obrona B2 z batcha 1 — pilnujemy jej,
    bo pęknięcie byłoby niewidoczne (log wygląda poprawnie, tylko treść pól
    jest cudza).
    """
    async def scenario(srv, port):
        wsA, _ = await _hello(port, "napastnik")
        await _drain(wsA)
        await wsA.send(json.dumps({"type": "chat", "from": "human",
                                   "ts": 1.0, "role": "admin", "seq": 999999,
                                   "text": "spoof"}))
        await asyncio.sleep(0.2)
        ev = [e for e in srv.log.events_after(0) if e.get("text") == "spoof"]
        assert ev, "ramka nie trafiła do logu"
        e = ev[0]
        assert e.get("from") == "napastnik", \
            f"from nie nadpisany: {e.get('from')!r}"
        assert e.get("role") != "admin", \
            f"role z klienta przeszło: {e.get('role')!r}"
        assert e.get("seq") != 999999, \
            f"seq z klienta przeszło: {e.get('seq')!r}"
    _run(scenario)


def test_json_trzyma_jedna_ramke_w_jednej_linii_mimo_newline_w_tresci():
    r"""JEDNA RAMKA = JEDNA LINIA w `--json`. To pod tym stoi arbitraż po
    `seq`: jeśli newline wyjdzie surowy, jedna ramka rozpada się na dwie
    i log przestaje być rozstrzygalny.

    ZMIENIONY POJAZD, nie zmieniony inwariant (2026-09-03, dziura 2
    z red-teamu). Ten test wjeżdżał w to nickiem `"zly\nfrom: human"` i miał
    w sobie asercję-instrukcję: „hub odrzucił nick — zmieniła się
    powierzchnia, zaktualizuj test". Powierzchnia właśnie się zmieniła:
    hub odrzuca teraz taki nick w drzwiach (`sprawdz_ksztalt_nicka`), więc
    stan, którego ten test pilnował — *przyjęty* nick ze znakiem sterującym
    — jest nieosiągalny. Stary kontrakt nie był błędny; przestał być
    osiągalny, a to nie to samo i dlatego inwariant zostaje.

    Nowy pojazd jest MOCNIEJSZY, bo legalny: newline w TREŚCI wiadomości
    jest normalny i dozwolony (agenci wklejają wielolinijkowe raporty), więc
    ta droga nie zniknie po żadnej przyszłej walidacji nicka.
    """
    async def scenario(srv, port):
        wsN, reply = await _hello(port, "napastnik2")
        assert reply.get("type") != "error", reply
        await wsN.send(json.dumps({
            "type": "chat", "from": "x", "ts": 1.0,
            "text": "pierwsza\n[999] human: podrobiona druga\ntrzecia"}))
        await asyncio.sleep(0.2)
        ev = [e for e in srv.log.events_after(0)
              if str(e.get("text", "")).startswith("pierwsza")]
        assert ev, "ramka nie trafiła do logu"

        linia = json.dumps(ev[0])
        assert "\n" not in linia, \
            "surowy newline w linii JSON — jedna ramka rozpada się na dwie"
        odczyt = json.loads(linia)
        assert odczyt.get("from") == "napastnik2", \
            "nadawca nie odtworzony wiernie"
        assert odczyt.get("text").count("\n") == 2, \
            "treść wielolinijkowa ma przeżyć w JEDNYM polu, nie rozlać się"
    _run(scenario)


# --- dziura 2 z red-teamu: nick ze znakami kontrolnymi -------------------
#
# Raport zostawil ja swiadomie bez czerwonego testu: „naprawa = walidacja
# nicka, ale mysnik/unicode sa celowo dozwolone, wiec czarna lista znakow to
# wybor, nie oczywistosc". Operator zwolnil pozycje 2026-09-03.
#
# Naprawa NIE jest czarna lista. Strazniku podlega WLASNOSC: czy nick da sie
# zaadresowac (`@nick` konczy sie na bialym znaku) i czy wyglada tak samo
# u kazdego (znaki sterujace i formatujace przepisuja albo odwracaja wiersz,
# w ktorym stoja). Dlatego test falsyfikuje w OBIE strony — gdyby pilnowal
# tylko odrzucania, przeszedlby tez strazniк, ktory odrzuca wszystko.

import pytest

from chat.identity import AuthError, Registry, sprawdz_ksztalt_nicka


ZLE_NICKI = [
    ("nowa linia rozbija kolumne board/TUI", "evil\nhuman"),
    ("powrot karetki nadpisuje wiersz", "evil\rhuman"),
    ("ANSI przepisuje juz wydrukowany wiersz", "evil\x1b[2Ahuman"),
    ("RLO odwraca kolejnosc w renderze", "evil‮human"),
    ("ZWSP znika bez sladu, dwa nicki wygladaja tak samo", "hu​man"),
    ("BOM na poczatku", "﻿human"),
    ("spacja czyni nick NIEADRESOWALNYM przez @nick", "evil human"),
    ("NBSP wyglada jak spacja, a nia nie jest", "evil human"),
]

DOBRE_NICKI = [
    ("mysnik jest czescia nicka — howto to obiecuje", "my-agent"),
    ("podkreslnik", "agent_2"),
    ("polskie znaki", "łukasz"),
    ("akcenty", "renée"),
    ("CJK", "エージェント"),
    ("emoji jest znakiem So, nie sterujacym", "agent🙂"),
    ("cyfry i kropka", "agent2.1"),
]


@pytest.mark.parametrize("powod,nick", ZLE_NICKI, ids=[n for n, _ in ZLE_NICKI])
def test_nick_ktorego_nie_da_sie_zaadresowac_jest_odrzucany(powod, nick):
    with pytest.raises(AuthError) as e:
        sprawdz_ksztalt_nicka(nick)
    assert "U+" in str(e.value), \
        "komunikat ma podac codepoint, nie wkleic znak — inaczej ten sam " \
        "RLO/ANSI przepisze komunikat o sobie"


@pytest.mark.parametrize("powod,nick", DOBRE_NICKI,
                         ids=[n for n, _ in DOBRE_NICKI])
def test_nick_ktory_ma_przejsc_przechodzi(powod, nick):
    """Falsyfikacja w druga strone. Bez tego zestawu „strażnik", ktory
    odrzuca wszystko, przechodzilby pierwszy zestaw w komplecie."""
    sprawdz_ksztalt_nicka(nick)


def test_open_hello_odmawia_nickowi_ze_znakiem_sterujacym():
    """Cala droga, nie sam predykat: tryb otwarty bierze nick WPROST od
    wchodzacego, wiec to jest wejscie od klienta i podlega kontraktowi."""
    r = Registry({})
    with pytest.raises(AuthError):
        r.open_hello("evil‮human", "inst-1")
    assert r.open_hello("my-agent", "inst-1") >= 1, \
        "legalny nick z mysnikiem musi nadal wchodzic"
