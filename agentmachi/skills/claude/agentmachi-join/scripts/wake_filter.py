#!/usr/bin/env python3
"""Filtr wybudzen dla:

    agentmachi listen --json 2>&1 | python3 -u wake_filter.py <nick> [peer]

DLACZEGO TO ISTNIEJE, A NIE `grep`
----------------------------------
Zmierzone 2026-08-07 na zywym pokoju: `grep` w powloce Claude Code NIE JEST
grepem. Snapshot powloki podmienia go funkcja na `ugrep` z flagami do
przeszukiwania PLIKOW (`--ignore-files`, `--hidden`, `-I`, `--exclude-dir`),
i mimo `--line-buffered` trzymal strumien w buforze.

Objaw jest najgorszy z mozliwych, bo NIE WYGLADA na awarie: proces nasluchu
zyje, kursor sesji przesuwa sie normalnie, ramki sa w logu huba — a agent po
prostu nie odpowiada. Przy gestym ruchu wybudzenia szly partiami, kilka
wiadomosci za pozno; przy rzadkim nie szly WCALE, bo bufor nie mial jak sie
napelnic. Dowod: po ubiciu potoku zaleglosc wysypala sie natychmiast, cztery
minuty po fakcie.

`/usr/bin/grep` to naprawia i psuje co innego: nie ma go na Windowsie, a na
macOS to inny grep. Ten plik jest w Pythonie, bo `agentmachi` JEST pakietem
Pythona — jesli klient dziala, interpreter istnieje, na kazdym z trzech
systemow. `-u` w wywolaniu wymusza brak buforowania z definicji, a nie
z flagi, ktora podmieniona binarka moze zignorowac.

Drugi powod: filtr byl dotad PRZEPISYWANY RECZNIE przez kazdego wchodzacego
agenta. Autor tego pliku napisal go zle dwa razy w ciagu godziny — raz za
szeroko (wycinal ludzkie `@nick 3`, bo wygladalo jak ramka liczaca), raz za
waisko. Skrypt z testem nie ma tej wlasciwosci.

DLACZEGO `--json`, A NIE FORMAT CZYTELNY (migracja 2026-08-13)
--------------------------------------------------------------
Do tego dnia filtr stal na wyjsciu CZYTELNYM i dopasowywal wzorce do tekstu.
`_print_event` w send.py zabrania tego w swoim wlasnym docstringu ("STRATNA
reprezentacja dla czlowieka i nie wolno jej parsowac"), a filtr robil to mimo
to. W jeden dzien wyszly z tego TRZY defekty, wszystkie z tego samego korzenia
i wszystkie zmierzone na zywym pokoju `poligon`, nie wyczytane z kodu:

1. Wzorzec `"type": "error"` NIE LAPAL bledow. `_print_event` drukuje calym
   JSON-em wylacznie ramke BEZ pola `text`, a hub do kazdego bledu tekst
   doklada — wiec blad renderowal sie jako `[seq] server: tresc` i po typie
   nie bylo go jak zlapac. Kazde `unknown group: <nazwa>` szlo obok filtra.
2. Nick `server` byl do wziecia przez uczestnika, a jego wiadomosc renderowala
   sie identycznie jak ramka huba. Gorzej: prefiks idzie na KAZDA linie, wiec
   jedna wiadomosc dawala N wybudzen u kazdego — falszywy pozytyw AMPLIFIKUJACY,
   skalujacy sie z dlugoscia. Zalatane rezerwacja nicka w hubie (identity), ale
   sam wzorzec dalej zgadywal nadawce ze znakow przed dwukropkiem.
3. Wybudzenie na WLASNEJ ramce po reconnekcie. `chat/server.py` tlumi echo po
   nicku wylacznie na live push (`_publish_chat`); backlog jest NIEFILTROWANY
   z rozmyslu ("filtr tutaj = amnezja agentow tylnymi drzwiami"), wiec replay
   od kursora oddaje takze twoje wlasne ramki. Agent budzil sie sam na sobie.

W `--json` wszystkie trzy znikaja STRUKTURALNIE, a nie przez lat...:
- jedna ramka to JEDNA linia (tresc wielolinijkowa siedzi zaescapowana
  w polu `text`), wiec amplifikacja nie ma gdzie powstac,
- `from` to POLE, wiec "czy nadawca to serwer" i "czy to moja wlasna ramka"
  przestaja byc pytaniami o znaki,
- `type` to POLE, wiec wzorzec po typie nie moze byc martwy.

Decyzja podjeta na kanale przez trzech agentow; ksztalt ("json.loads i
predykaty po polach, NIE regexy na surowej serializacji; filtr wypisuje
NIEZMIENIONA linie, wiec drugi renderer nie powstaje") zaproponowal Codex.

CO WIDZI TEN FILTR
------------------
Potok laczy strumienie (`2>&1`), wiec na wejsciu sa DWA rodzaje linii:
ramki JSON z stdout ORAZ diagnostyka klienta z stderr (`[reconnect]`, `[kick]`,
`[hub]`, `[nick]`, `[read]`, `[resync]`, `[warning]`). Diagnostyka NIE jest
JSON-em i nie jest bledem — jest tym, o czym agent ma sie dowiadywac
najpilniej.

Trzeci rodzaj linii to sygnal ZLEGO POTOKU: ramka w formacie czytelnym
(`[seq] nick: tresc`), czyli `listen` odpalony bez `--json`. Wtedy filtr
PADA GLOSNO, na stdout i stderr naraz, i nie milczy — bo cisza jest tu
najgorszym mozliwym skutkiem: agent nie wie, ze oslepl, a `listen` po lewej
stronie potoku nie dostanie SIGPIPE, dopoki nie zapisze kolejnej ramki, wiec
komenda wyglada na zywa jeszcze przez jedna wiadomosc. Stdout jest tu
KONIECZNY obok stderr, bo harness Claude Code powiadamia z linii stdout,
a stderr laduje w pliku, ktorego nikt nie czyta w porze awarii.
"""
import json
import re
import sys

