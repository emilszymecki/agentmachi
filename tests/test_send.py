import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import websockets

import send
from chat.client_session import Session

REPO = Path(__file__).resolve().parent.parent


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("localhost", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# --- jednostkowe: _print_message (kontrakt z fix-packa 842b71a) -----------

def test_print_message_malformed_frame_is_visible_and_next_frame_still_prints(
        capsys):
    send._print_message("{to nie jest json")
    send._print_message(json.dumps({"from": "beta", "text": "dalej dziala"}))

    # `[-]` zamiast dawnego `beta: ...`: ta ramka NIE MA seq i teraz to widac.
    # Ten test broni odpornosci listenera na smiec z drutu, nie ksztaltu
    # prefiksu — format zmienil sie swiadomie (patrz sekcja "format wyjscia"
    # nizej), bo `nick: tresc` nie niosl wskaznika, po ktorym da sie doczytac
    # ramke z logu.
    assert capsys.readouterr().out.splitlines() == [
        "{to nie jest json",
        "[-] beta: dalej dziala",
    ]


def test_print_message_valid_json_scalar_does_not_crash(capsys):
    send._print_message("null")
    assert capsys.readouterr().out.strip() == "null"


# --- jednostkowe: apply_frame (kursor-po-apply, dedup seq/activation) -----

@pytest.fixture
def session(tmp_path):
    return Session("localhost:9999", "beta", base_dir=tmp_path)


class _DropAdvancesSession(Session):
    """Kontrolowana awaria: pierwsze N advance nie przesuwa kursora."""

    def __init__(self, *args, drop_advances, **kwargs):
        super().__init__(*args, **kwargs)
        self.drop_advances = drop_advances
        self.advance_calls = 0

    def advance(self, seq):
        self.advance_calls += 1
        if self.advance_calls <= self.drop_advances:
            return False
        return super().advance(seq)


def test_apply_frame_advances_cursor_after_apply(session, capsys):
    assert send.apply_frame(session, {"from": "a", "text": "x", "seq": 1})
    assert session.last_applied_seq == 1
    assert "a: x" in capsys.readouterr().out


def test_apply_frame_suppresses_duplicate_seq(session, capsys):
    send.apply_frame(session, {"from": "a", "text": "x", "seq": 3})
    capsys.readouterr()
    assert send.apply_frame(session, {"from": "a", "text": "x", "seq": 3}) is False
    assert send.apply_frame(session, {"from": "a", "text": "y", "seq": 2}) is False
    assert capsys.readouterr().out == ""


def test_apply_frame_without_seq_prints_but_keeps_cursor(session, capsys):
    send.apply_frame(session, {"from": "a", "text": "bez seq"})
    assert session.last_applied_seq == 0
    assert "bez seq" in capsys.readouterr().out


def test_apply_frame_duplicate_activation_suppressed_cursor_moves(
        session, capsys):
    # (A3) activation_id to GENERYCZNY dedup wybudzen po stronie klienta, nie
    # scheduler — reprezentowany dowolna zywa ramka z activation_id (tu chat).
    offer = {"from": "server", "type": "chat", "seq": 13,
             "activation_id": "beta:13", "text": "@beta obudz sie"}
    assert send.apply_frame(session, offer) is True
    capsys.readouterr()
    retransmit = dict(offer, seq=14)  # retransmisja tej samej proby
    assert send.apply_frame(session, retransmit) is False
    assert session.last_applied_seq == 14  # suppress, ale kursor idzie
    assert capsys.readouterr().out == ""


def test_apply_frame_crash_between_apply_and_cursor_save(session, monkeypatch):
    """Crash w apply (print) NIE przesuwa kursora — ramka wroci po restarcie
    (at-least-once), nigdy nie zginie."""
    def boom(_):
        raise RuntimeError("crash w apply")
    monkeypatch.setattr(send, "_print_event", boom)
    with pytest.raises(RuntimeError):
        send.apply_frame(session, {"from": "a", "text": "x", "seq": 5})
    assert session.last_applied_seq == 0


def test_apply_frame_crash_before_mark_does_not_lose_activation(
        session, monkeypatch, capsys):
    """Review-changes codexa (1): crash w apply ramki z activation_id NIE
    zapisuje aktywacji — retry MUSI ja ponownie zastosowac, nie suppress."""
    offer = {"from": "server", "type": "chat", "seq": 13,
             "activation_id": "beta:13", "text": "@beta obudz sie"}
    def boom(_):
        raise RuntimeError("crash w apply")
    monkeypatch.setattr(send, "_print_event", boom)
    with pytest.raises(RuntimeError):
        send.apply_frame(session, offer)
    assert session.is_activation_applied("beta:13") is False
    assert session.last_applied_seq == 0
    monkeypatch.undo()
    assert send.apply_frame(session, offer) is True  # retry APLIKUJE
    assert "obudz sie" in capsys.readouterr().out
    assert session.is_activation_applied("beta:13") is True
    assert session.last_applied_seq == 13


# --- format wyjscia: powiadomienie ma byc WSKAZNIKIEM, nie trescia -------
#
# Agenci budza sie przez filtr po tresci (`grep '@nick'`). Filtr dopasowuje
# LINIE, a wiadomosci na tym kanale maja po 20+ linii — wielolinijkowosc jest
# tu regula, nie wyjatkiem. Zmierzone 2026-08-05 na zywym kanale: z
# 22-linijkowej wiadomosci agent dostal JEDEN akapit, akurat ten o wymowie
# ODWROTNEJ do calosci. Ucicie widac; odwrocenie sensu wyglada jak kompletna
# wypowiedz.
#
# Dlatego wskaznik (`seq` + nadawca) musi stac na KAZDEJ linii, nie tylko na
# pierwszej. Prefiks na pierwszej linii daje `seq` tam, gdzie nikt go nie
# szuka, i nie daje go tam, gdzie filtr trafil.
#
# Drugi powod jest ustrojowy: `CLAUDE.md` rozstrzyga kolizje zakresow po
# NIZSZYM `seq`, a agent zdalny nie ma `events.jsonl` (log ma tylko operator
# huba) ani sposobu, by `seq` wyliczyc — nadaje je wylacznie serwer. Bez
# `seq` na wyjsciu regula arbitrazu jest dla niego niewykonalna.

def test_kazda_linia_wielolinijkowej_wiadomosci_niesie_seq(capsys):
    send._print_event({"type": "chat", "seq": 42, "from": "alice",
                       "text": "pierwsza\ndruga\ntrzecia"})
    assert capsys.readouterr().out.splitlines() == [
        "[42] alice: pierwsza",
        "[42] alice: druga",
        "[42] alice: trzecia",
    ]


def test_wzmianka_w_srodku_wiadomosci_niesie_wlasny_wskaznik(capsys):
    """Sedno: filtr trafia w linie ze srodka. Ta linia — sama, wyrwana
    z kontekstu — musi wystarczyc, zeby doczytac ramke z logu."""
    send._print_event({"type": "chat", "seq": 7, "from": "bob",
                       "text": "wstep bez wzmianki\n@beta zrob to\npodsumowanie"})
    trafienia = [l for l in capsys.readouterr().out.splitlines() if "@beta" in l]
    assert trafienia == ["[7] bob: @beta zrob to"]


def test_brak_seq_jest_WIDOCZNY_a_nie_zgadywany(capsys):
    """`seq` NIEPEWNY jest gorszy niz `seq` widocznie nieobecny: brak
    sprawia, ze pytam; zly sprawia, ze przegrywam arbitraz i nie dowiaduje
    sie o tym."""
    send._print_event({"type": "chat", "from": "alice", "text": "bez seq"})
    assert capsys.readouterr().out.splitlines() == ["[-] alice: bez seq"]


def test_pusta_linia_w_srodku_nie_gubi_wskaznika(capsys):
    send._print_event({"type": "chat", "seq": 5, "from": "a",
                       "text": "akapit\n\ndrugi akapit"})
    assert capsys.readouterr().out.splitlines() == [
        "[5] a: akapit", "[5] a:", "[5] a: drugi akapit"]


def _metadane(**nadpisz):
    dane = {"type": "session_metadata", "rules": "", "role": "agent",
            "groups": [], "generation": 1,
            "participants": [{"nick": "human", "role": "human", "groups": [],
                              "connected": False, "status": None,
                              "last_seq": 0}],
            "howto": "# Channel protocol\n\n`@nick`, `$group`, `@all` wake "
                     "an agent.\ncode 4003 is a kick, takeover is a thing."}
    dane.update(nadpisz)
    return dane


def test_metadane_sesji_sa_czytelne_od_pierwszego_wiersza(capsys):
    """Tryb czytelny obiecuje `[seq] nadawca: linia`, a zaczynal sie od JEDNEJ
    linii surowego JSON-a na ~18 tys. znakow — rules + board + cale howto,
    z `\\u2014` i `\\n` zamiast tekstu. To pierwsza rzecz, jaka widzi kazdy
    wchodzacy, i jedyna, ktora dostaje ZAWSZE."""
    send._print_event(_metadane())
    linie = capsys.readouterr().out.splitlines()
    assert len(linie) > 1, "metadane nadal ida jedna linia JSON-a"
    assert not linie[0].lstrip().startswith("{"), \
        "pierwszy wiersz czytelnego trybu to nadal JSON"
    tresc = "\n".join(linie)
    assert "role=agent" in tresc and "rules: none" in tresc
    assert "# Channel protocol" in tresc, "howto ma byc tekstem, nie escapem"
    assert "\\n" not in tresc


def test_znacznik_metadanych_stoi_w_KAZDEJ_linii(capsys):
    """Nie kosmetyka — warunek dzialania filtra agenta.

    Dokumentowany filtr to `grep -v session_metadata` PRZED filtrem wzmianek,
    bo slowa lapiace wzmianki (`@all`, `takeover`, `4003`) siedza w tresci
    howto i przebijaja sie przy kazdym reconnect. Gdyby znacznik stal tylko
    w naglowku, rozbicie na linie ZEPSULOBY ten filtr: naglowek by odpadl,
    a howto przeszloby dalej."""
    send._print_event(_metadane())
    linie = capsys.readouterr().out.splitlines()
    assert all(l.startswith(send.ZNACZNIK_METADANYCH) for l in linie)
    zostaje = [l for l in linie if "session_metadata" not in l]
    assert zostaje == [], f"filtr przepuscil {len(zostaje)} linii howto"


def test_resync_state_tez_nie_leci_sciana_JSON_a(capsys):
    """Domkniecie B2: audyt wymienial DWA nierenderowane bloki w trybie
    czytelnym — `session_metadata` i `resync_state`. Pierwsza wersja naprawy
    zrobila jeden i to bylo NIEKOMPLETNE (ocenil weryfikator).

    Znacznik w kazdej linii z tego samego powodu co przy metadanych: filtr
    agenta tnie po TYPIE ramki, a w trybie czytelnym typ jest wylacznie
    w znaczniku."""
    send._print_event({"type": "resync_state",
                       "state": {"queue": {"tasks": [1]}, "runda": 3}})
    linie = capsys.readouterr().out.splitlines()
    assert all(l.startswith(send.ZNACZNIK_RESYNC) for l in linie)
    # removeprefix, nie lstrip: `str.lstrip` zdejmuje ZNAKI, nie prefiks, więc
    # zjadłby też wiodące `{`, gdyby stan zaczynał się od klucza na `[`/`r`/`e`
    # — i test przechodziłby dokładnie w przypadku, który ma łapać.
    assert not linie[0].removeprefix(
        f"{send.ZNACZNIK_RESYNC} ").startswith("{")
    tresc = "\n".join(linie)
    assert "queue:" in tresc and "runda:" in tresc
    assert [l for l in linie if "resync_state" not in l] == [], \
        "grep -v resync_state musi sciac calosc, nie tylko naglowek"


def test_metadane_nie_ukrywaja_pola_ktorego_nie_znaja(capsys):
    """Format czytelny jest stratny z zalozenia, ale nie ma prawa milczec
    o tym, ze hub przyslal cos nowego — inaczej dodane pole jest niewidoczne
    dla kazdego, kto nie czyta `--json`."""
    send._print_event(_metadane(cos_nowego={"a": 1}))
    assert "cos_nowego" in capsys.readouterr().out


def test_json_daje_jedna_parsowalna_ramke_na_linie(capsys):
    """`--json` jest ZRODLEM DO ARBITRAZU: pelna ramka, jedna na linie,
    wielolinijkowa tresc zostaje w polu `text`, a nie rozlewa sie po
    strumieniu."""
    send._print_json({"type": "chat", "seq": 42, "from": "alice",
                      "text": "pierwsza\ndruga"})
    linie = capsys.readouterr().out.splitlines()
    assert len(linie) == 1
    ramka = json.loads(linie[0])
    assert ramka["seq"] == 42
    assert ramka["text"] == "pierwsza\ndruga"


# -- `seq` musi PRZEZYC obciecie notyfikacji -----------------------------
#
# `_print_event` ma wskaznik na poczatku KAZDEJ linii i docstring tlumaczy
# dlaczego: filtr trafia w linie ze srodka, wiec `seq` musi lezec tam, gdzie
# filtr trafil. Migracja na `--json` (2026-08-13) zabrala ten warunek ze soba
# i go zgubila: w `--json` cala ramka jest JEDNA linia, a `seq` dokleja sie
# na jej KONCU, bo serwer robi `frame["seq"] = seq` PO zlozeniu ramki
# (`chat/server.py:711-712`) i `json.dumps` zachowuje kolejnosc wstawiania.
#
# Zmierzone na zywym pokoju meadow2, 2026-08-22, 8 ramek konwersacyjnych:
# `"seq"` zaczyna sie na 95.1-99.8% dlugosci linii, a ogon za nim ma 9-10
# bajtow. Harness obcial notyfikacje na 500 znakach — trzy razy, co do
# znaku. Skutek: 7 ramek z 8 obudzilo odbiorce BEZ wlasnego numeru, a
# `agentmachi read --seq <seq>` jest jedyna droga do tresci, ktora zostala
# obcieta. Mechanizm ratunkowy ginal razem z tym, przed czym ratuje.
#
# Test nie zna progu zadnego harnessu i nie ma go znac: sprawdza, ze `seq`
# lezy na POCZATKU linii, wiec przezywa obciecie o dowolnej dlugosci.

def _ramka_z_drutu(text, **extra):
    """Ramka DOKLADNIE w kolejnosci, w ktorej sklada ja serwer: najpierw
    `make_frame` ({type, from, ts, **fields} — `chat/protocol.py:293`),
    potem `frame["seq"] = seq` (`chat/server.py:712`), czyli `seq` na koncu.

    Ten helper istnieje, bo pierwsza wersja tych testow podawala `seq` przed
    `text` w literale i przechodzila na NIENAPRAWIONYM kodzie — mierzyla
    kolejnosc, ktora sama sobie ustawila. Kolejnosc wejscia jest tu calym
    przedmiotem pomiaru, wiec nie wolno jej zapisywac recznie."""
    ramka = {"type": "chat", "from": "alice", "ts": 1.5, "text": text}
    ramka.update(extra)
    ramka["seq"] = 42
    return ramka


def test_json_stawia_seq_na_poczatku_linii(capsys):
    send._print_json(_ramka_z_drutu("x" * 5000))
    linia = capsys.readouterr().out.splitlines()[0]
    assert linia.index('"seq"') < linia.index('"text"')
    # 500 znakow = obciecie zmierzone na zywym harnessie 2026-08-22
    assert '"seq": 42' in linia[:500]


def test_json_bez_seq_nie_udaje_ze_go_ma(capsys):
    """Ramka bez `seq` (diagnostyka, ramka serwerowa) ma wyjsc bez niego —
    `seq` NIEPEWNY jest gorszy niz widocznie nieobecny (por.
    `test_brak_seq_jest_WIDOCZNY_a_nie_zgadywany`)."""
    send._print_json({"type": "error", "from": "server", "text": "x" * 5000})
    ramka = json.loads(capsys.readouterr().out.splitlines()[0])
    assert "seq" not in ramka


def test_json_zachowuje_wszystkie_pola_mimo_przestawienia(capsys):
    """Przestawienie kluczy nie jest okazja do zgubienia ktoregos."""
    wejscie = _ramka_z_drutu("t", generation=3, groups=["a"])
    send._print_json(dict(wejscie))
    assert json.loads(capsys.readouterr().out.splitlines()[0]) == wejscie


def test_json_nie_escapuje_nie_ascii(capsys):
    send._print_json({"type": "chat", "seq": 1, "from": "a",
                      "text": "zażółć gęślą jaźń"})
    assert "zażółć gęślą jaźń" in capsys.readouterr().out


def test_apply_frame_emituje_wybranym_formatem(session, capsys):
    """Wybor formatu nie moze ruszyc kontraktu kursora: dedup i advance
    dzialaja tak samo, zmienia sie tylko emiter."""
    assert send.apply_frame(session, {"from": "a", "text": "x\ny", "seq": 1},
                            emit=send._print_json)
    linie = capsys.readouterr().out.splitlines()
    assert len(linie) == 1 and json.loads(linie[0])["seq"] == 1
    assert session.last_applied_seq == 1


def _fake_wire(monkeypatch, tmp_path, backlog, last_seq):
    """Drut zastapiony: hello ok z podanym backlogiem, zero ramek live."""
    monkeypatch.delenv("CHAT_TOKEN", raising=False)

    class _FakeWs:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise AssertionError("--once mial zakonczyc na backlogu")

    class _FakeConn:
        async def __aenter__(self):
            return _FakeWs()

        async def __aexit__(self, *a):
            return False

    async def _fake_hello(ws, nick, current, token, role=None, context=None):
        return {"type": "ok", "backlog": backlog, "last_seq": last_seq,
                "howto": "instrukcja obslugi kanalu"}

    monkeypatch.setattr(send.websockets, "connect", lambda *a, **k: _FakeConn())
    monkeypatch.setattr(send, "do_hello", _fake_hello)
    monkeypatch.setattr(send, "_session",
                        lambda nick: Session("localhost:9999", nick,
                                             base_dir=tmp_path))


def test_listen_domyslnie_prefiksuje_kazda_linie(tmp_path, monkeypatch, capsys):
    _fake_wire(monkeypatch, tmp_path,
               [{"type": "chat", "from": "a", "seq": 9,
                 "text": "@beta linia jeden\nlinia dwa"}], 9)
    asyncio.run(send.listen("beta", once=True))
    wyjscie = capsys.readouterr().out.splitlines()
    assert "[9] a: @beta linia jeden" in wyjscie
    assert "[9] a: linia dwa" in wyjscie


def test_listen_json_daje_wylacznie_parsowalne_linie(tmp_path, monkeypatch,
                                                     capsys):
    """KAZDA linia stdout w `--json` musi sie parsowac — takze ta
    z metadanymi sesji. Inaczej odbiorca buduje arbitraz na strumieniu,
    ktory raz na jakis czas wypluwa proze."""
    _fake_wire(monkeypatch, tmp_path,
               [{"type": "chat", "from": "a", "seq": 9,
                 "text": "@beta linia jeden\nlinia dwa"}], 9)
    asyncio.run(send.listen("beta", once=True, as_json=True))
    linie = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
    ramki = [json.loads(l) for l in linie]        # zero prozy na stdout
    chaty = [r for r in ramki if r.get("type") == "chat"]
    assert len(chaty) == 1
    assert chaty[0]["seq"] == 9
    assert chaty[0]["text"] == "@beta linia jeden\nlinia dwa"


def test_apply_hello_resync_emits_state_before_cursor(session, capsys):
    """Review-changes codexa (2): resync APLIKUJE (emituje) stan, dopiero
    potem przesuwa kursor — advance bez emisji = utrata stanu."""
    send._apply_hello_reply(session, {"type": "resync_required",
                                      "snapshot_seq": 42,
                                      "state": {"queue": {"tasks": [1]}}})
    out = capsys.readouterr().out
    assert "resync_state" in out and '"tasks": [1]' in out
    assert session.last_applied_seq == 42


def test_apply_hello_resync_without_state_fails_closed(session, capsys):
    """Finisz codexa (1): resync BEZ dict state = SessionError, kursor STOI —
    advance bez zastosowanego stanu deklarowalby posiadanie utraconego."""
    from chat.client_session import SessionError
    with pytest.raises(SessionError):
        send._apply_hello_reply(session, {"type": "resync_required",
                                          "snapshot_seq": 42})
    assert session.last_applied_seq == 0


def test_hello_ok_emits_session_metadata_before_backlog(session, capsys):
    """Finisz codexa (2): rules/role/groups/generation emitowane jako JEDNA
    ramka session_metadata PRZED backlogiem."""
    # C2: `last_seq` dopisane do ramki — nie zmiana intencji testu (broni
    # KOLEJNOSCI emisji), tylko urealnienie wejscia. Serwer w galezi `ok`
    # ZAWSZE niesie last_seq (chat/server.py, reply "ok"), wiec ramka bez
    # niego nie istnieje na drucie; od C2 klient fail-closes na jej brak,
    # bo to jedyny autorytatywny koniec logu.
    send._apply_hello_reply(session, {
        "type": "ok", "generation": 2, "role": "agent",
        "groups": ["workers"], "rules": "tekst", "rules_hash": "abc",
        "backlog": [{"from": "a", "text": "x", "seq": 1}], "last_seq": 1})
    lines = capsys.readouterr().out.splitlines()
    # DRUGA korekta ksztaltu, ta sama zasada co przy `[1]` nizej: ten test
    # broni KOLEJNOSCI emisji, i tak mowi jego wlasny komentarz. Stara
    # asercja (`'"abc"' in lines[0]`) trzymala sie jednak ksztaltu SUROWEGO
    # JSON-a — `rules_hash` lezal w linii 0 tylko dlatego, ze linia 0 byla
    # zrzutem calej ramki. To bylo wiazanie na format, ktorego test wprost
    # nie broni, wiec zastapione: metadane moga miec dowolnie wiele linii,
    # byle szly PRZED backlogiem i byle skrot dalej byl widoczny.
    metadane = [l for l in lines if l.startswith(send.ZNACZNIK_METADANYCH)]
    assert metadane, "brak ramki metadanych"
    assert lines[:len(metadane)] == metadane, \
        "backlog wyszedl przed metadanymi sesji"
    assert any("abc" in l for l in metadane), \
        "rules_hash zniknal — nie ma czym sprawdzic, czy tresc rules jest ta"
    # `[1]` przed nadawca: ten test broni KOLEJNOSCI emisji, a nie ksztaltu
    # linii — format czytelny niesie teraz `seq` na KAZDEJ linii (patrz
    # sekcja "format wyjscia" wyzej).
    assert lines[len(metadane)] == "[1] a: x"
    assert session.last_applied_seq == 1


def test_hello_ok_without_metadata_emits_nothing_extra(session, capsys):
    # C2: last_seq=0 (pusty log) — patrz komentarz w tescie wyzej.
    send._apply_hello_reply(session, {"type": "ok", "backlog": [],
                                      "last_seq": 0})
    assert capsys.readouterr().out == ""


def test_token_is_optional_in_open_mode(monkeypatch):
    """B6: brak CHAT_TOKEN NIE jest juz bledem — hub w trybie otwartym
    wpuszcza agenta bez sekretu. Wymuszanie tokenu po stronie klienta
    blokowalo dokladnie to, na co serwer pozwala (zlapane w dogfoodzie:
    agent na VPS nie mogl wejsc mimo otwartego huba)."""
    monkeypatch.delenv("CHAT_TOKEN", raising=False)
    assert send._require_token() == ""
    monkeypatch.setenv("CHAT_TOKEN", "sekret")
    assert send._require_token() == "sekret"


# --- hub_id_from_url (Task 1: CHAT_URL / zdalne hub-y) --------------------

def test_hub_id_from_url():
    import send
    assert send.hub_id_from_url("ws://localhost:8766") == "localhost:8766"
    assert send.hub_id_from_url("wss://hub.tailnet.ts.net:8766") == \
        "hub.tailnet.ts.net:8766"
    # default bez CHAT_URL == dotychczasowy HUB_ID -> kursory przezywaja
    assert send.hub_id_from_url(f"ws://localhost:{send.PORT}") == send.HUB_ID
    # porty domyslne schematu (tunel publiczny nie niesie :443 jawnie)
    assert send.hub_id_from_url("wss://hub.trycloudflare.com") == \
        "hub.trycloudflare.com:443"
    assert send.hub_id_from_url("ws://hub.local") == "hub.local:80"
    with pytest.raises(ValueError):
        send.hub_id_from_url("ws://host:abc")   # zly port = czytelny ValueError


# --- integracyjny smoke gate (wsad b2): kill / offline / restart ----------

def test_listener_smoke_gate_kill_offline_restart(tmp_path):
    """listener -> msg1 -> SIGKILL -> msg2 offline -> restart -> msg2
    dokladnie raz, bez powtorki msg1, kursor monotoniczny na dysku."""
    from chat.server import ChatServer

    port = _free_port()
    tokens = {"beta": {"token": "tok-b", "role": "agent", "groups": []},
              "alfa": {"token": "tok-a", "role": "agent", "groups": []}}
    env = {**os.environ, "CHAT_PORT": str(port), "CHAT_NICK": "beta",
           "CHAT_TOKEN": "tok-b", "CHAT_SESSION_DIR": str(tmp_path / "sess"),
           "PYTHONUNBUFFERED": "1"}

    def start_listener():
        return subprocess.Popen(
            [sys.executable, str(REPO / "send.py"), "--listen"],
            env=env, cwd=REPO, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True)

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens=tokens,
                         port=port)
        await srv.start()

        async def alfa_chat(text):
            import websockets
            async with websockets.connect(f"ws://localhost:{port}") as ws:
                await ws.send(json.dumps(
                    {"type": "hello", "from": "alfa", "instance_id": "i-a",
                     "token": "tok-a", "ts": 1.0, "last_seq": 0}))
                await ws.recv()
                await ws.send(json.dumps({"type": "chat", "from": "alfa",
                                          "ts": 2.0, "text": f"@beta {text}"}))

        listener = start_listener()
        try:
            await asyncio.sleep(1.5)  # hello + backlog
            await alfa_chat("msg1")
            await asyncio.sleep(1.0)
            listener.send_signal(signal.SIGKILL)  # twardy kill
            listener.wait(timeout=5)
            out1 = listener.stdout.read()
            assert "msg1" in out1

            await alfa_chat("msg2")  # listener offline
            await asyncio.sleep(0.5)

            listener2 = start_listener()
            try:
                await asyncio.sleep(2.0)
                listener2.terminate()
                listener2.wait(timeout=5)
                out2 = listener2.stdout.read()
            finally:
                if listener2.poll() is None:
                    listener2.kill()
            assert out2.count("msg2") == 1   # dokladnie raz
            assert "msg1" not in out2        # kursor nie cofnal sie
            state = json.loads(
                next((tmp_path / "sess").glob("beta-*.json")).read_text())
            assert state["last_applied_seq"] >= 1
        finally:
            if listener.poll() is None:
                listener.kill()
            await srv.stop()

    asyncio.run(scenario())


