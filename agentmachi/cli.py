"""CLI agentmachi: serve / tui / send / listen / card.

Zasada (plan B2): dane huba mieszkaja w ~/.agentmachi/<name>/ —
NIGDY w repo projektu. Repo projektu to rzecz, nad ktora pracuja agenci;
hub to infrastruktura obok (jak Hamachi obok CS-a).

Uklad ~/.agentmachi/<name>/:
  tokens.json  (0600)  nick -> {token, role, groups}
  config.json          {port, bind}
  data/                event-log + snapshot huba (chat.store)
  data/rules.md        opcjonalne ograniczenia pokoju (pusty = brak;
                       wpisuje human, plikiem)
"""
import argparse
import asyncio
import contextlib
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from chat.client_session import purge_session_files

DEFAULT_PORT = 8766
DEFAULT_HUB = "hub"
DEFAULT_BIND = "127.0.0.1"
STOP_WAIT = 10.0   # ile czekamy, az zatrzymywany hub naprawde zejdzie

# PAKIET 1 (plan V1): hub NIE nadaje domyslnej kultury.
#
# Konstytucja od 2026-07-24: "lekcja z dogfoodu domyslnie idzie do obserwacji,
# nie do regulaminu. Wyciecie pastucha z kodu nic nie daje, jesli odrasta
# w plikach .md jako kolejny obowiazkowy paragraf." Scheduler wylecial z kodu,
# a pastuch odrosl wlasnie tutaj: 15 regul organizacyjnych, ktore hub wkladal
# KAZDEMU nowemu pokojowi i serwowal kazdemu wchodzacemu przy kazdym hello.
#
# `rules` zostaje jako FUNKCJA: konkretny pokoj moze miec ograniczenia, gdy
# wpisze je czlowiek — plik istniejacy nigdy nie jest nadpisywany. Roznica
# wobec stanu poprzedniego jest ustrojowa: pusty plik znaczy "przestrzen jest
# wolna", a nie "zapomnielismy tresci". Zasady wspolpracy naleza do skilla,
# ktory agent instaluje SWIADOMIE — nie do transportu, ktory dostaje bez
# pytania i na kazdym projekcie.
DEFAULT_RULES = ""


class CliError(Exception):
    pass


def hub_home():
    return Path(os.environ.get("AGENTMACHI_HOME",
                               Path.home() / ".agentmachi"))


def hub_dir(name):
    if not name or "/" in name or name.startswith("."):
        raise CliError(f"bad hub name: {name!r}")
    return hub_home() / name


def _write_0600(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)


def _porty_hubow(wlasna_nazwa):
    """Mapa `port -> nazwa pokoju` dla POZOSTALYCH pokojow. Zrodlem jest
    config, nie zywy proces: hub zatrzymany nadal ma prawo do swojego portu,
    bo `start` odpali go pod tym samym adresem.

    Zwracamy NAZWE, nie sam fakt zajetosci, bo odmowa musi umiec powiedziec
    czlowiekowi, KTO trzyma port. "port taken" bez wlasciciela zostawia go
    z zagadka zamiast z naprawa."""
    mapa = {}
    home = hub_home()
    if not home.is_dir():
        return mapa
    for d in sorted(home.iterdir()):
        if not d.is_dir() or d.name == wlasna_nazwa:
            continue
        try:
            cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        p = cfg.get("port")
        if isinstance(p, int) and not isinstance(p, bool):
            mapa.setdefault(p, d.name)
    return mapa


def _porty_innych_hubow(wlasna_nazwa):
    """Same porty z `_porty_hubow` — dla alokatora, ktory nazw nie potrzebuje."""
    return set(_porty_hubow(wlasna_nazwa))


def _odmow_zajetego_portu(name, port, skutek):
    """Nic, gdy portu nikt nie zarezerwowal; CliError z nazwa wlasciciela,
    gdy trzyma go inny pokoj.

    Jedno miejsce na ten tekst, bo WEJSCIA SA DWA, a strzezone bylo jedno.
    `ensure_hub` pilnowal pokoju NOWEGO — i tyle wystarczylo, zeby uznac
    sprawe za zamknieta. Zmierzone przez recenzenta (2026-08-06) na drugim
    wejsciu: dwa ZATRZYMANE pokoje, `owner` na 8790 i `stary` na 8795, po
    `cmd_start(name="stary", port=8790)` dawaly `rc=0, owner=8790,
    stary=8790` — dwa configi na jednym porcie, bo `cmd_start` nadpisywal
    config istniejacego pokoju zaraz PO tym, jak `ensure_hub` swiadomie
    zachowal stary port i nie sprawdzil kolizji.

    Rezerwacja jest wlasnoscia CONFIGU, nie zywego procesu: zatrzymany pokoj
    nadal ma prawo do swojego portu, bo `start` postawi go pod tym samym
    adresem (patrz `_porty_hubow`). Dlatego kontrola zywego portu
    (`_port_accepts`) tej dziury nie zamykala i zamknac nie mogla.

    `skutek` mowi czlowiekowi, co przez odmowe NIE stalo sie z jego pokojem;
    reszta komunikatu jest wspolna, bo naprawa jest ta sama."""
    wlasciciel = _porty_hubow(name).get(port)
    if wlasciciel is None:
        return
    # Komendy KAZDA W OSOBNEJ LINII, nie za etykieta: nazwy pokojow maja
    # rozna dlugosc, wiec kolumna i tak by sie rozjechala, a to jest tekst
    # do kopiuj-wklej (CLAUDE.md, rola czlowieka).
    raise CliError(
        f"port {port} is already assigned to room {wlasciciel!r} — "
        f"{skutek}\n"
        f"You asked for this port explicitly, so it does not get shifted "
        f"for you: a silent shift is how a room ends up at an address "
        f"nobody was told about.\n"
        f"  see which room has which port:\n"
        f"      agentmachi list\n"
        f"  put {name!r} somewhere else:\n"
        f"      agentmachi start --name {name} --port <other>\n"
        f"  or move {wlasciciel!r} out of the way first:\n"
        f"      agentmachi stop --name {wlasciciel}\n"
        f"      agentmachi start --name {wlasciciel} --port <other>")


def _wybierz_port(preferowany, wlasna_nazwa, bind="127.0.0.1", prob=200):
    """Pierwszy wolny port od `preferowanego` w gore.

    C5: dwa huby na jednym porcie to cicha katastrofa, nie drobiazg. Nowy hub
    wstaje z PUSTYM logiem pod adresem starego, a kursory klientow sa per
    host:port — czlowiek dostaje wtedy fail-closed "last_seq 303 > serwerowy
    last_seq 0" i nie wie, dlaczego. `list` tez zaczyna klamac, bo rozpoznaje
    huby po porcie. Zmierzone na zywej maszynie: hub 'agentmachi' utworzony
    bez --port zabral 8766 dzialajacemu 'goldbergowi'.

    Sprawdzamy WYLACZNIE configi innych hubow, nie zajetosc portu w systemie:
    obcy proces na tym porcie i tak daje fail-fast przy bindzie (F7), a
    odpytywanie zywego systemu uzaleznialoby wynik `ensure_hub` od tego, co
    akurat chodzi na maszynie — testy stawaly sie flaky, gdy obok dzialal
    prawdziwy hub."""
    zajete = _porty_innych_hubow(wlasna_nazwa)
    kandydat = preferowany
    for _ in range(prob):
        if kandydat not in zajete:
            return kandydat
        kandydat += 1
    raise CliError(
        f"no free port in range "
        f"{preferowany}..{preferowany + prob - 1}; pass --port explicitly")


def _wybierz_port_zywy(preferowany, wlasna_nazwa, bind, prob=200):
    """Jak `_wybierz_port`, ale omija tez porty trzymane przez ZYWE procesy.

    Wolno tego uzyc wylacznie przy `start` NOWEGO pokoju, gdzie czlowiek nie
    podal --port. Powod rozdzialu: `_wybierz_port` swiadomie nie odpytuje
    systemu, bo wynik `ensure_hub` zaczynal wtedy zalezec od tego, co akurat
    chodzi na maszynie (testy flaky). Tu zywy system i tak jest odpytywany,
    bo `start` musi wiedziec, czy port da sie zbindowac.

    Zwraca None, gdy w zakresie nie ma nic wolnego — wtedy `start` wraca do
    komunikatu z rada, zamiast rzucac wyjatkiem."""
    zajete = _porty_innych_hubow(wlasna_nazwa)
    kandydat = preferowany
    for _ in range(prob):
        if kandydat not in zajete and not _port_accepts(kandydat, bind):
            return kandydat
        kandydat += 1
    return None


HOWTO_ZNACZNIK = ".howto-wydany"