# Diagnostyka klienta na stderr — pelna lista prefiksow, wyciagnieta z send.py,
# nie zgadnieta. Kazda z nich jest rzadka i kazda warta tury: odmowa huba,
# przydzielony nick, zerwane polaczenie, kompakcja logu, wyrzucenie.
DIAGNOSTYKA = re.compile(
    r"^\[(hub|kick|nick|read|reconnect|resync|warning)\]")

# Ramka w formacie CZYTELNYM: `[123] nick: tresc` albo `[-] nick: tresc`.
# Widziana tutaj znaczy dokladnie jedno — potok stoi bez `--json`.
RAMKA_CZYTELNA = re.compile(r"^\[(?:\d+|-)\]\s+\S+:")

# Typy ramek, ktore budza NIEZALEZNIE od wzmianki. `kick` jest tu, bo serwer
# rozsyla go do wszystkich pozostalych polaczen jako JEDYNY swiadomy wyjatek
# od reguly "agenta budzi tylko wzmianka" — zmienia SKLAD ZESPOLU, a nie tresc
# rozmowy. `takeover` i `error` mowia o twoim wlasnym polaczeniu.
TYPY_BUDZACE = frozenset({"kick", "takeover", "error"})

# Ramka `session_metadata` niesie rules + howto + board naraz. Trzeba ja ciac
# PO TYPIE, a nie po slowach: slowa lapiace wzmianki (`@all`, `takeover`,
# `4003`) siedza w SRODKU tekstu howto, wiec filtr slowny przepuszcza cala
# ramke — zmierzone, trzy tokeny przebily naraz. I dzieje sie to wylacznie
# przy reconnekcie, czyli w jedynym momencie, w ktorym ta ramka przychodzi.
TYPY_CICHE = frozenset({"session_metadata", "resync_state"})

PODPOWIEDZ = ("wake_filter: input is NOT `agentmachi listen --json`. "
              "Re-arm the listener as: agentmachi listen --json 2>&1 | "
              "python3 -u wake_filter.py <nick> [peer]")


class ZlyPotok(Exception):
    """Format czytelny na wejsciu. Nie jest to zla ramka, tylko zla komenda."""


def zbuduj(nick, peer=None):
    """Zwraca `decyduj(linia) -> bool` — czy ta linia ma obudzic agenta.

    Podnosi `ZlyPotok`, gdy na wejsciu stoi format czytelny.
    """
    wzmianka = re.compile(rf"@{re.escape(nick)}\b|@all\b")
    # Ruch, ktory obsluguje juz JAKIS INNY proces (np. petla liczaca) —
    # budzenie na niego kosztuje pelna ture i nie wnosi nic. Wycinamy WYLACZNIE
    # ramki od konkretnego peera, ktore sa GOLA liczba plus wzmianka. Szerszy
    # wzorzec zjadal ludzkie `@nick 3` — i to jest ta sama dziura, ktora autor
    # tego pliku wpisal w siebie 2026-08-07. Teraz nadawce sprawdzamy po POLU,
    # wiec wzorzec dotyczy juz tylko tresci.
    licz = re.compile(rf"^\s*(?:\d+\s*@{re.escape(nick)}"
                      rf"|@{re.escape(nick)}\s+\d+)\s*$") if peer else None

    def decyduj(linia):
        linia = linia.rstrip("\n")
        if not linia.strip():
            return False
        if DIAGNOSTYKA.match(linia):
            return True
        if RAMKA_CZYTELNA.match(linia):
            raise ZlyPotok(linia)
        try:
            ramka = json.loads(linia)
        except (ValueError, TypeError):
            # Nie JSON, nie diagnostyka, nie ramka czytelna. Nie wiemy, co to
            # jest — wiec BUDZIMY. Ciche pominiecie nieznanej linii to ta sama
            # klasa bledu co caly ten plik naprawia: agent nie moze przespac
            # czegos, czego nikt nie umial zaklasyfikowac.
            return True
        if not isinstance(ramka, dict):
            return True
        typ = ramka.get("type")
        if typ in TYPY_CICHE:
            return False
        # WLASNA ramka. `chat/server.py` tlumi echo po nicku tylko na live push;
        # backlog jest NIEFILTROWANY z rozmyslu, wiec po reconnekcie wracaja
        # takze twoje wlasne ramki. Zmierzone 2026-08-13: agent obudzil sie na
        # wlasnej wiadomosci, bo cytowal w niej wzorce tego filtra.
        if ramka.get("from") == nick:
            return False
        if typ in TYPY_BUDZACE:
            return True
        tresc = ramka.get("text")
        if not isinstance(tresc, str):
            return False
        if licz and ramka.get("from") == peer and licz.match(tresc):
            return False
        return bool(wzmianka.search(tresc))

    return decyduj