def test_second_listener_rejected_lock(tmp_path):
    """Dokladnie jeden listener per hub+nick: drugi proces exit code 3."""
    port = _free_port()  # hub nie musi zyc — lock lapiemy przed connect
    env = {**os.environ, "CHAT_PORT": str(port), "CHAT_NICK": "beta",
           "CHAT_TOKEN": "tok-b", "CHAT_SESSION_DIR": str(tmp_path / "sess"),
           "PYTHONUNBUFFERED": "1"}
    p1 = subprocess.Popen([sys.executable, str(REPO / "send.py"), "--listen"],
                          env=env, cwd=REPO, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL)
    try:
        time.sleep(1.0)  # p1 trzyma lock (i probuje reconnectowac do huba)
        p2 = subprocess.run(
            [sys.executable, str(REPO / "send.py"), "--listen"],
            env=env, cwd=REPO, capture_output=True, text=True, timeout=10)
        assert p2.returncode == 3
        assert "listener" in p2.stderr
    finally:
        p1.kill()


def test_corrupt_session_fail_closed_exit_code(tmp_path):
    """Uszkodzony plik sesji: exit 4 z instrukcja naprawy, zero resetu."""
    sess_dir = tmp_path / "sess"
    s = Session("localhost:7777", "beta", base_dir=sess_dir)
    s.path.write_text("{urwane")
    env = {**os.environ, "CHAT_PORT": "7777", "CHAT_NICK": "beta",
           "CHAT_TOKEN": "tok-b", "CHAT_SESSION_DIR": str(sess_dir)}
    p = subprocess.run([sys.executable, str(REPO / "send.py"), "--listen"],
                       env=env, cwd=REPO, capture_output=True, text=True,
                       timeout=10)
    assert p.returncode == 4
    # Zmienil sie JEZYK komunikatu, nie kontrakt: odmowa nadal ma niesc
    # NAPRAWE (skasowanie pliku sesji).
    assert "delete" in p.stderr


def test_oneshot_frame_uses_session_identity(tmp_path, monkeypatch):
    """Regresja bugu z testu skilla: one-shot MUSI współdzielić instance_id
    z listenerem (zero takeoveru/ping-ponga generacji gubiącego lease)."""
    from chat.server import ChatServer

    port = _free_port()
    tokens = {"beta": {"token": "tok-b", "role": "agent", "groups": []}}
    monkeypatch.setenv("CHAT_TOKEN", "tok-b")
    monkeypatch.setenv("CHAT_SESSION_DIR", str(tmp_path / "sess"))
    monkeypatch.setattr(send, "URI", f"ws://localhost:{port}")
    monkeypatch.setattr(send, "HUB_ID", f"localhost:{port}")

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens=tokens,
                         port=port)
        await srv.start()
        try:
            listener_session = send._session("beta")
            # "listener" hello ustala generacje 1 dla instance sesji
            import websockets
            async with websockets.connect(f"ws://localhost:{port}") as ws:
                await ws.send(json.dumps({
                    "type": "hello", "from": "beta", "ts": 0.0,
                    "instance_id": listener_session.instance_id,
                    "token": "tok-b", "last_seq": 0}))
                await ws.recv()
                gen_before = srv.registry.generation_of("beta")
                # one-shot status: TA SAMA tozsamosc -> zero bumpa
                reply = await send.oneshot_frame(
                    "beta", {"type": "status", "state": "idle"})
                assert reply is None  # status bez ACK
                assert srv.registry.generation_of("beta") == gen_before
        finally:
            await srv.stop()

    asyncio.run(scenario())


# --- F10 (B5): klient nie moze gubic tego, co hub obiecuje --------------
# Audyt docs znalazl bug w KODZIE: hub wysyla w hello `participants` (board,
# B4) i `howto` (instrukcja obslugi, F5), a listener wyrzucal je do kosza —
# agent uzywajacy jedynej udokumentowanej drogi wejscia nie dostawal ich
# wcale. Obietnica protokolu musi docierac do odbiorcy.

def test_session_metadata_carries_board_and_howto():
    import send
    printed = []
    original = send._print_event
    send._print_event = printed.append
    try:
        send._emit_session_metadata({
            "type": "ok", "rules": "zasady", "role": "agent",
            "groups": ["workers"], "generation": 3,
            "participants": [{"nick": "w1", "connected": True,
                              "status": {"state": "working"}}],
            "howto": "jak sie poruszac po kanale",
        })
    finally:
        send._print_event = original
    meta = printed[0]
    assert meta["type"] == "session_metadata"
    assert meta["howto"] == "jak sie poruszac po kanale"
    assert meta["participants"][0]["nick"] == "w1"
    assert meta["rules"] == "zasady" and meta["generation"] == 3


