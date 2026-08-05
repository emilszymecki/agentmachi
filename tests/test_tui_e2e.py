"""E2E strony CZLOWIEKA: prawdziwy ChatServer + prawdziwy HubAdapter +
prawdziwy AgentmachiApp (Textual Pilot) + prawdziwy agent na drucie.

Po co osobny plik, skoro jest `test_tui.py`: tamten napedza aplikacje
ATRAPA adaptera (`_StubAdapter`, `_StubQuietAdapter`) i wstrzykuje ramki
wprost do `apply_hub_frame`. Drut nie jest tam sprawdzony ani razu, wiec
kazdy blad na styku serwer->websocket->HubAdapter->ekran przechodzi
przez cala suite niezauwazony.

Testujemy dokladnie to, czego AGENT nie widzi ze swojej strony i czego
zaden test protokolu nie zlapie: serwer pcha `presence` i `takeover`
WYLACZNIE do ludzi (chat/server.py `_push_presence`, `_should_push`), wiec
jedynym obserwatorem tych ramek jest TUI.

Wzorzec jak w repo: sync test + `asyncio.run` + `_free_port()`.
"""
import asyncio
import json
import socket

import pytest

pytest.importorskip("textual", reason="TUI wymaga textual — "
                    "uv run --with textual ... (patrz README)")

import websockets  # noqa: E402

import tui  # noqa: E402
from chat.client_session import Session  # noqa: E402
from chat.server import ChatServer  # noqa: E402