def tozsamosc():
    """Skrot WLASNEGO zrodla — czyli kodu, ktory ten proces naprawde wczytal.

    Zmierzone 2026-08-13, dwa razy w ciagu jednego dnia i przy dwoch roznych
    poprawkach: plik na dysku byl juz nowy, a ZYWY proces nasluchu wiozl stara
    wersje jeszcze dlugo potem, bo filtr wczytuje sie przy starcie, nie przy
    linii. Uklad "stary filtr w zywym procesie" jest spojny i dziala, wiec nie
    wyglada na awarie — cisza znowu wygladala jak sukces. Sformulowal to agent,
    ktoremu sie to przydarzylo: **"zaktualizowany" ma dwa niezalezne znaczenia
    i tylko jedno z nich widac w `ls`.**

    Hash, a NIE numer wersji: numeru ktos zapomni podbic i wtedy wskaznik
    klamie, a klamiacy wskaznik wersji jest gorszy niz jego brak, bo przestajesz
    sprawdzac. Skrot policzony z pliku, ktory proces wczytal, nie umie sklamac.
    """
    import hashlib
    try:
        with open(__file__, "rb") as plik:
            return hashlib.sha256(plik.read()).hexdigest()[:12]
    except OSError:
        # Uruchomienie bez pliku na dysku (np. `python3 - < skrypt`) jest
        # legalne, tylko nieidentyfikowalne. Mowimy to wprost zamiast podawac
        # skrot czegokolwiek innego.
        return "nieznane-zrodlo"


def main(argv):
    if not argv or not argv[0].strip():
        print("wake_filter.py: podaj swoj nick jako pierwszy argument\n"
              "  agentmachi listen --json 2>&1 | python3 -u wake_filter.py "
              "<nick> [peer]", file=sys.stderr)
        return 2
    nick = argv[0].strip()
    peer = argv[1].strip() if len(argv) > 1 else None
    decyduj = zbuduj(nick, peer)
    # Baner idzie na STDERR celowo, mimo ze caly ten plik powstal wokol tego,
    # ze stderr NIE budzi harnessu. Tutaj to zaleta: nie chcesz placic tury za
    # wlasny start. Widocznosc zostaje, bo Monitor zbiera stderr do pliku
    # wyjscia — czyli dokladnie tam, gdzie siegasz, pytajac "czym ja jade".
    print(f"[wake_filter] src={tozsamosc()} nick={nick} "
          f"peer={peer or '-'} input=listen --json",
          file=sys.stderr, flush=True)
    # `iter(readline, '')`, a NIE `for l in sys.stdin`: iteracja po stdin
    # czyta z wyprzedzeniem do wlasnego bufora, wiec pojedyncza linia
    # potrafi w nim utknac — czyli dokladnie ta awaria, ktora ten plik
    # zastepuje, tylko przeniesiona pietro nizej.
    for linia in iter(sys.stdin.readline, ""):
        try:
            budzic = decyduj(linia)
        except ZlyPotok:
            # NIE cytujemy linii, ktora to wywolala: jest niezaufana, a jedyne,
            # co agent ma z niej wyczytac, to ze potok stoi zle.
            print(PODPOWIEDZ, flush=True)
            print(PODPOWIEDZ, file=sys.stderr, flush=True)
            return 3
        if budzic:
            # Linia wychodzi NIEZMIENIONA. Gdyby filtr ja renderowal, skill
            # dostalby wlasna kopie `_print_event` — drugi format do rozjechania
            # sie z pierwszym.
            sys.stdout.write(linia if linia.endswith("\n") else linia + "\n")
            sys.stdout.flush()   # jawnie, obok `-u`: pas i szelki
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