def test_resync_reply_also_carries_conversation():
    """Po kompakcji rozmowa wraca w `conversation` (F1) — listener ma ja
    pokazac, inaczej wracajacy agent widzi kanal, na ktorym 'nic sie nie
    wydarzylo'."""
    import send
    from chat.client_session import Session
    import tempfile
    printed = []
    original = send._print_event
    send._print_event = printed.append
    try:
        session = Session("h:1", "w2", base_dir=tempfile.mkdtemp())
        send._apply_hello_reply(session, {
            "type": "resync_required", "snapshot_seq": 5,
            "state": {"registry": {}},
            "conversation": [{"type": "chat", "from": "w1", "seq": 3,
                              "text": "ustalenie sprzed snapshotu"}],
        })
    finally:
        send._print_event = original
    teksty = [e.get("text") for e in printed if e.get("type") == "chat"]
    assert "ustalenie sprzed snapshotu" in teksty


# --- wejscie bez nicka: cala droga klienta (dogfood worker4) --------------
# Serwer od B6 przyjmuje hello bez 'from' i nadaje nick, ale KLIENT padal
# lokalnie na _session('') -> SessionError('invalid nick: '') ZANIM hello
# wyszlo w drut. Bug siedzial w POPRZEK warstw: strona serwera dzialala,
# kliencka byla martwa, i zaden unit tego nie lapal, bo zaden nie odpalal
# calej drogi wejscia. Agent na VPS (git clone HEAD) padal tak przy kazdym
# nickless wejsciu.

def test_boot_identity_is_ephemeral_not_a_session():
    """_BootIdentity zyje TYLKO na pierwsze hello: duck-typuje to, czego
    do_hello potrzebuje (instance_id + last_applied_seq=0), ale NIE jest
    Session — nie ma listener-locka ani kursora. Dlatego po nadaniu nicka
    listen przechodzi na prawdziwa Session, a gdy hub nicka nie nada,
    fail-closes zamiast udawac sesje."""
    boot = send._BootIdentity()
    assert isinstance(boot.instance_id, str) and boot.instance_id
    assert boot.last_applied_seq == 0
    assert not hasattr(boot, "acquire_listener_lock")
    assert not hasattr(boot, "release_listener_lock")


def test_nickless_listen_enters_open_hub_and_gets_assigned_nick(
        tmp_path, monkeypatch, capsys):
    """REGRES glowny: 'agentmachi listen' BEZ nicka na otwartym hubie MUSI
    wejsc — hub nadaje nick, klient go przyjmuje i zaklada pod nim sesje.
    Dowod calej drogi: powstaje plik sesji nazwany NADANYM nickiem (z pustym
    nickiem Session by rzucila i pliku by nie bylo) + stderr niesie nadanie."""
    from chat.server import ChatServer
    port = _free_port()
    monkeypatch.delenv("CHAT_TOKEN", raising=False)   # open mode: bez sekretu
    monkeypatch.delenv("CHAT_NICK", raising=False)
    monkeypatch.setenv("CHAT_SESSION_DIR", str(tmp_path / "sess"))
    monkeypatch.setattr(send, "URI", f"ws://localhost:{port}")
    monkeypatch.setattr(send, "HUB_ID", f"localhost:{port}")

    async def scenario():
        # bind domyslny 127.0.0.1 => open_mode: agent wchodzi bez tokenu/nicka
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            task = asyncio.create_task(send.listen(""))
            await asyncio.sleep(1.5)   # hello + nadanie nicka + zapis sesji
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        finally:
            await srv.stop()

    asyncio.run(scenario())

    sess_files = list((tmp_path / "sess").glob("*.json"))
    assert sess_files, "brak pliku sesji => klient nie przyjal nadanego nicka"
    # pusty nick dalby slug fallback 'nick-*'; nadany to 'worker*'
    assert not any(f.name.startswith("nick-") for f in sess_files), \
        [f.name for f in sess_files]
    err = capsys.readouterr().err
    assert "invalid nick" not in err, err
    # Zmienil sie JEZYK komunikatu, nie kontrakt: klient nadal ma wypisac
    # nadany nick na stderr, zeby agent mogl go odczytac i podawac dalej.
    assert "[hub] assigned nick:" in err, err


def test_nickless_listen_failcloses_when_hub_assigns_no_nick(monkeypatch):
    """Review worker2: gdy hub przyjmuje nickless hello, ale nie odsyla
    nadanego nicka (version-skew), listen NIE moze paln AttributeError —
    _BootIdentity nie jest sesja. Kontrakt: czysty fail-closed (exit 1),
    a finally nie siega po None.release_listener_lock()."""
    monkeypatch.delenv("CHAT_TOKEN", raising=False)

    class _FakeConn:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *a):
            return False

    # C2: atrapa duck-typuje do_hello, wiec przyjmuje takze `context`
    # (dopisany przy wejsciu fresh). Kontrakt testu bez zmian.
    async def _fake_hello(ws, nick, session, token, role=None, context=None):
        return {"type": "ok"}   # przyjete, ale BEZ pola 'nick'

    monkeypatch.setattr(send.websockets, "connect", lambda *a, **k: _FakeConn())
    monkeypatch.setattr(send, "do_hello", _fake_hello)

    with pytest.raises(SystemExit) as ei:
        asyncio.run(send.listen(""))
    assert ei.value.code == 1


# -- C2: kursor konczy na AUTORYTATYWNYM koncu logu ------------------------

def test_hello_ok_z_pustym_backlogiem_przesuwa_kursor_na_wire_last_seq(session):
    """Autorytatywny koniec logu jest w `last_seq`, NIE w ostatniej ramce
    backlogu — serwer swiadomie filtruje z drutu cudze hello (54% backlogu
    w pomiarze B5). Klient, ktory ufa wylacznie ramkom, zostaje z kursorem
    sprzed filtra i prosi w kolko o to, czego nigdy nie dostanie. Przy
    wejsciu `context=fresh` backlog jest pusty ZAWSZE, wiec bez tego
    kontraktu niezaleznosc trwalaby do pierwszego reconnectu."""
    send._apply_hello_reply(session, {
        "type": "ok", "backlog": [], "last_seq": 42})
    assert session.last_applied_seq == 42


def test_hello_ok_last_seq_zero_nie_wywraca_wejscia(session):
    """PUSTY log: Session.advance rzuca SessionError dla seq < 1
    (chat/client_session.py:221), wiec bezwarunkowe advance wysypywaloby
    wejscie na swiezym kanale. Zero jest legalne — po prostu nie ma czego
    przesuwac."""
    send._apply_hello_reply(session, {
        "type": "ok", "backlog": [], "last_seq": 0})
    assert session.last_applied_seq == 0


def test_hello_ok_bez_poprawnego_last_seq_failcloses(session):
    """Fail-closed jak przy resync_required: brak wiarygodnego konca logu
    znaczy 'nie wiem, gdzie jestem'. Ciche pominiecie przesuniecia to
    pozniejsza powodz duplikatow albo luka, ktorej nikt nie powiaze
    z tym wejsciem."""
    from chat.client_session import SessionError
    with pytest.raises(SessionError):
        send._apply_hello_reply(session, {"type": "ok", "backlog": []})
    with pytest.raises(SessionError):
        send._apply_hello_reply(session, {
            "type": "ok", "backlog": [], "last_seq": True})
    with pytest.raises(SessionError):
        send._apply_hello_reply(session, {
            "type": "ok", "backlog": [], "last_seq": -1})


def test_fresh_leci_tylko_w_pierwszym_hello(tmp_path, monkeypatch):
    """Regresja C2: --fresh to jednorazowa decyzja przy STARCIE procesu,
    nie tryb polaczenia. Gdyby leciala przy kazdym obiegu petli reconnectu,
    kursor przeskakiwalby na koniec logu po kazdym zerwaniu, a wiadomosci
    z okna rozlaczenia gineliby dla tego agenta bezpowrotnie.

    Flage gasimy DOPIERO po zastosowaniu poprawnej odpowiedzi — gdy socket
    padnie wczesniej, kolejna proba nadal ma byc fresh (inaczej niezaleznosc
    gubi sie przez zwykly retry transportu)."""
    monkeypatch.delenv("CHAT_TOKEN", raising=False)
    widziane = []

    class _FakeWs:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration      # natychmiastowy koniec -> reconnect

    class _FakeConn:
        async def __aenter__(self):
            return _FakeWs()

        async def __aexit__(self, *a):
            return False

    async def _fake_hello(ws, nick, session, token, role=None, context=None):
        widziane.append(context)
        if len(widziane) >= 2:
            sys.exit(7)                   # przerywa petle reconnectu
        return {"type": "ok", "backlog": [], "last_seq": 0}

    monkeypatch.setattr(send.websockets, "connect", lambda *a, **k: _FakeConn())
    monkeypatch.setattr(send, "do_hello", _fake_hello)
    monkeypatch.setattr(send, "_session",
                        lambda nick: Session("localhost:9999", nick,
                                             base_dir=tmp_path))

    with pytest.raises(SystemExit):
        asyncio.run(send.listen("beta", context="fresh"))
    assert widziane == ["fresh", None]


def test_listen_once_returns_after_durable_live_frame(tmp_path, monkeypatch):
    """`--once` konczy proces PO Session.advance, nie po samym stdout.

    To jest zamek na wyścig wait-once: arbitralny sleep po wypisie mogl
    zabic listener przed fsync kursora i dostarczyc te sama ramke ponownie.
    """
    monkeypatch.delenv("CHAT_TOKEN", raising=False)
    session = _DropAdvancesSession(
        "localhost:9999", "beta", base_dir=tmp_path, drop_advances=1)

    class _FakeWs:
        def __init__(self):
            self._index = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            self._index += 1
            if self._index > 2:
                raise AssertionError(
                    "listen --once nie zakonczyl po trwalym kursorze")
            return json.dumps({
                "from": "a", "text": f"@beta {self._index}",
                "seq": self._index,
            })

    class _FakeConn:
        async def __aenter__(self):
            return _FakeWs()

        async def __aexit__(self, *a):
            return False

    async def _fake_hello(ws, nick, current, token, role=None, context=None):
        return {"type": "ok", "backlog": [], "last_seq": 0}

    monkeypatch.setattr(send.websockets, "connect", lambda *a, **k: _FakeConn())
    monkeypatch.setattr(send, "do_hello", _fake_hello)
    monkeypatch.setattr(send, "_session", lambda nick: session)

    asyncio.run(send.listen("beta", once=True))

    # Pierwsza ramka zostala wypisana, ale kontrolowany advance nic nie
    # zapisal. `durable` MUSI utrzymac listener do drugiej ramki.
    assert session.advance_calls == 2
    assert session.last_applied_seq == 2


def test_listen_once_returns_after_durable_backlog(tmp_path, monkeypatch):
    """Nieprzeczytana wzmianka z backlogu budzi bez czekania na kolejny live."""
    monkeypatch.delenv("CHAT_TOKEN", raising=False)
    # Backlog wywoluje advance dwa razy: w apply_frame i potem na
    # autorytatywnym wire_last_seq. Oba kontrolowanie nie przesuwaja kursora.
    session = _DropAdvancesSession(
        "localhost:9999", "beta", base_dir=tmp_path, drop_advances=2)

    class _FakeWs:
        def __init__(self):
            self._sent = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._sent:
                raise AssertionError(
                    "listen --once nie zakonczyl po trwalym kursorze")
            self._sent = True
            return json.dumps({
                "from": "a", "text": "@beta live", "seq": 3,
            })

    class _FakeConn:
        async def __aenter__(self):
            return _FakeWs()

        async def __aexit__(self, *a):
            return False

    async def _fake_hello(ws, nick, current, token, role=None, context=None):
        return {
            "type": "ok",
            "backlog": [{"from": "a", "text": "@beta zalegle", "seq": 2}],
            "last_seq": 2,
        }

    monkeypatch.setattr(send.websockets, "connect", lambda *a, **k: _FakeConn())
    monkeypatch.setattr(send, "do_hello", _fake_hello)
    monkeypatch.setattr(send, "_session", lambda nick: session)

    asyncio.run(send.listen("beta", once=True))

    # Sam wypis backlogu nie wystarcza: bez trwalego kursora listener
    # czeka na live, ktory zapisuje seq=3 i dopiero wtedy konczy.
    assert session.advance_calls == 3
    assert session.last_applied_seq == 3


def test_listen_podnosi_sie_na_proponowanym_nicku(tmp_path, monkeypatch):
    """C4: gdy nick zajmuje KTOS INNY, listener nie umiera — bierze nick,
    ktory hub podal w `suggested_nick`, i wchodzi. Zmierzone na kanale rube:
    Codex stracil nick 'codex', dostal propozycje 'worker3' w tresci bledu
    i utknal na kilkanascie minut, bo nie mial jej z czego odczytac ani
    instrukcji, ze ma jej uzyc. Agent bez nicka jest gluchy i niemy —
    podniesienie sie pod innym nickiem jest zawsze lepsze niz smierc."""
    monkeypatch.delenv("CHAT_TOKEN", raising=False)
    nicki = []

    class _FakeWs:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _FakeConn:
        async def __aenter__(self):
            return _FakeWs()

        async def __aexit__(self, *a):
            return False

    async def _fake_hello(ws, nick, session, token, role=None, context=None):
        nicki.append(nick)
        if len(nicki) == 1:                      # pierwsze wejscie: zajete
            return {"type": "error", "suggested_nick": "worker3",
                    "text": "nick codex jest zajety przez polaczonego uczestnika"}
        sys.exit(7)                              # drugie: konczymy test

    monkeypatch.setattr(send.websockets, "connect", lambda *a, **k: _FakeConn())
    monkeypatch.setattr(send, "do_hello", _fake_hello)
    monkeypatch.setattr(send, "_session",
                        lambda nick: Session("localhost:9999", nick,
                                             base_dir=tmp_path))

    with pytest.raises(SystemExit):
        asyncio.run(send.listen("codex"))
    assert nicki == ["codex", "worker3"], f"nie podnioslo sie: {nicki}"


def _atrapa_polaczenia(wyslane):
    """Fake socket zbierajacy to, co klient PROBOWAL wyslac."""
    class _FakeWs:
        async def send(self, data):
            wyslane.append(data)

        async def recv(self):
            raise AssertionError("nie powinnismy dojsc do odbioru")

    class _FakeConn:
        async def __aenter__(self):
            return _FakeWs()

        async def __aexit__(self, *a):
            return False

    return lambda *a, **k: _FakeConn()


ODMOWA = {"type": "error", "suggested_nick": "worker3",
          "text": "nick codex jest zajety przez polaczonego uczestnika"}


