"""Red-team, batch 2 — regresje na RDZEŃ fizyki, który trzyma pod szturmem.

Eksperyment 2, 2026-09-01. agent1 (atak) uderzył w rdzeń trzema wektorami,
agent2 (triage) odtworzył każdy niezależnie na izolowanym `ChatServer` i
potwierdził obronę. W przeciwieństwie do batcha 1 (pękało WEJŚCIE — nick,
target) tu nie pękło nic: total order `seq` przeżywa współbieżność, nagłe
ubicie klienta jest wykrywane, burza reconnectów nie korumpuje stanu.

Te testy są mocniejsze niż batch 1, bo pilnują rdzenia, nie granicy wejścia.

A4/A5 zrywają połączenie przez `transport.abort()` — to nagły RST bez
ramki WS close, najbliższy izolowany odpowiednik `kill -9` na kliencie
(którym agent1 atakował żywą kopię). Wzorzec repo: sync + asyncio.run +
_free_port.
"""
import asyncio
import json
import pathlib
import socket
import tempfile

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
    async def go():
        port = _free_port()
        tmp = pathlib.Path(tempfile.mkdtemp())
        srv = ChatServer(data_dir=tmp, tokens=TOKENS, port=port,
                         open_mode=True)
        await srv.start()
        try:
            return await asyncio.wait_for(scenario(srv, port), timeout=15)
        finally:
            await srv.stop()
    asyncio.run(go())


async def _hello(port, nick, inst):
    ws = await websockets.connect(f"ws://127.0.0.1:{port}")
    await ws.send(json.dumps({"type": "hello", "from": nick, "ts": 0.0,
                              "instance_id": inst, "last_seq": 0,
                              "role": "agent", "groups": []}))
    await asyncio.wait_for(ws.recv(), 2)
    return ws


def _conn(srv, nick):
    return len(srv.conns.get(nick, ()) or ())


def test_seq_total_order_pod_wspolbieznoscia():
    r"""40 współbieżnych ramek → seq unikalne, bez dziur, monotoniczne.

    Rdzeń: serwer nadaje `seq` i log jest całkowicie uporządkowany. Pięciu
    nadawców wypala po osiem ramek naraz przez `asyncio.gather`. Serwer musi
    zserializować wszystkie do jednego łańcucha bez kolizji numeru i bez
    zgubienia ramki. To fundament, na którym stoi arbitraż po `seq`.

    Jeden socket na nick z rozmysłem: 40 socketów na 5 nickach wywołałoby
    takeover storm (nowszy `instance_id` wypiera starszy) — inny scenariusz,
    zmierzony osobno w A5.
    """
    async def scenario(srv, port):
        socks = {n: await _hello(port, f"racer{n}", f"i{n}")
                 for n in range(5)}

        async def fire(n, k):
            await socks[n].send(json.dumps(
                {"type": "chat", "from": f"racer{n}", "ts": float(k),
                 "text": f"RACE-{n}-{k}"}))

        await asyncio.gather(*(fire(n, k)
                               for n in range(5) for k in range(8)))
        await asyncio.sleep(1.0)
        ev = [e for e in srv.log.events_after(0)
              if str(e.get("text", "")).startswith("RACE-")]
        seqs = [e["seq"] for e in ev]
        assert len(ev) == 40, f"zgubiono ramki: {len(ev)}/40"
        assert len(seqs) == len(set(seqs)), "duplikat seq pod współbieżnością"
        assert sorted(seqs) == list(range(min(seqs), min(seqs) + 40)), \
            "dziura w seq — log nie jest ciągły"
        assert seqs == sorted(seqs), "kolejność w logu ≠ rosnące seq"
    _run(scenario)


def test_nagle_zerwanie_klienta_zdejmuje_go_z_connected():
    r"""Klient ubity nagłym RST (jak kill -9) przestaje być `connected`.

    Główny typ agent1 na realne złamanie — uczestnik-duch, który jest martwy,
    ale hub trzyma go jako obecnego. NIE wychodzi: `recv()` w handlerze dostaje
    `ConnectionClosed` przy RST i `finally` zdejmuje socket z `conns`. Nick
    pozostaje ZNANY w rejestrze (trwały z założenia — „nick stays yours after
    disconnect"), ale nie połączony.
    """
    async def scenario(srv, port):
        ws = await _hello(port, "duch", "id1")
        await asyncio.sleep(0.2)
        assert _conn(srv, "duch") == 1, "hub nie zarejestrował połączenia"

        ws.transport.abort()   # RST bez WS close — odpowiednik kill -9
        for _ in range(50):
            await asyncio.sleep(0.1)
            if _conn(srv, "duch") == 0:
                break
        assert _conn(srv, "duch") == 0, \
            "duch trzyma się jako connected po nagłym zerwaniu"
        assert "duch" in srv.registry.roles, \
            "nick zniknął z rejestru — powinien być trwały"
    _run(scenario)


def test_burza_reconnectow_nie_korumpuje_stanu():
    r"""30 cykli połącz→RST na jednym nicku: hub żyje, stan nie puchnie.

    Burza reconnectów nie może ani zabić huba, ani zostawić osieroconych
    połączeń, ani rozmnożyć nicka. Po 30 cyklach: nick `sztorm` ma zero
    połączeń (ostatnie zerwane) i DOKŁADNIE jeden wpis w rejestrze, hub nadal
    serwuje i przyjmuje świeżego klienta.
    """
    async def scenario(srv, port):
        for i in range(30):
            w = await _hello(port, "sztorm", f"is{i}")
            await asyncio.sleep(0.03)
            w.transport.abort()
        await asyncio.sleep(1.0)

        assert srv._server is not None and srv._server.is_serving(), \
            "hub padł po burzy reconnectów"
        assert _conn(srv, "sztorm") == 0, \
            f"osierocone połączenia po burzy: {_conn(srv, 'sztorm')}"
        assert sum(1 for n in srv.registry.roles if n == "sztorm") == 1, \
            "nick rozmnożył się mimo trwałości"

        wk = await _hello(port, "kontrola", "ik")
        assert _conn(srv, "kontrola") == 1, \
            "hub po burzy nie przyjmuje nowych połączeń"
    _run(scenario)