TOKENS = {
    "Emil": {"token": "te", "role": "human", "groups": []},
    "beta": {"token": "tb", "role": "agent", "groups": ["workers"]},
}


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("localhost", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _tokens_file(tmp_path):
    p = tmp_path / "hub.tokens.json"
    p.write_text(json.dumps(TOKENS))
    return p


def _build_app(tmp_path, port, *, session_dir=None):
    """To, co robi `build_app`, ale z portem efemerycznym: produkcyjny
    `build_app` bierze URI ze stalej modulu (env `CHAT_URL` czytany przy
    imporcie), a test nie moze zalezec od kolejnosci importow."""
    identity, roster = tui.load_human_identity(_tokens_file(tmp_path))
    session = Session(f"localhost:{port}", identity.nick,
                      base_dir=session_dir or (tmp_path / "sesje"))
    adapter = tui.HubAdapter(identity, session=session,
                             uri=f"ws://localhost:{port}")
    return tui.AgentmachiApp(adapter, roster), session


async def _until(pilot, predykat, *, timeout=5.0, opis="warunek"):
    """Czekaj na stan EKRANU, nie na sleep. Zwraca, gdy predykat prawdziwy;
    rzuca z opisem, gdy nie doczekal — cisza w TUI wyglada identycznie
    przy 'jeszcze nie doszlo' i przy 'nigdy nie dojdzie'."""
    petla = asyncio.get_running_loop()
    koniec = petla.time() + timeout
    while petla.time() < koniec:
        if predykat():
            return True
        await pilot.pause()
        await asyncio.sleep(0.05)
    raise AssertionError(f"nie doczekalem: {opis}")


async def _agent_hello(port, nick="beta", token="tb", instance="i1",
                       last_seq=0):
    ws = await websockets.connect(f"ws://localhost:{port}")
    await ws.send(json.dumps({
        "type": "hello", "from": nick, "ts": 0.0, "instance_id": instance,
        "token": token, "last_seq": last_seq, "role": "agent",
        "groups": ["workers"]}))
    reply = json.loads(await asyncio.wait_for(ws.recv(), 5))
    assert reply.get("type") in {"ok", "resync_required"}, reply
    return ws, reply


def _panel(app):
    """Co widzi czlowiek w panelu uczestnikow: RENDEROWANY tekst widgetu,
    nie `app.roster`. Roster moze byc poprawny, a panel i tak pusty —
    `_render_participants` filtruje po presence i to on jest ostatnim
    ogniwem miedzy hubem a oczami czlowieka."""
    return app.query_one("#participants", tui.Static).render().plain


# --- 1. presence: wejscie i wyjscie agenta zmieniaja obraz ----------------

def test_e2e_wejscie_i_wyjscie_agenta_zmienia_panel_czlowieka(tmp_path):
    """Agent NIE dostaje `presence` — to ramka wylacznie dla ludzi. Jesli
    sie zgubi po drodze, panel klamie, ze pokoj jest pusty (albo ze ktos
    wciaz siedzi), a zaden test protokolu tego nie zobaczy."""
    port = _free_port()
    app, _ = _build_app(tmp_path, port)

    async def scenariusz():
        server = ChatServer(data_dir=tmp_path / "hub", tokens=TOKENS,
                            port=port)
        await server.start()
        try:
            async with app.run_test() as pilot:
                await _until(pilot, lambda: app.connected,
                             opis="TUI polaczylo sie z hubem")
                # pokoj pusty: agent jeszcze nie wszedl
                assert "beta" not in _panel(app)

                ws, _ = await _agent_hello(port)
                await _until(pilot, lambda: "beta" in _panel(app),
                             opis="agent pojawil sie w panelu po wejsciu")
                assert app.roster["beta"].presence == "connected"

                await ws.close()
                await _until(pilot, lambda: "beta" not in _panel(app),
                             opis="agent zniknal z panelu po rozlaczeniu")
                assert app.roster["beta"].presence == "known"
        finally:
            await server.stop()
    asyncio.run(scenariusz())


# --- 2. rozmowa dochodzi na ekran, w kolejnosci -----------------------------

def test_e2e_rozmowa_agenta_laduje_na_ekranie_w_kolejnosci(tmp_path):
    port = _free_port()
    app, sesja = _build_app(tmp_path, port)

    async def scenariusz():
        server = ChatServer(data_dir=tmp_path / "hub", tokens=TOKENS,
                            port=port)
        await server.start()
        try:
            async with app.run_test() as pilot:
                await _until(pilot, lambda: app.connected, opis="polaczenie")
                ws, _ = await _agent_hello(port)
                for tekst in ("pierwsza", "druga", "trzecia"):
                    await ws.send(json.dumps({
                        "type": "chat", "from": "beta", "ts": 0.0,
                        "text": tekst}))
                await _until(
                    pilot,
                    lambda: [t for who, t in app.history if who == "beta"]
                    == ["pierwsza", "druga", "trzecia"],
                    opis="trzy wiadomosci na ekranie w kolejnosci nadania")
                # czlowiek slyszy chat BEZ wzmianki (agent by nie uslyszal)
                assert ("beta", "druga") in app.history
                # kursor przesuniety -> po restarcie nie zobaczy tego drugi raz
                assert sesja.last_applied_seq > 0
                await ws.close()
        finally:
            await server.stop()
    asyncio.run(scenariusz())


# --- 3. wysylka z ekranu dochodzi do agenta pod tozsamoscia czlowieka -------

def test_e2e_wyslane_z_ekranu_dochodzi_do_agenta_jako_human(tmp_path):
    """`from` nadaje SERWER. Gdyby TUI wysylalo cudza tozsamosc albo serwer
    ja przepisywal z ramki klienta, agent zobaczylby nie tego nadawce."""
    port = _free_port()
    app, _ = _build_app(tmp_path, port)
    odebrane = []

    async def scenariusz():
        server = ChatServer(data_dir=tmp_path / "hub", tokens=TOKENS,
                            port=port)
        await server.start()
        try:
            async with app.run_test() as pilot:
                await _until(pilot, lambda: app.connected, opis="polaczenie")
                ws, _ = await _agent_hello(port)

                wejscie = app.query_one("#message-input")
                wejscie.focus()
                await pilot.pause()
                wejscie.text = "@beta zrob X"
                await pilot.press("enter")

                async def zbieraj():
                    while True:
                        ramka = json.loads(await ws.recv())
                        if ramka.get("type") == "chat":
                            odebrane.append(ramka)
                            return
                await asyncio.wait_for(zbieraj(), 5)
                await ws.close()
        finally:
            await server.stop()
    asyncio.run(scenariusz())

    assert len(odebrane) == 1
    ramka = odebrane[0]
    assert ramka["from"] == "Emil"        # nadane przez serwer
    # `role` w ramce chat NIE ma i to jest zmierzone, nie zalozone: agent
    # dostaje {from, ts, type, text, seq}. Kto jest czlowiekiem, a kto
    # agentem, czyta sie z boardu, nie z pojedynczej ramki.
    assert "role" not in ramka
    assert ramka["text"] == "@beta zrob X"
    assert isinstance(ramka["seq"], int) and ramka["seq"] > 0
    # `ts` nadaje serwer (f8cf9df) — klient wysyla 0.0
    assert isinstance(ramka["ts"], float) and ramka["ts"] > 0.0


# --- 4. kick z ekranu naprawde wyrzuca agenta z kanalu ----------------------

def test_e2e_kick_z_ekranu_wyrzuca_agenta_kodem_4003(tmp_path):
    """Moderacja jest jedynym uprawnieniem, ktore hub egzekwuje. Sprawdzamy
    CALA droge: znak na klawiaturze -> ramka -> zamkniecie socketu agenta
    kodem 4003 -> znikniecie z panelu czlowieka."""
    port = _free_port()
    app, _ = _build_app(tmp_path, port)
    kod = {}

    async def scenariusz():
        server = ChatServer(data_dir=tmp_path / "hub", tokens=TOKENS,
                            port=port)
        await server.start()
        try:
            async with app.run_test() as pilot:
                await _until(pilot, lambda: app.connected, opis="polaczenie")
                ws, _ = await _agent_hello(port)
                await _until(pilot, lambda: "beta" in _panel(app),
                             opis="agent w panelu przed kickiem")

                wejscie = app.query_one("#message-input")
                wejscie.focus()
                await pilot.pause()
                wejscie.text = "/kick beta"
                await pilot.press("enter")

                async def czekaj_na_zamkniecie():
                    try:
                        while True:
                            await ws.recv()
                    except websockets.ConnectionClosed as exc:
                        kod["code"] = exc.code
                        kod["reason"] = exc.reason
                await asyncio.wait_for(czekaj_na_zamkniecie(), 5)

                await _until(pilot, lambda: "beta" not in _panel(app),
                             opis="wyrzucony zniknal z panelu czlowieka")
                # Zmienil sie JEZYK komunikatu, nie kontrakt.
                assert any("kicked" in t for _, t in app.history)
        finally:
            await server.stop()
    asyncio.run(scenariusz())

    assert kod["code"] == 4003, kod


# --- 5. restart huba pod otwartym TUI --------------------------------------

def test_e2e_restart_huba_pod_otwartym_tui_odbudowuje_panel(tmp_path):
    """Moment, w ktorym czlowiek jako jedyny widzi 'wyglada na obecnego,
    a juz nie slyszy'. Po restarcie TUI ma: wrocic samo, odzyskac roster
    z autorytatywnego snapshotu i NIE pokazac rozmowy drugi raz."""
    port = _free_port()
    dane = tmp_path / "hub"
    app, _ = _build_app(tmp_path, port)

    async def scenariusz():
        s1 = ChatServer(data_dir=dane, tokens=TOKENS, port=port)
        await s1.start()
        ws = None
        try:
            async with app.run_test() as pilot:
                await _until(pilot, lambda: app.connected, opis="polaczenie")
                ws, _ = await _agent_hello(port)
                await ws.send(json.dumps({"type": "chat", "from": "beta",
                                          "ts": 0.0, "text": "przed padem"}))
                await _until(pilot,
                             lambda: ("beta", "przed padem") in app.history,
                             opis="wiadomosc sprzed restartu na ekranie")
                przed = list(app.history)

                await ws.close()
                await s1.stop()
                await _until(pilot, lambda: not app.connected,
                             opis="TUI zauwazylo, ze hub padl")

                s2 = ChatServer(data_dir=dane, tokens=TOKENS, port=port)
                await s2.start()
                try:
                    await _until(pilot, lambda: app.connected, timeout=15,
                                 opis="TUI wrocilo samo po restarcie huba")
                    ws2, _ = await _agent_hello(port, instance="i2")
                    await _until(pilot,
                                 lambda: "beta" in _panel(app),
                                 opis="panel odbudowany po restarcie")
                    # brak duplikatu: kursor przetrwal restart
                    ile = sum(1 for w, t in app.history
                              if (w, t) == ("beta", "przed padem"))
                    assert ile == 1, f"rozmowa pokazana {ile} razy"
                    assert len(app.history) >= len(przed)
                    await ws2.close()
                finally:
                    await s2.stop()
        finally:
            if ws is not None:
                await ws.close()
    asyncio.run(scenariusz())


# --- 6. takeover: ramka, ktora hub pcha WYLACZNIE do ludzi -----------------

def test_e2e_takeover_dociera_na_ekran_czlowieka(tmp_path):
    """`takeover` ma jednego adresata na zywo — czlowieka (`_should_push`:
    `return role == "human"`). Raz juz zniknal po cichu, bo TUI nie mialo
    galezi na ten typ, i nikt tego nie zobaczyl: agent tej ramki nie
    dostaje, wiec zaden test agenta jej nie obroni. Jesli zginie znowu,
    czlowiek traci JEDYNY sygnal, ze ktos na kanale wyglada na obecnego,
    a juz nie slyszy."""
    port = _free_port()
    app, _ = _build_app(tmp_path, port)

    async def scenariusz():
        server = ChatServer(data_dir=tmp_path / "hub", tokens=TOKENS,
                            port=port)
        await server.start()
        try:
            async with app.run_test() as pilot:
                await _until(pilot, lambda: app.connected, opis="polaczenie")
                ws1, _ = await _agent_hello(port, instance="i1")
                await _until(pilot, lambda: "beta" in _panel(app),
                             opis="pierwszy klient agenta w panelu")

                # drugi klient na TYM SAMYM nicku, inny instance_id
                ws2, _ = await _agent_hello(port, instance="i2")
                await _until(
                    pilot,
                    # Zmienil sie JEZYK komunikatu, nie kontrakt.
                    lambda: any("took over" in t and "beta" in t
                                for _, t in app.history),
                    opis="czlowiek zobaczyl takeover na ekranie")
                # tresc jest SERWEROWA, nie fallbackiem TUI — gdyby TUI
                # zjadlo ramke i zalogowalo wlasny domysl, brakloby numerow
                # generacji, a to one mowia czlowiekowi, ktore polaczenie
                # wygralo
                # Zmienil sie JEZYK komunikatu, nie kontrakt.
                slad = [t for _, t in app.history if "took over" in t][-1]
                assert "generation" in slad and "1 -> 2" in slad, slad
                await ws1.close()
                await ws2.close()
        finally:
            await server.stop()
    asyncio.run(scenariusz())


# --- 7. /groups z ekranu zmienia board po stronie serwera ------------------

def test_e2e_groups_z_ekranu_dochodzi_i_wraca_na_panel(tmp_path):
    port = _free_port()
    app, _ = _build_app(tmp_path, port)

    async def scenariusz():
        server = ChatServer(data_dir=tmp_path / "hub", tokens=TOKENS,
                            port=port)
        await server.start()
        try:
            async with app.run_test() as pilot:
                await _until(pilot, lambda: app.connected, opis="polaczenie")
                ws, _ = await _agent_hello(port)
                await _until(pilot, lambda: "beta" in _panel(app),
                             opis="agent w panelu")

                wejscie = app.query_one("#message-input")
                wejscie.focus()
                await pilot.pause()
                wejscie.text = "/groups beta head,admin"
                await pilot.press("enter")

                await _until(pilot, lambda: "head" in _panel(app),
                             opis="nowe grupy widoczne w panelu czlowieka")
                assert app.roster["beta"].groups == ["head", "admin"]
                # i serwer naprawde je zna, nie tylko ekran
                # `groups_of` zwraca LISTE (kolejnosc znaczaca), nie zbior
                assert list(server.registry.groups_of("beta")) == ["head",
                                                                   "admin"]
                await ws.close()
        finally:
            await server.stop()
    asyncio.run(scenariusz())


# --- 8. rules z huba laduja w panelu -------------------------------------

def test_e2e_rules_z_huba_laduja_w_panelu(tmp_path):
    """`rules` sa opcjonalne i naleza do pokoju. Jesli nie dojda na ekran,
    czlowiek moderuje pokoj, ktorego regulaminu nie widzi."""
    port = _free_port()
    dane = tmp_path / "hub"
    dane.mkdir(parents=True, exist_ok=True)
    (dane / "rules.md").write_text("regula pokoju: nie budz bez wzmianki\n",
                                   encoding="utf-8")
    app, _ = _build_app(tmp_path, port)

    async def scenariusz():
        server = ChatServer(data_dir=dane, tokens=TOKENS, port=port)
        await server.start()
        try:
            async with app.run_test() as pilot:
                await _until(pilot, lambda: app.connected, opis="polaczenie")
                await _until(
                    pilot,
                    lambda: "nie budz bez wzmianki" in app.rules_text,
                    opis="rules pokoju na ekranie czlowieka")
                widok = app.query_one("#rules", tui.Static).render().plain
                assert "nie budz bez wzmianki" in widok
        finally:
            await server.stop()
    asyncio.run(scenariusz())
