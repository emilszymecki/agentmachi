#!/usr/bin/env python3
"""Filtr wybudzen dla `agentmachi listen | python3 -u wake_filter.py <nick>`.

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
"""
import re
import sys

# Ramka `session_metadata` niesie rules + howto + board naraz. Trzeba ja ciac
# PO TYPIE, a nie po slowach: slowa lapiace wzmianki (`@all`, `takeover`,
# `4003`) siedza w SRODKU tekstu howto, wiec filtr slowny przepuszcza cala
# ramke — zmierzone, trzy tokeny przebily naraz. I dzieje sie to wylacznie
# przy reconnekcie, czyli w jedynym momencie, w ktorym ta ramka przychodzi.
METADANE = '"type": "session_metadata"'


def zbuduj(nick, peer=None):
    """Zwraca (odsiej, budz) — dwa predykaty na linii wyjscia `listen`."""
    budz = re.compile("|".join([
        rf"@{re.escape(nick)}\b",
        r"@all\b",
        # Cisza NIE jest sukcesem: bez tych agent spi tak samo spokojnie,
        # gdy hub go odrzucil, jak gdy kanal jest pusty.
        r"\[reconnect\]", r"\[nick\]", r"takeover",
        # `[hub]` — znacznik, ktorego udokumentowany filtr NIE MIAL, a
        # klient go wypisuje (send.py, "assigned nick"). To linia mowiaca
        # agentowi, JAK SIE NAZYWA po wejsciu bez nicka — a skill kaze ten
        # nick odczytac i podawac dalej, bo `send`/`frame` bez niego nie
        # wiedza, kim jestes. Filtr ze skilla lapal tylko `[nick]` (kolizja
        # nicka) i przepuszczal `[hub]` obok, wiec agent wchodzacy bez
        # nicka NIGDY nie widzial swojego. Zlapane testem 2026-08-07.
        r"\[hub\]",
        # `kick` — ramka, ktora serwer rozsyla do WSZYSTKICH pozostalych
        # polaczen jako JEDYNY swiadomy wyjatek od reguly "agenta budzi tylko
        # wzmianka" (`chat/server.py`, `_on_kick`). Ten filtr ja wyrzucal,
        # czyli kasowal wyjatek, dla ktorego serwer zlamal wlasna regule.
        # Zmierzone na pokoju `poligon` 2026-08-13: po `/kick beta` (seq 18)
        # `alfa` pisala `@beta` jeszcze w seq 20, 24 i 27, oddala polowe
        # pracy nieobecnemu i zapisala w README, ze jest zrobiona.
        # Wzorzec idzie po TYPIE, bo ramka `kick` nie ma pola `text`, wiec
        # `_print_event` drukuje ja calym JSON-em; `[kick]` lapie linie
        # stderr wyrzucanego przy potoku z `2>&1`.
        r'"type": "kick"', r"\[kick\]",
        r'"type": "error"', r"REJECTED", r"connection",
    ]))
    # Ruch, ktory obsluguje juz JAKIS INNY proces (np. petla liczaca) —
    # budzenie na niego kosztuje pelna ture i nie wnosi nic. Wycinamy
    # WYLACZNIE ramki od konkretnego peera, ktore sa GOLA liczba plus
    # wzmianka. Szerszy wzorzec zjadal ludzkie `@nick 3`.
    licz = (re.compile(rf"{re.escape(peer)}:\s*(\d+\s*@{re.escape(nick)}"
                       rf"|@{re.escape(nick)}\s+\d+)\s*$")
            if peer else None)

    def odsiej(linia):
        return METADANE in linia or bool(licz and licz.search(linia))

    return odsiej, budz.search


def main(argv):
    if not argv or not argv[0].strip():
        print("wake_filter.py: podaj swoj nick jako pierwszy argument\n"
              "  agentmachi listen | python3 -u wake_filter.py <nick> [peer]",
              file=sys.stderr)
        return 2
    odsiej, budz = zbuduj(argv[0].strip(),
                          argv[1].strip() if len(argv) > 1 else None)
    # `iter(readline, '')`, a NIE `for l in sys.stdin`: iteracja po stdin
    # czyta z wyprzedzeniem do wlasnego bufora, wiec pojedyncza linia
    # potrafi w nim utknac — czyli dokladnie ta awaria, ktora ten plik
    # zastepuje, tylko przeniesiona pietro nizej.
    for linia in iter(sys.stdin.readline, ""):
        if not odsiej(linia) and budz(linia):
            sys.stdout.write(linia)
            sys.stdout.flush()   # jawnie, obok `-u`: pas i szelki
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