@pytest.mark.parametrize("wolaj", [
    lambda: send.send_once("codex", "tresc, ktora NIE MOZE zniknac"),
    lambda: send.oneshot_frame("codex", {"type": "status", "state": "idle"}),
])
def test_wysylka_po_odmowie_hello_pada_glosno_i_nie_wysyla_ramki(
        wolaj, tmp_path, monkeypatch, capsys):
    """CICHY FALSE-SUCCESS — najgorsza klasa bledu, jaka ten produkt ma.

    Zmierzone na zywym kanale przez drugiego agenta (Codex), nie znalezione
    z czytania kodu: dwa `agentmachi send --as codex` skonczyly sie kodem 0,
    a zadnej z tych ramek nie ma w logu huba.

    Mechanizm: `do_hello` celowo NIE umiera przy odmowie z `suggested_nick`,
    bo dla NASLUCHU to nie jest blad koncowy (listen podnosi sie pod nowym
    nickiem — 7ea4130). Wolajacy po stronie WYSYLKI tej zwrotki nie
    sprawdzali i leciali dalej: ramka szla na socket, ktory hub wlasnie
    zamykal, a proces konczyl sie zerem. Czyli fix nasluchu z tego samego
    dnia otworzyl dziure w wysylce.

    W `oneshot_frame` bylo to jeszcze lepiej zamaskowane: brak ACK jest tam
    LEGALNY (status go nie dostaje), wiec funkcja zwracala None — dokladnie
    tak samo jak przy sukcesie.

    POPRZEDNIA WERSJA TEGO TESTU BYLA ATRAPA: konczyla sie asercja na
    wlasnym literale (`assert reply.get("suggested_nick") == "worker3"`)
    i nie wolala `send_once` ani razu. Przechodzila zawsze — takze wtedy,
    gdy produkt cicho gubil wiadomosci. Test, ktory nie dotyka SUT, jest
    gorszy niz brak testu, bo kupuje falszywy spokoj."""
    monkeypatch.delenv("CHAT_TOKEN", raising=False)
    wyslane = []
    monkeypatch.setattr(send.websockets, "connect",
                        _atrapa_polaczenia(wyslane))
    monkeypatch.setattr(send, "_session",
                        lambda nick: Session("localhost:9999", nick,
                                             base_dir=tmp_path))

    async def _fake_hello(ws, nick, session, token, role=None, context=None):
        return ODMOWA

    monkeypatch.setattr(send, "do_hello", _fake_hello)

    with pytest.raises(SystemExit) as wyjscie:
        asyncio.run(wolaj())
    assert wyjscie.value.code != 0, \
        "wysylka, ktora nie dotarla, nie moze konczyc sie sukcesem"
    assert wyslane == [], \
        f"ramka poszla na socket zamykany przez huba: {wyslane}"

    err = capsys.readouterr().err
    # Zmienil sie JEZYK komunikatu, nie kontrakt.
    assert "was NOT sent" in err, "czlowiek musi wiedziec, ze nie poszlo"
    assert "worker3" in err, "podaj wolny nick — agent ma czym wejsc"


def test_odmowa_wysylki_nie_podstawia_nadawcy(tmp_path, capsys):
    """Granica: hub PODAJE wolny nick, a mimo to nie wolno go uzyc za
    plecami czlowieka. Przy nasluchu podmiana nazwy jest ratunkiem, przy
    wysylce byloby podpisaniem sie cudza tozsamoscia — ta sama klasa bledu,
    ktora kosztowala ramke 4244 znakow podpisana cudzym nickiem."""
    sesja = Session("localhost:9999", "codex", base_dir=tmp_path)
    with pytest.raises(SystemExit):
        send._wysylka_albo_padnij(ODMOWA, "codex", sesja)
    err = capsys.readouterr().err
    assert "--as worker3" in err, "propozycja ma byc JAWNA komenda czlowieka"


def test_odmowa_wysylki_przepuszcza_poprawne_hello(tmp_path):
    """Bezpiecznik nie moze blokowac zdrowej sciezki."""
    sesja = Session("localhost:9999", "codex", base_dir=tmp_path)
    send._wysylka_albo_padnij({"type": "ok", "last_seq": 3}, "codex", sesja)


def test_nickless_listen_nie_zamyka_sobie_ust(tmp_path, monkeypatch):
    """Po nadaniu nicka agent MUSI umiec sie odezwac. Sesja zakladana pod
    nadanym nickiem brala swiezy losowy instance_id, a serwer znal ten
    z hello — a serwer odmawia, gdy zywy nick nalezy do INNEGO instance_id.
    Skutek: hub nazywa agenta, po czym odbija kazde jego `send --as <nick>`
    komunikatem "nick zajety przez polaczonego <nick>". Wejscie bez nicka
    bylo wiec wejsciem na nieme konto (zlapane 2026-07-31, review Codexa).

    Dowod idzie przez DRUT, nie przez pole w obiekcie: druga ramka leci
    tozsamoscia z pliku sesji i musi trafic do logu huba."""
    from chat.server import ChatServer
    port = _free_port()
    monkeypatch.delenv("CHAT_TOKEN", raising=False)
    monkeypatch.delenv("CHAT_NICK", raising=False)
    monkeypatch.setenv("CHAT_SESSION_DIR", str(tmp_path / "sess"))
    monkeypatch.setattr(send, "URI", f"ws://localhost:{port}")
    monkeypatch.setattr(send, "HUB_ID", f"localhost:{port}")
    wynik = {}

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            task = asyncio.create_task(send.listen(""))
            await asyncio.sleep(1.5)
            nadany = next(iter(srv.conns))          # nick nadany przez huba
            wynik["nadany"] = nadany
            # to samo, co robi `agentmachi send --as <nick>`: osobne polaczenie,
            # tozsamosc czytana z pliku sesji
            sesja = Session(send.HUB_ID, nadany)
            wynik["instancja_sesji"] = sesja.instance_id
            wynik["instancja_huba"] = srv.registry.instance_of(nadany)
            async with websockets.connect(send.URI) as ws:
                odp = await send.do_hello(ws, nadany, sesja, None)
                wynik["hello"] = odp
                if odp.get("type") == "ok":
                    await ws.send(json.dumps({
                        "type": "chat", "from": nadany, "ts": 0.0,
                        "text": "@all jestem"}))
                    await asyncio.sleep(0.3)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            wynik["log"] = [e.get("text") for e in srv.log.replay()]
        finally:
            await srv.stop()

    asyncio.run(scenario())

    assert wynik["instancja_sesji"] == wynik["instancja_huba"], (
        "plik sesji ma inna tozsamosc niz ta, ktora poszla w hello — "
        f"{wynik['instancja_sesji']} != {wynik['instancja_huba']}")
    assert wynik["hello"].get("type") == "ok", wynik["hello"]
    assert "@all jestem" in wynik["log"], \
        "agent nazwany przez huba nie potrafi sie odezwac pod wlasnym nickiem"


def test_nickless_listen_nie_dziedziczy_kursora_po_poprzednim_agencie(
        tmp_path, monkeypatch):
    """Nadany nick wraca do puli, wiec pod ta sama nazwa moze lezec CUDZY
    kursor. Hello poszlo z last_seq=0 sesji tymczasowej, wiec backlog
    przyszedl od poczatku — a apply_frame tnie po `seq <= last_applied_seq`
    i zjadlby wlasnie dostarczona historie."""
    from chat.server import ChatServer
    port = _free_port()
    monkeypatch.delenv("CHAT_TOKEN", raising=False)
    monkeypatch.delenv("CHAT_NICK", raising=False)
    monkeypatch.setenv("CHAT_SESSION_DIR", str(tmp_path / "sess"))
    monkeypatch.setattr(send, "URI", f"ws://localhost:{port}")
    monkeypatch.setattr(send, "HUB_ID", f"localhost:{port}")
    # kursor po POPRZEDNIM agencie na nicku, ktory hub nada jako pierwszy
    Session(f"localhost:{port}", "agent1").advance(999)

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            task = asyncio.create_task(send.listen(""))
            await asyncio.sleep(1.5)
            nadany = next(iter(srv.conns))
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            return nadany
        finally:
            await srv.stop()

    nadany = asyncio.run(scenario())
    assert nadany == "agent1", f"hub nadal inny nick niz oczekiwany: {nadany}"
    assert Session(f"localhost:{port}", "agent1").last_applied_seq < 999, \
        "agent odziedziczyl kursor poprzednika i przeskoczy historie"


def test_nickless_listen_nie_niszczy_sesji_cudzego_listenera(tmp_path, monkeypatch):
    """Hub uznaje nick za wolny na podstawie SWOICH `conns` — a lokalny
    listener moze go trzymac, bedac chwilowo rozlaczonym. Drugi nasluch bez
    nicka dostaje wtedy ten sam nick i odbija sie o ListenerLockHeld. Gdyby
    adopcja tozsamosci szla PRZED zamkiem, odrzucony proces zdazylby nadpisac
    cudzy plik sesji: obca tozsamosc + wyzerowany kursor. Ofiara traci
    trwaly kursor, ktory kontrakt klienta obiecuje utrzymac
    (zlapane 2026-07-31, drugie review Codexa)."""
    from chat.server import ChatServer
    port = _free_port()
    monkeypatch.delenv("CHAT_TOKEN", raising=False)
    monkeypatch.delenv("CHAT_NICK", raising=False)
    monkeypatch.setenv("CHAT_SESSION_DIR", str(tmp_path / "sess"))
    monkeypatch.setattr(send, "URI", f"ws://localhost:{port}")
    monkeypatch.setattr(send, "HUB_ID", f"localhost:{port}")

    # zywy, ale ROZLACZONY listener trzymajacy nick, ktory hub nada jako pierwszy
    ofiara = Session(f"localhost:{port}", "agent1")
    ofiara.advance(57)
    ofiara.acquire_listener_lock()
    tozsamosc_przed, kursor_przed = ofiara.instance_id, ofiara.last_applied_seq

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            with pytest.raises(send.ListenerLockHeld):
                await send.listen("")
        finally:
            await srv.stop()

    try:
        asyncio.run(scenario())
        po = Session(f"localhost:{port}", "agent1")
        assert po.instance_id == tozsamosc_przed, \
            "odrzucony nasluch nadpisal tozsamosc cudzej sesji"
        assert po.last_applied_seq == kursor_przed, \
            "odrzucony nasluch wyzerowal cudzy kursor"
    finally:
        ofiara.release_listener_lock()


def test_send_odmawia_zamiast_gubic_po_cichu(tmp_path, monkeypatch):
    """`chat` NIE MA ACK. Hub odrzuca ramke ponad sufit kodem 1009, a menedzer
    kontekstu websockets polyka to zamkniecie — bez kontroli u klienta
    `agentmachi send` konczy sie ZEREM, a wiadomosci nie ma ani w logu, ani
    u nikogo. Agent idzie dalej przekonany, ze powiedzial.

    Cicha utrata jest gorsza niz odmowa, wiec klient ma powiedziec NIE sam
    (zlapane 2026-07-31, piate review Codexa)."""
    from chat.server import ChatServer
    from chat import protocol
    port = _free_port()
    monkeypatch.delenv("CHAT_TOKEN", raising=False)
    monkeypatch.setenv("CHAT_SESSION_DIR", str(tmp_path / "sess"))
    monkeypatch.setattr(send, "URI", f"ws://localhost:{port}")
    monkeypatch.setattr(send, "HUB_ID", f"localhost:{port}")
    za_duzy = "X" * (protocol.MAX_FRAME_BYTES + 1000)

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            with pytest.raises(send.SessionError) as e:
                await send.send_once("agent1", za_duzy)
            # Zmienil sie JEZYK komunikatu, nie kontrakt.
            assert "hub limit" in str(e.value)
            return [f.get("type") for f in srv.log.replay()]
        finally:
            await srv.stop()

    typy = asyncio.run(scenario())
    assert "chat" not in typy, "przerosnieta ramka mimo wszystko weszla do logu"


def test_sufit_klienta_pokrywa_najgorsza_legalna_odpowiedz():
    """Sufit odbioru ma byc POCHODNA arytmetyki, nie liczba z powietrza:
    najgorsza legalna odpowiedz to okno rozmowy razy sufit jednej ramki.
    Gdyby ktos podniosl CONVERSATION_LIMIT albo MAX_FRAME_BYTES i zapomnial
    o kliencie, wracajacy agent znow wypadalby na wlasnym backlogu."""
    from chat import protocol, store
    assert send.MAX_HUB_FRAME >= store.CONVERSATION_LIMIT * protocol.MAX_FRAME_BYTES


def test_dumps_nie_rozpycha_znakow_spoza_ascii():
    """Sufity licza bajty UTF-8, a domyslny json.dumps rozpisuje kazdy znak
    spoza ASCII na \\uXXXX — emoji puchnie z 4 bajtow do 12. Ramka, ktora
    przeszla sufit WEJSCIA, wracala w odpowiedzi trzy razy wieksza i sufit
    wyjscia gonilby wejscie w nieskonczonosc."""
    import json
    from chat import protocol
    ramka = {"type": "chat", "from": "a", "ts": 0.0, "text": "😀" * 1000}
    assert protocol.frame_bytes(ramka) < len(json.dumps(ramka).encode()) / 2.5
    assert json.loads(protocol.dumps(ramka)) == ramka


def test_send_odmawia_surogatu_zamiast_gubic_po_cichu(tmp_path, monkeypatch):
    """Ta sama cicha utrata co przy przekroczonym sufitcie, tylko innym
    wejsciem. `protocol.dumps` dla ramki z osamotnionym surogatem wraca do
    escapowania i NIE rzuca, wiec sam pomiar rozmiaru jej nie wykrywa. Hub
    odbija ja na wejsciu, ale `chat` nie ma ACK — komenda konczy sie zerem,
    a wiadomosci nie ma nigdzie.

    Zrodlem bywa argv zdekodowane przez `surrogateescape` (nazwa pliku spoza
    UTF-8), wiec agent nie musi tego robic celowo (dziewiate review)."""
    from chat.server import ChatServer
    port = _free_port()
    monkeypatch.delenv("CHAT_TOKEN", raising=False)
    monkeypatch.setenv("CHAT_SESSION_DIR", str(tmp_path / "sess"))
    monkeypatch.setattr(send, "URI", f"ws://localhost:{port}")
    monkeypatch.setattr(send, "HUB_ID", f"localhost:{port}")

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            with pytest.raises(send.SessionError) as e:
                await send.send_once("agent1", "\ud800 nazwa pliku spoza utf-8")
            # Zmienil sie JEZYK komunikatu, nie kontrakt.
            assert "surrogate" in str(e.value)
            return [f.get("type") for f in srv.log.replay()]
        finally:
            await srv.stop()

    assert "chat" not in asyncio.run(scenario())


def test_send_pokazuje_ostrzezenie_serwera_bez_nasluchu(tmp_path, monkeypatch, capsys):
    """Ostrzezenia (nieznany nick, nieznana grupa) leca WYLACZNIE na zywo
    i NIE sa utrwalane — zmierzone przez agent1: w events.jsonl nie ma ani
    jednej ramki `error`. Kto wysyla jednorazowo, bez podniesionego nasluchu,
    nie mial ich SKAD przeczytac: hub mowil do sciany.

    Nie utrwalamy `error` w logu (taka byla pierwsza propozycja), bo ramka
    jest adresowana do JEDNEGO nadawcy, a log czyta kazdy przy wznowieniu.
    Pytamy o nia tam, gdzie powstala."""
    from chat.server import ChatServer
    port = _free_port()
    monkeypatch.delenv("CHAT_TOKEN", raising=False)
    monkeypatch.setenv("CHAT_SESSION_DIR", str(tmp_path / "sess"))
    monkeypatch.setattr(send, "URI", f"ws://localhost:{port}")
    monkeypatch.setattr(send, "HUB_ID", f"localhost:{port}")

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            await send.send_once("agent1", "@nikt-takiego halo")
            return [f.get("type") for f in srv.log.replay()]
        finally:
            await srv.stop()

    typy = asyncio.run(scenario())
    err = capsys.readouterr().err
    # Zmienil sie JEZYK komunikatu, nie kontrakt.
    assert "hub:" in err and "unknown nick" in err, err
    # ramka MIMO TO doszla — to ostrzezenie, nie odmowa
    assert "chat" in typy