def _hash_tekstu(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def odswiez_howto(hub_katalog):
    """Dopilnuj, zeby pokoj serwowal AKTUALNE howto. Zwraca (co, kopia).

    `co` to jedno z: "utworzone" | "odswiezone" | "aktualne" | "zachowane".
    `kopia` to sciezka kopii recznych zmian albo None.

    Po co to w ogole istnieje. `howto` idzie DRUTEM w kazdej odpowiedzi na
    hello i CLAUDE.md wskazuje je jako zrodlo prawdy dla wchodzacego agenta.
    Dotad kopiowalo sie z szablonu WYLACZNIE gdy pliku nie bylo, wiec kazdy
    istniejacy pokoj byl zamrozony na tekscie z dnia swojego powstania.
    Zmierzone 2026-08-01 na zywym pokoju: hub serwowal 4087 B ze zdaniem
    o wypieraniu nicka, ktore agent1 tego samego dnia obalil pomiarem
    i poprawil w repo. Poprawka byla w gicie i nie docierala do nikogo.

    Dlaczego NADPISUJEMY, choc wczesniej sam proponowalem "nie dotykac
    zmienionego": podzial w tym repo jest jasny — `howto` to MECHANIKA
    PROTOKOLU, czyli nasz tekst (CLAUDE.md: "<hub>/data/howto.md = mechanika
    protokolu"), a tekstem POKOJU sa `rules`, ktore ida osobnym polem
    w hello i ktorych ten kod nie tyka. Zamrazanie howto chronilo wiec punkt
    rozszerzen, ktory nie istnieje, a placil za to kazdy agent, czytajac
    nieprawde przy kazdym wejsciu.

    Reczna zmiana nie ginie po cichu: ladu-je obok jako kopia, a wolajacy
    dostaje jej sciezke do pokazania czlowiekowi. Znacznik z hashem WYDANEGO
    tekstu pozwala odroznic "to nasz tekst, tylko starszy" od "ktos to
    zmienil" — bez niego kazde odswiezenie wygladaloby jak nadpisanie cudzej
    pracy. Precedens na hashowanie tresci: rules_hash w hello.
    """
    dane = hub_katalog / "data"
    dane.mkdir(parents=True, exist_ok=True)
    howto = dane / "howto.md"
    znacznik = dane / HOWTO_ZNACZNIK
    wzorzec = (Path(__file__).with_name("howto_default.md")).read_text(
        encoding="utf-8")

    if not howto.exists():
        howto.write_text(wzorzec, encoding="utf-8")
        znacznik.write_text(_hash_tekstu(wzorzec), encoding="utf-8")
        return "utworzone", None

    biezacy = howto.read_text(encoding="utf-8")
    if biezacy == wzorzec:
        # Nic do roboty, ale znacznik moze byc starszy niz plik (pokoj sprzed
        # tego mechanizmu) — domykamy go, zeby nastepnym razem bylo wiadomo.
        znacznik.write_text(_hash_tekstu(wzorzec), encoding="utf-8")
        return "aktualne", None

    try:
        wydany = znacznik.read_text(encoding="utf-8").strip()
    except OSError:
        wydany = None

    if wydany == _hash_tekstu(biezacy):
        # Plik jest DOKLADNIE tym, co sami tam wpisalismy, tylko starszym.
        howto.write_text(wzorzec, encoding="utf-8")
        znacznik.write_text(_hash_tekstu(wzorzec), encoding="utf-8")
        return "odswiezone", None

    # Rozjazd, ktorego nie umiemy przypisac sobie: albo reczna zmiana, albo
    # pokoj sprzed znacznika. Nadpisujemy — ale NIGDY bez zostawienia sladu.
    kopia = dane / "howto.md.zastapione"
    kopia.write_text(biezacy, encoding="utf-8")
    howto.write_text(wzorzec, encoding="utf-8")
    znacznik.write_text(_hash_tekstu(wzorzec), encoding="utf-8")
    return "zachowane", kopia


def ensure_hub(name, port, bind="127.0.0.1", port_jawny=False):
    """Utworz strukture huba przy pierwszym uzyciu; istniejacej NIE ruszaj.

    `port_jawny` mowi, czy `port` to DECYZJA czlowieka (podal `--port`), czy
    tylko punkt startu dla alokatora. Bez tego rozroznienia ta funkcja nie
    miala jak uszanowac decyzji: przesuwala port ZAWSZE, gdy nowy pokoj
    trafial na adres zapisany w configu innego pokoju.

    Zmierzone na zywej maszynie (Windows 11 przez tailnet, 2026-08-06): agent
    poprosil o 8790, dostal 8791, komenda skonczyla sie EXIT 0 i jedna linia
    na stderr. Warstwa wyzej (`cmd_start`) deklarowala w komentarzu "jawne
    --port (decyzja czlowieka, nie zgadujemy za niego)" i robila fail-fast —
    a warstwa nizej i tak zgadywala, bo nie wiedziala, skad ten port
    pochodzi. To ta sama klasa co ciche wejscie `--name` do cudzego pokoju:
    intencja uzytkownika przegrywa z wygoda, po cichu.

    Przy `port_jawny=True` kolizja to ODMOWA (CliError), a nie przesuniecie —
    i sprawdzamy ja PRZED utworzeniem czegokolwiek na dysku, zeby nieudane
    wejscie nie zostawilo pokoju-widma straszacego potem w `list`."""
    d = hub_dir(name)
    if port_jawny and not (d / "config.json").exists():
        # Tylko NOWY pokoj: istniejacy i tak zachowuje swoj port (nizej),
        # a jawne przepiecie istniejacego robi swiadomie `cmd_start` — i tam
        # ta sama kontrola musi byc powtorzona, bo tamta sciezka omija te.
        _odmow_zajetego_portu(name, port, f"room {name!r} was NOT created.")
    (d / "data").mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    tokens_path = d / "tokens.json"
    if not tokens_path.exists():
        # TYLKO human. Zadnych agentow z gory.
        #
        # `human` jest KONIECZNY: TUI wymaga dokladnie jednego humana
        # w tokens.json, a tryb otwarty odmawia wejscia na te role bez tokenu
        # (to jedyne konto z moderacja). Bez niego nie byloby czym moderowac.
        #
        # `agent1`/`agent2` wycietе. Poprzednia zmiana usunela z nich ustroj
        # w NAZWACH (worker->agent) i w GRUPACH (koniec domyslnego `workers`),
        # ale zostawila ETAT: swiezy pokoj twierdzil, ze ma dwoch uczestnikow,
        # zanim ktokolwiek wszedl. `list` wypisywal ich w kolumnie uczestnikow,
        # a board serwowal agentom jako `connected: false` — czyli kanal
        # opowiadal o ludziach, ktorych nie ma. Zgloszone przez operatora:
        # "na kanale powinni byc ci co sa, a nie ci co byc moze beda".
        #
        # Nic nie ginie: tryb otwarty (loopback/tailnet) wpuszcza agenta BEZ
        # tokenu i sam nadaje mu wolny nick — `_wolny_nick()` na pustym pokoju
        # zwraca dokladnie `agent1`, wiec karta moze go dalej proponowac.
        # Do wejscia wymagajacego sekretu (bind publiczny, cudza maszyna)
        # operator dopisuje wpis swiadomie — tak samo jak dzis musi to zrobic
        # dla trzeciego i kazdego kolejnego agenta.
        tokens = {
            "human": {"token": secrets.token_urlsafe(16), "role": "human",
                      "groups": []},
        }
        _write_0600(tokens_path, json.dumps(tokens, indent=2))
    rules_path = d / "data" / "rules.md"
    if not rules_path.exists():
        rules_path.write_text(DEFAULT_RULES, encoding="utf-8")
    # F5 (B5): howto ma dojsc do agenta PROTOKOLEM (hub czyta ten plik i
    # doklada do hello) — plik w repo jest bezuzyteczny dla klienta, ktory
    # ma tylko socket.
    #
    # KONTRAKT ZMIENIONY 2026-08-01, bo stary byl bledny. Stalo tu: "Szablon
    # idzie z pakietu; human moze go nadpisac" i dlatego kopiowalo sie
    # WYLACZNIE gdy pliku nie bylo. To byla swiadoma decyzja (slusznie
    # przypomniana przez agent1), tylko oparta na zalozeniu, ktore nie
    # zgadza sie z reszta projektu: ze `howto` jest miejscem, w ktorym
    # wypowiada sie operator. Nie jest — od tego sa `rules`, ktore ida
    # OSOBNYM polem w hello i ktorych ten kod nie tyka. CLAUDE.md nazywa
    # `<hub>/data/howto.md` mechanika protokolu, czyli NASZYM tekstem.
    #
    # Cena starego kontraktu byla mierzalna: pokoj 'agentmachi' serwowal
    # zdanie o wypieraniu nicka, obalone pomiarem i poprawione w repo tego
    # samego dnia — kazdy wchodzacy agent czytal nieprawde, bo poprawka nie
    # miala jak dojsc. Zamrazalismy punkt rozszerzen, ktory nie istnieje,
    # a placil za to kazdy uczestnik przy kazdym hello.
    #
    # Reczna zmiana NIE ginie po cichu — patrz odswiez_howto.
    stan, kopia = odswiez_howto(d)
    if kopia is not None:
        print(f"agentmachi: howto of room '{name}' had drifted from the "
              f"shipped text — replaced with the current one, the previous "
              f"one is kept in:\n"
              f"  {kopia}", file=sys.stderr)
    config_path = d / "config.json"
    if config_path.exists():
        # Hub ISTNIEJACY zachowuje swoj port — nigdy go nie przesuwamy,
        # bo kursory klientow sa per host:port.
        port = json.loads(config_path.read_text(encoding="utf-8")).get("port", port)
    elif port_jawny:
        # Kolizje sprawdzilismy na gorze tej funkcji i przezylismy ja, wiec
        # port jest wolny. Alokatora tu NIE wolamy — nie dlatego, ze zwrocilby
        # co innego (nie zwrocilby), tylko zeby w kodzie bylo widac, ze jawny
        # --port nie przechodzi przez nic, co moglo by go przesunac.
        config_path.write_text(json.dumps({"port": port, "bind": bind}),
                               encoding="utf-8")
    else:
        # C5: NOWY hub nie moze zabrac portu innemu (ani niczemu w systemie).
        # Bez jawnego --port przesuniecie jest w porzadku: czlowiek nie wskazal
        # adresu, wiec zaden kursor ani wklejona karta jeszcze go nie zna.
        wybrany = _wybierz_port(port, name, bind)
        if wybrany != port:
            print(f"agentmachi: port {port} is taken — hub '{name}' "
                  f"gets {wybrany}", file=sys.stderr)
        port = wybrany
        config_path.write_text(json.dumps({"port": port, "bind": bind}), encoding="utf-8")
    return d, port


def load_tokens(name):
    d = hub_dir(name)
    tokens_path = d / "tokens.json"
    if not tokens_path.exists():
        raise CliError(f"hub {name!r} does not exist (no {tokens_path}); "
                       f"first run: agentmachi start --name {name}")
    return json.loads(tokens_path.read_text(encoding="utf-8")), d


def hub_port(name, fallback=DEFAULT_PORT):
    """Port pokoju albo `fallback`. UWAGA: fallback wolno brac WYLACZNIE
    komendom TWORZACYM pokoj (serve/start/restart) — patrz join_addr."""
    config = hub_dir(name) / "config.json"
    if config.exists():
        return json.loads(config.read_text(encoding="utf-8")).get("port", fallback)
    return fallback


def hub_bind(name, fallback=DEFAULT_BIND):
    """Bind pokoju albo `fallback`. Ten sam warunek co przy hub_port."""
    config = hub_dir(name) / "config.json"
    if config.exists():
        return json.loads(config.read_text(encoding="utf-8")).get("bind", fallback)
    return fallback


def hub_istnieje_lokalnie(name):
    """Czy ten pokoj ma tu zapisany adres. Bez adresu nie ma dokad dolaczac."""
    return (hub_dir(name) / "config.json").exists()


def join_addr(name):
    """(bind, port) pokoju, DO KTOREGO DOLACZAMY. Brak pokoju = CliError.

    Podzial na komendy TWORZACE i DOLACZAJACE jest fizyczny, nie kosmetyczny.
    `serve`/`start`/`restart` maja prawo do DEFAULT_PORT: pokoj dopiero
    powstaje, wiec domyslny adres nie nalezy jeszcze do nikogo, a alokator
    (_wybierz_port) i tak przesunie sie w gore, gdy port jest zajety.
    `listen`/`send`/`frame`/`node`/`card`/`tui` nie maja czego zgadywac —
    gdy config.json pokoju nie istnieje, KAZDY domysl trafia w ten pokoj,
    ktory akurat stoi na tym porcie.

    Zmierzone na zywo 2026-08-05, nie wyczytane z kodu: agent przeszedl
    README doslownie, zrobil `agentmachi listen --name openrepo` (pokoju nie
    bylo w lokalnym ~/.agentmachi/) i wszedl do CUDZEGO pokoju 'test' na
    DEFAULT_PORT. Dostal poprawne session_metadata, board, howto i exit 0 —
    zero ostrzezenia, pelna pewnosc, ze jest na openrepo. `send` domknal
    dowod: exit 0, komunikat "unknown nick: orchestrator" (brzmi jak
    literowka w nicku, nie jak "jestes w zlym pokoju") i ramka w cudzym
    events.jsonl. Raport przepadl, a nadawca byl przekonany, ze go wyslal.

    Klient meldujacy sukces, gdy wyslal dane obcemu odbiorcy, to zlamana
    fizyka transportu, nie brak wygody. Wiec: fail-closed z instrukcja."""
    if not hub_istnieje_lokalnie(name):
        config = hub_dir(name) / "config.json"
        raise CliError(
            f"room {name!r} is not on this machine (no {config}) — refusing "
            f"to guess its port. A guess would silently join whatever room "
            f"happens to run on the default one, and you would get a board, "
            f"a howto and exit 0 from SOMEONE ELSE'S room.\n"
            f"  rooms you have here:    agentmachi list\n"
            f"  room on another host:   CHAT_URL=ws://host:port agentmachi "
            f"listen   (needs no local room at all)\n"
            f"  create it here:         agentmachi start --name {name}")
    return hub_bind(name), hub_port(name)


# --- cykl zycia huba (F6 UX + F7 split-brain) ---------------------------
# Jeden komputer = wiele kanalow (projektow) na wielu portach. Bez listingu
# i bez blokady podwojnego startu operator nie ma jak stwierdzic, co u niego
# dziala — zmierzone bolesnie: pkill nie ubil starego huba, `serve` postawil
# drugi obok, dwa procesy pisaly do jednego katalogu (split-brain).

# --- warstwa wykrywania procesow: /proc na Linuksie, `ps` gdzie indziej ---
#
# Zmierzone przez CI, nie przez czytanie kodu: suita padala na macos-latest
# (8 failed, 509 passed, identycznie na 3.11/3.12/3.13), bo macOS NIE MA
# /proc w ogole. To nie byla usterka testow, tylko dziura w fizyce produktu:
# bez /proc nie dzialalo wykrywanie zywego huba bez pidfile, zapora przed
# split-brainem, `agentmachi kill` (FileNotFoundError na `/proc`) ani `list`
# pokazujacy cudzy zywy hub.
#
# /proc ZOSTAJE sciezka glowna — jest szybkie (bez podprocesow), dokladne
# (`exe` to prawdziwy plik wykonywalny, nie argv) i przetestowane. `ps` jest
# FALLBACKIEM: jest na obu platformach, ale kosztuje fork+exec i zna mniej.
#
# O platforme pyta DOKLADNIE JEDNO miejsce — `_procfs_dostepne()`. Nie
# `sys.platform`, bo pytamy o MOZLIWOSC, nie o nazwe systemu: nie mamy macOS
# pod reka, wiec sciezke bez /proc trzeba dac sie przejsc na Linuksie
# (fixture `bez_procfs` w tests/test_cli.py odbiera temu modulowi /proc).
# Rozproszenie tego pytania po szesciu miejscach dalo szesc osobnych awarii
# na cudzej platformie — kazde nowe czytanie /proc ma isc przez te bramke.

def _procfs_dostepne():
    """Czy mamy /proc (Linux)? Jedyne miejsce, ktore pyta o MOZLIWOSC."""
    return Path("/proc").is_dir()


# --- Windows: platforma, na ktorej ta warstwa nie dziala wcale ----------
#
# Zmierzone na Windows 11 (issue #2), nie wyczytane z kodu: `pip install
# agentmachi` DZIALA, wiec ludzie tam trafiaja — a wykrywania procesow nie
# ma z czego zbudowac. Nie ma /proc i nie ma `ps` jako pliku wykonywalnego
# (`ps` w PowerShell to alias na Get-Process, wiec `_ps` dostaje OSError
# i zwraca None, czyli nasze "procesu nie ma"). Skutek jest najgorszy
# z mozliwych, bo wyglada na awarie produktu, a nie platformy: hub WSTAJE
# (serve.log konczy sie "chat server on ...", port odpowiada), po czym
# `start` mowi "did NOT come up" i kasuje pidfile ZYWEGO huba, `list`
# pokazuje "stopped", `stop` — "is not running", `kill` — "nothing matches".
#
# Wsparcie Windows to osobna robota (issue #2). TU naprawiamy wylacznie to,
# ze produkt klamie o sobie: ostrzegamy, ale NIE odmawiamy — hub naprawde
# wstaje, wiec odmowa zabralaby czlowiekowi dzialajaca czesc.
#
# `_procfs_dostepne` pyta o MOZLIWOSC ("czy da sie czytac /proc") i to
# zostaje. Tu pytamy o NAZWE systemu, bo komunikat mowi czlowiekowi, gdzie
# jest — i to pytanie tez ma miec DOKLADNIE JEDNO miejsce.

ISSUE_WINDOWS = "https://github.com/emilszymecki/agentmachi/issues/2"


def _windows():
    """Czy to Windows? Jedyne miejsce, ktore pyta o NAZWE platformy."""
    return sys.platform == "win32"


# Komendy, ktore stoja na wykrywaniu procesow — czyli te, ktore na Windows
# odpowiadaja pewnie i nieprawdziwie.
KOMENDY_WYKRYWAJACE_PROCESY = frozenset(
    {"start", "list", "stop", "restart", "kill"})


def _ostrzez_o_platformie(cmd):
    """Ostrzez PRZED komenda, ktora na Windows odpowie nieprawde.

    Kluczowe jest rozroznienie, ktorego czlowiek sam nie zrobi: "ta
    platforma jest niesprawdzona" vs "twoj hub jest zepsuty". Hub tam stoi
    — tylko produkt go nie widzi."""
    if not _windows() or cmd not in KOMENDY_WYKRYWAJACE_PROCESY:
        return
    print(
        "agentmachi: WARNING — Windows is not a tested platform yet "
        f"(issue: {ISSUE_WINDOWS}).\n"
        "  This is not your hub being broken: the hub itself starts and "
        "serves normally,\n"
        "  but agentmachi cannot see processes here, so start/list/stop/"
        "restart/kill\n"
        "  report a LIVE hub as stopped or missing. Trust the address from "
        "`agentmachi card`\n"
        "  and the room's serve.log, not this command's verdict.",
        file=sys.stderr)


def _podpowiedz_kto_ma_port(port):
    """Jak sprawdzic, czyj to port — komenda, ktora na TEJ platformie jest.

    `ss` nie istnieje na Windows, a podpowiedz z nieistniejaca komenda jest
    gorsza niz jej brak: zabiera czlowiekowi jedyny trop i wyglada jak
    kolejna usterka.

    Wariant windowsowy jest DWUKROKOWY i to nie jest przeoczenie. `ss -tlnp`
    pokazuje pid RAZEM z nazwa procesu, a `netstat -ano` konczy sie na golej
    liczbie — czlowiek dowiaduje sie, ze port trzyma 33020, i dalej nie wie,
    CO to jest. `tasklist` domyka odpowiedz. Zmierzone na zywym gniezdzie
    2026-08-05 przez agenta na Windows: netstat pokazuje wlasciwy pid co do
    cyfry, brakuje mu wylacznie nazwy."""
    if _windows():
        return (f"netstat -ano | findstr :{port}"
                f"   (then: tasklist /fi \"PID eq <pid>\")")
    return f"ss -tlnp | grep {port}"


def _ps(*argv):
    """Stdout `ps` albo None, gdy sie nie udalo (brak ps, blad, pusty wynik).

    `ps -p <nieistniejacy>` konczy sie kodem 1 — dla nas to poprawna
    odpowiedz "procesu nie ma", wiec None znaczy TO SAMO co OSError przy
    czytaniu /proc. Zawsze `-ww`: macOS bez tego ucina linie polecen do
    szerokosci terminala i `--name <kanal>` wypada z cmdline."""
    try:
        wynik = subprocess.run(("ps",) + argv, capture_output=True,
                               text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if wynik.returncode != 0:
        return None
    return wynik.stdout or None


# Zdjecie `ps -A` na czas JEDNEGO przegladu procesow (patrz
# `_przeglad_procesow`) albo None poza nim. Globalne, bo `_cmdline_of(pid)`
# ma zostac JEDYNYM miejscem, ktore odpowiada na pytanie "jaka linie polecen
# ma ten proces" — i dla kodu, i dla testow, ktore je podmieniaja.
#
# Zmierzone przy tej zmianie: gdy skan czytal cmdline ze zdjecia, a
# `_pid_is_our_hub` przez `_cmdline_of`, testy z podmienionym `_cmdline_of`
# zaczynaly widziec PRAWDZIWE procesy maszyny — `restart` meldowal "pokoj
# juz dziala (PID 3509)", bo na maszynie chodzil hub. To ta sama awaria, co
# w `_ten_sam_home`: wynik suity zalezal od tego, co akurat chodzi.
#
# Dlaczego nie cache z TTL: "zero zegara w logice" (CLAUDE.md). Dlaczego nie
# argument: podmieniona w tescie funkcja przyjmuje `(pid)` i tylko `(pid)`.
_ZDJECIE_PS = None


def _cmdline_of(pid):
    """Linia polecen procesu albo None, gdy go nie ma. Wydzielone, zeby
    test mogl podstawic cudzy proces bez zabawy w prawdziwe PID-y."""
    if _procfs_dostepne():
        try:
            raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        except OSError:
            return None
        return raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()
    if _ZDJECIE_PS is not None:
        return _ZDJECIE_PS.get(pid)
    out = _ps("-ww", "-o", "command=", "-p", str(pid))
    return out.strip() if out else None


def _pid_is_our_hub(pid, name):
    """Czy PID to NA PEWNO hub tego kanalu? Pidfile bywa nieaktualny, a PID-y
    sa recyklowane — bez tej kontroli `stop` moglby ubic cudzy proces.

    C6: nazwe kanalu dopasowujemy jako ARGUMENT (`--name X`), nie jako
    podciag calego cmdline. Dawne `name in cmd` czynilo hub nazwany
    'agentmachi' NIEUSUWALNYM: kazdy hub ma w cmdline `-m agentmachi.cli`,
    wiec nazwa pakietu trafiala jako nazwa kanalu i `del` odmawial, pokazujac
    PID CUDZEGO huba. `stop` mogl przy tym ubic nie ten proces. Ta sama
    rodzina bledu co `pkill -f` trafiajacy we wlasny wrapper powloki:
    dopasowanie tekstowe tam, gdzie potrzebne jest dopasowanie argumentu.
    """
    cmd = _cmdline_of(pid)
    if not cmd:
        return False
    if "agentmachi" not in cmd and "chat.server" not in cmd:
        return False
    slowa = cmd.split()
    try:
        kanal = slowa[slowa.index("--name") + 1]
    except (ValueError, IndexError):
        kanal = DEFAULT_HUB          # hub bez --name obsluguje kanal domyslny
    return kanal == name


_SHELLS = ("zsh", "bash", "sh", "dash", "fish", "setsid", "nohup", "timeout", "env")


def _ancestor_pids():
    """My i cala nasza linia rodzicow. Jeden zbior, DWA powody — obie awarie
    zmierzone, kazda osobno:

    1. Skaner nie ma prawa uznac zadnego z nich za "juz dzialajacy hub" —
       to nie inny serwer, to my w drodze do startu.
    2. `kill` nie ma prawa ich ubic. `pkill -f <wzorzec>` dopasowuje takze
       WLASNY wrapper powloki (wzorzec siedzi w jego argv) i zabija sam
       siebie (exit 144). Ostrzezenie o tym jest w skillu od dawna; w jednej
       sesji dogfoodu weszlo w te pulapke DWOCH agentow, obaj po przeczytaniu
       ostrzezenia. Dokumentacja nie jest zabezpieczeniem.

    Do 2026-07-31 byly to DWIE funkcje czytajace dwa rozne pliki /proc
    (`status` -> PPid vs `stat` -> pole 4) i zwracajace — sprawdzone —
    identyczny zbior. Dwie odpowiedzi na to samo pytanie bezpieczenstwa,
    zrodzone z dwoch osobnych awarii i oddalone od siebie o 300 linii, wiec
    niewidoczne. Jedna moglaby sie zepsuc bez drugiej."""
    out = set()
    cur = os.getpid()
    while cur and cur > 1 and cur not in out:
        out.add(cur)
        cur = _ppid_of(cur)
    return out


def _ppid_of(pid):
    """PID rodzica albo 0, gdy nie wiadomo (proces znikl, brak dostepu).

    Wydzielone z `_ancestor_pids`, bo to jedyny kawalek tamtej funkcji,
    ktory dotykal /proc — reszta (petla po przodkach, ochrona przed cyklem)
    jest przenosna i nie ma powodu istniec w dwoch wariantach."""
    if _procfs_dostepne():
        try:
            status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
        except OSError:
            return 0
        ppid = next((l.split()[1] for l in status.splitlines()
                     if l.startswith("PPid:")), None)
        return int(ppid) if ppid and ppid.isdigit() else 0
    out = _ps("-o", "ppid=", "-p", str(pid))
    ppid = (out or "").strip()
    return int(ppid) if ppid.isdigit() else 0


def _exe_nazwa(pid):
    """Nazwa PLIKU WYKONYWALNEGO procesu (basename) albo None.

    Sedno: ma NIE pochodzic z argv, bo argv klamie (patrz
    `_is_shell_wrapper`). Na Linuksie to `/proc/<pid>/exe`, czyli prawda
    jadra. Bez /proc pytamy `ps -o comm=` — pole `comm` tez pochodzi
    z pliku wykonywalnego, a nie z argumentow: na macOS to sciezka
    binarki, na Linuksie nazwa z jadra (ucieta do 15 znakow, co nam nie
    przeszkadza — porownujemy z krotkimi nazwami powlok).

    Roznica wobec /proc, ktorej NIE DA SIE zalatac: gdy `comm` pochodzi
    mimo wszystko z argv[0] powloki logowania, ma wiodacy `-` (`-zsh`).
    Zdejmujemy go, zeby taki proces nadal rozpoznac jako powloke."""
    if _procfs_dostepne():
        try:
            return os.path.basename(os.readlink(f"/proc/{pid}/exe"))
        except OSError:
            return None
    out = _ps("-o", "comm=", "-p", str(pid))
    if not out:
        return None
    return os.path.basename(out.strip()).lstrip("-") or None


def _is_shell_wrapper(pid):
    """Czy proces to powloka/opakowanie odpalajace polecenie, a nie sam hub?

    `zsh -c "... agentmachi serve --name X"` ma cale polecenie we wlasnym
    argv, wiec kazdy wzorzec tekstowy trafia w niego tak samo jak w prawdziwy
    serwer. Rozstrzygamy po PLIKU WYKONYWALNYM, nie po tresci argumentow —
    argv klamie, exe nie."""
    exe = _exe_nazwa(pid)
    if exe is None:
        return False           # brak dostepu: nie zgadujemy, decyduje wzorzec
    return any(exe == s or exe.startswith(s) for s in _SHELLS)


@contextlib.contextmanager
def _przeglad_procesow():
    """Lista PID-ow wszystkich widocznych procesow — jedno zrodlo dla skanu
    hubow i dla `kill`. Linie polecen bierze sie z `_cmdline_of`, nie stad.

    Bez /proc kazde `_cmdline_of` byloby forkiem `ps`, a `list` pyta o setki
    procesow razy liczba pokoi. Dlatego na czas przegladu robimy JEDNO
    zdjecie `ps -A` i to z niego odpowiada `_cmdline_of`. Zdjecie zyje tylko
    tutaj i jest przywracane w `finally` — poza przegladem `_cmdline_of`
    pyta system na biezaco, bo `stop` czeka wtedy na smierc procesu."""
    global _ZDJECIE_PS
    if _procfs_dostepne():
        try:
            pidy = [int(w.name) for w in Path("/proc").iterdir()
                    if w.name.isdigit()]
        except OSError:
            pidy = []
        yield pidy
        return
    zdjecie = {}
    out = _ps("-A", "-ww", "-o", "pid=,command=")
    for linia in (out or "").splitlines():
        pid_txt, _, cmd = linia.strip().partition(" ")
        if pid_txt.isdigit():
            zdjecie[int(pid_txt)] = cmd.strip()
    poprzednie = _ZDJECIE_PS
    _ZDJECIE_PS = zdjecie
    try:
        yield list(zdjecie)
    finally:
        _ZDJECIE_PS = poprzednie


def _scan_hub_pid(name):
    """Znajdz zywy hub tego kanalu po procesach, bez pidfile.

    F8 (B5): pidfile nie jest zrodlem prawdy o tym, czy hub zyje. Nie ma go
    dla hubow wystartowanych przed F6, znika przy recznym sprzataniu katalogu
    i nie powstaje, gdy ktos odpali serwer inaczej niz przez `serve`. Sam brak
    pliku raportowany jako "zatrzymany" jest grozny w JEDNA strone: kusi, zeby
    postawic drugi hub na tym samym katalogu — czyli split-brain z F7, ktory
    16:05 zzarl nam rozmowe. Dlatego przy braku pidfile pytamy system.
    """
    # REGRESJA z produkcji: startujacy hub pytal "czy juz dzialam?", skaner
    # znajdowal JEGO WLASNY proces (cmdline pasuje idealnie) i serve odmawial
    # startu — hub nie mogl wstac w ogole. Ten sam wzorzec, co pkill -f
    # trafiajacy we wlasny wrapper powloki. Wlasny PID jest zawsze wykluczony.
    # ...a razem z nim CALE nasze drzewo przodkow. Wrapper powloki
    # (`zsh -c "... serve --name X"`, setsid, nohup) trzyma cale polecenie
    # we WLASNYM argv, wiec pasuje do wzorca rownie dobrze jak prawdziwy hub.
    # Bez tego startujacy przez powloke hub znajduje swojego rodzica i znow
    # odmawia startu — ta sama pulapka, tylko o jedno pietro wyzej.
    mine = _ancestor_pids()
    with _przeglad_procesow() as pidy:
        for pid in pidy:
            if pid in mine:
                continue
            cmd = _cmdline_of(pid)
            # Kolejnosc warunkow jest teraz istotna, a nie kosmetyczna: filtr
            # po cmdline jest w przegladzie DARMOWY, a `_is_shell_wrapper` bez
            # /proc kosztuje forka `ps`. Najpierw odsiewamy setki procesow,
            # ktore hubem nie sa, potem pytamy o plik wykonywalny tych kilku,
            # ktore moga nim byc. Oba warunki sa czystymi predykatami — wynik
            # ten sam, zmienia sie tylko liczba forkow.
            if not cmd or "serve" not in cmd:
                continue
            if _is_shell_wrapper(pid):
                continue
            if _pid_is_our_hub(pid, name) and _ten_sam_home(pid):
                return pid
    return None


def _home_procesu(pid):
    """AGENTMACHI_HOME, w ktorym siedzi ten proces, albo None gdy nie wiadomo.

    Czytamy srodowisko procesu, bo w cmdline huba tej informacji nie ma
    (`serve --name X --port N --bind B`). Nieczytelne environ (cudzy
    uzytkownik, proces znikl) daje None — wolimy nie wiedziec niz zgadnac."""
    if _procfs_dostepne():
        try:
            raw = Path(f"/proc/{pid}/environ").read_bytes()
        except OSError:
            return None
        for wpis in raw.split(b"\0"):
            if wpis.startswith(b"AGENTMACHI_HOME="):
                return str(Path(wpis.split(b"=", 1)[1]
                                .decode("utf-8", "replace")))
        return str(Path.home() / ".agentmachi")
    return _home_procesu_ps(pid)


# `ps` pokazujace srodowisko ma DWIE skladnie i zadna nie dziala wszedzie:
# macOS/BSD chce `-E` (procps: "nie obsługiwana opcja SysV"), procps chce
# stylu BSD `eww` (macOS ma `e` jako modyfikator, ale mieszanie go z `-o`
# nie jest udokumentowane). Probujemy po kolei zamiast zgadywac platforme —
# ta sama zasada co `_procfs_dostepne`: pytamy o MOZLIWOSC, nie o nazwe
# systemu. Efekt uboczny jest celowy: wariant BSD dziala takze na Linuksie,
# wiec te sciezke da sie przejsc testem bez macOS.
_PS_ENVIRON = (("-E", "-ww", "-o", "command=", "-p"),
               ("eww", "-o", "command=", "-p"))

# Environ z `ps` przychodzi jako plaski tekst "cmdline KEY=VAL KEY=VAL...",
# a nie jako lista rozdzielona \0 — wartosc konczy sie dopiero przed
# nastepnym kluczem. Stad lookahead: sciezka domowa ze spacja przezyje.
_RE_HOME = re.compile(r"AGENTMACHI_HOME=(.*?)(?= [A-Za-z_][A-Za-z0-9_]*=|$)")


def _home_procesu_ps(pid):
    """`_home_procesu` bez /proc. Zwraca None takze wtedy, gdy environ jest
    NIEWIDOCZNE — a to trzeba odroznic od "zmiennej nie ma".

    Znacznikiem widocznosci jest PATH: dziedziczy go praktycznie kazdy
    proces, wiec wynik `ps` bez `PATH=` znaczy "srodowiska nie pokazano"
    (na macOS zdarza sie to dla procesow spoza naszego uid i dla binarek
    z hardened runtime), a nie "hub startowal bez PATH". Bez tego
    rozroznienia niewidoczne environ udawaloby domyslny `~/.agentmachi`
    i skan mowilby "to inna instalacja" o hubie z TEJ SAMEJ — czyli
    falszywe "zatrzymany", a to jest droga do split-brainu. Wolimy None,
    bo `_ten_sam_home` zostawia wtedy trafienie."""
    for wariant in _PS_ENVIRON:
        out = _ps(*wariant, str(pid))
        if out:
            break
    else:
        return None
    if not re.search(r"(?:^| )PATH=", out):
        return None
    trafienie = _RE_HOME.search(out)
    if trafienie:
        return str(Path(trafienie.group(1)))
    return str(Path.home() / ".agentmachi")


def _ten_sam_home(pid):
    """Czy ten proces obsluguje huby z TEGO SAMEGO katalogu, co my?

    Nazwa kanalu jest unikalna w obrebie jednej instalacji, nie na maszynie.
    Bez tej kontroli hub 'warsztat' w AGENTMACHI_HOME=/tmp/... i hub
    'warsztat' w ~/.agentmachi byly dla skanu tym samym hubem — a to dwa
    rozne huby, z osobnymi tokenami, logami i portami.

    Zmierzone: pelna suita przestawala byc zielona, gdy na maszynie chodzil
    pokoj o nazwie uzytej w tescie. Fixture przekierowuje AGENTMACHI_HOME do
    tmp_path, wiec katalogi byly rozdzielone — ale skan i tak znajdowal
    produkcyjny proces i `cmd_start` melodowal "pokoj juz dziala (PID ...)".
    Wynik suity zalezal wiec od tego, co akurat chodzi na maszynie.

    Ta sama rodzina bledu co C6: dopasowanie zbyt luzne. Tam nazwa pakietu
    przechodzila za nazwe kanalu, tu nazwa kanalu przechodzila przez granice
    instalacji.

    Gdy environ jest nieczytelny, ZOSTAJEMY przy trafieniu: skan istnieje po
    to, zeby nie kusic czlowieka do postawienia drugiego huba na tym samym
    katalogu (split-brain z F7, ktory raz zzarl nam rozmowe). Falszywe
    "dziala" jest tu tansze niz falszywe "zatrzymany"."""
    home = _home_procesu(pid)
    return home is None or home == str(hub_home())


def hub_pid(name):
    """PID zywego huba albo None. Martwy pidfile sprzatamy od razu — inaczej
    `list` klamie, ze kanal dziala. Gdy pidfile nie ma, a proces jest,
    dowiadujemy sie tego ze skanu (patrz _scan_hub_pid): lepiej powiedziec
    'dziala' bez pliku niz 'zatrzymany' o zywym hubie."""
    path = hub_dir(name) / "hub.pid"
    if not path.exists():
        return _scan_hub_pid(name)
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        path.unlink(missing_ok=True)
        return _scan_hub_pid(name)
    if _cmdline_of(pid) is None:
        path.unlink(missing_ok=True)
        return _scan_hub_pid(name)
    # UWAGA (poza zakresem F8, zgloszone osobno): nie sprawdzamy tu, czy PID
    # to NA PEWNO nasz hub. PID-y sa recyklowane, wiec nieaktualny pidfile
    # wskazujacy na cudzy zywy proces daje falszywe "dziala". `stop` jest
    # na to odporny (_pid_is_our_hub przed zabiciem), `list` jeszcze nie.
    return pid


def write_hub_pid(name):
    (hub_dir(name) / "hub.pid").write_text(str(os.getpid()), encoding="utf-8")


def hub_rows():
    """Stan wszystkich kanalow tego uzytkownika — zrodlo dla `list`."""
    home = hub_home()
    if not home.exists():
        return []
    rows = []
    for d in sorted(p for p in home.iterdir() if p.is_dir()):
        name = d.name
        if not (d / "tokens.json").exists():
            continue
        pid = hub_pid(name)
        try:
            tokens = json.loads((d / "tokens.json").read_text(encoding="utf-8"))
            nicks = sorted(tokens)
        except (json.JSONDecodeError, OSError):
            nicks = []
        rows.append({"name": name, "port": hub_port(name),
                     "bind": hub_bind(name), "pid": pid,
                     "running": pid is not None,
                     # hub bez pidfile dziala, ale `stop` nie zostawi po sobie
                     # sladu w katalogu — user ma to widziec, a nie zgadywac
                     "pidfile": (d / "hub.pid").exists(),
                     "nicks": nicks})
    return rows


def connect_host(bind):
    """Adres POLACZENIOWY != bind: bind loopback/wildcard laczy sie lokalnie
    po 'localhost' (a) zachowuje dotychczasowy hub_id 'localhost:<port>' —
    kursory zywych sesji w ~/.chat-sessions/ przezywaja upgrade (hub sprzed
    B3 ma config bez 'bind' i dostaje fallback loopback tutaj), (b) nie
    drukuje na karcie nieroutowalnego ws://0.0.0.0:... . Prawdziwy adres
    tailnetu/publiczny (np. 100.x.y.z) zostaje bez zmian."""
    return "localhost" if bind in ("127.0.0.1", "0.0.0.0", "localhost") else bind


def print_card(name, port, tokens, bind=DEFAULT_BIND):
    """Karta wejsciowa: wszystko, czego potrzebuje czlowiek i agenci."""
    d = hub_dir(name)
    addr = f"ws://{connect_host(bind)}:{port}"
    print(f"""
=== agentmachi: hub '{name}' ===
address: {addr}
tokens:  {d / 'tokens.json'}  (0600 — do not commit!)
rules:   {d / 'data' / 'rules.md'}
data:    {d / 'data'}
""")
    if bind == "0.0.0.0":
        print("warning: bound to every interface — from another host use the "
              "machine's tailnet address (see README: Remote hubs)\n")
    print("identities (config):")
    for nick, entry in tokens.items():
        role = entry.get("role", "agent")
        groups = ",".join(entry.get("groups", [])) or "-"
        line = f"  {nick}  {role}  [{groups}]"
        print(line)
    print(f"""
human (TUI):
  agentmachi tui --name {name}

agent joins (listen + send; paste one of these to an agent):
  AGENTMACHI_HUB={name} CHAT_URL={addr} CHAT_NICK=agent1 agentmachi listen
  AGENTMACHI_HUB={name} CHAT_URL={addr} agentmachi send "@agent1 hi" --as agent2
  on loopback and inside a tailnet no token is needed — the hub hands out a
  free nick itself. For a public bind (0.0.0.0) or a machine outside the
  tailnet add an entry to tokens.json first and pass CHAT_TOKEN=<that token>

sentence for an agent (join skill):
  "join agentmachi '{name}' ({addr}) as agent1"
""")


def _agent_env(args):
    """Zloz srodowisko klienta: hub z --name/AGENTMACHI_HUB, nick+token
    z tokens.json huba (CHAT_TOKEN z env wygrywa — nie wymuszamy pliku).
    CHAT_URL z env WYGRYWA NAD configiem lokalnym (fix C1 — na maszynie
    zdalnej, bez ~/.agentmachi/<hub>, ustawiamy tylko gdy env pusty;
    inaczej agent na VPS dostalby CHAT_URL z lokalnego configu i celowal
    w localhost zamiast w adres operatora). Gdy ustawiamy sami, adres to
    connect_host(bind) (NIE surowy bind — patrz connect_host:
    loopback/wildcard -> localhost, zeby hub_id agenta nie zmienial sie
    przy kazdym upgradzie/bindzie)."""
    name = args.name or os.environ.get("AGENTMACHI_HUB", DEFAULT_HUB)
    nick = getattr(args, "nick", None) or os.environ.get("CHAT_NICK") or ""
    token = os.environ.get("CHAT_TOKEN", "")
    remote = bool(os.environ.get("CHAT_URL"))
    # B6: hub ZDALNY (CHAT_URL w env) nie ma lokalnego katalogu — nie
    # ladujemy tokens.json, nie wymuszamy nicka, nie wymuszamy tokenu.
    # Tryb otwarty huba (loopback/tailnet) wpuszcza bez sekretu, a nick
    # nada sam. Token/nick bierzemy WYLACZNIE, gdy operator poda je w env.
    if not remote:
        # Bez CHAT_URL adres MUSI pochodzic z lokalnego config.json. Brak
        # pokoju to blad, nie DEFAULT_PORT — inaczej wchodzimy w cudzy pokoj
        # i meldujemy sukces (patrz join_addr).
        bind, port = join_addr(name)
        if not token:
            # Hub LOKALNY: jesli stoi w trybie otwartym, tez wejdziemy bez
            # tokenu. Tokens.json czytamy tylko, gdy istnieje i ma nasz nick
            # — w przeciwnym razie zdajemy sie na tryb otwarty.
            try:
                tokens, _ = load_tokens(name)
                if nick and nick in tokens:
                    token = tokens[nick]["token"]
            except CliError:
                pass
        os.environ["CHAT_URL"] = f"ws://{connect_host(bind)}:{port}"
    os.environ["CHAT_TOKEN"] = token
    os.environ["CHAT_NICK"] = nick
    return nick


def _import_send():
    # send.py liczy URI z env przy imporcie — env MUSI byc ustawione wczesniej
    import send
    return send


# --- tresc ze stdin: droga, ktorej powloka nie tyka ----------------------
#
# Zgloszone z Windows 11 / PowerShell, z pomiarem: tresc konczaca sie
# backslashem (`C:\Users\x\` — normalna sciezka, nie przypadek brzegowy)
# dochodzila do huba PRZEKLAMANA, exit 0, zero ostrzezen. Cudzyslow rozbijal
# argument na kilka i argparse odrzucal cala wiadomosc. Hub, protokol i CLI
# sa czyste — psuje to POWLOKA, zanim CLI cokolwiek zobaczy, wiec CLI nie ma
# tego jak wykryc. Jedyna naprawa to wejscie, ktorego powloka nie dotyka.
STDIN_ARG = "-"


def _stdin_zazadany(args, pozycyjny):
    """Czy wolajacy JAWNIE poprosil o stdin (`--stdin` albo `-` jako tresc)."""
    return bool(getattr(args, "stdin", False)) or pozycyjny == STDIN_ARG


def _czytaj_stdin(czego):
    """Wczytaj tresc ze stdin. Wolane WYLACZNIE po jawnym `-`/`--stdin`.

    NIE MA TU AUTODETEKCJI I NIE WOLNO JEJ DOPISAC. Kusi warunek
    `if not sys.stdin.isatty(): czytaj z stdin` — i to jest blad zmierzony
    na zywym srodowisku: agent headless ma stdin podpiety do /dev/null, wiec
    taki warunek idzie czytac, dostaje natychmiastowe EOF i wysyla na kanal
    PUSTA wiadomosc z exit 0. Czyli dokladnie ta cicha porazka udajaca
    sukces, przed ktora ta droga ma bronic. Zrodlo tresci wybiera argv —
    to, co wolajacy NAPISAL — a nie to, czym akurat jest deskryptor 0.

    Bajty bierzemy z `.buffer` i dekodujemy UTF-8 strict: polska powloka
    Windowsa potrafi wypchnac cp1250, a mojibake w logu huba jest
    nieodwracalne i wyglada na wine autora wiadomosci."""
    strumien = getattr(sys.stdin, "buffer", None)
    if strumien is None:            # stdin podmieniony (testy, REPL)
        tekst = sys.stdin.read()
    else:
        try:
            tekst = strumien.read().decode("utf-8")
        except UnicodeDecodeError as e:
            raise CliError(
                f"{czego} on stdin is not valid UTF-8 ({e}); nothing was "
                f"sent. Encode it as UTF-8 first — on PowerShell: "
                f"[Console]::OutputEncoding = "
                f"[System.Text.Encoding]::UTF8")
    # Jedna koncowa nowa linia to slad po `echo`/pipeline, nie tresc.
    # DOKLADNIE jedna (z CRLF-em Windowsa), zeby backslash tuz przed nia
    # przezyl, a celowa pusta linia na koncu nie zniknela.
    if tekst.endswith("\n"):
        tekst = tekst[:-1]
    if tekst.endswith("\r"):
        tekst = tekst[:-1]
    if not tekst.strip():
        raise CliError(f"empty {czego} on stdin — nothing was sent. A blank "
                       f"message would wake the addressee and carry nothing.")
    return tekst


def cmd_serve(args):
    # F7: fail-fast zamiast split-brain. Drugi `serve` na tej samej nazwie
    # nie dostanie portu (bind zawiedzie), ale ZDAZY otworzyc ten sam
    # katalog danych i pisac do tego samego events.jsonl — dwa procesy,
    # jeden log. Sprawdzamy PRZED czymkolwiek innym.
    running = hub_pid(args.name)
    # `agentmachi start` zapisuje hub.pid z PID-em procesu, ktory WLASNIE
    # tu jestesmy — wiec wlasny PID w pidfile nie oznacza "inny hub juz
    # dziala". Trzeci wariant tej samej pulapki w jednym dniu: dopasowanie
    # po argv (pkill), skan procesow, teraz pidfile.
    if running == os.getpid():
        running = None
    if running is not None and _pid_is_our_hub(running, args.name):
        print(f"agentmachi: hub {args.name!r} is already running (PID "
              f"{running}). Stop it: agentmachi stop --name {args.name}",
              file=sys.stderr)
        return 1
    # `--port` w `serve` ma default=None (nie DEFAULT_PORT), zeby dalo sie
    # odroznic "czlowiek podal port" od "nie podal" — inaczej ensure_hub
    # dostawalo tu ZAWSZE jawny port i albo zgadywalo za czlowiekiem, albo
    # odmawialo kazdemu `serve` bez portu. DEFAULT_PORT wyliczamy tu, bo to
    # domysl KOMENDY, nie decyzja uzytkownika.
    port_jawny = args.port is not None
    d, port = ensure_hub(args.name, args.port if port_jawny else DEFAULT_PORT,
                         bind=args.bind, port_jawny=port_jawny)
    bind = hub_bind(args.name, fallback=args.bind)
    write_hub_pid(args.name)
    tokens = json.loads((d / "tokens.json").read_text(encoding="utf-8"))
    print_card(args.name, port, tokens, bind=bind)
    os.environ["CHAT_TOKENS"] = str(d / "tokens.json")
    os.environ["CHAT_DATA"] = str(d / "data")
    os.environ["CHAT_PORT"] = str(port)
    os.environ["CHAT_BIND"] = bind
    from chat.server import main as server_main
    server_main()
    return 0


def cmd_list(args):
    """Co u mnie dziala? Jeden komputer = wiele kanalow na wielu portach."""
    rows = hub_rows()
    if not rows:
        print(f"no rooms in {hub_home()} — create the first one: "
              f"agentmachi start --name <name>")
        return 0
    # NIE "UCZESTNICY": ta kolumna czyta tokens.json, wiec pokazuje
    # TOZSAMOSCI, ktore pokoj zna — nie ludzi i agentow, ktorzy sa w srodku.
    # Swiezy pokoj wypisywal "agent1, agent2, human" i wygladal na zaludniony,
    # zanim ktokolwiek wszedl (zgloszone przez operatora). `list` czyta sam
    # dysk i celowo nie rusza sieci, wiec obecnosci nie zna i nie ma udawac,
    # ze zna. Kto JEST na kanale, pokazuje TUI ("(nikt nie jest online)").
    print(f"{'ROOM':<16} {'ADDRESS':<28} {'STATE':<24} IDENTITIES (config)")
    for r in rows:
        addr = f"ws://{connect_host(r['bind'])}:{r['port']}"
        if not r["running"]:
            stan = "stopped"
        elif r["pidfile"]:
            stan = f"running (PID {r['pid']})"
        else:
            stan = f"running (PID {r['pid']}, no pidfile)"
        print(f"{r['name']:<16} {addr:<28} {stan:<24} {', '.join(r['nicks'])}")
    zatrzymane = [r["name"] for r in rows if not r["running"]]
    if zatrzymane:
        # `start`, nie `serve`: serve blokuje terminal, czyli dokladnie to,
        # od czego uciekamy w komendach dla czlowieka.
        print(f"\nstopped ones you can launch: agentmachi start --name "
              f"{zatrzymane[0]}")
    return 0


def cmd_kill(args):
    """Ubij procesy pasujace do wzorca — bez zabijania samego siebie."""
    wzorzec = args.wzorzec
    swoje = _ancestor_pids()
    trafione = []
    # Kiedys chodzilo po `/proc` wprost i na macOS padalo z FileNotFoundError
    # na samym `/proc` — komenda nie dzialala tam W OGOLE, a jest to komenda
    # ratunkowa. Teraz to samo zrodlo procesow, co skan hubow.
    with _przeglad_procesow() as pidy:
        for pid in pidy:
            if pid in swoje:
                continue
            cmdline = _cmdline_of(pid)
            if cmdline and wzorzec in cmdline:
                trafione.append((pid, cmdline))

    if not trafione:
        print(f"agentmachi kill: nothing matches {wzorzec!r}")
        return 0

    for pid, cmdline in trafione:
        print(f"  {pid}  {cmdline[:100]}")
    if args.dry_run:
        print(f"(--dry-run: nothing killed; {len(trafione)} match)")
        return 0

    sig = signal.SIGKILL if args.force else signal.SIGTERM
    ubite = 0
    for pid, _ in trafione:
        try:
            os.kill(pid, sig)
            ubite += 1
        except ProcessLookupError:
            pass          # zdazyl sam sie skonczyc — nie jest bledem
        except PermissionError:
            print(f"agentmachi kill: no permission for {pid}", file=sys.stderr)
    print(f"agentmachi kill: sent {sig.name} to {ubite} "
          f"process{'' if ubite == 1 else 'es'} "
          f"(own skipped: {len(swoje)})")
    return 0


def stop_hub(name):
    """Zatrzymaj hub `name`. Zwraca (udalo_sie, komunikat) i NIC nie drukuje.

    Wydzielone z cmd_stop, zeby TUI zatrzymywalo pokoj TYM SAMYM kodem.
    Druga implementacja obok tej rozjechalaby sie przy pierwszej zmianie
    warunku bezpieczenstwa ponizej — a to on chroni przed ubiciem cudzego
    procesu po recyklowanym PID-zie."""
    pid = hub_pid(name)
    if pid is None:
        return False, f"hub {name!r} is not running"
    if not _pid_is_our_hub(pid, name):
        # Pidfile moze byc nieaktualny, a PID-y sa recyklowane przez system.
        # Lepiej odmowic i zostawic decyzje czlowiekowi niz ubic cudzy proces.
        return False, (f"PID {pid} from hub.pid does NOT look like hub "
                       f"{name!r} (cmdline: {_cmdline_of(pid)!r}) — not "
                       f"killing it. Check it yourself and remove "
                       f"{hub_dir(name) / 'hub.pid'}")
    os.kill(pid, signal.SIGTERM)
    return True, f"sent SIGTERM to hub {name!r} (PID {pid})"


def cmd_stop(args):
    if _all_kontra_name(args):
        return 1
    if getattr(args, "all", False):
        # Bez potwierdzenia, bo `stop` jest ODWRACALNY: `start` przywraca
        # historie i tokeny. Potwierdzenie przy operacji odwracalnej uczy je
        # klikac odruchowo, a wtedy przestaje dzialac tam, gdzie jest potrzebne.
        cele = _cele_all(True)
        if not cele:
            print("agentmachi: no running rooms")
            return 0
        rc = 0
        for nazwa in cele:
            ok, komunikat = stop_hub(nazwa)
            print(f"agentmachi: {komunikat}",
                  file=sys.stdout if ok else sys.stderr)
            rc = rc or (0 if ok else 1)
        return rc
    ok, komunikat = stop_hub(args.name)
    print(f"agentmachi: {komunikat}",
          file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


# --- cykl zycia dla operatora: start / stop / list / del ----------------
# Czlowiek ma odpalac i moderowac pokoje, a nie pamietac zaklec powloki.
# Do dzis start w tle wymagal recznego `setsid nohup ... & disown` — cztery
# razy dyktowanego przez czat, raz wklejonego w zlej kolejnosci (skonczylo
# sie split-brainem). Prompt musi wrocic do czlowieka, a adres ma byc na
# ekranie.

def _spawn_detached(argv, log_path):
    """Odpal proces w tle, odpiety od terminala. Zwraca PID."""
    with open(log_path, "a") as log:
        proc = subprocess.Popen(
            argv, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
            start_new_session=True)
    return proc.pid


def _port_accepts(port, bind):
    """Czy cos przyjmuje polaczenia na tym porcie NA TYM INTERFEJSIE.

    Zakres jest wezszy, niz brzmial poprzedni opis ("czy cokolwiek przyjmuje
    polaczenia na tym porcie") i ta roznica jest widoczna golym okiem:
    sprawdzamy WYLACZNIE `connect_host(bind)`, wiec hub sluchajacy na adresie
    tailnetu (100.x.y.z:8766) NIE zostanie tu wykryty przy pytaniu o
    127.0.0.1:8766 — i odwrotnie.

    Zachowanie jest poprawne, bo pytamy o to, czy uda sie zbindowac TAM, gdzie
    zamierzamy; dwa gniazda na tym samym porcie i roznych interfejsach
    wspolistnieja legalnie. Falszywy byl OPIS, i tylko on sie zmienia.

    Druga zapora — i to ona lapie cudze pokoje — jest w `_porty_innych_hubow`:
    czyta configi z `AGENTMACHI_HOME`, wiec dziala niezaleznie od interfejsu.
    Uwaga przy diagnostyce: w IZOLOWANYM `AGENTMACHI_HOME` (testy, repro) ta
    zapora nie widzi pokojow operatora, wiec swiezy pokoj potrafi wziac port
    zajety przez zywy hub na innym interfejsie. To artefakt izolacji, nie
    dziura w produkcie — zmierzone 2026-08-06, gdy wygladalo dokladnie
    odwrotnie."""
    try:
        with socket.create_connection((connect_host(bind), port), timeout=0.5):
            return True
    except OSError:
        return False


READY_MARK = "chat server on"     # linia, ktora wypisuje NASZ serwer


def _wait_until_listening(timeout=10.0, pid=None,
                          log_path=None, log_from=0):
    """Czekaj, az NASZ hub potwierdzi start WLASNYM glosem.

    KRYTYCZNE: fakt, ze port odpowiada, NIC nie dowodzi — moze go trzymac
    cudzy proces. Zdarzylo sie naprawde: nowy pokoj dostal domyslny port
    zajety przez inny serwer, nasze dziecko padlo z 'Address already in use',
    a `start` zameldowal sukces, bo polaczyl sie z TAMTYM nasluchem i wypisal
    PID trupa. Sprawdzanie samego zycia procesu tez nie wystarcza: dziecko
    zyje jeszcze przez chwile po spawnie, wiec wyscig wraca.

    Dowodem startu jest wiec linia w NASZYM logu (`chat server on ...`),
    ktora wypisuje wylacznie nasz proces po udanym bindzie.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if log_path is not None and Path(log_path).exists():
            with open(log_path) as f:
                f.seek(log_from)
                if READY_MARK in f.read():
                    return True
        if pid is not None and _cmdline_of(pid) is None:
            return False           # dziecko padlo, a linii nie ma
        time.sleep(0.15)
    return False


def _start_all(args):
    """Odpal wszystkie ZATRZYMANE pokoje — odwrotny cel niz `stop`/`restart`.

    Symetria, o ktora poprosil operator 2026-08-13: „start --all startuje te,
    ktore nie sa started; restart te, ktore sa; stop te, ktore sa". Dzialajacy
    pokoj NIE jest tu bledem i nie przerywa petli — `--all` ma doprowadzic do
    stanu „wszystko chodzi", a on juz w nim jest.

    Petla idzie dalej mimo bledu pojedynczego pokoju i dopiero na koncu zwraca
    niezero. Inaczej jeden zajety port zatrzymywalby start calej reszty, a to
    jest dokladnie odwrotnosc tego, po co czlowiek pisze `--all`.
    """
    cele = _cele_all(False)
    if not cele:
        print("agentmachi: no stopped rooms — everything is already running")
        return 0
    rc = 0
    for nazwa in cele:
        rc = cmd_start(argparse.Namespace(
            name=nazwa, port=None, bind=None, all=False)) or rc
    return rc


def cmd_start(args):
    if _all_kontra_name(args):
        return 1
    if getattr(args, "all", False):
        return _start_all(args)
    running = hub_pid(args.name)
    if running is not None and _pid_is_our_hub(running, args.name):
        print(f"agentmachi: room {args.name!r} is already running "
              f"(PID {running}).\n"
              f"  stop it:  agentmachi stop --name {args.name}\n"
              f"  see it:   agentmachi card --name {args.name}",
              file=sys.stderr)
        return 1
    # Port sprawdzamy PRZED ensure_hub: nieudany start nie moze zostawic
    # pokoju-widma, ktory potem straszy w `list`. Jawny --port ma tez
    # pierwszenstwo nad configem istniejacego pokoju — inaczej pokoj zapisany
    # przy nieudanej probie zostawal na trwale przypiety do zajetego portu
    # i rada "wybierz inny port" nie dzialala (pulapka bez wyjscia).
    istnieje = (hub_dir(args.name) / "config.json").exists()
    port = args.port if args.port is not None else hub_port(args.name)
    bind = args.bind if args.bind is not None else hub_bind(args.name)
    if _port_accepts(port, bind):
        # NOWY pokoj bez jawnego --port sam przesuwa sie w gore: czlowiek nie
        # wskazal adresu, wiec zaden kursor ani zadna wklejona karta jeszcze
        # go nie zna. Fail-fast zostaje w dwoch przypadkach, gdzie adres jest
        # juz czyjas umowa: pokoj ISTNIEJACY (kursory klientow sa per
        # host:port — przesuniecie znaczy pusty log pod znanym adresem)
        # i jawne --port (decyzja czlowieka, nie zgadujemy za niego).
        wybrany = None
        if not istnieje and args.port is None:
            wybrany = _wybierz_port_zywy(port, args.name, bind)
        if wybrany is None:
            print(f"agentmachi: port {port} is already taken by another "
                  f"process — room {args.name!r} has nothing to start on.\n"
                  f"  check whose port it is:  "
                  f"{_podpowiedz_kto_ma_port(port)}\n"
                  f"  or pick another one:     agentmachi start --name "
                  f"{args.name} --port <other>", file=sys.stderr)
            return 1
        print(f"agentmachi: port {port} is taken — room {args.name!r} "
              f"gets {wybrany}", file=sys.stderr)
        port = wybrany
    # Ta sama decyzja idzie DO ensure_hub, nie tylko do gornej galezi: bez
    # tego argumentu warstwa nizej przesuwala jawny port mimo fail-fastu tuz
    # wyzej (agent prosil o 8790, dostawal 8791, exit 0).
    d, port = ensure_hub(args.name, port, bind=bind,
                         port_jawny=args.port is not None)
    if istnieje and args.port is not None and hub_port(args.name) != args.port:
        # Przepiecie ISTNIEJACEGO pokoju to drugie wejscie do tej samej
        # decyzji co w `ensure_hub` — i przez pol dnia jedyne niestrzezone.
        # `ensure_hub` dla istniejacego pokoju swiadomie zachowuje stary port
        # i kolizji nie sprawdza, wiec ten blok nadpisywal config zyczeniem
        # uzytkownika bez zadnej kontroli: `owner` 8790 + `stary` 8795 ->
        # `start --name stary --port 8790` konczylo sie `rc=0, owner=8790,
        # stary=8790`. Odmawiamy PRZED zapisem, wiec configi OBU pokoi
        # zostaja nietkniete.
        _odmow_zajetego_portu(args.name, args.port,
                              f"room {args.name!r} keeps its port "
                              f"{hub_port(args.name)} and was NOT moved.")
        config = d / "config.json"
        dane = json.loads(config.read_text(encoding="utf-8"))
        dane["port"] = args.port
        config.write_text(json.dumps(dane), encoding="utf-8")
        port = args.port
    if args.bind is not None and hub_bind(args.name) != args.bind:
        # Blizniaczej kontroli tu NIE MA i nie jest potrzebna: rezerwacja
        # w `_porty_hubow` jest kluczowana SAMYM portem (bindu nie czyta),
        # a ten blok portu nie rusza. Przepiecie bindu nie moze wiec stworzyc
        # kolizji, ktorej nie byloby juz przed nim. Gdyby kiedys rezerwacja
        # stala sie para (bind, port), to miejsce trzeba dopisac.
        config = d / "config.json"
        dane = json.loads(config.read_text(encoding="utf-8"))
        dane["bind"] = args.bind
        config.write_text(json.dumps(dane), encoding="utf-8")
        bind = args.bind
    log_path = d / "serve.log"
    argv = [sys.executable, "-m", "agentmachi.cli", "serve",
            "--name", args.name, "--port", str(port), "--bind", bind]
    log_before = log_path.stat().st_size if log_path.exists() else 0
    pid = _spawn_detached(argv, log_path)
    if not _wait_until_listening(10.0, pid=pid,
                                 log_path=log_path, log_from=log_before):
        # pidfile NIE powstaje przy nieudanym starcie — martwy plik klamalby
        # potem `list` i `stop`.
        powod = ""
        if log_path.exists():
            with log_path.open(encoding="utf-8") as f:
                f.seek(log_before)
                ogon = f.read().strip().splitlines()
            if ogon:
                powod = "\n  reason: " + "\n          ".join(ogon[-3:])
        print(f"agentmachi: room {args.name!r} did NOT come up.{powod}\n"
              f"  full log: {log_path}\n"
              f"  is port {port} free:  agentmachi list", file=sys.stderr)
        return 1
    (d / "hub.pid").write_text(str(pid), encoding="utf-8")
    tokens = json.loads((d / "tokens.json").read_text(encoding="utf-8"))
    print_card(args.name, port, tokens, bind=bind)
    # NIE "kto jest w srodku: list". `list` czyta sam dysk i zna wylacznie
    # tozsamosci z configu — obecnosc widzi tylko TUI, ktore trzyma polaczenie.
    print(f"room runs in the background (PID {pid}), log: {log_path}\n"
          f"  who IS on the channel:  agentmachi tui --name {args.name}\n"
          f"  which rooms exist:      agentmachi list\n"
          f"  stop it:                agentmachi stop --name {args.name}")
    return 0


def cmd_restart(args):
    """Jeden czasownik zamiast trzech komend. Restart to najczestsza operacja
    operatora (nowy nick w tokens.json, nowy kod, zawieszony proces), a do
    dzis wymagal sekwencji stop -> start -> list, dyktowanej przez czat.
    Czekamy, az stary proces NAPRAWDE zejdzie — inaczej `start` zobaczy
    wlasny, jeszcze zajety port i odmowi."""
    if _all_kontra_name(args):
        return 1
    if getattr(args, "all", False):
        # Cele liczone RAZ, na poczatku: inaczej pokoj zatrzymany w polowie
        # petli przez kogos innego zostalby wciagniety do restartu, czyli
        # `restart --all` potrafilby URUCHOMIC cos, co bylo wylaczone.
        cele = _cele_all(True)
        if not cele:
            print("agentmachi: no running rooms")
            return 0
        rc = 0
        for nazwa in cele:
            rc = cmd_restart(argparse.Namespace(
                name=nazwa, port=None, bind=None, all=False)) or rc
        return rc
    # Kolizje portu rozstrzygamy PRZED `os.kill`, nie po. Kolejnosc jest tu
    # calym sensem: `cmd_start` ponizej i tak odmowi, gdy zadany port trzyma
    # inny pokoj — ale wtedy ten pokoj jest juz UBITY, wiec komenda, ktora
    # niczego nie zmienila, zostawia operatora z zatrzymanym hubem. "Chcialem
    # przepiac, dostalem martwy pokoj" to nie jest odmowa, tylko szkoda
    # wyrzadzona przy okazji.
    #
    # Zgloszone przez subagenta jako znane ograniczenie wlasnej naprawy
    # (2026-08-06) — czyli dokladnie ten przypadek, w ktorym latwo powiedziec
    # "poprawne, bo nic nie kradnie" i zostawic. Nie kradnie. Po prostu placi
    # za odmowe cudzym dzialajacym pokojem.
    if getattr(args, "port", None) is not None:
        _odmow_zajetego_portu(
            args.name, args.port,
            f"room {args.name!r} was NOT restarted and keeps running")
    pid = hub_pid(args.name)
    if pid is not None and _pid_is_our_hub(pid, args.name):
        os.kill(pid, signal.SIGTERM)
        print(f"agentmachi: stopping room {args.name!r} (PID {pid})...")
        deadline = time.monotonic() + STOP_WAIT
        while time.monotonic() < deadline:
            if _cmdline_of(pid) is None:
                break
            time.sleep(0.2)
        else:
            print(f"agentmachi: room {args.name!r} did not go down within "
                  f"{STOP_WAIT:.0f}s (PID {pid}) — not starting a new one, so "
                  f"there are never two hubs on one directory.\n"
                  f"  finish it off by hand:  kill -9 {pid}\n"
                  f"  then:                   agentmachi start --name "
                  f"{args.name}", file=sys.stderr)
            return 1
        (hub_dir(args.name) / "hub.pid").unlink(missing_ok=True)
    else:
        print(f"agentmachi: room {args.name!r} was not running — starting it")
    return cmd_start(args)


def wait_until_down(pid, timeout=STOP_WAIT):
    """Czekaj, az proces `pid` zniknie. True = zszedl, False = wisi.

    Wydzielone z cmd_restart, bo `/kill` w TUI potrzebuje dokladnie tego
    samego: skasowanie katalogu pod zywym hubem zostawiloby proces bez
    danych, piszacy do nieistniejacej sciezki."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _cmdline_of(pid) is None:
            return True
        time.sleep(0.2)
    return _cmdline_of(pid) is None


def _nicki_pokoju(name):
    """Kazdy nick, ktory ten pokoj zna: tokens.json + snapshot rejestru +
    hello z logu eventow. Uzywane WYLACZNIE do sprzatania kursorow.

    Trzy zrodla, bo kazde samo ma dziure: w tokens.json nie ma nikogo, kto
    wszedl bez tokenu (a w swiezym pokoju to wszyscy agenci); w snapshocie
    nie ma nikogo, kto wszedl PO nim — a hub, ktory padl bez `stop`, nie
    zdazyl dopisac swojego. Zostaje events.jsonl, gdzie hello jest zawsze.
    Nick pominiety tutaj zostawia po sobie kursor, ktory wybuchnie dopiero
    pod NASTEPNYM hubem na tym porcie ("last_seq N > serwerowy last_seq 0")
    — czyli w miejscu bez zwiazku z przyczyna."""
    d = hub_dir(name)
    nicki = set()
    try:
        nicki |= set(json.loads((d / "tokens.json").read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    try:
        stan = json.loads((d / "data" / "snapshot.json").read_text(encoding="utf-8"))
        gen = stan.get("state", {}).get("registry", {}).get("gen", {})
        if isinstance(gen, dict):
            nicki |= {n for n in gen if isinstance(n, str) and n}
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    try:
        with open(d / "data" / "events.jsonl", encoding="utf-8") as f:
            for linia in f:
                linia = linia.strip()
                if not linia:
                    continue
                try:
                    event = json.loads(linia)
                except json.JSONDecodeError:
                    continue      # ogon ucieciy crashem — reszta logu jest wazna
                if not isinstance(event, dict):
                    continue
                for klucz in ("from", "target"):
                    kto = event.get(klucz)
                    if isinstance(kto, str) and kto and kto != "server":
                        nicki.add(kto)
    except OSError:
        pass
    return nicki


def _pisownie_adresu(name):
    """ZNANE hub_id, pod ktorymi mogly powstac kursory TEGO pokoju.

    Kursor jest kluczowany stringiem `host:port`, ktorym klient sie DOBIL,
    a nie nazwa pokoju — i te dwie rzeczy rozjezdzaja sie legalnie, bo
    jeden hub slucha pod wiecej niz jedna nazwa (bind z configu, forma
    polaczeniowa z `connect_host`, loopback wpisany recznie).

    Zmierzone przez operatora 2026-08-10: `del test_agentmachi` (bind
    tailnetowy) zabral dziewiec plikow dla `100.84.163.11:8766`, a kursor
    `localhost:8766` przezyl, przechwycil nastepny pokoj na tym porcie
    i wywalil mu wejscie komunikatem `last_seq 92 > server last_seq 0`.

    **Skad sie wzial:** operator potwierdza, ze pokoj byl restartowany, a kod
    daje na to mechanizm — `cmd_restart` konczy sie `return cmd_start(args)`,
    wiec `restart --bind X` PRZEPISUJE config przed startem. Adres
    polaczeniowy pokoju zmienia sie wtedy w locie, a kursory sprzed i po
    ladują pod roznymi kluczami, choc pokoj jest ten sam. Zwykly `restart`
    bez argumentow zachowuje zapisany bind i tego nie robi — **jesli restart
    szedl bez zmiany bindu, mechanizm zostaje nadal otwarty.**

    Opis tego miejsca zmienial sie dwa razy i warto wiedziec dlaczego.
    Najpierw wskazywal `_tui_env` ("TUI laczy sie fallbackiem przez
    localhost") — obalone: dzisiejszy `_tui_env` bierze `CHAT_URL` z
    `connect_host(bind)`, wiec TUI pokoju tailnetowego celuje w tailnet.
    Potem mowil "NIE JEST USTALONE" — i to bylo uczciwe dopoki nie doszlo
    swiadectwo operatora. Pomiar (kursor istnial) byl prawdziwy przez caly
    czas; zmienialo sie wylacznie to, co doklejalismy jako przyczyne.

    Lista jest BEST-EFFORT i tak trzeba ja czytac. `_slug` jest hashem
    jednokierunkowym, a plik sesji nie zapisuje adresu, wiec z samego dysku
    nie da sie odzyskac, pod jakim stringiem powstal dany kursor —
    wyliczamy wiec ZNANE pisownie, nie wszystkie mozliwe. Kursor zalozony
    przez klienta z jawnym `CHAT_URL` na jeszcze inna nazwe tego samego
    hosta zostanie na dysku; to jest znany dlug, nie przeoczenie.

    Surowy `hub_bind` jest na liscie osobno, bo `connect_host` GUBI go dla
    bindu wildcard: `0.0.0.0` mapuje sie na `localhost`, wiec bez tego
    wpisu kursor zalozony dosłownie na `0.0.0.0:<port>` przezywalby pokoj.

    Bezpieczenstwo: `localhost:<port>` nie moze nalezec do innego
    ZARZADZANEGO pokoju, bo `_odmow_zajetego_portu` nie pozwala dwom
    pokojom w tym samym `AGENTMACHI_HOME` trzymac jednego portu. Poza ta
    granica (inny AGENTMACHI_HOME, proces spoza CLI) kolizja jest mozliwa
    i tego ta funkcja nie rozstrzyga."""
    port = hub_port(name)
    bind = hub_bind(name)
    hosty = [connect_host(bind), bind, "localhost", "127.0.0.1"]
    widziane, out = set(), []
    for host in hosty:
        hub = f"{host}:{port}"
        if hub not in widziane:
            widziane.add(hub)
            out.append(hub)
    return out


def purge_cursors(name):
    """Skasuj kursory klientow tego pokoju. Zwraca liczbe usunietych plikow.

    Kursor klienta jest per host:port, a port po skasowanym pokoju wraca do
    puli — wiec kursor, ktory przezyl swoj log, trafia na NASTEPNY hub pod
    tym adresem i wywala go komunikatem "last_seq N > serwerowy last_seq 0".
    Zmierzone trzy razy: 2026-07-26 na zywym pokoju, raz przez operatora
    przy pierwszym uruchomieniu po sprzataniu i 2026-08-10 — ten ostatni raz
    juz PO tej funkcji, bo kasowala tylko jedna pisownie adresu (patrz
    `_pisownie_adresu`).

    Wolane z delete_hub PRZED rmtree — po nim nie ma juz skad wziac nickow."""
    if not hub_istnieje_lokalnie(name):
        # Pokoj bez config.json nie ma adresu, a zgadniety DEFAULT_PORT
        # wskazywalby kursory CUDZEGO pokoju stojacego na tym porcie —
        # skasowalibysmy komus zywy kursor przy sprzataniu po sobie. Lepiej
        # zostawic wlasne smieci niz ruszyc nie swoje.
        return 0
    usuniete = 0
    for nick in _nicki_pokoju(name):
        for hub in _pisownie_adresu(name):
            usuniete += purge_session_files(hub, nick)
    return usuniete


def delete_hub(name, confirm):
    """Skasuj pokoj NA ZAWSZE. Zwraca (udalo_sie, komunikat), nic nie drukuje.

    Potwierdzeniem jest POWTORZONA NAZWA, nie flaga `--force`/`--yes`: flage
    dopisuje sie odruchowo, a nazwe trzeba przeczytac. Kolejnosc kontroli
    (istnieje -> dziala -> potwierdzenie) jest zachowana z cmd_del, bo od niej
    zalezy, ktory blad czlowiek zobaczy najpierw."""
    d = hub_dir(name)
    if not d.exists():
        return False, f"room {name!r} does not exist"
    running = hub_pid(name)
    if running is not None and _pid_is_our_hub(running, name):
        return False, (f"room {name!r} is RUNNING (PID {running}) — "
                       f"first: agentmachi stop --name {name}")
    if confirm != name:
        return False, (f"this deletes room {name!r} FOREVER "
                       f"(tokens, rules, howto, the whole conversation "
                       f"history).\n"
                       f"  if you are sure:  agentmachi del --name {name} "
                       f"--yes-delete {name}")
    # Kursory PRZED rmtree — potem nie ma juz skad wziac nickow pokoju.
    kursory = purge_cursors(name)
    shutil.rmtree(d)
    ogon = f" (+ {kursory} cursor files)" if kursory else ""
    return True, f"room {name!r} deleted{ogon}"


def _cele_all(dzialajace):
    """Nazwy pokoi w zadanym stanie, w kolejnosci z `hub_rows()`.

    Jedno zrodlo dla `--all` i dla `list`, zeby czlowiek nie mogl zobaczyc
    w jednym czegos innego niz w drugim. Prosba operatora 2026-08-13.
    """
    return [r["name"] for r in hub_rows() if bool(r["running"]) is dzialajace]


def _all_kontra_name(args):
    """`--all` razem z jawnym `--name` to ODMOWA, nie zgadywanie.

    Dwa sprzeczne wskazania celu przy komendzie, ktora potrafi byc
    nieodwracalna. Zgadywanie, ktore wygrywa, jest tu gorsze niz blad.
    """
    if getattr(args, "all", False) and args.name != DEFAULT_HUB:
        print(f"agentmachi: --all and --name {args.name!r} contradict each "
              f"other; pick one", file=sys.stderr)
        return True
    return False


def _del_all(args):
    """Skasuj WSZYSTKIE zatrzymane pokoje. Dzialajacych nie tyka.

    Potwierdzeniem jest LICZBA, nie flaga — z tego samego powodu, dla ktorego
    przy jednym pokoju jest nim nazwa (`delete_hub`): flage dopisuje sie
    odruchowo. Liczba ma nad stalym slowem przewage, ktora jest calym sensem
    tego wyboru: WIAZE SIE ZE STANEM. Gdy miedzy `list` a ta komenda pojawi
    sie nowy pokoj, liczba przestaje pasowac i czlowiek dostaje odmowe zamiast
    cichego skasowania czegos, czego nie widzial.
    """
    zatrzymane = _cele_all(False)
    dzialajace = _cele_all(True)
    if not zatrzymane:
        print("agentmachi: no stopped rooms to delete")
        if dzialajace:
            print(f"agentmachi: still running (untouched): "
                  f"{', '.join(dzialajace)}")
        return 0
    if args.confirm_all != len(zatrzymane):
        print(f"this deletes {len(zatrzymane)} room(s) FOREVER (tokens, "
              f"rules, howto, the whole conversation history):",
              file=sys.stderr)
        for nazwa in zatrzymane:
            print(f"  {nazwa}", file=sys.stderr)
        if dzialajace:
            print(f"running rooms are NOT touched: "
                  f"{', '.join(dzialajace)}", file=sys.stderr)
        print(f"  if you are sure:  agentmachi del --all --yes-delete-all "
              f"{len(zatrzymane)}", file=sys.stderr)
        return 1
    rc = 0
    for nazwa in zatrzymane:
        ok, komunikat = delete_hub(nazwa, nazwa)
        print(f"agentmachi: {komunikat}",
              file=sys.stdout if ok else sys.stderr)
        rc = rc or (0 if ok else 1)
    if dzialajace:
        # NIE po cichu: milczenie znaczyloby dla czlowieka "skasowalem
        # wszystko", a to nieprawda.
        print(f"agentmachi: left running, not deleted: "
              f"{', '.join(dzialajace)}")
    return rc


def cmd_del(args):
    """Skasuj pokoj. Nieodwracalne: znikaja tokeny, rules, howto i log."""
    if _all_kontra_name(args):
        return 1
    if getattr(args, "all", False):
        return _del_all(args)
    ok, komunikat = delete_hub(args.name, args.confirm)
    print(f"agentmachi: {komunikat}",
          file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


def cmd_card(args):
    name = args.name or os.environ.get("AGENTMACHI_HUB", DEFAULT_HUB)
    tokens, d = load_tokens(name)
    # Karta niesie zdanie DO WKLEJENIA agentowi — zgadniety adres rozsialby
    # blad dalej, na kazdego, kto ta karte dostanie.
    bind, port = join_addr(name)
    print_card(name, port, tokens, bind=bind)
    return 0


def _tui_env(name):
    """Zloz srodowisko TUI (wydzielone z cmd_tui — testowalne bez Textuala).
    I3 fix: CHAT_URL musi isc z bindu huba (connect_host(hub_bind(name))),
    nie tylko CHAT_PORT — inaczej tui.py fallbackuje do ws://localhost i
    nie polaczy sie z hubem bindowanym na adres tailnetowy. Env CHAT_URL
    WYGRYWA nad configiem lokalnym (symetrycznie do C1 w _agent_env)."""
    tokens_path = hub_dir(name) / "tokens.json"
    if not tokens_path.exists():
        raise CliError(f"hub {name!r} does not exist; first run: "
                       f"agentmachi start --name {name}")
    os.environ["AGENTMACHI_TOKENS"] = str(tokens_path)
    # TUI musi wiedziec, KTORYM pokojem jest — inaczej nie ma czego
    # zatrzymac. Adres (CHAT_URL) nie wystarcza: cykl zycia huba jest
    # nazwany (start/stop/del biora --name), a `~/.agentmachi/<nazwa>/`
    # jest jedynym miejscem z pidfile.
    os.environ["AGENTMACHI_HUB"] = name
    bind, port = join_addr(name)
    os.environ["CHAT_PORT"] = str(port)
    if not os.environ.get("CHAT_URL"):
        os.environ["CHAT_URL"] = f"ws://{connect_host(bind)}:{port}"
    return tokens_path


def cmd_tui(args):
    name = args.name or os.environ.get("AGENTMACHI_HUB", DEFAULT_HUB)
    _tui_env(name)
    import tui
    return tui.main()


def cmd_send(args):
    # Tresc ma DOKLADNIE jedno zrodlo i wybiera je argv: argument albo stdin
    # (`-` / `--stdin`). Gdy padly oba naraz, odmawiamy zamiast po cichu
    # wybierac jedno — cichy wybor to ta sama klasa bledu, ktora ta droga
    # naprawia: wysylajacy widzi exit 0 i nie wie, ktora wersje dostal kanal.
    ze_stdin = _stdin_zazadany(args, args.text)
    tekst = None if args.text == STDIN_ARG else args.text
    if ze_stdin and (tekst is not None or args.legacy_text is not None):
        podany = tekst if tekst is not None else args.legacy_text
        print(f"agentmachi send: the text was given TWICE — as an argument "
              f"({podany!r}) and via --stdin/-. Pick ONE source; nothing was "
              f"sent.", file=sys.stderr)
        return 2
    # C3: dwa pozycyjne argumenty = dawna skladnia `send <nick> "tekst"`,
    # w ktorej <nick> byl NADAWCA, choc czytal sie jak adresat. Fail-closed
    # z instrukcja zamiast wyslania w cudzym imieniu.
    if getattr(args, "legacy_text", None) is not None:
        print(f"agentmachi send: you passed TWO arguments "
              f"({args.text!r}, {args.legacy_text!r}).\n"
              f"The old syntax `send <nick> \"text\"` was removed: <nick> was "
              f"the SENDER while it read like the addressee — in practice it "
              f"cost a frame sent under someone else's name.\n"
              f"Now:\n"
              f"  agentmachi send --as {args.text} \"@someone "
              f"{args.legacy_text}\""
              f"   # who you are -> --as, who you talk to -> @mention\n"
              f"  CHAT_NICK={args.text} agentmachi send \"@someone "
              f"{args.legacy_text}\"", file=sys.stderr)
        return 2
    if not ze_stdin and tekst is None:
        print("agentmachi send: I do not know WHAT to send. Give the text as "
              "an argument, or read it from stdin with --stdin (or `-`) — a "
              "path the shell never touches:\n"
              "  agentmachi send \"@someone text\" --as <nick>\n"
              "  cat report.md | agentmachi send - --as <nick>\n"
              "stdin is NEVER read on its own: a headless agent has it on "
              "/dev/null, so guessing would publish an empty message.",
              file=sys.stderr)
        return 2
    args.nick = args.as_nick          # _agent_env czyta args.nick
    nick = _agent_env(args)
    if not nick:
        print("agentmachi send: I do not know WHO you are — pass --as <nick> "
              "or set CHAT_NICK. You point at the addressee with an @mention "
              "in the text.", file=sys.stderr)
        return 2
    if ze_stdin:
        # Czytamy DOPIERO tu: gdyby wczesniej odbila sie tozsamosc, tresc
        # bylaby juz zjedzona ze strumienia i nie dalo sie ponowic bez
        # wpisania jej drugi raz.
        try:
            tekst = _czytaj_stdin("message")
        except CliError as e:
            print(f"agentmachi send: {e}", file=sys.stderr)
            return 2
    send = _import_send()
    try:
        asyncio.run(send.send_once(nick, tekst,
                                   quiet=getattr(args, "quiet", False)))
    except send.SessionError as e:
        # Dwa rozne przypadki, oba niezerowo i oba jedna czytelna linia:
        # (a) kontrakt klienta zlamany PRZED drutem (np. ramka ponad sufit
        #     huba) — ramki NIE MA w logu;
        # (b) `WysylkaNieznana` — transport padl w oknie ostrzezen, wiec nie
        #     wiadomo, czy ramka jest w logu. Kod jest ten sam, bo exit 0
        #     znaczylby "sprawdzilem i bylo dobrze"; roznice niesie TRESC,
        #     ktora w (b) mowi wprost, ze to nie jest raport o porazce.
        # Czytelna linia zamiast tracebacku: odbiorca tego komunikatu to agent,
        # ktory ma z niego wyciagnac, co zrobic inaczej — stos wywolan mu w tym
        # nie pomaga, tylko zjada kontekst.
        print(f"agentmachi send: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_listen(args):
    # nick moze byc pusty — wtedy hub nada go sam (B6). NIE podstawiamy
    # "listener": to psulo i wybor wlasnej nazwy (--nick banan), i
    # przydzial przez huba (dostawales "listener" zamiast worker5).
    nick = _agent_env(args)
    send = _import_send()
    asyncio.run(send.listen(
        nick,
        context="fresh" if getattr(args, "fresh", False) else None,
        once=getattr(args, "once", False),
        as_json=getattr(args, "json", False)))
    return 0


def cmd_read(args):
    """Odczyt logu kanalu przez drut — patrz send.read_frames.

    Istnieje, bo agent na ZDALNYM hubie nie mial zadnej drogi do wlasnej
    ramki: serwer tlumi echo po nicku, kursor nasluchu przeskakuje za nia,
    a `events.jsonl` ma wylacznie operator huba. Zmierzone 2026-08-06 —
    agent musial prosic czlowieka o zajrzenie w TUI, zeby zweryfikowac
    WLASNY dowod."""
    # Zakres ma DOKLADNIE jedno zrodlo i wybiera je argv (wzorzec z cmd_send).
    # Cichy wybor jednego z dwoch bylby ta sama klasa bledu, ktora ta komenda
    # naprawia: wolajacy dostaje wynik i nie wie, o co zapytal.
    if args.seq is not None and args.from_seq is not None:
        print(f"agentmachi read: --seq ({args.seq}) and --from-seq "
              f"({args.from_seq}) were given TOGETHER. Pick ONE — --seq asks "
              f"for a single frame, --from-seq for everything from there up. "
              f"Nothing was read.", file=sys.stderr)
        return 2
    if args.seq is None and args.from_seq is None:
        print("agentmachi read: I do not know WHAT to read.\n"
              "  agentmachi read --seq 731        # exactly that one frame\n"
              "  agentmachi read --from-seq 700   # everything from seq 700 "
              "up\n"
              "`seq` is assigned by the server and you see it at the start of "
              "every `agentmachi listen` line.", file=sys.stderr)
        return 2
    nick = _agent_env(args)
    if not nick:
        print("agentmachi read: I do not know WHO you are — pass --nick "
              "<nick> or set CHAT_NICK. read enters with the identity from "
              "your session file, exactly so that it does NOT take over your "
              "own `agentmachi listen`.", file=sys.stderr)
        return 2
    send = _import_send()
    from_seq = args.seq if args.seq is not None else args.from_seq
    try:
        asyncio.run(send.read_frames(nick, from_seq, only_seq=args.seq))
    except send.SessionError as e:
        # Ta sama granica co w cmd_send/cmd_frame: jedna czytelna linia dla
        # agenta zamiast stosu wywolan, ktory zjada mu kontekst i niczego nie
        # mowi o tym, co zrobic inaczej.
        print(f"agentmachi read: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"agentmachi read: cannot reach the hub at "
              f"{os.environ.get('CHAT_URL', '?')}: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_board(args):
    """Kto jest na kanale — patrz send.read_board.

    Istnieje, bo board dociera do agenta WYLACZNIE w `session_metadata`,
    a filtr nasluchu musi te ramke ciac po typie (bez tego howto w jej
    srodku przebija filtr wzmianek). Jedyna droga do boardu byla wiec
    ponowne wejscie na kanal — okolo 5k tokenow za odpowiedz na pytanie
    "kto tu jest"."""
    nick = _agent_env(args)
    if not nick:
        print("agentmachi board: I do not know WHO you are — pass --nick "
              "<nick> or set CHAT_NICK. board enters with the identity from "
              "your session file, exactly so that it does NOT take over your "
              "own `agentmachi listen`.", file=sys.stderr)
        return 2
    send = _import_send()
    try:
        asyncio.run(send.read_board(nick, as_json=args.json))
    except send.SessionError as e:
        # Ta sama granica co w cmd_read: jedna czytelna linia zamiast stosu.
        print(f"agentmachi board: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"agentmachi board: cannot reach the hub at "
              f"{os.environ.get('CHAT_URL', '?')}: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_frame(args):
    # Ten sam kontrakt co w cmd_send, a powod jeszcze mocniejszy: JSON JEST
    # z cudzyslowow, wiec cytowanie powloki boli tu podwojnie (w apostrofach
    # PowerShell zjada `"` i agent wysyla niepoprawny JSON).
    ze_stdin = _stdin_zazadany(args, args.json)
    surowy = None if args.json == STDIN_ARG else args.json
    if ze_stdin and surowy is not None:
        raise CliError(f"the frame was given TWICE — as an argument "
                       f"({surowy!r}) and via --stdin/-. Pick ONE source; "
                       f"nothing was sent.")
    if not ze_stdin and surowy is None:
        raise CliError("frame needs the JSON: pass it as an argument or read "
                       "it from stdin with --stdin (or `-`). stdin is NEVER "
                       "read on its own — guessing would send an empty frame.")
    nick = _agent_env(args)
    if not nick:
        raise CliError("frame requires a nick (--nick or CHAT_NICK)")
    if ze_stdin:
        surowy = _czytaj_stdin("frame JSON")
    try:
        frame = json.loads(surowy)
    except json.JSONDecodeError as e:
        raise CliError(f"bad frame JSON: {e}")
    if not isinstance(frame, dict) or not frame.get("type"):
        raise CliError("frame must be an object with a type field")
    send = _import_send()
    try:
        reply = asyncio.run(send.oneshot_frame(nick, frame))
    except send.SessionError as e:
        # ta sama granica co w cmd_send: kontrakt klienta zlamany PRZED drutem
        # (np. ramka ponad sufit) ma wyjsc jedna czytelna linia, nie stosem.
        print(f"agentmachi frame: {e}", file=sys.stderr)
        return 1
    if reply is None:
        print("(sent; the server does not ACK this frame type)")
        return 0
    print(json.dumps(reply, ensure_ascii=False))
    return 1 if reply.get("type") == "error" else 0


def cmd_node(args):
    """Headless node: budzi/wznawia runtime agenta na wzmianke (Task 3).

    Token/URL jak _agent_env (CHAT_TOKEN z env wygrywa nad tokens.json).
    Stan w hub_dir(hub)/nodes/<nick>/state.json (katalog 0700).
    Runtime wybiera --runtime (claude|codex) — patrz agentmachi.node.RUNTIMES."""
    args.name = args.hub
    nick = _agent_env(args)
    # Node budzi runtime KONKRETNEGO agenta (claude -p --resume dla jego
    # sesji), wiec wymaga STABILNEGO, znanego nicka — inaczej nie wiadomo,
    # czyj stan wznawiac. To wyjatek od otwartego wejscia: listen/send moga
    # byc anonimowe (hub nada nick), node NIE. Walidujemy wprost, bo
    # _agent_env w trybie otwartym juz tego nie wymusza.
    if not nick:
        print("agentmachi node: requires --nick or CHAT_NICK "
              "(node resumes the session of one specific agent)",
              file=sys.stderr)
        return 2
    # Blokada ZOSTAJE: bez niej literowka w nicku wpada w nieskonczona petle
    # reconnect zamiast dac blad (patrz test_cli.py, komentarz przy
    # test_node_cmd_wires_runtime). C4 zmienia natomiast KOMUNIKAT: dawny
    # mowil tylko "nieznany" i zostawial agenta bez wyjscia — zmierzone na
    # kanale rube, gdzie Codex utknal na kilkanascie minut, szukajac po
    # kodzie sposobu na dodanie sobie nicka. Teraz odmowa niesie naprawe.
    try:
        tokens, _ = load_tokens(args.hub)
        if not os.environ.get("CHAT_TOKEN") and nick not in tokens:
            znane = ", ".join(sorted(n for n, v in tokens.items()
                                     if v.get("role") != "human")) or "(none)"
            print(f"agentmachi node: nick {nick!r} is unknown in "
                  f"{hub_dir(args.hub) / 'tokens.json'}.\n"
                  f"  node resumes the session of ONE specific agent, so it "
                  f"needs a nick with an entry — otherwise there is no way to "
                  f"tell whose state to resume.\n"
                  f"  agent nicks on this hub: {znane}\n"
                  f"  Enter as one of them (--nick <nick>), or — if you want "
                  f"your own name — ask the human for an entry in "
                  f"tokens.json.\n"
                  f"  Plain LISTENING needs no entry: `agentmachi listen` "
                  f"enters in open mode, and when the nick is taken the "
                  f"client comes up under a free one by itself.",
                  file=sys.stderr)
            return 2
    except CliError:
        pass
    humans = {h.strip() for h in args.humans.split(",") if h.strip()}
    state_dir = hub_dir(args.hub) / "nodes" / nick
    state_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(state_dir, 0o700)
    state_path = state_dir / "state.json"
    from agentmachi.node import RUNTIMES, RateLimiter, node_loop
    runtime_cls = RUNTIMES.get(args.runtime)
    if runtime_cls is None:
        print(f"agentmachi node: unknown runtime {args.runtime!r}; "
              f"available: {', '.join(sorted(RUNTIMES))}", file=sys.stderr)
        return 2
    # Node jest listenerem tej samej logicznej sesji co send/frame. Wczesniej
    # wchodzil na swiezym `node-<uuid>`, wiec budzony runtime nie mogl
    # odpowiedziec jako ten sam nick bez takeoveru/odmowy. Na warsztacie
    # Codex uruchomil przez to drugi listen i podniosl sie jako worker3;
    # node czekal na jego dluga runde, a kolejne @codex lezalo w logu.
    send = _import_send()
    try:
        session = send._session(nick)
        session.acquire_listener_lock()
    except (send.ListenerLockHeld, send.SessionError) as e:
        raise CliError(f"node cannot take over listening for {nick!r}: {e}")
    runtime = runtime_cls(args.workspace, max_duration=args.max_wake_duration)
    limiter = RateLimiter(max_wakes_per_hour=args.max_wakes_per_hour,
                          cooldown_after_agent_wake=args.cooldown)
    try:
        asyncio.run(node_loop(
            os.environ["CHAT_URL"], nick, os.environ["CHAT_TOKEN"],
            state_path, runtime, humans, limiter=limiter,
            instance_id=session.instance_id))
    finally:
        session.release_listener_lock()
    return 0


def cmd_install_skills(args) -> int:
    from agentmachi import skills_install

    harnessy = (
        list(skills_install.HARNESSY) if args.harness == "all" else [args.harness]
    )
    lacznie = 0
    for harness in harnessy:
        cel = (
            Path(args.dest)
            if args.dest
            else skills_install.HARNESSY[harness]
        )
        try:
            zainstalowane = skills_install.zainstaluj(harness, cel, args.force)
        except FileNotFoundError as e:
            # CliError to wzorzec repo: main() lapie go i zwraca 2 z prefiksem
            # "agentmachi:". Wlasny print + return 1 dalby inny format bledu
            # niz reszta komend.
            raise CliError(str(e)) from e
        cel_pokazany = cel.expanduser()
        if zainstalowane:
            print(f"{harness}: {', '.join(zainstalowane)} -> {cel_pokazany}")
            lacznie += len(zainstalowane)
        else:
            print(
                f"{harness}: nothing new in {cel_pokazany} "
                f"(use --force to overwrite)"
            )
    if lacznie:
        print("done — tell your agent: 'show my agentmachi rooms'")
    return 0


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="agentmachi",
        description="a Hamachi server for agents — a shared space to talk in")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # Pierwsza komenda po `pip install agentmachi`, wiec stoi pierwsza
    # w --help: bez skilli CLI dziala, ale agent nie ma jak wejsc na kanal.
    p = sub.add_parser(
        "install-skills",
        help="unpack the agentmachi skills into a harness directory",
    )
    p.add_argument(
        "--harness",
        choices=["claude", "codex", "all"],
        default="all",
        help="who to install for (default: both)",
    )
    p.add_argument(
        "--dest",
        help="target directory (defaults to one per harness)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing skills",
    )
    p.set_defaults(fn=cmd_install_skills)

    p = sub.add_parser("serve",
                       help="run a hub (creates ~/.agentmachi/<name>)")
    p.add_argument("--name", default=DEFAULT_HUB)
    # default=None jak w `start`, choc `serve` ZAWSZE konczy na jakims porcie:
    # DEFAULT_PORT dokladamy w cmd_serve. Tu chodzi wylacznie o to, zeby dalo
    # sie odczytac, czy port jest DECYZJA czlowieka — argparse jest jedynym
    # miejscem, ktore to jeszcze wie. `start` spawnuje `serve --port <N>`
    # jawnie, ale wtedy config.json pokoju juz istnieje (zapisal go rodzic),
    # wiec dziecko idzie sciezka "pokoj istniejacy" i odmowa go nie dotyczy.
    p.add_argument("--port", type=int, default=None,
                   help=f"default {DEFAULT_PORT}; an explicitly given port is "
                        f"never shifted for you")
    p.add_argument("--bind", default=DEFAULT_BIND,
                  help="interface to bind to (0.0.0.0 = all; "
                       "default 127.0.0.1 — local only)")
    p.set_defaults(fn=cmd_serve)

    p = sub.add_parser("start",
                       help="run a room IN THE BACKGROUND and print its "
                            "address")
    p.add_argument("--name", default=DEFAULT_HUB)
    # default=None, zeby odroznic "user podal --port" od "wziete z configu":
    # jawny --port musi wygrac z zapisanym, inaczej pokoj przypiety do
    # zajetego portu nie ma jak wstac.
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--bind", default=None,
                   help="0.0.0.0 = visible on the network; local only by "
                        "default")
    p.add_argument("--all", action="store_true",
                   help="every STOPPED room")
    p.set_defaults(fn=cmd_start)

    p = sub.add_parser("restart",
                       help="stop and start a room with one command")
    p.add_argument("--name", default=DEFAULT_HUB)
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--bind", default=None)
    p.add_argument("--all", action="store_true",
                   help="every running room")
    p.set_defaults(fn=cmd_restart)

    p = sub.add_parser("del", help="delete a room (irreversible)")
    p.add_argument("--name", default=DEFAULT_HUB)
    p.add_argument("--all", action="store_true",
                   help="every STOPPED room; running ones are never touched")
    p.add_argument("--yes-delete", dest="confirm", default=None,
                   help="type the room name to confirm")
    p.add_argument("--yes-delete-all", dest="confirm_all", type=int,
                   default=None,
                   help="with --all: type HOW MANY rooms will be deleted; "
                        "a mismatch refuses, so a room that appeared since "
                        "your last `list` cannot be deleted unseen")
    p.set_defaults(fn=cmd_del)

    p = sub.add_parser("list", help="which rooms exist and which are running")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("kill", help="kill processes matching a pattern — "
                                    "WITHOUT killing yourself (pkill -f "
                                    "cannot do that)")
    p.add_argument("wzorzec",
                   help="fragment of a command line, e.g. 'agentmachi listen'")
    p.add_argument("--force", action="store_true",
                   help="SIGKILL instead of SIGTERM")
    p.add_argument("--dry-run", action="store_true",
                   help="only show, do not kill")
    p.set_defaults(fn=cmd_kill)

    p = sub.add_parser("stop",
                       help="stop a hub (SIGTERM to the PID from hub.pid)")
    p.add_argument("--name", default=DEFAULT_HUB)
    p.add_argument("--all", action="store_true",
                   help="every running room")
    p.set_defaults(fn=cmd_stop)

    p = sub.add_parser("card", help="show the hub entry card")
    p.add_argument("--name", default=None)
    p.set_defaults(fn=cmd_card)

    p = sub.add_parser("tui", help="TUI for the human operator")
    p.add_argument("--name", default=None)
    p.set_defaults(fn=cmd_tui)

    # C3: skladnia ZLAMANA swiadomie. Dawne `send <nick> "tekst"` czytalo sie
    # jak "wyslij DO nicka", a bylo podpisem NADAWCY — pomylka kosztowala
    # ramke 4244 znakow wyslana w cudzym imieniu na zywym kanale (goldberg
    # seq 275, sprostowanie w seq 281). Stary wariant NIE zostaje "dla
    # kompatybilnosci": dopoki istnieje, pulapka istnieje razem z nim.
    #   --as <nick>        = KIM jestem
    #   @nick w tresci     = DO KOGO mowie
    p = sub.add_parser("send", help="send a message (you address it with an "
                                    "@mention in the text, --as says who "
                                    "you are)")
    p.add_argument("text", nargs="?", default=None,
                   help="the message. `-` means: read it from stdin "
                        "(same as --stdin)")
    p.add_argument("--stdin", action="store_true",
                   help="read the message from stdin, byte for byte — the "
                        "shell never touches it, so a trailing backslash "
                        "(C:\\Users\\x\\), quotes and newlines survive. One "
                        "trailing newline is dropped. Never implicit: "
                        "without --stdin (or `-`) stdin is not read at all.")
    # Wylapuje DAWNE uzycie `send <nick> "tekst"`: bez tego argparse mowi
    # tylko "unrecognized arguments", a agent nie dowiaduje sie, ze wlasnie
    # o wlos nie podpisal sie cudzym nickiem.
    p.add_argument("legacy_text", nargs="?", default=None,
                   help=argparse.SUPPRESS)
    p.add_argument("--as", dest="as_nick", default=None,
                   help="the SENDER's nick (defaults to CHAT_NICK). You point "
                        "at the addressee with an @mention in the text.")
    p.add_argument("--name", default=None)
    p.add_argument("--quiet", action="store_true",
                   help="publish without waking agents (humans get it anyway)")
    p.set_defaults(fn=cmd_send)

    p = sub.add_parser("listen", help="resumable listen (cursor+lock); "
                       "every line carries the frame's [seq]")
    p.add_argument("--nick", default=None)
    p.add_argument("--name", default=None)
    p.add_argument("--json", action="store_true",
                   help="print full frames as JSON, ONE PER LINE. This is the "
                        "source for ARBITRATION — the log settles scope "
                        "collisions by `seq`, and only the server assigns it. "
                        "The default format `[seq] nick: line` (the marker "
                        "repeated on EVERY line, because a content filter "
                        "matches LINES and a message here is many of them) is "
                        "a LOSSY rendering for humans: agents paste each "
                        "other's logs onto the channel, so it contains quoted "
                        "lines indistinguishable from real ones. Never parse "
                        "it.")
    p.add_argument("--fresh", action="store_true",
                   help="enter WITHOUT the conversation history — cursor at "
                        "the current end of the log. For an agent that is to "
                        "give an INDEPENDENT perspective: someone else's "
                        "diagnosis in your context is an anchor no "
                        "instruction can undo. Applies ONCE, at start — a "
                        "reconnect resumes normally, so nothing is lost when "
                        "the connection drops.")
    p.add_argument("--once", action="store_true",
                   help="exit after the first applied frame, and only once "
                        "the cursor is durably written; for a harness that "
                        "returns to the model when a command finishes")
    p.set_defaults(fn=cmd_listen)

    p = sub.add_parser(
        "read",
        help="read frames from the channel log THROUGH THE WIRE — including "
             "YOUR OWN, which listen never shows you",
        description="Read frames from the channel log through the wire. Output "
                    "is FULL JSON frames, ONE PER LINE — the same machine "
                    "format as `listen --json`, never the lossy human one. "
                    "This is the only way an agent on a REMOTE hub can see "
                    "what it said itself: the hub suppresses echo back to the "
                    "sender, the listen cursor moves past your own frame, and "
                    "events.jsonl exists only on the hub operator's machine. "
                    "read takes no listener lock and never moves your cursor, "
                    "so it runs next to a live `agentmachi listen`.")
    p.add_argument("--seq", type=int, default=None,
                   help="one frame with exactly this seq. Not found = exit 1 "
                        "with the range that DID come back — silence is never "
                        "a confirmation here.")
    p.add_argument("--from-seq", dest="from_seq", type=int, default=None,
                   help="everything from this seq up")
    p.add_argument("--nick", default=None)
    p.add_argument("--name", default=None)
    p.set_defaults(fn=cmd_read)

    p = sub.add_parser(
        "board",
        help="who is on the channel — roster, presence and each agent's own "
             "status declaration",
        description="Print the participants board through the wire: every "
                    "nick the hub knows, whether its socket is open, the seq "
                    "of its last frame, and the status it declared itself "
                    "(plus how many frames ago). The hub already sends all of "
                    "this inside the `session_metadata` frame at hello — but "
                    "the listener filter has to drop that frame by type, so "
                    "until now the only way to see the board was to enter the "
                    "channel again. Reports RAW fields: it never concludes "
                    "'idle' or 'stuck' — a stale declaration reads as one "
                    "that is old, and what that means is yours to decide. "
                    "Takes no listener lock, never moves your cursor and "
                    "wakes nobody, so it runs next to a live `agentmachi "
                    "listen`. Read-only towards YOUR SESSION, not towards the "
                    "hub log: every hello appends one durable event, so asking "
                    "who is here moves the log end by one and ages every "
                    "declaration on the board by one frame. Watch `status_seq` "
                    "if you poll — it stands still; the age does not.")
    p.add_argument("--json", action="store_true",
                   help="one JSON line with current_seq and the whole board — "
                        "the machine format. The readable one is for eyes "
                        "only; never parse it.")
    p.add_argument("--nick", default=None)
    p.add_argument("--name", default=None)
    p.set_defaults(fn=cmd_board)

    p = sub.add_parser("frame", help="one-shot status frame "
                       "(session identity — zero takeover)")
    p.add_argument("json", nargs="?", default=None,
                   help='e.g. \'{"type":"status","state":"idle"}\'. `-` means: '
                        'read it from stdin (same as --stdin)')
    p.add_argument("--stdin", action="store_true",
                   help="read the frame JSON from stdin, byte for byte — no "
                        "shell quoting around the quotes JSON is made of. "
                        "Never implicit: without --stdin (or `-`) stdin is "
                        "not read at all.")
    p.add_argument("--nick", default=None)
    p.add_argument("--name", default=None)
    p.set_defaults(fn=cmd_frame)

    p = sub.add_parser("node",
                       help="headless node: wakes an agent on a mention")
    p.add_argument("hub")
    p.add_argument("--nick", required=True)
    p.add_argument("--workspace", required=True)
    p.add_argument("--humans", default="human",
                   help="human nicks (comma-separated) — the cooldown does "
                        "not apply to their mentions")
    p.add_argument("--runtime", default=os.environ.get("AGENTMACHI_RUNTIME", "claude"),
                   help="which runtime to wake: claude | codex")
    p.add_argument("--max-wakes-per-hour", type=int,
                   default=int(os.environ.get("MAX_AGENT_WAKES_PER_HOUR", "6")))
    p.add_argument("--cooldown", type=float,
                   default=float(os.environ.get("AGENT_WAKE_COOLDOWN", "60")))
    p.add_argument("--max-wake-duration", type=float,
                   default=float(os.environ.get("MAX_WAKE_DURATION", "1200")))
    p.set_defaults(fn=cmd_node)

    return parser


def _force_utf8_output(*streams):
    """Wymus UTF-8 z errors=replace na strumieniach wyjscia.

    Windows: konsola/plik koduja wyjscie wg codepage systemu (np. cp1250 na
    polskim Windows), a log kanalu niesie znaki spoza niego (mojibake, emoji,
    obce nazwy) — _print_event (send.py) padal wtedy na UnicodeEncodeError i
    UBIJAL listener. Zlapane na Windows Bartka przez codeksa: `agentmachi
    listen` czytal resync i wychodzil z EXIT 1 na U+FF82. errors=replace daje
    poprawne znaki tam, gdzie codepage je zna, i znak zastepczy zamiast crashu.
    No-op tam, gdzie strumien nie wspiera reconfigure (starszy/owiniety)."""
    for stream in streams:
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    _force_utf8_output(sys.stdout, sys.stderr)
    parser = _build_parser()
    args = parser.parse_args(argv)
    # PRZED komenda, nie po: na Windows jej werdykt bedzie nieprawdziwy,
    # wiec czlowiek ma czytac go juz z ta wiedza. Jedno miejsce zamiast
    # piatki wywolan w cmd_* — `restart` wola `cmd_start`, wiec ostrzegalby
    # dwa razy, a `main` zna nazwe komendy i widzi kazde wejscie z terminala.
    _ostrzez_o_platformie(args.cmd)
    try:
        return args.fn(args)
    except CliError as e:
        print(f"agentmachi: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