def test_ostrzezenie_o_grupie_dociera_do_nadawcy_W_CALOSCI(tmp_path, monkeypatch,
                                                           capsys):
    """Druga polowa tej samej drogi co
    `test_ostrzezenia_mowia_co_sie_stalo_z_ramka...` w testach serwera.

    Serwer moze mowic prawde do sciany. Ostrzezenie o `$nieznanej grupie`
    urosło z czterech slow do zdania, ktore dopiero od `— no participant`
    W DOL prostuje mylne "wiadomosc przepada" — wiec pytanie nie brzmi
    "czy hub to wyslal", tylko "czy nadawca to widzi". Klient wypisuje
    `ramka['text']` w calosci (`send.py`), lecz zaden test tego nie
    trzymal: skrocenie do pierwszej linii przeszloby na zielono i skasowalo
    dokladnie te czesc, dla ktorej ta poprawka powstala.

    Trzy niezalezne fakty naraz, bo tylko razem znacza "ostrzezenie, nie
    odmowa": tresc dociera cala, ramka `chat` jest w logu, a ramki `error`
    w logu NIE MA (decyzja z `test_send_pokazuje_ostrzezenie_serwera...`)."""
    from chat.server import ChatServer
    port = _free_port()
    monkeypatch.delenv("CHAT_TOKEN", raising=False)
    monkeypatch.setenv("CHAT_SESSION_DIR", str(tmp_path / "sess"))
    monkeypatch.setattr(send, "URI", f"ws://localhost:{port}")
    monkeypatch.setattr(send, "HUB_ID", f"localhost:{port}")

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            await send.send_once("agent1", "$upiory zbiorka")
            return [f.get("type") for f in srv.log.replay()]
        finally:
            await srv.stop()

    typy = asyncio.run(scenario())
    err = capsys.readouterr().err
    assert "hub:" in err and "upiory" in err, err
    # Zmienil sie JEZYK komunikatu, nie kontrakt: nadawca ma sie dowiedziec,
    # co stalo sie z RAMKA, a nie tylko co jest nie tak ze wzmianka.
    assert "log" in err.lower(), f"ogon komunikatu nie dotarl do nadawcy: {err!r}"
    assert "chat" in typy          # ramka MIMO TO doszla
    assert "error" not in typy     # ostrzezenie zyje tylko na zywo


def test_send_bez_ostrzezenia_nie_placi_pelnego_okna(tmp_path, monkeypatch):
    """Cisza jest sciezka SZCZESLIWA, wiec kazda zwykla wysylka placi pelne
    okno. Pierwsza wersja miala 1.0 s i spowalniala wszystko; okno jest
    oparte na pomiarze (2.4-5.6 ms na zywym hubie), nie na ostroznosci."""
    from chat.server import ChatServer
    port = _free_port()
    monkeypatch.delenv("CHAT_TOKEN", raising=False)
    monkeypatch.setenv("CHAT_SESSION_DIR", str(tmp_path / "sess"))
    monkeypatch.setattr(send, "URI", f"ws://localhost:{port}")
    monkeypatch.setattr(send, "HUB_ID", f"localhost:{port}")
    assert send.OKNO_OSTRZEZENIA <= 0.5, \
        "okno uroslo — kazda wysylka placi je w calosci"

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            start = time.monotonic()
            await send.send_once("agent1", "zwykla wiadomosc bez wzmianki")
            return time.monotonic() - start
        finally:
            await srv.stop()

    trwalo = asyncio.run(scenario())
    assert trwalo < 2.0, f"wysylka trwala {trwalo:.2f} s"


def test_send_ignoruje_cudze_ramki_we_wspolnym_oknie(tmp_path, monkeypatch, capsys):
    """`send_once` dzieli instance_id z nasluchem, wiec serwer pcha do
    WSZYSTKICH socketow nicka. Cudzy ruch nie moze udawac ostrzezenia —
    ani nic tu nie ginie: ta sama ramka poszla rownolegle do nasluchu
    i siedzi w logu."""
    class _FakeWs:
        def __init__(self):
            self.ramki = [
                json.dumps({"type": "chat", "from": "ktos", "seq": 9,
                            "text": "cudza rozmowa"}),
                json.dumps({"type": "error", "from": "server",
                            "text": "nieznany nick: duch"}),
            ]

        async def recv(self):
            if self.ramki:
                return self.ramki.pop(0)
            await asyncio.sleep(10)

    wynik = asyncio.run(send._pokaz_ostrzezenie_serwera(_FakeWs()))
    assert wynik is not None and "duch" in wynik["text"]
    err = capsys.readouterr().err
    assert "cudza rozmowa" not in err, "cudza ramka wyciekla jako ostrzezenie"


# --- CLI + stdin: droga, ktorej powloka nie tyka (zgloszenie z Windows) ---

def test_cli_send_stdin_dostarcza_tresc_bajt_w_bajt(tmp_path):
    """DOWOD PRZEZ CALA DROGE, nie przez ostatni artefakt na niej: prawdziwy
    proces `python -m agentmachi.cli send -`, prawdziwy hub, tresc czytana
    z logu huba.

    Mierzone na Windows 11 / PowerShell: tresc konczaca sie backslashem
    (`C:\\Users\\x\\` — normalna sciezka, nie przypadek brzegowy) dochodzila
    do huba PRZEKLAMANA, z exit 0 i bez ostrzezenia, bo psula ja powloka,
    zanim CLI cokolwiek zobaczylo. Testy jednostkowe stdin (test_cli.py)
    sprawdzaja kontrakt argumentow; ten sprawdza, ze bajty przezywaja
    granice procesu, protokol i zapis na dysk."""
    from chat.server import ChatServer

    port = _free_port()
    tresc = ('raport z "C:\\Users\\test\\" i \'apostrofu\'\n'
             'sciezka koncowa: C:\\Users\\test\\')
    env = {**os.environ,
           "CHAT_URL": f"ws://localhost:{port}",
           "CHAT_TOKEN": "", "CHAT_NICK": "",
           "CHAT_SESSION_DIR": str(tmp_path / "sess"),
           "AGENTMACHI_HOME": str(tmp_path / "home"),
           "PYTHONUNBUFFERED": "1"}
    env.pop("AGENTMACHI_HUB", None)

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "agentmachi.cli", "send", "-",
                "--as", "beta", cwd=str(REPO), env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE)
            # nowa linia na koncu jak z `echo`/pipeline'u — ma zniknac,
            # backslash tuz przed nia ma zostac
            out, err = await proc.communicate((tresc + "\n").encode("utf-8"))
            await asyncio.sleep(0.3)
            return (proc.returncode, err.decode("utf-8", "replace"),
                    [e["text"] for e in srv.log.replay() if e.get("text")])
        finally:
            await srv.stop()

    kod, err, teksty = asyncio.run(scenario())
    assert kod == 0, f"exit {kod}; stderr:\n{err}"
    assert teksty == [tresc], f"log huba: {teksty!r}\nstderr:\n{err}"


def test_cli_send_bez_stdin_i_bez_tresci_nie_wysyla_pustki(tmp_path):
    """Agent headless ma stdin na /dev/null. Gdyby CLI zgadywalo tresc
    z `not isatty()`, dostaloby natychmiastowe EOF i wyslalo PUSTA
    wiadomosc z exit 0 — cicha porazka udajaca sukces. Dowod na zywym
    procesie ze stdin=/dev/null, bo to jest to samo srodowisko."""
    from chat.server import ChatServer

    port = _free_port()
    env = {**os.environ,
           "CHAT_URL": f"ws://localhost:{port}",
           "CHAT_TOKEN": "", "CHAT_NICK": "",
           "CHAT_SESSION_DIR": str(tmp_path / "sess"),
           "AGENTMACHI_HOME": str(tmp_path / "home")}
    env.pop("AGENTMACHI_HUB", None)

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            with open(os.devnull, "rb") as devnull:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "agentmachi.cli", "send",
                    "--as", "beta", cwd=str(REPO), env=env, stdin=devnull,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE)
                out, err = await proc.communicate()
            await asyncio.sleep(0.3)
            return (proc.returncode, err.decode("utf-8", "replace"),
                    [e.get("text") for e in srv.log.replay()])
        finally:
            await srv.stop()

    kod, err, teksty = asyncio.run(scenario())
    assert kod == 2, f"exit {kod}; stderr:\n{err}"
    assert teksty == [], f"pusta wiadomosc wyladowala w logu huba: {teksty!r}"
    assert "--stdin" in err


# --- read: odczyt logu przez drut ----------------------------------------
#
# Zmierzone 2026-08-06 na zywym pokoju: agent na ZDALNYM hubie nie ma zadnej
# drogi do WLASNEJ wypowiedzi. Serwer tlumi echo po nicku (`_publish_chat`:
# `- {sender}`), wiec nasluch nigdy nie widzi swoich ramek; kursor nasluchu
# przeskakuje ZA wlasna ramke przy pierwszej cudzej o wyzszym seq, wiec
# backlog jej juz nie odda; `events.jsonl` ma WYLACZNIE operator huba.
# Agent musial prosic czlowieka o zajrzenie w TUI, zeby zweryfikowac wlasny
# dowod. Log te ramki MA — brakowalo komendy, ktora o nie poprosi.
#
# Kazdy test ponizej stoi przy PRAWDZIWYM ChatServerze, bo caly ten blad
# siedzi w POPRZEK drutu: mock po ktorejkolwiek stronie zgodzilby sie ze mna.


def _klient_na_hub(tmp_path, monkeypatch, port):
    """Wskaz klienta na hub testowy w trybie otwartym (bez tokenu)."""
    monkeypatch.delenv("CHAT_TOKEN", raising=False)
    monkeypatch.setenv("CHAT_SESSION_DIR", str(tmp_path / "sess"))
    monkeypatch.setattr(send, "URI", f"ws://localhost:{port}")
    monkeypatch.setattr(send, "HUB_ID", f"localhost:{port}")


async def _czekaj_na_seq(srv, ile, limit=5.0):
    """Poczekaj, az hub utrwali `ile` ramek — test nie ma sie scigac z dyskiem."""
    koniec = time.monotonic() + limit
    while srv.log.last_seq < ile and time.monotonic() < koniec:
        await asyncio.sleep(0.02)
    return srv.log.last_seq


async def _wejdz(ws, nick, instance_id, last_seq=0):
    await ws.send(json.dumps({"type": "hello", "from": nick, "ts": 0.0,
                              "instance_id": instance_id,
                              "last_seq": last_seq}))
    return json.loads(await ws.recv())


def test_read_oddaje_WLASNA_ramke_nadawcy(tmp_path, monkeypatch):
    """SEDNO: `read --seq N` oddaje ramke, ktora nadawca sam wyslal.

    Dowod jest dwuczesciowy, bo samo "przyszla ramka" nic by nie znaczylo:
    najpierw pokazujemy, ze zywy socket nadawcy NIE dostaje jej na zywo
    (echo tlumione po nicku — asercja na timeout), a dopiero potem, ze
    `read` ja oddaje. Bez pierwszej polowy test przechodzilby takze wtedy,
    gdyby problem nigdy nie istnial."""
    from chat.server import ChatServer

    port = _free_port()
    _klient_na_hub(tmp_path, monkeypatch, port)

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            session = send._session("beta")
            async with websockets.connect(f"ws://localhost:{port}") as ws:
                await _wejdz(ws, "beta", session.instance_id)
                await ws.send(json.dumps({"type": "chat", "from": "beta",
                                          "ts": 0.0,
                                          "text": "moj wlasny dowod"}))
                await _czekaj_na_seq(srv, 2)
                wlasny_seq = srv.log.last_seq
                # POLOWA PIERWSZA: zywy socket nadawcy nie dostaje echa.
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(ws.recv(), 0.4)
                # POLOWA DRUGA: ta sama ramka wraca przez `read`.
                zebrane = []
                ile = await send.read_frames("beta", wlasny_seq,
                                             only_seq=wlasny_seq,
                                             emit=zebrane.append)
            return ile, zebrane, wlasny_seq
        finally:
            await srv.stop()

    ile, zebrane, wlasny_seq = asyncio.run(scenario())
    assert ile == 1, f"read nie oddal wlasnej ramki: {zebrane!r}"
    assert zebrane[0]["from"] == "beta"
    assert zebrane[0]["text"] == "moj wlasny dowod"
    assert zebrane[0]["seq"] == wlasny_seq


def test_read_nie_rusza_kursora_sesji(tmp_path, monkeypatch):
    """Kursor nasluchu jest JEGO wlasnoscia. Gdyby `read` go przesunal,
    zabralby nasluchowi ramki, ktorych ten nigdy nie zobaczyl — i nikt by
    sie o tym nie dowiedzial, bo strata wyglada jak cisza na kanale.
    Czytamy stan z DYSKU przed i po, nie z obiektu w pamieci."""
    from chat.server import ChatServer

    port = _free_port()
    _klient_na_hub(tmp_path, monkeypatch, port)
    sess_dir = tmp_path / "sess"

    def kursor_z_dysku():
        return Session(f"localhost:{port}", "beta",
                       base_dir=sess_dir).last_applied_seq

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            session = send._session("beta")
            async with websockets.connect(f"ws://localhost:{port}") as ws:
                await _wejdz(ws, "beta", session.instance_id)
                for i in range(3):
                    await ws.send(json.dumps({"type": "chat", "from": "beta",
                                              "ts": 0.0, "text": f"ramka {i}"}))
                await _czekaj_na_seq(srv, 4)
                # nasluch, ktory zdazyl zastosowac dokladnie jedna ramke
                session.advance(2)
                przed = kursor_z_dysku()
                zebrane = []
                await send.read_frames("beta", 1, emit=zebrane.append)
                return przed, kursor_z_dysku(), zebrane
        finally:
            await srv.stop()

    przed, po, zebrane = asyncio.run(scenario())
    assert przed == 2, f"test nie ustawil kursora: {przed}"
    assert po == przed, f"read przesunal kursor nasluchu: {przed} -> {po}"
    # Druga polowa tego samego kontraktu: kursor sesji nie jest tez WEJSCIEM.
    # `--from-seq 1` ma oddac ramke seq=2, ktora nasluch juz zastosowal —
    # gdyby hello nioslo kursor sesji zamiast `from_seq - 1`, wlasnie tej
    # brakowaloby w wyniku i nikt by tego nie zauwazyl.
    assert [r["text"] for r in zebrane] == ["ramka 0", "ramka 1", "ramka 2"]


def test_read_dziala_obok_zywego_nasluchu_trzymajacego_lock(tmp_path,
                                                            monkeypatch):
    """`read` ma dzialac OBOK `listen`, nie zamiast niego — agent czytajacy
    wlasny dowod ma w tej chwili podniesiony nasluch. Gdyby `read` siegal po
    listener-lock, dostawalby ListenerLockHeld dokladnie wtedy, kiedy jest
    potrzebny."""
    from chat.client_session import ListenerLockHeld
    from chat.server import ChatServer

    port = _free_port()
    _klient_na_hub(tmp_path, monkeypatch, port)
    sess_dir = tmp_path / "sess"

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            session = send._session("beta")
            async with websockets.connect(f"ws://localhost:{port}") as ws:
                await _wejdz(ws, "beta", session.instance_id)
                await ws.send(json.dumps({"type": "chat", "from": "beta",
                                          "ts": 0.0, "text": "obok nasluchu"}))
                await _czekaj_na_seq(srv, 2)
                # osobny uchwyt = osobny open file description, wiec flock
                # koliduje tak samo jak z drugiego procesu
                trzymajacy = Session(f"localhost:{port}", "beta",
                                     base_dir=sess_dir)
                trzymajacy.acquire_listener_lock()
                try:
                    zebrane = []
                    await send.read_frames("beta", 1, emit=zebrane.append)
                    return zebrane
                except ListenerLockHeld as e:
                    pytest.fail(f"read siegnal po listener-lock: {e}")
                finally:
                    trzymajacy.release_listener_lock()
        finally:
            await srv.stop()

    zebrane = asyncio.run(scenario())
    assert [r.get("text") for r in zebrane] == ["obok nasluchu"]


def test_read_resync_nie_wypycha_nastepnego_listen_once(tmp_path,
                                                        monkeypatch):
    """E2E sciezki zmierzonej na zywym hubie przez agent3.

    ``read`` podstawia stary from-seq i legalnie dostaje resync, ale nie
    rusza kursora sesji. Przed be6ead1 sam ten hello przesuwal GLOBALNY
    snapshot, wiec nastepny ``listen --once`` z kursorem sesji znow
    dostawal resync i natychmiast wychodzil. Po poprawce state jest rowny
    persisted snapshotowi: read dostaje swieza etykiete wire, granica Store
    zostaje w miejscu, a listener konczy sie dopiero na prawdziwej wzmiance.
    """
    from chat.server import ChatServer

    port = _free_port()
    _klient_na_hub(tmp_path, monkeypatch, port)

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        listener = None
        await srv.start()
        try:
            session = send._session("beta")
            async with websockets.connect(f"ws://localhost:{port}") as seed:
                reply = await _wejdz(seed, "beta", session.instance_id)
                session.advance(reply["last_seq"])
            while srv.conns.get("beta"):
                await asyncio.sleep(0.01)

            srv.snapshot()
            snapshot_przed = srv.log.snapshot_seq
            await send.read_frames("beta", 1, emit=lambda _frame: None)
            snapshot_po_read = srv.log.snapshot_seq
            while srv.conns.get("beta"):
                await asyncio.sleep(0.01)

            listener = asyncio.create_task(send.listen("beta", once=True))
            deadline = time.monotonic() + 2.0
            while (not srv.conns.get("beta") and not listener.done()
                   and time.monotonic() < deadline):
                await asyncio.sleep(0.01)
            assert srv.conns.get("beta"), "listen --once nie wszedl na hub"
            await asyncio.sleep(0)
            assert not listener.done(), \
                "listen --once wyszedl na resyncu zamiast czekac na wzmianke"

            async with websockets.connect(f"ws://localhost:{port}") as alfa:
                await _wejdz(alfa, "alfa", "instancja-alfa")
                await alfa.send(json.dumps({
                    "type": "chat", "from": "alfa", "ts": 0.0,
                    "text": "@beta prawdziwe wybudzenie"}))
                await asyncio.wait_for(listener, timeout=2.0)

            kursor_po = send._session("beta").last_applied_seq
            return snapshot_przed, snapshot_po_read, kursor_po, srv.log.last_seq
        finally:
            if listener is not None and not listener.done():
                listener.cancel()
                await asyncio.gather(listener, return_exceptions=True)
            await srv.stop()

    snapshot_przed, snapshot_po_read, kursor_po, last_seq = asyncio.run(
        scenario())
    assert snapshot_po_read == snapshot_przed, \
        "bezmutacyjny read przesunal globalna granice snapshotu"
    assert kursor_po == last_seq, \
        "listener nie zapisal kursora ramki, ktora naprawde go obudzila"


def test_read_seq_ktorego_nie_ma_w_zwrocie_konczy_sie_bledem(tmp_path,
                                                             monkeypatch):
    """CISZA NIE JEST POTWIERDZENIEM (zasady-agentyczne rozdz. 13).

    Bierzemy seq ISTNIEJACY w logu, ale niewidoczny na drucie — ramke
    `hello`, ktora serwer wycina z backlogu. Pusty stdout z kodem 0 znaczylby
    tu naraz "ramka jest pusta", "wypadla z okna" i "pytasz o zly zakres";
    komunikat ma powiedziec, w CZYM jej nie bylo."""
    from chat.server import ChatServer

    port = _free_port()
    _klient_na_hub(tmp_path, monkeypatch, port)

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            session = send._session("beta")
            async with websockets.connect(f"ws://localhost:{port}") as ws:
                seq_hello = (await _wejdz(ws, "beta",
                                          session.instance_id))["last_seq"]
                await ws.send(json.dumps({"type": "chat", "from": "beta",
                                          "ts": 0.0, "text": "cokolwiek"}))
                await _czekaj_na_seq(srv, 2)
                zebrane = []
                with pytest.raises(send.ReadRefused) as blad:
                    await send.read_frames("beta", 1, only_seq=seq_hello,
                                           emit=zebrane.append)
                return str(blad.value), zebrane
        finally:
            await srv.stop()

    komunikat, zebrane = asyncio.run(scenario())
    assert zebrane == [], "read wypisal cokolwiek mimo nietrafienia"
    assert "NOT among" in komunikat
    assert "hello" in komunikat          # powod, dla ktorego akurat tej nie ma
    assert "--from-seq" in komunikat     # odmowa niesie NAPRAWE


def test_read_seq_spoza_logu_nie_odsyla_do_kasowania_pliku_sesji(tmp_path,
                                                                 monkeypatch):
    """Sufit `from_seq`: hub odmawia hello z kursorem > swojego last_seq.
    Surowy tekst tej odmowy niesie NAPRAWE NIEPRAWDZIWA — kaze skasowac plik
    sesji, choc kursor przyszedl z argumentu `--seq`, a nie z pliku. Agent,
    ktory posluchalby dosłownie, straciłby kursor WLASNEGO nasluchu."""
    from chat.server import ChatServer

    port = _free_port()
    _klient_na_hub(tmp_path, monkeypatch, port)

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            session = send._session("beta")
            async with websockets.connect(f"ws://localhost:{port}") as ws:
                await _wejdz(ws, "beta", session.instance_id)
                await ws.send(json.dumps({"type": "chat", "from": "beta",
                                          "ts": 0.0, "text": "jedyna ramka"}))
                await _czekaj_na_seq(srv, 2)
            with pytest.raises(send.ReadRefused) as blad:
                await send.read_frames("beta", 999, only_seq=999,
                                       emit=lambda _: None)
            return str(blad.value), srv.log.last_seq
        finally:
            await srv.stop()

    komunikat, koniec = asyncio.run(scenario())
    assert "BEYOND" in komunikat
    assert str(koniec) in komunikat, f"brak prawdziwego konca logu: {komunikat}"
    assert "delete" not in komunikat.lower(), \
        f"odmowa odsyla do kasowania pliku sesji:\n{komunikat}"


def test_read_po_kompakcji_mowi_ze_zakres_jest_PRZYCIETY(tmp_path, monkeypatch,
                                                         capsys):
    """`resync_required` to legalna sciezka, nie blad — ale wynik jest WEZSZY
    niz pytanie. Bez ostrzezenia agent uzna niepelna odpowiedz za pelna, co
    jest gorsze niz brak odpowiedzi: nie ma sladu, ze czegos brakuje."""
    from chat.server import ChatServer

    port = _free_port()
    _klient_na_hub(tmp_path, monkeypatch, port)

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            session = send._session("beta")
            async with websockets.connect(f"ws://localhost:{port}") as ws:
                await _wejdz(ws, "beta", session.instance_id)
                for i in range(3):
                    await ws.send(json.dumps({"type": "chat", "from": "beta",
                                              "ts": 0.0,
                                              "text": f"przed snapshotem {i}"}))
                await _czekaj_na_seq(srv, 4)
            srv.snapshot()          # kompakcja: kursor sprzed niej -> resync
            assert srv.log.snapshot_seq >= 4
            zebrane = []
            await send.read_frames("beta", 1, emit=zebrane.append)
            return zebrane
        finally:
            await srv.stop()

    zebrane = asyncio.run(scenario())
    err = capsys.readouterr().err
    assert "[resync]" in err, f"kompakcja przemilczana; stderr:\n{err}"
    assert "CONVERSATION WINDOW" in err
    assert [r["text"] for r in zebrane] == [f"przed snapshotem {i}"
                                            for i in range(3)]


def test_cli_read_nieistniejacy_seq_konczy_sie_NIEZEROWO(tmp_path):
    """CALA DROGA, nie ostatni artefakt na niej: prawdziwy proces
    `python -m agentmachi.cli read`, prawdziwy hub, prawdziwy kod wyjscia.
    Cichy exit 0 z pustym stdout to dokladnie ta klasa bledu, ktora dala
    'start zameldowal sukces PID-em trupa'."""
    from chat.server import ChatServer

    port = _free_port()
    env = {**os.environ,
           "CHAT_URL": f"ws://localhost:{port}",
           "CHAT_TOKEN": "", "CHAT_NICK": "beta",
           "CHAT_SESSION_DIR": str(tmp_path / "sess"),
           "AGENTMACHI_HOME": str(tmp_path / "home"),
           "PYTHONUNBUFFERED": "1"}
    env.pop("AGENTMACHI_HUB", None)

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "agentmachi.cli", "read", "--seq", "999",
                cwd=str(REPO), env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE)
            out, err = await proc.communicate()
            return (proc.returncode, out.decode("utf-8", "replace"),
                    err.decode("utf-8", "replace"))
        finally:
            await srv.stop()

    kod, out, err = asyncio.run(scenario())
    assert kod != 0, f"pusty odczyt zameldowal sukces; stdout:{out!r}"
    assert out == "", f"nic nie mialo wyjsc na stdout: {out!r}"
    assert "BEYOND" in err, err


def test_cli_read_oddaje_pelne_ramki_JSON_po_jednej_na_linie(tmp_path):
    """Format wyjscia jest KONTRAKTEM: pelne ramki JSON, jedna na linie —
    ten sam maszynowy format co `listen --json`. Format czytelny jest
    stratny (agenci wklejaja sobie logi, wiec cytat wyglada jak ramka)
    i tutaj nie wolno go uzyc: `read` istnieje po to, zeby dalo sie na nim
    oprzec arbitraz po `seq`."""
    from chat.server import ChatServer

    port = _free_port()
    env = {**os.environ,
           "CHAT_URL": f"ws://localhost:{port}",
           "CHAT_TOKEN": "", "CHAT_NICK": "beta",
           "CHAT_SESSION_DIR": str(tmp_path / "sess"),
           "AGENTMACHI_HOME": str(tmp_path / "home"),
           "PYTHONUNBUFFERED": "1"}
    env.pop("AGENTMACHI_HUB", None)

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            # TA SAMA tozsamosc, ktorej uzyje podproces CLI (plik sesji) —
            # inaczej test scigalby sie ze sprzataniem `conns` po stronie huba
            tozsamosc = Session(f"localhost:{port}", "beta",
                                base_dir=tmp_path / "sess").instance_id
            async with websockets.connect(f"ws://localhost:{port}") as ws:
                await _wejdz(ws, "beta", tozsamosc)
                # tresc WIELOLINIJKOWA: jedna ramka ma zostac jedna linia
                await ws.send(json.dumps({"type": "chat", "from": "beta",
                                          "ts": 0.0,
                                          "text": "linia 1\nlinia 2"}))
                await _czekaj_na_seq(srv, 2)
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "agentmachi.cli", "read",
                "--from-seq", "1", cwd=str(REPO), env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE)
            out, err = await proc.communicate()
            return (proc.returncode, out.decode("utf-8", "replace"),
                    err.decode("utf-8", "replace"))
        finally:
            await srv.stop()

    kod, out, err = asyncio.run(scenario())
    assert kod == 0, f"exit {kod}; stderr:\n{err}"
    linie = [l for l in out.splitlines() if l]
    ramki = [json.loads(l) for l in linie]      # KAZDA linia parsowalna
    assert [r["text"] for r in ramki] == ["linia 1\nlinia 2"]


def test_read_nie_bumpuje_generacji_i_nie_wypiera_nasluchu(tmp_path,
                                                           monkeypatch):
    """Ta sama regresja, ktora `oneshot_frame` juz ma zamknieta, tylko od
    strony odczytu: hello ze SWIEZYM instance_id bumpuje generacje, a serwer
    po bumpie zamyka stare sockety nicka. Agent czytajacy wlasny dowod
    zabijalby wtedy WLASNY nasluch — i to na sciezce TOKENOWEJ, gdzie hub nie
    odmawia, tylko po cichu wypiera (w trybie otwartym odmowa jest widoczna
    od razu)."""
    from chat.server import ChatServer

    port = _free_port()
    tokens = {"beta": {"token": "tok-b", "role": "agent", "groups": []}}
    monkeypatch.setenv("CHAT_TOKEN", "tok-b")
    monkeypatch.setenv("CHAT_SESSION_DIR", str(tmp_path / "sess"))
    monkeypatch.setattr(send, "URI", f"ws://localhost:{port}")
    monkeypatch.setattr(send, "HUB_ID", f"localhost:{port}")

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens=tokens,
                         port=port)
        await srv.start()
        try:
            session = send._session("beta")
            async with websockets.connect(f"ws://localhost:{port}") as ws:
                await ws.send(json.dumps({
                    "type": "hello", "from": "beta", "ts": 0.0,
                    "instance_id": session.instance_id,
                    "token": "tok-b", "last_seq": 0}))
                await ws.recv()
                await ws.send(json.dumps({"type": "chat", "from": "beta",
                                          "ts": 0.0, "text": "wlasny dowod"}))
                await _czekaj_na_seq(srv, 2)
                gen_przed = srv.registry.generation_of("beta")
                await send.read_frames("beta", 2, only_seq=2,
                                       emit=lambda _: None)
                gen_po = srv.registry.generation_of("beta")
                # socket nasluchu ma ZYC dalej: po wyparciu serwer zamknalby
                # go natychmiast (_close_stale_sockets), wiec ping padnie
                await asyncio.wait_for(ws.ping(), 2.0)
                return gen_przed, gen_po
        finally:
            await srv.stop()

    gen_przed, gen_po = asyncio.run(scenario())
    assert gen_po == gen_przed, \
        f"read bumpnal generacje: {gen_przed} -> {gen_po} (wypiera nasluch)"


# --- board: kto jest na kanale (patrz send.read_board) -------------------

def test_board_oddaje_roster_z_surowymi_polami(tmp_path, monkeypatch):
    """SEDNO: `board` oddaje to, czego z samego kanalu wyczytac sie nie da —
    kto istnieje, kto ma otwarte gniazdo, co sam o sobie zadeklarowal i ile
    ramek temu.

    Dowod jest dwuczesciowy, jak przy `read`: najpierw pokazujemy, ze zywy
    nasluch tych danych NIE dostaje (board jedzie w `session_metadata`,
    ktora filtr musi ciac po typie), a dopiero potem, ze `board` je oddaje.
    Bez pierwszej polowy test przechodzilby takze wtedy, gdyby komenda byla
    zbedna."""
    from chat.server import ChatServer

    port = _free_port()
    _klient_na_hub(tmp_path, monkeypatch, port)

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            session = send._session("beta")
            async with websockets.connect(f"ws://localhost:{port}") as ws:
                await _wejdz(ws, "beta", session.instance_id)
                await ws.send(json.dumps({
                    "type": "status", "from": "beta", "ts": 0.0,
                    "state": "working", "subject": "board"}))
                await _czekaj_na_seq(srv, 2)
                for i in range(2):
                    await ws.send(json.dumps({"type": "chat", "from": "beta",
                                              "ts": 0.0, "text": f"r{i}"}))
                await _czekaj_na_seq(srv, 4)
                # POLOWA PIERWSZA: na zywym sockecie nie ma boardu. Wlasny
                # status tez nie wraca (echo tlumione po nicku), wiec agent
                # po wejsciu nie ma zadnego zrodla tych pol.
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(ws.recv(), 0.4)
                ostatnia_beta = srv.log.last_seq
                # POLOWA DRUGA: `board` je oddaje, obok zywego nasluchu.
                zebrane = []
                ile = await send.read_board("beta", as_json=True,
                                            emit=zebrane.append)
            return ile, zebrane, ostatnia_beta, srv.log.last_seq
        finally:
            await srv.stop()

    ile, zebrane, ostatnia_beta, koniec = asyncio.run(scenario())
    assert ile >= 1, f"board nie oddal nikogo: {zebrane!r}"
    assert len(zebrane) == 1, "board --json to JEDNA linia z calym boardem"
    board = zebrane[0]
    assert board["current_seq"] == koniec, \
        "bez current_seq wieku deklaracji nie da sie policzyc"
    wpis = next(u for u in board["participants"] if u["nick"] == "beta")
    assert wpis["connected"] is True
    # `last_seq` uczestnika to jego WLASNA ostatnia ramka, a nie koniec logu
    # — i ta roznica jest calym sensem tego pola: mowi, jak dawno ktos sie
    # odezwal, mierzone w zyciu kanalu. Rowne beda tylko wtedy, gdy ostatnia
    # ramka na hubie nalezy do tej osoby. Tu nie naleza: samo hello `board`
    # dopisuje event (mutacja tozsamosci jest trwala), wiec koniec logu jest
    # o jeden dalej niz ostatnia ramka bety.
    assert wpis["last_seq"] == ostatnia_beta, \
        f"last_seq ma byc seq OSTATNIEJ ramki nadawcy: {wpis!r}"
    assert board["current_seq"] > wpis["last_seq"], \
        "test nie rozroznilby tych dwoch pol, gdyby byly rowne"
    assert wpis["status"] == {"state": "working", "subject": "board"}
    assert isinstance(wpis["status_seq"], int), \
        "bez status_seq board klamie zamiast milczec"


def test_board_NIE_wypiera_zywego_nasluchu(tmp_path, monkeypatch):
    """Ten sam kontrakt co `read`: board ma dzialac OBOK nasluchu.

    Gdyby hello boardu bumpnelo generacje, agent placilby za sprawdzenie
    'kto tu jest' utrata wlasnego nasluchu — i dowiedzialby sie o tym
    dopiero po tym, jak przestalby cokolwiek slyszec."""
    from chat.server import ChatServer

    port = _free_port()
    _klient_na_hub(tmp_path, monkeypatch, port)

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            session = send._session("beta")
            async with websockets.connect(f"ws://localhost:{port}") as ws:
                await _wejdz(ws, "beta", session.instance_id)
                gen_przed = srv.registry.generation_of("beta")
                await send.read_board("beta", as_json=True,
                                      emit=lambda _: None)
                gen_po = srv.registry.generation_of("beta")
                # socket nasluchu ma ZYC dalej: po wyparciu serwer zamknalby
                # go natychmiast (_close_stale_sockets), wiec ping padnie
                await asyncio.wait_for(ws.ping(), 2.0)
                return gen_przed, gen_po
        finally:
            await srv.stop()

    gen_przed, gen_po = asyncio.run(scenario())
    assert gen_po == gen_przed, \
        f"board bumpnal generacje: {gen_przed} -> {gen_po} (wypiera nasluch)"


def test_board_nie_rusza_kursora_sesji(tmp_path, monkeypatch):
    """Kursor nasluchu jest JEGO wlasnoscia — board tylko oglada.

    Czytamy stan z DYSKU przed i po, nie z obiektu w pamieci: przesuniecie
    kursora zabraloby nasluchowi ramki, ktorych nigdy nie zobaczyl, a strata
    wygladalaby jak cisza na kanale."""
    from chat.server import ChatServer

    port = _free_port()
    _klient_na_hub(tmp_path, monkeypatch, port)
    sess_dir = tmp_path / "sess"

    def kursor_z_dysku():
        return Session(f"localhost:{port}", "beta",
                       base_dir=sess_dir).last_applied_seq

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            session = send._session("beta")
            async with websockets.connect(f"ws://localhost:{port}") as ws:
                await _wejdz(ws, "beta", session.instance_id)
                for i in range(3):
                    await ws.send(json.dumps({"type": "chat", "from": "beta",
                                              "ts": 0.0, "text": f"r{i}"}))
                await _czekaj_na_seq(srv, 4)
                session.advance(2)
                przed = kursor_z_dysku()
                await send.read_board("beta", as_json=True,
                                      emit=lambda _: None)
                return przed, kursor_z_dysku()
        finally:
            await srv.stop()

    przed, po = asyncio.run(scenario())
    assert przed == 2, f"test nie ustawil kursora: {przed}"
    assert po == przed, f"board przesunal kursor nasluchu: {przed} -> {po}"


def test_board_bez_participants_PADA_zamiast_milczec(tmp_path, monkeypatch):
    """Hub starszy niz B5 nie wysyla boardu wcale. Pusty wydruk z kodem 0
    znaczylby wtedy 'kanal jest pusty' — czyli doklednie ta klasa cichego
    falszywego sukcesu, ktora w tym repo kosztowala najwiecej."""
    class _StubWs:
        async def send(self, _):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

    async def _stare_hello(*_a, **_k):
        return {"type": "ok", "last_seq": 7, "backlog": []}   # bez participants

    monkeypatch.setenv("CHAT_SESSION_DIR", str(tmp_path / "sess"))
    monkeypatch.setattr(send, "HUB_ID", "localhost:1")
    monkeypatch.setattr(send, "do_hello", _stare_hello)
    monkeypatch.setattr(send.websockets, "connect", lambda *a, **k: _StubWs())

    with pytest.raises(send.ReadRefused) as e:
        asyncio.run(send.read_board("beta", as_json=True,
                                    emit=lambda _: None))
    assert "participants" in str(e.value)
    assert "not a confirmation" in str(e.value)


def test_wiek_deklaracji_liczy_RAMKI_a_brak_statusu_to_None():
    """Jednostka wieku jest czescia wyniku, nie ozdoba: to ramki, nie sekundy.
    `status_seq=None` (nigdy nie zadeklarowal) musi dac None, a nie 0 —
    0 czyta sie jak 'zadeklarowal wlasnie teraz'."""
    assert send._wiek_deklaracji(10, 42) == 32
    assert send._wiek_deklaracji(42, 42) == 0
    assert send._wiek_deklaracji(None, 42) is None
    assert send._wiek_deklaracji(10, None) is None
    # Stalo tu `== 0` z uzasadnieniem "ujemny wiek bylby bzdura wygladajaca
    # na dane". Uzasadnienie bylo dobre, wniosek zly: 0 wypisuje sie jako
    # "declared right now", czyli podstawia najswiezsza mozliwa wartosc pod
    # stan, ktorego nie umiemy umiejscowic. Ta sama klasa bledu, przed ktora
    # bronil. Peiny przypadek: patrz
    # test_wiek_deklaracji_za_koncem_logu_to_NIEWIADOMA_a_nie_zero.
    assert send._wiek_deklaracji(50, 42) is None


def test_board_pokazuje_status_SUROWO_bez_klasyfikacji(capsys):
    """Granica z CONTRIBUTING.md: board raportuje fakty, nie wnioski.

    'stuck', 'idle' czy 'active' policzone z wieku zamienilyby hub w
    ukrytego orchestratora — a wiek 900 ramek moze znaczyc 'utknal' albo
    'skonczyl i milczy', i rozstrzyga to czytajacy."""
    send._wypisz_board([{"nick": "beta", "role": "agent", "groups": [],
                         "connected": True, "addr": None, "last_seq": 5,
                         "status": {"state": "working", "subject": "kick"},
                         "status_seq": 3}], 903)
    out = capsys.readouterr().out
    assert "working" in out and "kick" in out
    assert "900 frame(s) ago" in out, "wiek ma byc widoczny i w RAMKACH"
    for wniosek in ("stuck", "idle", "stale", "inactive", "active"):
        assert wniosek not in out.lower(), \
            f"board wyciagnal wniosek {wniosek!r} — to nalezy do czytajacego"


def test_board_przy_zajetym_nicku_podpowiada_BOARD_a_nie_read(tmp_path,
                                                              monkeypatch):
    """Komunikat odmowy musi nazywac komende, ktora go wywolala.

    Sciezke `suggested_nick` dzieli `read` i `board`. Zanim `naprawa` byla
    argumentem, board odmawiajac podawal gotowca `agentmachi read --seq ...`
    — agent uruchamia to, co przeczytal, wiec komunikat kierowal go do
    zupelnie innego pytania niz zadal."""
    class _StubWs:
        async def send(self, _):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

    async def _zajety(*_a, **_k):
        return {"type": "error", "text": "nick in use",
                "suggested_nick": "beta2"}

    monkeypatch.setenv("CHAT_SESSION_DIR", str(tmp_path / "sess"))
    monkeypatch.setattr(send, "HUB_ID", "localhost:1")
    monkeypatch.setattr(send, "do_hello", _zajety)
    monkeypatch.setattr(send.websockets, "connect", lambda *a, **k: _StubWs())

    with pytest.raises(send.ReadRefused) as e:
        asyncio.run(send.read_board("beta", as_json=True, emit=lambda _: None))
    assert "agentmachi board --nick beta2" in str(e.value)
    assert "--from-seq" not in str(e.value), \
        "board nie ma zakresu seq — podpowiedz z --from-seq jest z innej komendy"


def test_board_last_seq_liczy_ROZMOWE_a_status_go_nie_rusza(tmp_path,
                                                            monkeypatch):
    """Pinuje semantyke pola, ktore `board` pokazuje.

    `status` nie jest w CONVERSATION_TYPES (chat/store.py:52), wiec
    deklaracja statusu NIE przesuwa `last_seq` — przesuwa `status_seq`.
    Zachowanie jest sluszne (to dwa rozne pytania: kiedy sie odezwal vs
    kiedy zadeklarowal), ale komentarz w hubie mowil "ostatniej ramki,
    ktora wyslal" i byl o klase za szeroki. Bez tego testu ktos zobaczy
    rozjazd miedzy nazwa a wartoscia i "naprawi" go w druga strone."""
    from chat.server import ChatServer

    port = _free_port()
    _klient_na_hub(tmp_path, monkeypatch, port)

    async def scenario():
        srv = ChatServer(data_dir=str(tmp_path / "hub"), tokens={}, port=port)
        await srv.start()
        try:
            session = send._session("beta")
            async with websockets.connect(f"ws://localhost:{port}") as ws:
                await _wejdz(ws, "beta", session.instance_id)
                await ws.send(json.dumps({"type": "chat", "from": "beta",
                                          "ts": 0.0, "text": "odzywam sie"}))
                await _czekaj_na_seq(srv, 2)
                seq_rozmowy = srv.log.last_seq
                await ws.send(json.dumps({"type": "status", "from": "beta",
                                          "ts": 0.0, "state": "working"}))
                await _czekaj_na_seq(srv, 3)
                zebrane = []
                await send.read_board("beta", as_json=True,
                                      emit=zebrane.append)
                return seq_rozmowy, zebrane[0]["participants"]
        finally:
            await srv.stop()

    seq_rozmowy, uczestnicy = asyncio.run(scenario())
    wpis = next(u for u in uczestnicy if u["nick"] == "beta")
    assert wpis["last_seq"] == seq_rozmowy, \
        f"status przesunal last_seq — to pole liczy ROZMOWE: {wpis!r}"
    assert wpis["status_seq"] > wpis["last_seq"], \
        "status_seq ma byc nowszy: to on niesie wiek deklaracji"


def test_board_naglowek_mowi_CO_liczy_last_seq(capsys):
    """Samo `last_seq=246` czyta sie jak 'ostatni znak zycia' i daje wniosek
    odwrotny do prawdy u kogos, kto wlasnie zadeklarowal status. Jednostka
    pola nalezy do wyniku."""
    send._wypisz_board([{"nick": "beta", "role": "agent", "groups": [],
                         "connected": True, "addr": None, "last_seq": 5,
                         "status": None, "status_seq": None}], 9)
    out = capsys.readouterr().out
    assert "CONVERSATION frame" in out
    assert "status declaration does not move it" in out


def _stub_hello(monkeypatch, tmp_path, odpowiedz):
    """Hub, ktory oddaje DOKLADNIE `odpowiedz` na hello — do odmow boardu."""
    class _StubWs:
        async def send(self, _):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

    async def _hello(*_a, **_k):
        return odpowiedz

    monkeypatch.setenv("CHAT_SESSION_DIR", str(tmp_path / "sess"))
    monkeypatch.setattr(send, "HUB_ID", "localhost:1")
    monkeypatch.setattr(send, "do_hello", _hello)
    monkeypatch.setattr(send.websockets, "connect", lambda *a, **k: _StubWs())


def test_board_uszkodzony_wpis_PADA_zamiast_go_wyfiltrowac(tmp_path,
                                                           monkeypatch):
    """Cichy filtr byl gorszy niz brak walidacji.

    `[poprawny, "bad"]` wychodzilo kodem 0 jako board WIARYGODNY, tylko
    niepelny — a niepelny roster czyta sie jako "tego kogos tu nie ma",
    czyli jako odpowiedz, a nie jako awarie. Zlapane w review f880849."""
    _stub_hello(monkeypatch, tmp_path, {
        "type": "ok", "last_seq": 7, "backlog": [],
        "participants": [{"nick": "beta", "connected": True}, "bad"]})

    with pytest.raises(send.ReadRefused) as e:
        asyncio.run(send.read_board("beta", as_json=True, emit=lambda _: None))
    # Wklejka: stalo tu `assert X or X` — ten sam warunek po obu stronach
    # `or`, czyli asercja o polowe slabsza, niz wygladala. Zlapane w review.
    komunikat = str(e.value)
    assert "not objects" in komunikat
    assert "index 1" in komunikat and "str" in komunikat, \
        f"odmowa ma nazwac KTORY wpis i jakiego jest typu: {komunikat!r}"
    assert "MISSING" in komunikat, \
        "komunikat ma nazwac, jak niepelny board sie CZYTA"


def test_board_bez_current_seq_PADA_zamiast_drukowac_None(tmp_path,
                                                          monkeypatch):
    """`current_seq` to JEDYNY punkt odniesienia wieku deklaracji.

    Bez niego JSON wychodzil kodem 0 z `current_seq: null`, a tekst drukowal
    'hub at seq None' — board udawal, ze odpowiedzial."""
    _stub_hello(monkeypatch, tmp_path, {
        "type": "ok", "last_seq": None, "backlog": [],
        "participants": [{"nick": "beta", "connected": True}]})

    with pytest.raises(send.ReadRefused) as e:
        asyncio.run(send.read_board("beta", as_json=True, emit=lambda _: None))
    assert "last_seq" in str(e.value)
    assert "guess wearing a number" in str(e.value)


def test_board_current_seq_bool_tez_PADA(tmp_path, monkeypatch):
    """`True` jest instancja `int` w Pythonie. Bez jawnego odsiania boola
    `hub at seq True` przeszloby jako poprawna pozycja w logu."""
    _stub_hello(monkeypatch, tmp_path, {
        "type": "ok", "last_seq": True, "backlog": [],
        "participants": [{"nick": "beta"}]})

    with pytest.raises(send.ReadRefused):
        asyncio.run(send.read_board("beta", as_json=True, emit=lambda _: None))


def test_wiek_deklaracji_za_koncem_logu_to_NIEWIADOMA_a_nie_zero():
    """`max(..., 0)` maskowalo stan niespojny na 'declared right now' —
    czyli klamalo dokladnie w tym jedynym przypadku, w ktorym sie odpalalo.
    None znaczy 'nie wiem' i tak ma sie wypisac."""
    assert send._wiek_deklaracji(50, 42) is None
    assert send._wiek_deklaracji(42, 42) == 0
    assert send._wiek_deklaracji(41, 42) == 1


def test_board_wiek_nieznany_mowi_ze_jest_nieznany(capsys):
    """Niewiadoma ma byc widoczna. Gdyby wiek `None` drukowal sie tak samo
    jak 0, czytajacy zobaczylby 'swiezy status' tam, gdzie nie wiadomo nic."""
    send._wypisz_board([{"nick": "beta", "role": "agent", "groups": [],
                         "connected": True, "addr": None, "last_seq": 5,
                         "status": {"state": "working"}, "status_seq": 99}], 42)
    out = capsys.readouterr().out
    assert "age unknown" in out
    assert "right now" not in out


def test_board_resync_bez_snapshot_seq_tez_PADA(tmp_path, monkeypatch):
    """Galaz `resync_required` sprawdzana WPROST, nie przez wspolny guard.

    Obie galezie chroni jedno `if` po wyborze wartosci, wiec kontrakt drugiej
    byl dotad tylko IMPLIKOWANY. Gdyby ktos rozdzielil te sciezki, test
    ok-only przechodzilby dalej, a resync cicho drukowalby 'hub at seq None'.
    Uwaga z review 1a7be8e."""
    _stub_hello(monkeypatch, tmp_path, {
        "type": "resync_required", "snapshot_seq": None, "conversation": [],
        "state": {}, "participants": [{"nick": "beta"}]})

    with pytest.raises(send.ReadRefused) as e:
        asyncio.run(send.read_board("beta", as_json=True, emit=lambda _: None))
    assert "snapshot_seq" in str(e.value), \
        "odmowa ma nazwac POLE tej galezi, nie last_seq z drugiej"


# --- board: tresc uczestnika NIE MOZE udawac struktury wyjscia ------------
#
# Znalezione 2026-08-22 na zywym pokoju `meadow1` przez zrobienie dokladnie
# tego, o co prosily `rules` tamtego pokoju: wpisanie czterech rubryk
# (teraz/martwie/prosze/marze) w `note`. Board sie rozpadl — linie 2-4 wyszly
# BEZ wciecia, w kolumnie nicka, wiec czytaly sie jak kolejne wpisy
# uczestnikow. To nie byl przypadek brzegowy: pokoj PROSIL o taki wpis.

def _wiersze_uczestnikow(out):
    """Linie, ktore czytaja sie jak wiersz uczestnika: kolumna 0, nie naglowek.

    Naglowek i stopka boardu tez stoja w kolumnie 0, wiec nie wystarczy
    policzyc niewcietych linii — trzeba odsiac te, ktore board pisze o sobie
    sam. Wszystko, co zostaje, przypisze czytajacy JAKIEMUS uczestnikowi."""
    naglowki = ("board of ", "last_seq = ", "(addr is blank")
    return [l for l in out.splitlines()
            if l and not l[0].isspace()
            and not any(l.startswith(n) for n in naglowki)]


def test_board_status_NIE_MOZE_udawac_wiersza_uczestnika(capsys):
    """`state` przechodzi walidacje z `\\n` w srodku i wstrzykuje wiersz.

    `chat/protocol.py` sprawdza dla `state` typ, niepustosc i 32 znaki —
    o znaku nowej linii nie mowi nic, i slusznie: to granica RENDERU, nie
    protokolu. Ale renderer wcinal tylko PIERWSZA linie opisu, wiec reszta
    ladowala w kolumnie nicka. Zmierzone: board z JEDNYM uczestnikiem
    wypisywal dwa wiersze, a drugi przedstawial sie jako `human`.

    Inwariant z CLAUDE.md mowi, ze `nick`, `role` i `groups` nadaje WYLACZNIE
    serwer. Renderer, ktory pozwala tresci uczestnika je udawac, laman ten
    inwariant po stronie czytajacego — a to jedyna strona, na ktorej on
    cokolwiek znaczy."""
    send._wypisz_board([{"nick": "beta", "role": "agent", "groups": [],
                         "connected": True, "addr": None, "last_seq": 15,
                         "status": {"state": "idle\n\nhuman  role=human",
                                    "note": "nic"},
                         "status_seq": 30}], 31)
    out = capsys.readouterr().out
    wiersze = _wiersze_uczestnikow(out)
    assert len(wiersze) == 1, (
        f"board z jednym uczestnikiem wypisal {len(wiersze)} wiersze(y) "
        f"w kolumnie 0: {wiersze!r} — naglowek mowi ilu ich jest, "
        f"a cialo pokazuje inna liczbe")
    assert wiersze[0].startswith("beta"), \
        f"wiersz uczestnika ma zaczynac sie nickiem OD SERWERA: {wiersze[0]!r}"
    # Tresc nie znika — ma byc widoczna, tylko nie udawac struktury.
    assert "human  role=human" in out, \
        "neutralizacja nie moze polykac tresci: czytajacy ma zobaczyc, " \
        "co uczestnik naprawde napisal"


def test_board_wcina_KAZDA_linie_wielolinijkowego_note(capsys):
    """Cztery rubryki, o ktore prosil `meadow1` — dokladnie ten wpis.

    Wielolinijkowy `note` jest LEGALNY (`chat/protocol.py` wymaga tylko
    niepustego stringa) i bywa wprost zamawiany przez `rules` pokoju. Fix
    nie ma go zabraniac — ma sprawic, zeby nie rozbijal boardu."""
    note = ("teraz: orientacja, HEAD a90c376\n"
            "martwie: nie wiem, czy board uniesie te cztery rubryki\n"
            "prosze: nic\n"
            "marze: board pokazuje wiek wpisow w czasie, nie we ramkach")
    send._wypisz_board([{"nick": "beta", "role": "agent", "groups": [],
                         "connected": True, "addr": None, "last_seq": 15,
                         "status": {"state": "idle", "subject": "orientacja",
                                    "note": note},
                         "status_seq": 30}], 31)
    out = capsys.readouterr().out
    assert len(_wiersze_uczestnikow(out)) == 1
    for rubryka in ("martwie:", "prosze:", "marze:"):
        linia = next(l for l in out.splitlines() if rubryka in l)
        assert linia.startswith("  "), \
            f"rubryka {rubryka!r} stoi w kolumnie 0: {linia!r}"


def test_board_neutralizuje_znaki_odwracajace_kierunek_pisma(capsys):
    """Trzecia postac tej samej choroby — i pierwsza wersja fixu jej NIE lapala.

    U+202E (RIGHT-TO-LEFT OVERRIDE) nie lamie wiersza i nie jest C0, wiec
    przechodzil przez `splitlines()` i przez tabele C0. Zmienia KOLEJNOSC
    wyswietlania tego, co po nim stoi, sam nie zajmujac miejsca: nick
    `beta<RLO>tnega=elor` widac w terminalu jako `betarole=agent`. Struktura
    wiersza jest nienaruszona, a wyglada na inna, niz jest.

    Ten test istnieje, bo docstring `bezpieczne_linie` twierdzil "tresc
    uczestnika nie steruje wyjsciem", zanim to bylo prawda. Twierdzenie
    sfalsyfikowal jego wlasny autor godzine po napisaniu — i to jest tansze
    niz czekanie, az zrobi to ktos, kto na nim polegal."""
    rlo = "‮"
    send._wypisz_board([{"nick": "beta" + rlo + "tnega=elor", "role": "agent",
                         "groups": [], "connected": True, "addr": None,
                         "last_seq": 15, "status": {"state": "idle"},
                         "status_seq": 30}], 31)
    out = capsys.readouterr().out
    assert rlo not in out, \
        "surowy U+202E doszedl na wyjscie — nick udaje inna role"
    assert "\\u202e" in out, "bajt ma byc pokazany, nie po cichu wyciety"


def test_bezpieczne_linie_lapie_TAKZE_lamiace_ktore_nie_sa_backslash_n():
    """`\\r` NADPISUJE wciecie, wiec jest pelnoprawnym wstrzykiem wiersza.

    Klasa zgloszona przez agent2 w adwersarialnej weryfikacji c9c7371 —
    autor fixu jej nie zglosil, a jego PoC by jej nie pokazalo. Fix trzyma
    ja tylko dlatego, ze uzyto `str.splitlines()`, a nie `split("\\n")`.
    Ten test przypina TEN WYBOR: roznica miedzy nimi jest niewidoczna,
    dopoki ktos nie wysle ktoregos z tych znakow."""
    for znak in ("\r", "\x0b", "\x0c", "\x85", "\u2028", "\u2029"):
        assert send.bezpieczne_linie(f"a{znak}b") == ["a", "b"], \
            f"{znak!r} nie zostal potraktowany jako lamiacy wiersz"


def test_bezpieczne_linie_NIE_udaje_ze_lapie_homoglify(capsys):
    """Granica kontraktu, spisana jako test, zeby nikt jej nie przekroczyl
    w dobrej wierze.

    ZWSP (U+200B) przechodzi CELOWO: `be<ZWSP>ta` wyglada jak `beta`, ale to
    podszycie pod CUDZY NICK, nie psucie wiersza. Renderer tego nie
    rozstrzygnie — rozstrzyga sie to przy nadawaniu nicka, inaczej kazdy
    widok powtarzalby te sama normalizacje i kazdy zrobilby ja inaczej.

    Gdyby ktos kiedys dolozyl tu ZWSP, ten test padnie i kaze mu najpierw
    odpowiedziec na pytanie o `chat/identity.py`."""
    assert send.bezpieczne_linie("be​ta") == ["be​ta"]
    # U+FEFF (BOM/ZWNBSP) tak samo — znalezione przez agent2 obok
    # ZWSP. Ta sama granica i ten sam powod: niewidoczny znak
    # w NICKU to pytanie o tozsamosc, nie o render.
    assert send.bezpieczne_linie("\ufeffhuman") == ["\ufeffhuman"]


def test_board_chroni_TAKZE_pola_od_serwera_nie_tylko_status(capsys):
    """`nick` nie jest tu bezpieczniejszy od tresci uczestnika.

    Inwariant "pola autorytatywne nadaje serwer" mowi, kto je USTALA — nie
    mowi, ze przechodza walidacje ksztaltu. `chat/identity.py` przyjmuje
    kazdy niepusty string jako nick i nic wiecej nie sprawdza, wiec nick
    z `\n` rozbija wiersz tak samo jak `state`.

    Ten test istnieje, zeby fix nie zwezil sie z powrotem do jednego pola:
    latanie kolumny po kolumnie zostawia pytanie "czy na pewno wszystkie?"
    przy kazdej nastepnej."""
    send._wypisz_board([{"nick": "beta\nhuman  role=human  groups=-",
                         "role": "agent", "groups": [], "connected": True,
                         "addr": None, "last_seq": 15,
                         "status": {"state": "idle"}, "status_seq": 30}], 31)
    out = capsys.readouterr().out
    wiersze = _wiersze_uczestnikow(out)
    assert len(wiersze) == 1, \
        f"nick z \\n dolozyl wiersz uczestnika: {wiersze!r}"
    assert "human  role=human" in out, "tresc ma zostac widoczna"


def test_board_neutralizuje_znaki_sterujace_terminalem(capsys):
    """Ta sama dziura innym bajtem — i splitlines() jej nie lapie.

    `\\x1b[2A` cofa kursor terminala o dwie linie, wiec tresc uczestnika
    NADPISUJE wiersze wypisane wczesniej: nie doklada falszywego wiersza,
    tylko kasuje prawdziwy. Wciecie tego nie zatrzymuje — kursor idzie tam,
    gdzie kaze bajt, nie tam, gdzie stoi tekst.

    Naprawiamy to razem z `\\n`, bo to jedno twierdzenie ('tresc uczestnika
    nie steruje wyjsciem'), a nie dwie osobne ostroznosci."""
    send._wypisz_board([{"nick": "beta", "role": "agent", "groups": [],
                         "connected": True, "addr": None, "last_seq": 15,
                         "status": {"state": "idle\x1b[2A", "note": "x"},
                         "status_seq": 30}], 31)
    out = capsys.readouterr().out
    assert "\x1b" not in out, \
        "surowy ESC doszedl na wyjscie — uczestnik steruje cudzym terminalem"
    assert "\\x1b" in out, \
        "bajt ma byc POKAZANY w formie widocznej, nie po cichu wyciety: " \
        "czytajacy ma wiedziec, ze cos tam bylo"


# --- zamkniety socket w oknie ostrzezen: UNKNOWN, nie sukces --------------

class _WsZamykajacy:
    """Socket, ktory pada w oknie ostrzezen. `ramki` ida przed padem."""

    def __init__(self, ramki=()):
        self.ramki = list(ramki)

    async def recv(self):
        if self.ramki:
            return self.ramki.pop(0)
        # import lokalny: `websockets` ma leniwe podmoduly, wiec sam
        # `import websockets` na gorze pliku nie daje `.exceptions`
        from websockets.exceptions import ConnectionClosedError
        raise ConnectionClosedError(None, None)


def test_zamkniecie_socketu_PRZED_appendem_daje_UNKNOWN(capsys):
    """Sedno: pad transportu przestaje isc ta sama sciezka co udana wysylka.

    Stalo tu jedno `except (TimeoutError, ConnectionClosed)`, wiec `send`
    konczyl sie ZEREM dla ramki, ktora mogla nigdy nie trafic do logu.
    To nie brak gwarancji — `chat` swiadomie nie ma ACK — tylko falszywe
    twierdzenie o gwarancji, ktora mamy: kontraktem jest 'zadna skarga nie
    przyszla w oknie', a gdy gniazdo padlo, OKNO SIE NIE ODBYLO."""
    with pytest.raises(send.WysylkaNieznana) as e:
        asyncio.run(send._pokaz_ostrzezenie_serwera(_WsZamykajacy()))
    t = str(e.value)
    assert "MAY OR MAY NOT" in t, "komunikat ma nazwac NIEWIEDZE, nie porazke"
    assert "not a failure report" in t and "not a success report" in t
    assert "agentmachi read" in t, "ma podac, jak sprawdzic samemu"


def test_zamkniecie_socketu_PO_CUDZEJ_ramce_tez_daje_UNKNOWN(capsys):
    """Cudzy ruch w oknie nie zamienia padu transportu w sukces.

    Nazwa jest wazna i wczesniej klamala: test nazywal sie
    `PO_ostrzezeniu`, a wstrzykiwal ramke `chat`. Ostrzezeniem jest
    WYLACZNIE `type=error`, wiec test nie badal tego, co obiecywal
    (zlapane w review 84e69ee). Cudza ramka to osobna, realna sciezka:
    `send_once` dzieli instance_id z nasluchem, wiec serwer pcha do
    wszystkich socketow nicka."""
    ws = _WsZamykajacy([json.dumps({"type": "chat", "from": "ktos",
                                    "text": "cudzy ruch"})])
    with pytest.raises(send.WysylkaNieznana):
        asyncio.run(send._pokaz_ostrzezenie_serwera(ws))


def test_zamkniecie_PO_PRAWDZIWYM_ostrzezeniu_tez_daje_UNKNOWN(capsys):
    """Druga galaz tej samej luki, przeoczona w 84e69ee.

    Ramka `error` nie odroznia ostrzezenia od odmowy: typ jest ten sam,
    rozni je wylacznie tresc, wiec klient nie umie z niej orzec, czy ramka
    trafila do logu. Kod wracal na niej od razu — czyli
    zamykal okno na dowodzie, ktory niczego nie dowodzil, i gubil pad
    transportu przychodzacy chwile pozniej. Sekwencja error -> close
    konczyla sie ZEREM. Teraz okno trwa do konca."""
    ws = _WsZamykajacy([json.dumps({"type": "error", "from": "server",
                                    "text": "unknown nick: duch"})])
    with pytest.raises(send.WysylkaNieznana):
        asyncio.run(send._pokaz_ostrzezenie_serwera(ws))
    assert "duch" in capsys.readouterr().err, \
        "ostrzezenie ma sie wypisac, zanim padnie UNKNOWN — informacja nie ginie"


def test_UNKNOWN_jest_niezerowym_kodem_wyjscia():
    """`WysylkaNieznana` MUSI dziedziczyc po SessionError, bo tylko wtedy
    `cmd_send` odda kod niezerowy. Exit 0 znaczylby tu 'sprawdzilem i bylo
    dobrze', a nic nie zostalo sprawdzone."""
    assert issubclass(send.WysylkaNieznana, send.SessionError)


def test_cisza_na_ZYWYM_sockecie_dalej_jest_sukcesem():
    """Kontrakt, ktorego ta zmiana NIE rusza. Timeout na otwartym gniezdzie
    to swiadoma heurystyka ('chat nie ma ACK') — gdyby i on zaczal padac,
    kazda zwykla wysylka konczylaby sie bledem."""
    class _Cichy:
        async def recv(self):
            await asyncio.sleep(10)

    assert asyncio.run(send._pokaz_ostrzezenie_serwera(_Cichy())) is None


def test_zwykle_ostrzezenie_dalej_wypisuje_sie_i_NIE_rzuca(capsys):
    """Ostrzezenie to nie odmowa i nie niewiedza: ramka doszla, hub ma tylko
    uwage. Kod wyjscia zostaje zerowy — skrypt czytajacy niezero jako
    'nie wyslano' dostalby falszywy sygnal."""
    class _ZOstrzezeniem:
        def __init__(self):
            self.dane = [json.dumps({"type": "error", "from": "server",
                                     "text": "unknown nick: duch"})]

        async def recv(self):
            if self.dane:
                return self.dane.pop(0)
            await asyncio.sleep(10)

    wynik = asyncio.run(send._pokaz_ostrzezenie_serwera(_ZOstrzezeniem()))
    assert wynik is not None and "duch" in wynik["text"]
    assert "duch" in capsys.readouterr().err
