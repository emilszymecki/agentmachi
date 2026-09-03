"""Frontmatter skilli musi byc wazny — inaczej skill nie istnieje.

Zgloszone przez drugiego agenta (Codex) przy review, potwierdzone
empirycznie: `agentmachi/skills/claude/agentmachi-join/SKILL.md` mial w description
niecytowane `Trigger: "...` i `hydraulike: hello,`. YAML czyta `: ` jako
poczatek zagniezdzonego mapowania, wiec parser rzucal ScannerError,
a harness NIE LADOWAL skilla wcale. Skill wpuszczajacy agentow na kanal
byl niewidoczny dla agenta, ktory mial go uzyc.

Objaw byl cichy w najgorszy sposob: plik istnial, wygladal poprawnie
i dawal sie czytac czlowiekowi. Dopiero po naprawie pozycja pojawila sie
na liscie dostepnych skilli w tej samej sesji.

Nie uzywamy tu pyyaml: nie ma go w srodowisku testowym repo (suita chodzi
przez `uv run --with pytest --with websockets --with textual`), a dokladanie
zaleznosci dla jednego testu jest drozsze niz regula ponizej. Sprawdzamy
dokladnie to, co zlamalo sie naprawde — `: ` w niecytowanej wartosci.
"""

import difflib
import json
import re
import sys
from pathlib import Path

import pytest

# Skille mieszkaja pod katalogiem pakietu, bo `package-data` pakuje tylko
# to, co jest WEWNATRZ pakietu — inaczej `pip install agentmachi` daje CLI
# bez skilli, czyli produkt bez sciezki wejscia dla agenta.
SKILLS = Path(__file__).resolve().parent.parent / "agentmachi" / "skills" / "claude"
SKILLS_CODEX = Path(__file__).resolve().parent.parent / "agentmachi" / "skills" / "codex"


def _bloki_kodu(tekst):
    """Fragmenty, ktore agent KOPIUJE: plotki ``` oraz wciecia czterema
    spacjami. `howto_default.md` uzywa wciec, skille plotkow — obie formy
    sa gotowe do wklejenia, wiec obie licza sie tak samo."""
    w_plotku = False
    biezacy = []
    for linia in tekst.splitlines():
        if linia.lstrip().startswith("```"):
            if w_plotku:
                yield "\n".join(biezacy)
                biezacy = []
            w_plotku = not w_plotku
            continue
        if w_plotku:
            biezacy.append(linia)
        elif linia.startswith(("    ", "\t")) and linia.strip():
            yield linia
    if biezacy:
        yield "\n".join(biezacy)


def _frontmattery():
    for sciezka in sorted(SKILLS.glob("*/SKILL.md")):
        czesci = sciezka.read_text().split("---")
        assert len(czesci) >= 3, f"{sciezka.name}: brak frontmattera YAML"
        yield sciezka, czesci[1].strip()


def test_kazdy_skill_ma_frontmatter_z_name_i_description():
    znalezione = list(_frontmattery())
    assert znalezione, "nie ma zadnego skilla — glob trafil w pustke"
    for sciezka, blok in znalezione:
        klucze = {linia.split(":", 1)[0].strip()
                  for linia in blok.splitlines() if ":" in linia}
        assert "name" in klucze, f"{sciezka.name}: brak 'name'"
        assert "description" in klucze, f"{sciezka.name}: brak 'description'"


def _komendy_z_kodu(tekst):
    """Wystapienia `agentmachi <slowo>` z BLOKOW KODU i backtickow.

    Proza jest pomijana celowo: zdanie "agentmachi to serwer Hamachi dla
    agentow" nie jest instrukcja i nie ma po co go walidowac. Liczy sie to,
    co agent skopiuje i wklei."""
    fragmenty, w_bloku = [], False
    for linia in tekst.splitlines():
        if linia.lstrip().startswith("```"):
            w_bloku = not w_bloku
            continue
        if w_bloku:
            fragmenty.append(linia)
        else:
            fragmenty.extend(re.findall(r"`([^`]+)`", linia))
    komendy = set()
    for f in fragmenty:
        # Myslnik jest czescia nazwy komendy (`install-skills`), nie jej
        # koncem. Bez niego skill uczacy `agentmachi install-skills` zglasza
        # nieistniejaca komende `install` — czyli test lapie wlasna literowke
        # zamiast bledu skilla.
        komendy.update(re.findall(r"\bagentmachi\s+([a-z][a-z-]*)", f))
    return komendy


def test_skille_nie_ucza_komend_ktorych_CLI_nie_ma():
    """Skill uczacy nieistniejacej komendy jest gorszy niz milczenie: agent
    wykonuje ja, dostaje blad i traci runde na ustalanie, czy zepsul cos sam.

    Zmierzone przy review 2026-07-29 (dwaj agenci niezaleznie): skill
    operatora podawal `agentmachi del --name <pokoj>`, a `del` wymaga
    `--yes-delete <nazwa>` (do 2026-08-05: `--tak-kasuj`). Potknal sie o to
    autor tego testu, na zywej
    maszynie, w trakcie sprzatania po wlasnym eksperymencie.

    Zrodlem prawdy jest parser CLI, nie ta lista — czytamy subkomendy
    wprost z argparse, wiec test nie zdezaktualizuje sie po dodaniu nowej."""
    import contextlib
    import io

    from agentmachi import cli

    # Parser powstaje wewnatrz main(), wiec pytamy o niego tak, jak zrobilby
    # to czlowiek: przez --help. Argparse sam drukuje liste subkomend
    # w nawiasach klamrowych, wiec zrodlem prawdy zostaje kod, nie ten test.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.suppress(SystemExit):
        cli.main(["--help"])
    tekst = buf.getvalue()
    # Klasa znakow musi znac myslnik, bo znaja go nazwy subkomend
    # (`install-skills`, T6). KONTRAKT sie nie zmienil — zrodlem prawdy dalej
    # jest parser argparse, nie lista w tescie. Zmienil sie sposob CZYTANIA
    # tej listy: `[a-z,]+` nie dopasowywalo grupy `{...}` z myslnikiem
    # w srodku, wiec test padal na `assert None` — na wlasnym parserze, nie na
    # tresci skilla. Docstring obiecywal, ze test nie zdezaktualizuje sie po
    # dodaniu komendy; ta poprawka dotrzymuje obietnicy.
    dopasowanie = re.search(r"\{([a-z,-]+)\}", tekst)
    assert dopasowanie, f"nie umiem odczytac subkomend z --help:\n{tekst}"
    znane = set(dopasowanie.group(1).split(","))
    assert "start" in znane and "send" in znane, \
        f"odczytalem bzdury zamiast subkomend: {sorted(znane)}"

    for sciezka in sorted(SKILLS.rglob("*.md")):
        uzyte = _komendy_z_kodu(sciezka.read_text())
        nieznane = uzyte - znane
        assert not nieznane, (
            f"{sciezka.relative_to(SKILLS)}: skill uczy komend, ktorych CLI "
            f"nie ma: {sorted(nieznane)}. Znane: {sorted(znane)}")


def test_kto_uczy_send_uczy_TAKZE_drogi_omijajacej_powloke():
    """Plik uczacy `agentmachi send` bez `--stdin` uczy formy, ktora gubi
    wiadomosci — i robi to cicho, bo powloka zjada tresc przy exit 0.

    ZMIERZONE, nie przewidziane. Raport z pokoju `justjoinet`
    (2026-08-15/16, dwa Opusy 5, ~200 wiadomosci, 14 commitow): jedna
    wiadomosc NIE WYSZLA W OGOLE, bo backtick w cytowanym
    `order by o.published_at` powloka wzieta za podstawienie komendy.
    Drugi agent przez caly dzien redagowal wiadomosci pod skladnie powloki.

    Najciekawsze jest to, czego raport nie widzial: `--stdin` STAL wtedy
    w `howto_default.md:19,22`, a howto hub wysyla przy KAZDYM hello
    i reconnekcie. Sprawdzone na pliku, ktory ich pokoj wydal naprawde
    (`~/.agentmachi/justjoinet/data/howto.md`, diff wobec drzewa pusty),
    a nie na drzewie roboczym. Czyli tresc byla dostarczona i mimo to
    nieznaleziona: przychodzi przy `hello`, gdy agent nie ma jeszcze nic
    do wyslania, a gdy dwie godziny pozniej pisze, kopiuje forme, ktora ma
    przed oczami. Uczy PRZYKLAD, nie zdanie obok niego w innym pliku.

    Dlatego test pilnuje WSPOLOBECNOSCI w jednym pliku, nie samego
    pokrycia w repo. Sufit 4096 B na `SKILL.md` (patrz BUDZETY) stale
    naciska, zeby cos wyciac; bez tego straznika `--stdin` jest naturalnym
    kandydatem, bo wyglada na duplikat `--help`. Raz juz tak wygladal."""
    bezpieczna = ("--stdin", "send - --as", "send -\n")
    pliki = [*SKILLS.rglob("*.md"), *SKILLS_CODEX.rglob("*.md"),
             Path(__file__).resolve().parent.parent
             / "agentmachi" / "howto_default.md"]

    uczace = []
    for sciezka in sorted(pliki):
        tekst = sciezka.read_text()
        # PRZYKLAD, nie wzmianka w prozie. Pierwsza wersja tego testu pytala
        # o `agentmachi send` w calym pliku i zapalila sie na
        # `troubleshooting.md`, ktory opisuje wyjatek PO wyslaniu ramki
        # i zadnej formy nie uczy. Kopiuje sie blok kodu, wiec blok kodu
        # jest tu jednostka — inaczej test kaze dopisywac `--stdin` tam,
        # gdzie nikt niczego nie wklei.
        bloki = list(_bloki_kodu(tekst))
        if not any("agentmachi send" in b for b in bloki):
            continue
        uczace.append(sciezka)
        # ASERCJA MUSI MIERZYC TE SAMA JEDNOSTKE CO WYKRYWANIE. Pierwsza
        # wersja wykrywala po bloku, a sprawdzala po CALYM PLIKU — wiec plik
        # mogl uczyc formy cytowanej w bloku i zaliczyc straznika wzmianka
        # w prozie dwiescie linii dalej. Czyli dokladnie defekt, ktorego ten
        # test pilnuje, ocalaly w srodku samego testu. Zlapala to gamma
        # w review 2026-08-16 i podala JEDYNY plik, ktory tamtedy przechodzil:
        # wariant Codexa mial `--stdin` w prozie kroku 4, a w bloku wylacznie
        # forme cytowana.
        assert any(w in b for b in bloki for w in bezpieczna), (
            f"{sciezka.name} uczy `agentmachi send`, ale nie pokazuje drogi "
            f"omijajacej powloke ({' / '.join(bezpieczna)}). Agent skopiuje "
            f"forme cytowana i straci pierwsza wiadomosc z backtickiem — "
            f"cicho, z exit 0.")

    # Bez tego test przechodzi takze wtedy, gdy `agentmachi send` zniknie
    # z calego drzewa skilli, czyli mierzylby wlasny brak wejscia.
    assert len(uczace) >= 3, (
        f"za malo plikow uczy `agentmachi send` ({len(uczace)}) — sprawdz, "
        f"czy test patrzy tam, gdzie mysli")


def test_ANTYPRZYKLAD_w_bloku_jest_oznaczony_W_BLOKU():
    """Zepsuta komenda pokazana w bloku kodu bez znacznika W TYM BLOKU jest
    gotowcem do wklejenia, a nie ostrzezeniem.

    Ten test to drugie zastosowanie mechanizmu z
    `test_kto_uczy_send_uczy_TAKZE_drogi_omijajacej_powloke` — tam chodzilo
    o brak dobrej formy, tu o obecnosc ZLEJ. Grozniejsze, bo agent nie musi
    niczego szukac: ma pod reka gotowiec, w bloku, podswietlony jak reszta.

    Znalezione grepem po konkretnej pulapce, nie audytem, i pierwszy strzal
    trafil (2026-08-16). Oba warianty skilla pokazuja ten sam zepsuty potok
    w `references/troubleshooting.md`; wariant Claude'a mial `# BROKEN`
    w linii, wariant Codexa nie mial nic w bloku — ostrzezenie stalo
    wylacznie w prozie nad i pod nim.

    Dlaczego akurat `listen | grep -m1`: ta jedna pulapka kosztowala projekt
    dzien pracy (`CLAUDE.md`, sekcja o nasluchu) i jest NIEWYKRYWALNA
    z zewnatrz — `grep` konczy sie po trafieniu, ale `listen` nie dostanie
    `SIGPIPE`, dopoki nie napisze kolejnej linii. Proces zyje, kursor sie
    rusza, agent po prostu milczy.

    Lista jest jednoelementowa z rozmyslu. Rosnie, gdy jakas forma NAPRAWDE
    kogos kosztuje — nie profilaktycznie, bo wtedy jest to lista zakazow,
    a te przeciekaja."""
    zepsute = {"grep -m1": "listen konczy sie o wiadomosc za pozno"}
    znaczniki = ("BROKEN", "ZLE", "WRONG", "do not", "Do not", "never", "Never")

    # Ten sam zasieg co `test_kto_uczy_send...` — z howto wlacznie. Rozjazd
    # miedzy blizniaczymi straznikami zglosila gamma jako niegrozny dzis
    # (howto ma `grep -m1` wylacznie w prozie) i nie prosila o zmiane. Zmiana
    # i tak idzie, bo ta roznica nie byla decyzja, tylko przypadkiem pisania:
    # gdyby ktos wstawil do howto blok, jeden straznik by go zobaczyl, a drugi
    # nie, i nikt by nie wiedzial dlaczego.
    sprawdzone = 0
    for sciezka in sorted([*SKILLS.rglob("*.md"), *SKILLS_CODEX.rglob("*.md"),
                           Path(__file__).resolve().parent.parent
                           / "agentmachi" / "howto_default.md"]):
        for blok in _bloki_kodu(sciezka.read_text()):
            for linia in blok.splitlines():
                for forma, powod in zepsute.items():
                    if forma not in linia:
                        continue
                    sprawdzone += 1
                    assert any(z in linia for z in znaczniki), (
                        f"{sciezka.name}: antyprzyklad `{forma}` stoi w bloku "
                        f"bez znacznika W TEJ LINII ({powod}). Proza obok "
                        f"bloku nie wystarcza — kopiuje sie blok:\n  {linia}")

    assert sprawdzone >= 2, (
        f"antyprzyklad `grep -m1` zniknal ze skilli ({sprawdzone} trafien) — "
        f"albo go usunieto, albo test przestal patrzec tam, gdzie mysli")


def test_wartosci_frontmattera_nie_udaja_zagniezdzonego_mapowania():
    """`: ` w niecytowanej wartosci = ScannerError = skill sie nie laduje."""
    for sciezka, blok in _frontmattery():
        for linia in blok.splitlines():
            if not linia.strip() or ":" not in linia:
                continue
            wartosc = linia.split(":", 1)[1].strip()
            if wartosc[:1] in ('"', "'"):
                continue                     # zacytowane — YAML nie zajrzy
            assert ": " not in wartosc, (
                f"{sciezka.name}: '{linia.strip()[:60]}...' — dwukropek ze "
                f"spacja w niecytowanej wartosci. YAML czyta to jako mapowanie "
                f"i CALY skill przestaje sie ladowac. Uzyj myslnika albo "
                f"zacytuj wartosc.")


def test_skill_nie_odwraca_priorytetu_nad_projektem():
    """PAKIET 0 (plan V1): agentmachi jest NARZEDZIEM w cudzym projekcie,
    nie jego zwierzchnikiem.

    Skill mowil "gdy prompt startowy kloci sie z rules/howto z huba, wygrywa
    to, co przyszlo z huba". W repo agentmachi to bylo prawdziwe. W obcym
    repo znaczy: czat wygrywa z AGENTS.md wlasciciela — czyli narzedzie
    komunikacji przejmuje wladze nad projektem, do ktorego je podpieto.

    UWAGA O SAMYM TESCIE: pierwsza wersja szukala frazy zapisanej BEZ polskich
    znakow ("przyszlo") i przechodzila na kodzie, ktory zawieral "przyszło".
    Zielony wynik znaczyl tylko tyle, ze asercja nie trafila w cel — ta sama
    klasa, co zasada 13 w docs/pl/zasady-agentyczne.md. Dlatego szukamy tu
    WZORCA odpornego na zapis, a nie jednego literalnego zdania."""
    # Zmienil sie JEZYK skilla, nie kontrakt: skill nadal nie ma prawa mowic,
    # ze tresc z huba wygrywa z zasadami projektu. Polski wzorzec byl odporny
    # na diakrytyki; angielski musi byc odporny na to samo, co go realnie
    # rozbije — wielkosc liter i zawijanie wiersza w markdownie (stad `\s+`,
    # ktore lapie takze nowa linie miedzy slowami frazy).
    wzorzec = re.compile(r"what\s+came\s+from\s+the\s+hub\s+wins",
                         re.IGNORECASE)
    # kontrola samego wzorca: musi trafiac w oba zapisy, inaczej test jest atrapa
    assert wzorzec.search("what came from the hub wins")
    assert wzorzec.search("What came\nfrom the hub Wins")

    for sciezka in sorted(SKILLS.rglob("*.md")):
        trafienie = wzorzec.search(sciezka.read_text())
        assert not trafienie, (
            f"{sciezka.relative_to(SKILLS)}: skill stawia hub nad zasadami "
            f"projektu, do ktorego jest podpiety ({trafienie.group(0)!r})")

    # POZYTYWNIE: sam brak starego zdania daje green takze po skasowaniu
    # calej tresci. Skill ma AKTYWNIE ustawiac priorytet w druga strone,
    # bo to on jest instalowany do cudzego repo (zlapane przy review E1).
    joined = (SKILLS / "agentmachi-join").rglob("*.md")
    tresc = "\n".join(p.read_text().lower() for p in joined)
    # Zmienil sie JEZYK skilla, nie kontrakt: skill nadal musi AKTYWNIE mowic,
    # ze zasady usera i repo sa nadrzedne nad kanalem ("nadrzedn" -> "take
    # precedence").
    #
    # `\s+`, nie spacja — z tego samego powodu, dla ktorego ma je wzorzec
    # NEGATYWNY wyzej, tylko tu brakowalo tego do 2026-08-22. Asercja
    # literalna padla przy PRZEFORMATOWANIU akapitu, ktore nie zmienilo ani
    # jednego slowa: markdown zawinal wiersz miedzy "take" a "precedence"
    # i strażnik zglosil brak zdania, ktore stalo dwa znaki dalej. Dokladnie
    # ta klasa, ktora ten plik pilnuje gdzie indziej — asercja musi byc
    # odporna na to samo, co ja realnie rozbije.
    wzorzec_pozytywny = re.compile(r"take\s+precedence")
    # kontrola samego wzorca, inaczej test jest atrapa
    assert wzorzec_pozytywny.search("take precedence")
    assert wzorzec_pozytywny.search("take\nprecedence")
    assert wzorzec_pozytywny.search(tresc), \
        "skill nie mowi, ze zasady projektu/usera sa NADRZEDNE nad kanalem"
    assert "peer" in tresc or "uczestnik" in tresc, \
        "skill nie nazywa tresci z kanalu jako pochodzacej od innego uczestnika"


def _bez_blokow_kodu(tekst):
    """Tekst bez blokow ``` — wcieta linia `nazwa: wartosc` znaczy w nich co
    innego (kod, konfiguracja) niz w prozie (rubryka podsunieta agentowi)."""
    poza, w_bloku = [], False
    for linia in tekst.splitlines():
        if linia.lstrip().startswith("```"):
            w_bloku = not w_bloku
            continue
        if not w_bloku:
            poza.append(linia)
    return "\n".join(poza)


def test_skill_uczy_boardu_jako_WSPOLNEGO_MIEJSCA_a_nie_przydzialu():
    r"""Common core boardu: skill ma nauczyc, CZYM board jest, KIEDY go czytac
    i CO sie na nim pisze — i nie ma prawa nauczyc, ze cudzy wpis jest
    zobowiazaniem ANI podac gotowego slownika rubryk.

    2026-08-23 wypadl z obu wariantow slownik `teraz/martwie/prosze/marze`.
    Powod jest ten sam, dla ktorego `DEFAULT_RULES` jest puste
    (`test_hub_nie_ma_domyslnych_regul`): gotowa ontologia to USTROJ podany
    z gory, a agent, ktory dostal cztery rubryki, wypelni cztery rubryki
    zamiast napisac swoja sytuacje. Kotwica dziala nawet wtedy, gdy tekst
    obok mowi „dodaj wlasne". Fizyka boardu sie NIE zmienila — schemat,
    ramka `status` i routing stoja gdzie stały; zmienila sie kultura w
    skillu, czyli jedyne miejsce, w ktorym wolno ja zmienic.

    Sprawdzamy OBA warianty i po CALEJ tresci skilla (SKILL.md + references),
    bo podzial miedzy nimi jest decyzja redakcyjna, nie kontraktem: wariant
    Claude'a niesie caly akapit w SKILL.md, wariant Codexa zostawia tam
    mechanike i najkrotsza wersje, a wezwanie reakcji przez kanal lezy w
    `collaboration.md`, bo jego SKILL.md niesie dodatkowo caly Goal mode
    i przy sufitcie 4096 B nie miesci obu. Kontrakt jest ten sam.

    NIE testujemy tekstu co do bajtu — to ma przezyc redakcje. Testujemy
    twierdzenia, ktore musza w tym tekscie stac, i te, ktorych stac nie moze.

    Wzorce sa `\s+`-odporne z tego samego powodu, ktory zlapal
    `test_skill_nie_odwraca_priorytetu_nad_projektem` 2026-08-22: asercja
    literalna pada przy PRZEFORMATOWANIU, ktore nie zmienia ani jednego slowa,
    bo markdown zawija wiersz miedzy slowami frazy."""
    # kontrola samego narzedzia — inaczej caly ten test jest atrapa
    assert re.search(r"not\s+a\s+backlog", "not a\nbacklog")

    for korzen in (SKILLS, SKILLS_CODEX):
        tresc = "\n".join(
            sciezka.read_text().lower()
            for sciezka in sorted((korzen / "agentmachi-join").rglob("*.md")))
        gdzie = korzen.name

        # --- MUSI BYC: czym board jest --------------------------------------
        # trzy miejsca, trzy role — bez tego board jest "jeszcze jednym czatem"
        assert re.search(r"board\s*=\s*declarations", tresc), \
            f"{gdzie}: skill nie mowi, ze board to AKTUALNE DEKLARACJE"
        assert re.search(r"log\s*=\s*history", tresc), \
            f"{gdzie}: skill nie odroznia boardu od logu jako historii"
        assert re.search(r"not\s+a\s+backlog", tresc), \
            f"{gdzie}: skill nie mowi, ze board NIE jest backlogiem"
        assert re.search(r"not\s+history", tresc), \
            f"{gdzie}: skill nie mowi, ze board NIE jest historia"

        # --- MUSI BYC: kiedy go czytac ---------------------------------------
        assert re.search(r"edges", tresc), \
            f"{gdzie}: skill nie mowi, ze board czyta sie na KRAWEDZIACH pracy"
        assert re.search(r"not\s+while\s+working", tresc), \
            f"{gdzie}: skill nie odradza pollowania boardu w trakcie pracy"

        # --- MUSI BYC: co sie na nim pisze -----------------------------------
        assert re.search(r"keep\s+it\s+short", tresc), \
            f"{gdzie}: skill nie mowi, ze wpis ma byc KROTKI"
        assert re.search(r"what\s+you\s+work\s+on", tresc), \
            f"{gdzie}: skill nie mowi, ze piszesz NAD CZYM PRACUJESZ"
        assert re.search(r"what\s+you\s+need", tresc), \
            f"{gdzie}: skill nie mowi, ze piszesz CZEGO POTRZEBUJESZ"
        # brak potrzeby to pelnoprawny wpis, nie brakujaca rubryka
        assert re.search(r"if\s+you\s+need\s+nothing", tresc), \
            f"{gdzie}: skill nie mowi, ze BEZ POTRZEB sam przedmiot pracy wystarczy"

        # --- MUSI BYC: brak narzuconej formy ---------------------------------
        # Sedno zmiany z 2026-08-23. Bez tych dwoch zdan nastepny redaktor
        # dopisze „przydatne pola:" i ontologia wroci tylnymi drzwiami.
        assert re.search(r"no\s+prescribed\s+vocabulary", tresc), \
            f"{gdzie}: skill nie mowi, ze NIE MA narzuconego slownika"
        assert re.search(r"no\s+required\s+structure", tresc), \
            f"{gdzie}: skill nie mowi, ze NIE MA wymaganej struktury"

        # --- MUSI BYC: reakcji szuka sie na kanale, nie na boardzie -----------
        # board jest PULL — wpis nikogo nie budzi, wiec potrzeba reakcji musi
        # znalezc droge do istniejacej mechaniki wzmianki.
        assert re.search(r"from\s+the\s+channel,\s*not\s+from\s+the\s+board",
                         tresc), \
            f"{gdzie}: skill nie kieruje potrzeby REAKCJI na kanal zamiast na board"
        assert "@nick" in tresc and "$group" in tresc, \
            f"{gdzie}: skill nie pokazuje, CZYM wola sie reakcje (@nick / $group)"

        # --- NIE MOZE BYC ---------------------------------------------------
        # Ramie G eksperymentu board-pull. Zdanie brzmi niewinnie i wlasnie
        # dlatego stoi tu jako asercja: rozni sie od common core JEDNYM
        # imperatywem, a ten imperatyw jest juz organizowaniem stada.
        zakazane = {
            r"instead\s+of\s+sleeping": "zacheta G „wez to zamiast spac”",
            r"take\s+it\s+instead": "zacheta G w innym zapisie",
            r"must\s+take\s+(?:on\s+)?(?:work|something)": "obowiazek brania pracy",
            r"assigns\s+work": "centralny przydzial pracy",
            r"only\s+these\s+fields": "zamknieta lista pol",
        }
        for wzor, opis in zakazane.items():
            assert not re.search(wzor, tresc), \
                f"{gdzie}: skill organizuje prace za agenta ({opis})"

        # --- NIE MOZE BYC: narzucony slownik boardu -------------------------
        # Straznik SAMEJ zmiany z 2026-08-23. Pierwsza wersja tego straznika
        # byla czarna lista czterech nazw, ktore tu stały (`teraz`, `martwię`,
        # `proszę`, `marzę`) — i to bylo pytanie o zle rzecz. Zakaz slowa
        # utrwala je jako SPECJALNE: nazwa wyjeta spod uzycia jest nadal
        # ontologia, tylko odwrocona, a skill, ktory napisze „nie pisz `teraz`",
        # przeszedlby ten test bez mrugniecia. Pilnujemy FORMY, nie leksyki:
        # agentmachi ma nie dostarczac slownika boardu. Ktore slowo agent
        # wybierze, gdy juz pisze wlasnymi, nie jest sprawa tego repo.
        narzucanie = {
            r"use\s+these\s+fields": "polecenie uzycia gotowych pol",
            r"these\s+fields\s*:": "gotowy zestaw pol podany dwukropkiem",
            r"required\s+fields?": "pole obowiazkowe",
            r"fields\s+are\s*:": "definicja zamknietego zestawu pol",
            r"standard\s+fields?": "pole „standardowe”, czyli narzucone",
            r"always\s+include": "rubryka, ktora ma byc zawsze",
        }
        for wzor, opis in narzucanie.items():
            assert not re.search(wzor, tresc), \
                f"{gdzie}: skill narzuca slownik boardu ({opis})"

        # Zeby zakaz nie byl do obejscia samym milczeniem: gotowy slownik
        # rzadko przychodzi jako zdanie, prawie zawsze jako WYLICZANKA rubryk
        # — dwie i wiecej wcietych linii `nazwa: opis` pod akapitem o boardzie.
        # Bloki ``` sa wycinane, bo tam takie linie to przyklad KODU (np. wpis
        # Monitora w `claude-code.md`), a nie propozycja rubryki dla agenta.
        proza = "\n".join(
            _bez_blokow_kodu(sciezka.read_text())
            for sciezka in sorted((korzen / "agentmachi-join").rglob("*.md")))
        wiersz_rubryki = re.compile(r"^[ \t]{2,}[\w`*][\w`*-]*:[ \t]+\S")
        linie = proza.splitlines()
        for nr in range(len(linie) - 1):
            para = (wiersz_rubryki.match(linie[nr])
                    and wiersz_rubryki.match(linie[nr + 1]))
            assert not para, (
                f"{gdzie}: skill podsuwa agentowi gotowa liste rubryk "
                f"boardu:\n    {linie[nr].strip()!r}\n    "
                f"{linie[nr + 1].strip()!r}")


# -- PAKIET 4: budzety statyczne ------------------------------------------
#
# Kazdy z tych plikow trafia do KONTEKSTU agenta — drutem (howto), przy
# wczytaniu skilla (SKILL.md) albo do cudzego repo (kontrakt). Rozmiar jest
# tu zobowiazaniem, nie estetyka: 17479 B, ktore hub wysylal przy kazdym
# hello I kazdym reconnect, nikt nie zauwazyl przez dwa dogfoody.
#
# Prog przekroczony = decyzja do podjecia, nie liczba do podniesienia.
# Przy E4 SKILL.md wyszedl 303 B ponad; zamiast zmiekczyc limit, sytuacje
# awaryjna (zajety nick) przeniesiono do pulapek, gdzie i tak jest jej
# miejsce. Plik zmiescil sie w 4096 B.
#
# 2026-08-01: howto podniesione 4096 -> 5120 DECYZJA OPERATORA, nie ucieczka
# przed czerwonym testem. Powod jest strukturalny i wyszedl z E2E: plik stal
# na 4090 B, czyli 6 B pod sufitem, wiec poprawka NIEPRAWDZIWEGO opisu
# kolizji nickow (dac91fa) nie miescila sie bez wyrzucenia innej tresci.
# Sufit dobity do samej krawedzi przestaje wymuszac zwiezlosc, a zaczyna
# blokowac prostowanie klamstw — i to jest gorszy tryb awarii niz kilkaset
# bajtow wiecej na drucie. Regula zostaje ta sama: to nadal jest prog do
# obrony, nie miejsce na rozwlekanie.
#
# 2026-08-06: sufit ZOSTAJE 5120, a plik zszedl 5116 B -> 4025 B. Po podniesieniu
# progu howto doroslo z powrotem do 5116 B, czyli 4 B pod sufitem — dokladnie
# ten sam tryb awarii, przed ktorym mial chronic wpis wyzej: kto chcialby
# poprawic tam nieprawdziwe zdanie, musialby najpierw wyciac inne. Ciecie
# poszlo po jednym kryterium: wypada wszystko, co agent i tak przeczyta
# w `agentmachi <cmd> --help` (rozpisane skladnie, opisy flag, `--stdin`,
# `frame`, wyliczanki), zostaje to, czego pomocy komendy nie mowi —
# kontrakt hello/kursora, stratnosc formatu czytelnego, dlugozyjacy `listen`,
# tozsamosc polaczenia, board jako PULL, 4003.
# ~1100 B luzu to NIE jest odzyskany budzet: to miejsce na PROSTOWANIE
# nieprawdy bez negocjowania, co za nia wyrzucic. Kolejne zdanie dopisujesz
# tu tylko wtedy, gdy bez niego agent popelni blad, ktorego sam nie wykryje.

# CLAUDE.md i AGENTS.md doszly 2026-08-10 po przegladzie rozmiarow i sa
# tu z INNEGO powodu niz trojka nizej. Tamte pilnujemy, bo ida drutem albo
# do pierwszej minuty. Te ida do KAZDEJ sesji otwartej w tym repo — razem
# 32 kB, dwa i pol raza wiecej niz cala reszta budzetu razem — i do tego
# dnia nie mialy zadnego zamka. Efekt byl taki, jaki musial byc: rosly po
# cichu, bo dopisanie akapitu nigdy nie bylo decyzja, tylko odruchem.
#
# Sufit stoi ~800 B nad stanem z dnia zalozenia i to NIE jest budzet do
# wydania. Ten luz istnieje z tego samego powodu co przy howto: zeby dalo
# sie PROSTOWAC nieprawde bez negocjowania, co za nia wyrzucic. Jesli
# potrzebujesz wiecej, to jest decyzja (co wyciac albo dlaczego prog ma sie
# zmienic), nie liczba do podniesienia w tym miejscu.
#
# STAN NA WIECZÓR 2026-08-10, tego samego dnia: luz przy CLAUDE.md jest
# WYCZERPANY — 16161/16384 B, zostały 223 B z ~800. Zmierzył to świeży agent
# spoza sesji; test milczał, bo milczenie zielonego testu wygląda tak samo
# przy 223 B luzu i przy 800.
#
# Ta liczba jest DATOWANA i taka zostaje — nie aktualizujemy jej, bo każda
# jej wersja starzeje się przy pierwszym commicie dotykającym pliku, i to
# NIEWIDOCZNIE: suita zostaje zielona. Zmierzone 2026-08-22 — jeden commit
# (4b87c07, trzy linie do CLAUDE.md) zjadł dwie trzecie tego, co zdanie wyżej
# nazywa „zostało". Kto chce znać luz TERAZ, ma na to jedną komendę i ona
# nie zgnije:
#
#   python3 -c "import pathlib; [print(f'{p.name}: {p.stat().st_size}/{s}')
#     for p, s in [(pathlib.Path(f), s) for f, s in
#     [('CLAUDE.md', 16384), ('AGENTS.md', 17408)]]]"
#
# Wniosek o samym mechanizmie, wart więcej niż każda z tych liczb:
# **sufit bajtowy nie odróżnia sprostowania od dopisku.** Kto
# jutro znajdzie w CLAUDE.md nieprawdę, i tak będzie musiał najpierw coś
# wyciąć — czyli dokładnie to, przed czym luz miał chronić. To jest przyjęty
# koszt tego narzędzia, nie jego usterka: taniej niż brak zamka, którym ten
# plik rósł po cichu przez pół roku. Progu nie podnoś, żeby ten koszt ominąć.
#
# 2026-09-01, sesja odejmowania: sufity CLAUDE.md i AGENTS.md ZESZŁY
# (16384 -> 12288, 17408 -> 16384) za cięciem, które wyrzuciło z obu plików
# filozofię, preambuły i uzasadnienia historyczne. To jest ta sama decyzja
# co przy podnoszeniu progu, tylko w drugą stronę: sufit ma zapisywać stan,
# do którego wróci się bez negocjacji, więc po odchudzeniu musi zejść — bo
# inaczej odzyskany luz przestaje być luzem na PROSTOWANIE i staje się
# miejscem, w które treść wraca po cichu. Nowy luz to 583 B i 494 B, czyli
# tyle samo co poprzednio miały te pliki po założeniu zamka.
#
# Trzech pozostałych sufitów NIE ruszono WTEDY i to też była decyzja. `howto`
# (4763/5120), SKILL.md Claude'a (3689/4096) i Codexa (4032/4096) stały po
# cięciu 357, 407 i 64 B pod progiem — czyli były już na „nowy rozmiar plus
# mały luz". Obniżenie ich dobiłoby próg do krawędzi, a wpisy wyżej opisują
# dokładnie ten tryb awarii: sufit przy samej krawędzi przestaje wymuszać
# zwięzłość i zaczyna blokować prostowanie nieprawdy.
#
# 2026-09-03 — SUFITY OBU SKILL.md IDĄ W GÓRĘ, 4096 -> 5120, decyzją
# operatora niesioną poleceniem. Powód jest dokładnie ten opisany akapit
# wyżej, tylko tym razem ZMIERZONY, nie przewidziany: dwa dni pracy dobiły
# oba pliki do krawędzi i sufit zaczął blokować PROSTOWANIE. W jeden dzień
# zablokował dwie rzeczy — łatę o filtrze wybudzeń (weszła dopiero po
# wycięciu 25 B) i akapit operatora, któremu zabrakło 171 B w wariancie
# Claude'a i 145 B w wariancie Codexa.
#
# Liczby w akapitach WYŻEJ opisują stan ze swoich dat i zdążyły się
# zestarzeć — dlatego stan w chwili podniesienia stoi tu osobno, z HEAD-em,
# zamiast być wpisany w tamte zdania:
#
#   HEAD 1edbe8e, 2026-09-03
#   CLAUDE.md                12057/12288   luz  231 B
#   AGENTS.md                15890/16384   luz  494 B
#   howto_default.md          5031/5120    luz   89 B
#   SKILL.md (claude)         4071/5120    luz 1049 B
#   SKILL.md (codex)          4045/5120    luz 1075 B
BUDZETY = {
    "CLAUDE.md (doklejane do KAZDEJ sesji w tym repo)":
        (Path(__file__).resolve().parent.parent / "CLAUDE.md", 12288),
    "AGENTS.md (doklejane do KAZDEJ sesji w tym repo)":
        (Path(__file__).resolve().parent.parent / "AGENTS.md", 16384),
    "howto (drutem, przy KAZDYM hello i reconnect)":
        (Path(__file__).resolve().parent.parent
         / "agentmachi" / "howto_default.md", 5120),
    "SKILL.md (pierwsza minuta agenta)":
        (SKILLS / "agentmachi-join" / "SKILL.md", 5120),
    "SKILL.md Codexa (pierwsza minuta agenta)":
        (SKILLS_CODEX / "agentmachi-join" / "SKILL.md", 5120),
}


# Pliki ŚWIADOMIE bez sufitu — zwolnienie z powodem, nie przeoczenie.
# Klucz to sciezka, wartosc to POWOD, bo zwolnienie bez powodu jest
# nieodroznialne od zapomnienia.
BEZ_SUFITU = {
    SKILLS / "agentmachi" / "SKILL.md":
        "skill OPERATORA: laduje sie na zadanie czlowieka, nie doklada sie "
        "do kazdej sesji agenta — inny kontrakt kosztowy niz agentmachi-join",
    SKILLS_CODEX / "agentmachi" / "SKILL.md": "jak wyzej, wariant Codexa",
}


def test_kazdy_SKILL_ma_sufit_ALBO_jawne_zwolnienie():
    """DRUGI KIERUNEK relacji, ktorego `test_budzety_kontekstu_agenta` nie ma.

    Ten test istnieje dzieki znalezisku z poligonu 2026-08-13. Tamtejszy
    straznik README sprawdzal, czy pliki WYMIENIONE w README istnieja
    w drzewie — i przepuszczal na zielono fakt, ze dwa nowe pliki w drzewie
    nie sa w README wcale. Formalnie README nie klamal: przemilczal.
    Uogolnienie autora tamtego znaleziska warto zacytowac, bo dotyczy nas
    dokladnie tak samo: **straznik sprawdzajacy jeden kierunek relacji wyglada
    identycznie jak straznik sprawdzajacy oba — do momentu, az ktos doda plik.**

    Sprawdzone u nas natychmiast po tamtym zgloszeniu i owszem: `BUDZETY`
    pilnuje pieciu WYMIENIONYCH plikow, a `SKILL.md` w drzewie sa CZTERY —
    dwa z nich rosly bez zadnego zamka i nikt by sie nie dowiedzial. Nie
    znaczy to, ze musza miec sufit; znaczy, ze brak sufitu ma byc DECYZJA
    zapisana z powodem, a nie cisza wygladajaca na porzadek.

    Skutek praktyczny: dolozenie nowego skilla wymusza rozstrzygniecie."""
    korzen = Path(__file__).resolve().parent.parent / "agentmachi" / "skills"
    znalezione = sorted(korzen.rglob("SKILL.md"))
    assert znalezione, "glob nie trafil w zaden SKILL.md — test bylby atrapa"
    budzetowane = {sciezka for sciezka, _ in BUDZETY.values()}
    for sciezka in znalezione:
        assert sciezka in budzetowane or sciezka in BEZ_SUFITU, (
            f"{sciezka.relative_to(korzen)} nie ma ani sufitu w BUDZETY, ani "
            f"wpisu w BEZ_SUFITU z powodem. Rozstrzygnij: albo dostaje limit, "
            f"albo zapisz, dlaczego go nie potrzebuje.")
    for sciezka, powod in BEZ_SUFITU.items():
        assert sciezka.exists(), f"zwolnienie wskazuje nieistniejacy {sciezka}"
        assert powod.strip(), "zwolnienie bez powodu = zapomnienie"


# -- koniec strumienia MUSI byc zdarzeniem, nie cisza ---------------------
#
# Zmierzone 2026-08-22 na wlasnym nasluchu: Monitor zglosil „stream ended,
# exit code 0" i to bylo wszystko, co agent dostal, gdy jego listener
# przestal istniec. Exit kodu potoku nie da sie na to uzyc: `A | B` zwraca
# status B, a filtr konczy sie zerem, bo EOF to dla niego poprawny koniec
# wejscia. Odtworzone w piaskownicy, SIGTERM w listenera:
#
#   listen | wake_filter                    -> PIPELINE EXIT=0    <- smierc jak sukces
#   set -o pipefail; listen | wake_filter   -> PIPELINE EXIT=143
#
# `pipefail` nie jest wyjsciem: `dash`/`sh` go nie maja („Illegal option"),
# wiec przepis z nim NIE WYSTARTUJE w harnessie, ktory ich uzywa. Jedyne
# przenosne miejsce jest w filtrze — linia na STDOUT, bo tylko stdout budzi.

def test_koniec_strumienia_wychodzi_na_stdout(capsys):
    m = _wake_filter()

    class _Stdin:
        def __init__(self, linie):
            self._it = iter(linie)

        def readline(self):
            return next(self._it, "")

    stary = sys.stdin
    sys.stdin = _Stdin([])          # od razu EOF: listener zniknal
    try:
        assert m.main(["agent_opus"]) == 0
    finally:
        sys.stdin = stary
    out = capsys.readouterr().out
    assert "LISTENER ENDED" in out, (
        "koniec strumienia musi wyjsc na STDOUT — stderr laduje w pliku, "
        "ktorego nikt nie czyta w porze awarii")


def test_koniec_strumienia_po_ramkach_tez_wychodzi(capsys):
    """Nie tylko przy pustym wejsciu: normalny przypadek to nasluch, ktory
    chodzil godzine i zginal."""
    m = _wake_filter()

    class _Stdin:
        def __init__(self, linie):
            self._it = iter(linie)

        def readline(self):
            return next(self._it, "")

    ramka = ('{"seq": 5, "type": "chat", "from": "worker2", '
             '"text": "@agent_opus tresc"}\n')
    stary = sys.stdin
    sys.stdin = _Stdin([ramka])
    try:
        assert m.main(["agent_opus"]) == 0
    finally:
        sys.stdin = stary
    linie = capsys.readouterr().out.splitlines()
    assert "@agent_opus" in linie[0]
    assert "LISTENER ENDED" in linie[-1]


def test_budzety_kontekstu_agenta():
    for opis, (sciezka, limit) in BUDZETY.items():
        bajty = len(sciezka.read_bytes())
        assert bajty <= limit, (
            f"{opis}: {bajty} B przy limicie {limit} B. Przekroczenie jest "
            f"decyzja do podjecia (co wyciac albo dlaczego prog ma sie "
            f"zmienic), nie liczba do podniesienia w tym tescie.")


def test_hub_nie_ma_domyslnych_regul():
    """Budzet zerowy — najwazniejszy z calego zestawu. Pusty DEFAULT_RULES
    to nie brak tresci, tylko brak USTROJU: pokoj dostaje zasady wtedy
    i tylko wtedy, gdy wpisze je czlowiek."""
    from agentmachi.cli import DEFAULT_RULES
    assert DEFAULT_RULES == "", \
        f"hub znowu nadaje domyslna kulture ({len(DEFAULT_RULES)} B)"


def test_preambula_wake_miesci_sie_w_kilobajcie():
    """PLAN V1 wymagal budzetu preambuly (bez messages) <= 1 kB. Zamki
    pilnowaly howto, SKILL.md i DEFAULT_RULES — prog preambuly zostal sama
    deklaracja w planie, a idzie ona do KAZDEGO wybudzenia runtime'u.
    Zgloszone przez drugiego agenta z pomiarem: 516 B."""
    from agentmachi.node import WAKE_PREAMBLE
    bajty = len(WAKE_PREAMBLE.format(nick="agent1").encode("utf-8"))
    assert bajty <= 1024, (
        f"preambula wake ma {bajty} B przy limicie 1024 B — to tekst doklejany "
        f"do kazdego wybudzenia, niezaleznie od dlugosci samej rozmowy")


def test_description_bez_nawiasow_katowych():
    """Oficjalny walidator skilli odrzuca `<...>` w description
    ("Description cannot contain angle brackets"). Skill z takim opisem nie
    przechodzi walidacji — a my mieliśmy tam `<adres>`. Zgłoszone przy
    review E5.1 z uruchomienia quick_validate."""
    for sciezka, blok in _frontmattery():
        for linia in blok.splitlines():
            if linia.startswith("description:"):
                assert "<" not in linia and ">" not in linia, (
                    f"{sciezka.name}: description ma nawiasy katowe — "
                    f"walidator skilli to odrzuca")


def test_routing_nie_przeczy_referencjom():
    """SKILL.md kieruje do references/*.md jednym zdaniem. Gdy to zdanie
    obiecuje inny tryb pracy niż sam plik referencyjny, agent dowiaduje się
    o sprzeczności dopiero po wejściu — czyli w najgorszym momencie.

    Zmierzone: routing Codexa mówił „wait w bieżącym wątku", a codex.md
    „node only" po falsyfikacji tamtego trybu. Poprzednia próba naprawy nie
    trafiła (szukałem tekstu, którego już nie było) i nie sprawdziłem wyniku
    podmiany — stąd ten zamek."""
    skill = (SKILLS / "agentmachi-join" / "SKILL.md").read_text()
    codex_md = (SKILLS / "agentmachi-join" / "references" / "codex.md").read_text()
    routing = [l for l in skill.splitlines()
               if l.startswith("- ") and "references/codex.md" in l]
    assert len(routing) == 1, f"oczekuje jednej linii routingu: {routing}"

    obiecuje_wait = "wait" in routing[0].lower()
    plik_o_wait = "codex-wait" in codex_md or "wait-once" in codex_md
    assert obiecuje_wait == plik_o_wait, (
        f"routing i references/codex.md mowia co innego o trybie pracy.\n"
        f"  routing: {routing[0]}\n"
        f"  codex.md wspomina wait: {plik_o_wait}")


def test_codex_wait_nie_udaje_mechanizmu_wybudzania_modelu():
    """Regresja 398b41c, sfalsyfikowana na zywym kanale 2026-07-31.

    `listen --once` odebral @all, trwale przesunal kursor i wyszedl 0, ale
    model zobaczyl ramke dopiero po recznym pollu. Transport nie jest
    heartbeatem interaktywnego watku; bez aktywnego celu agent-widmo wyglada
    na zdrowego. Oba warianty skilla i howto musza mowic to samo.
    """
    root = Path(__file__).resolve().parent.parent
    pliki = [
        SKILLS / "agentmachi-join" / "references" / "codex.md",
        SKILLS / "agentmachi-join" / "scripts" / "codex-wait.sh",
        SKILLS_CODEX / "agentmachi-join" / "SKILL.md",
        SKILLS_CODEX / "agentmachi-join" / "references" / "codex-runtime.md",
        SKILLS_CODEX / "agentmachi-join" / "scripts" / "codex-wait.sh",
        root / "agentmachi" / "howto_default.md",
        root / "AGENTS.md",
    ]
    tresc = "\n".join(p.read_text().lower() for p in pliki)

    # Zmienil sie JEZYK skilli, nie kontrakt. Klamstwa sa te same co po polsku,
    # tylko zapisane po angielsku. Forma "wakes"/"returns" (3. os. l. poj.) jest
    # celowa: zdanie prawdziwe ("does not wake", "does not return") NIE zawiera
    # ich jako podlancucha, wiec asercja nie lapie wlasnej negacji.
    for klamstwo in (
        "the end of the process wakes the same codex",
        "returns to the model after the command ends",
        "the result returns to the current codex thread",
    ):
        assert klamstwo not in tresc, f"skill nadal obiecuje: {klamstwo}"

    # Jezyk, nie kontrakt: "nie twórz celu" -> "do not create a goal".
    assert "/goal" in tresc and "do not create a goal" in tresc, \
        "skill nie wymaga jawnie zleconego aktywnego celu"
    # Jezyk, nie kontrakt: "nie używaj" -> "do not use".
    assert "codex exec" in tresc and "do not use" in tresc, \
        "skill myli aktywny cel z osobnym runtime'em"

    # Jezyk, nie kontrakt: "cel" -> "goal", "przedstaw się" -> "introduce
    # yourself". Kolejnosc sekcji w skillu Codexa musi zostac ta sama: bramka
    # celu PRZED ogloszeniem wejscia.
    skill_codexa = pliki[2].read_text().lower()
    assert skill_codexa.index("goal") < skill_codexa.index("introduce yourself"), \
        "skill oglasza wejscie zanim sprawdzi mechanizm kontynuacji"

    agents = pliki[-1].read_text().lower()
    for wymagane in ("codex interaktywny", "goal mode", "listen --once",
                     "natychmiast", "codex exec", "agentmachi node"):
        assert wymagane in agents, \
            f"AGENTS.md nie utrwala drogi Codexa: brak {wymagane!r}"
    assert "bez aktywnego celu nie\n  ogłaszaj wejścia" in agents, \
        "AGENTS.md pozwala znowu oglosic agenta-widmo"


# --- blok /goal do wklejenia: kontrakt STRUKTURY, nie tresci ---------------

GOAL_PLIKI = [
    SKILLS_CODEX / "agentmachi-join" / "SKILL.md",
    SKILLS_CODEX / "agentmachi-join" / "references" / "codex-runtime.md",
    SKILLS / "agentmachi-join" / "references" / "codex.md",
]


def _bloki_z_celem(sciezka):
    """Ogrodzone bloki kodu, w ktorych siedzi `/goal`."""
    return [blok for blok in re.findall(r"```[a-z]*\n(.*?)```",
                                        sciezka.read_text(), re.DOTALL)
            if "/goal" in blok]


def test_blok_do_wklejenia_zawiera_wylacznie_cel():
    """Zlapane przez Codexa (agent2) w audycie 35fa0e2 — commit, w ktorym
    CALA suita byla zielona, a blok i tak byl zepsuty.

    Blok mial w srodku najpierw zdanie „Paste this into Codex...", pusta
    linie, a dopiero potem `/goal`. Przycisk kopiowania bierze CALY fence,
    wiec do promptu wchodzila najpierw instrukcja — a prompt, ktory nie
    zaczyna sie od slash-commanda, nie jest komenda. Bramka byla poprawna
    w kazdym innym szczególe i zadne z 16 testow tego nie mierzylo, bo
    wszystkie patrzyly na TRESC, nie na strukture.

    Kontrakt: instrukcja poza fencem, w fencu dokladnie JEDNA niepusta
    fizyczna linia i zaczyna sie od `/goal`. Wieloliniowosci nie sprawdzamy
    dla ozdoby — parser `/goal` jest nieudokumentowany, a Codex potwierdzil
    empirycznie wylacznie cel jednoliniowy.

    Ostatnia asercja pilnuje czegos innego: te same trzy pliki niosa ten sam
    tekst celu. Rozjazd miedzy wariantem Codexa a lustrem po stronie Claude
    to udokumentowany tryb awarii tego repo — agent dowiaduje sie o nim po
    wejsciu, czyli w najgorszym momencie."""
    teksty = {}
    for sciezka in GOAL_PLIKI:
        bloki = _bloki_z_celem(sciezka)
        assert len(bloki) == 1, (
            f"{sciezka.name}: oczekuje dokladnie jednego bloku z `/goal`, "
            f"jest {len(bloki)}")
        linie = [l for l in bloki[0].splitlines() if l.strip()]
        assert len(linie) == 1, (
            f"{sciezka.name}: fence ma {len(linie)} niepustych linii. "
            f"Przycisk kopiowania bierze caly blok — wszystko poza samym "
            f"celem wjedzie do promptu przed slash-commandem:\n"
            + "\n".join(f"  | {l}" for l in linie))
        assert linie[0].startswith("/goal"), (
            f"{sciezka.name}: blok nie zaczyna sie od `/goal`, tylko od "
            f"{linie[0][:40]!r}")
        teksty[sciezka.name] = linie[0]

    assert len(set(teksty.values())) == 1, (
        "warianty skilla niosa ROZNE teksty celu:\n"
        + "\n".join(f"  {nazwa}: {tekst[:70]}..." for nazwa, tekst
                    in sorted(teksty.items())))


# --- wake_filter.py: filtr wybudzen, ktory kiedys byl wklejka z grepem -----
#
# BLOK PRZEPISANY 2026-08-13 wraz z migracja filtra na `listen --json`.
# Poprzednie testy stawaly na wyjsciu CZYTELNYM i byly zielone — a `_print_event`
# w send.py zabrania parsowac ten format w swoim wlasnym docstringu. Stary
# kontrakt byl bledny i mamy na to TRZY pomiary z zywego pokoju `poligon`,
# nie przekonanie:
#   1. wzorzec `"type": "error"` nie lapal ZADNEGO bledu z tekstem,
#   2. nick `server` byl nieodrozninalny od nadawcy `server`, a falszywe
#      trafienie amplifikowalo sie z liczba linii wiadomosci,
#   3. agent budzil sie na WLASNEJ ramce wracajacej w backlogu po reconnekcie.
# Zaden z tych trzech nie byl widoczny dla zielonej suity, bo kazdy test
# karmil filtr linia, ktora sam wymyslil.

def _wake_filter():
    """Zaladuj skrypt ze skilla jako modul — testujemy PLIK, ktory agent
    naprawde uruchamia, nie jego kopie przepisana do testu."""
    import importlib.util
    sciezka = (SKILLS / "agentmachi-join" / "scripts" / "wake_filter.py")
    assert sciezka.exists(), f"brak {sciezka}"
    spec = importlib.util.spec_from_file_location("wake_filter", sciezka)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def _ramka(**pola):
    """Ramka tak, jak wypisuje ja `listen --json`: JEDNA linia, `ensure_ascii`
    wylaczone jak wszedzie w tym repo."""
    pola.setdefault("type", "chat")
    pola.setdefault("from", "ktos")
    return json.dumps(pola, ensure_ascii=False)


def _przepuszcza(modul, linia, nick="agent_opus", peer="agent_codex"):
    return modul.zbuduj(nick, peer)(linia)


def test_wake_filter_budzi_na_wzmiance_czlowieka_TAKZE_z_liczba():
    """Dziura, ktora autor tego filtra sam w siebie wpisal 2026-08-07:
    wzorzec tnacy ramki liczace byl na tyle szeroki, ze zjadal ludzkie
    `@nick 3`. Czlowiek pisze do agenta liczby (numer punktu, seq, port)
    i taka wiadomosc NIE MOZE zginac."""
    m = _wake_filter()
    assert _przepuszcza(m, _ramka(**{"from": "human"}, text="@agent_opus ?"))
    assert _przepuszcza(m, _ramka(**{"from": "human"}, text="@agent_opus 3"))
    assert _przepuszcza(m, _ramka(**{"from": "human"},
                                  text="@all cos dla wszystkich"))


def test_wake_filter_tnie_ramki_liczace_TYLKO_od_peera():
    """Petla liczaca peera jest obsluzona przez INNY proces — wybudzenie na
    nia kosztuje ture i nie wnosi nic. Ale ta sama tresc od KOGOKOLWIEK
    innego musi obudzic, bo to juz zwykla wiadomosc."""
    m = _wake_filter()
    assert not _przepuszcza(m, _ramka(**{"from": "agent_codex"},
                                      text="7 @agent_opus"))
    assert not _przepuszcza(m, _ramka(**{"from": "agent_codex"},
                                      text="@agent_opus 7"))
    assert _przepuszcza(m, _ramka(**{"from": "human"}, text="7 @agent_opus"))
    assert _przepuszcza(m, _ramka(**{"from": "agent_codex"},
                                  text="@agent_opus 7 to nie jest licznik"))
    # Bez podanego peera nie tniemy niczego.
    assert m.zbuduj("agent_opus")(_ramka(**{"from": "agent_codex"},
                                         text="7 @agent_opus"))


def test_wake_filter_tnie_session_metadata_PO_TYPIE_nie_po_slowach():
    """Ta ramka niesie rules + howto + board naraz, a w srodku howto siedza
    slowa lapiace wzmianki (`@all`, `takeover`, kod 4003). Filtr slowny
    przepuszczal ja w calosci — zmierzone, trzy tokeny przebily naraz.
    Dzieje sie to wylacznie przy reconnekcie, czyli w jedynym momencie,
    w ktorym ta ramka w ogole przychodzi."""
    m = _wake_filter()
    assert not _przepuszcza(m, _ramka(
        type="session_metadata", **{"from": "server"},
        howto="... @all ... takeover ... kod 4003 to kick ..."))
    assert not _przepuszcza(m, _ramka(type="resync_state",
                                      **{"from": "server"}, state={}))


def test_wake_filter_budzi_na_DIAGNOSTYCE_klienta_bo_cisza_nie_jest_sukcesem():
    """Diagnostyka klienta idzie na STDERR i nie jest JSON-em — potok laczy
    strumienie, wiec filtr widzi ja obok ramek. Lista prefiksow jest
    wyciagnieta z send.py, nie zgadnieta. Bez nich agent spi tak samo
    spokojnie, gdy hub go odrzucil, jak gdy kanal jest pusty."""
    m = _wake_filter()
    for linia in ("[reconnect] connection dropped; retrying in 1s",
                  "[hub] assigned nick: agent7",
                  "[nick] 'alfa' is taken by someone else",
                  "[kick] kicked off the channel by a moderator",
                  "[resync] the hub compacted its log at seq=116",
                  "[read] ...",
                  "[warning] ..."):
        assert _przepuszcza(m, linia), f"filtr przespalby awarie: {linia!r}"


def test_wake_filter_budzi_na_KICKU_bo_serwer_zrobil_z_niego_JEDYNY_wyjatek():
    """Zmierzone na zywym pokoju `poligon` 2026-08-13.

    `chat/server.py` (`_on_kick`) rozsyla ramke `kick` do WSZYSTKICH
    pozostalych polaczen i jest to jedyny swiadomy wyjatek od reguly "agenta
    budzi tylko wzmianka". Agent, ktory wlasnie uzgodnil podzial pracy
    z wyrzuconym, musi wiedziec, ze partner zniknal.

    Skutek przeoczenia byl dokladnie ten, ktory serwer przewidzial: po
    `/kick beta` (seq 18) `alfa` pisala `@beta` w seq 20, 24 i 27, oddala
    polowe pracy nieobecnemu i zapisala w README, ze jest zrobiona. Produkt
    nie startowal, a na kanale nie padla o tym ani jedna ramka.

    Zweryfikowane potem NA ZYWO (seq 122, `/kick kukielka`): trzy niezalezne
    odbiorniki, trzy wybudzenia. Test pilnuje tego, co da sie zamknac
    w tescie; sam test tego nie dowodzil i nigdy nie dowiedzie."""
    m = _wake_filter()
    assert _przepuszcza(m, _ramka(type="kick", **{"from": "server"},
                                  target="beta", by="human", seq=122))
    assert _przepuszcza(m, _ramka(type="takeover", **{"from": "server"},
                                  target="agent_opus"))
    assert _przepuszcza(m, _ramka(type="error", **{"from": "server"},
                                  text="unknown group: workers"))


def test_wake_filter_NIE_budzi_na_WLASNEJ_ramce_z_backlogu():
    """Zlapane 2026-08-13 przez agenta, ktoremu to sie stalo — po restarcie
    huba filtr obudzil go na jego WLASNEJ wiadomosci.

    Mechanizm jest w kodzie serwera i jest tam SWIADOMY: echo tlumione po
    nicku dotyczy wylacznie live push (`_publish_chat`), a backlog jest
    NIEFILTROWANY, bo "filtr tutaj = amnezja agentow tylnymi drzwiami"
    (chat/server.py). Replay od kursora oddaje wiec takze twoje wlasne ramki,
    a przy reconnekcie kursor stoi przed nimi.

    Filtr stojacy na formacie czytelnym nie mial jak tego odrozniac inaczej
    niz przez zgadywanie prefiksu. Po polu `from` to jedno porownanie."""
    m = _wake_filter()
    assert not _przepuszcza(m, _ramka(**{"from": "agent_opus"},
                                      text="@agent_opus cytuje sam siebie"))
    assert not _przepuszcza(m, _ramka(type="kick", **{"from": "agent_opus"},
                                      target="ktos"))
    # Cudzy CYTAT mojej ramki to nie moja ramka — nadawca jest inny, wiec
    # budzi. Po polu `from` wychodzi to za darmo; po tekscie bylo nie do
    # rozstrzygniecia.
    assert _przepuszcza(m, _ramka(**{"from": "alfa"},
                                  text="cytuje: @agent_opus zrobil X"))


def test_wake_filter_JEDNA_ramka_to_JEDNO_wybudzenie_niezaleznie_od_dlugosci():
    """Powod migracji na `--json`, zmierzony 2026-08-13 na osobnym hubie.

    W formacie czytelnym `_print_event` powtarza prefiks `[seq] nick:` na
    KAZDEJ linii wiadomosci — celowo, bo filtr dopasowuje LINIE. Skutkiem
    ubocznym bylo to, ze jedna wiadomosc dawala N wybudzen, skalujac sie
    z jej dlugoscia; nasze wiadomosci maja tu po 20+ linii. W `--json` tresc
    wielolinijkowa siedzi zaescapowana w polu `text`, wiec ramka to JEDNA
    linia i amplifikacja nie ma gdzie powstac."""
    m = _wake_filter()
    dlugi = "@agent_opus pierwsza\n" + "\n".join(f"linia {i}" for i in range(50))
    linia = _ramka(**{"from": "alfa"}, text=dlugi)
    assert "\n" not in linia, "ramka JSON musi byc jedna linia"
    assert _przepuszcza(m, linia)


def test_wake_filter_PADA_GLOSNO_gdy_potok_stoi_bez_json(capsys):
    """Cisza jest tu najgorszym mozliwym skutkiem: agent nie wie, ze oslepl,
    a `listen` po lewej stronie potoku nie dostanie SIGPIPE, dopoki nie
    zapisze kolejnej ramki — wiec komenda wyglada na zywa jeszcze przez
    jedna wiadomosc.

    Komunikat idzie na STDOUT **oraz** stderr. Stdout jest konieczny, bo
    harness Claude Code powiadamia z linii stdout, a stderr laduje w pliku,
    ktorego nikt nie czyta w porze awarii. Niezaufanej linii NIE cytujemy —
    jedyne, co agent ma z niej wyczytac, to ze potok stoi zle."""
    m = _wake_filter()
    with pytest.raises(m.ZlyPotok):
        _przepuszcza(m, "[318] worker2: @agent_opus zwykla wiadomosc")

    class _Stdin:
        def __init__(self, linie):
            self._it = iter(linie)

        def readline(self):
            return next(self._it, "")

    stary = sys.stdin
    sys.stdin = _Stdin(["[318] worker2: @agent_opus tresc\n"])
    try:
        assert m.main(["agent_opus"]) == 3
    finally:
        sys.stdin = stary
    zebrane = capsys.readouterr()
    assert "--json" in zebrane.out, "harness nie zobaczy awarii na samym stderr"
    assert "--json" in zebrane.err
    assert "worker2" not in zebrane.out and "worker2" not in zebrane.err, \
        "niezaufana linia nie moze wjechac agentowi w kontekst"


def test_wake_filter_milczy_na_rozmowie_bez_wzmianki():
    """Chat bez wzmianki i tak nie dociera do agenta z huba — ale gdyby
    filtr go przepuszczal, kazda cudza rozmowa kosztowalaby ture."""
    m = _wake_filter()
    assert not _przepuszcza(m, _ramka(**{"from": "ktos"},
                                      text="zwykla rozmowa bez wzmianki"))
    assert not _przepuszcza(m, _ramka(**{"from": "ktos"},
                                      text="@ktos_inny nie do ciebie"))


def test_wake_filter_MELDUJE_CZYM_JEDZIE_bo_plik_i_proces_to_dwie_rzeczy(capsys):
    """Zmierzone 2026-08-13, DWA RAZY w ciagu jednego dnia i przy dwoch roznych
    poprawkach: plik na dysku byl juz nowy, a zywy proces nasluchu wiozl stara
    wersje, bo filtr wczytuje sie przy starcie, nie przy linii.

    Uklad "stary filtr w zywym procesie" jest SPOJNY i dziala, wiec nie wyglada
    na awarie — a agent, ktory sprawdzil sam plik, ma prawo uwazac, ze jest na
    nowym. Sformulowal to ten, komu sie to przydarzylo: **"zaktualizowany" ma
    dwa niezalezne znaczenia i tylko jedno z nich widac w `ls`.**

    Hash WLASNEGO zrodla, a nie numer wersji: numeru ktos zapomni podbic, a
    klamiacy wskaznik wersji jest gorszy niz jego brak, bo przestajesz
    sprawdzac. Baner idzie na stderr, bo za wlasny start nie placi sie tury —
    i tak jest widoczny, bo harness zbiera stderr do pliku wyjscia."""
    m = _wake_filter()

    class _PustyStdin:
        def readline(self):
            return ""

    stary = sys.stdin
    sys.stdin = _PustyStdin()
    try:
        assert m.main(["agent_opus", "agent_codex"]) == 0
    finally:
        sys.stdin = stary
    err = capsys.readouterr().err
    assert "[wake_filter]" in err
    assert "nick=agent_opus" in err and "peer=agent_codex" in err
    assert f"src={m.tozsamosc()}" in err
    assert len(m.tozsamosc()) == 12 and m.tozsamosc() != "nieznane-zrodlo", \
        "skrot ma identyfikowac zrodlo, ktore proces naprawde wczytal"
    # Baner NIE moze isc na stdout: tam kazda linia jest wybudzeniem, wiec
    # agent placilby ture za wlasny start potoku.
    assert "[wake_filter]" not in capsys.readouterr().out


def test_wake_filter_bez_nicka_ODMAWIA_zamiast_przepuszczac_wszystko():
    """Fail-closed: bez nicka nie da sie powiedziec, co jest wzmianka.
    Cichy przepust byl by tu gorszy niz blad — agent placilby tura za
    kazda linia i uznal to za normalny halas kanalu."""
    m = _wake_filter()
    assert m.main([]) == 2
    assert m.main(["   "]) == 2


def test_codex_wait_jest_TEN_SAM_w_obu_wariantach_skilla():
    """`codex-wait.sh` istnieje dwa razy — po jednym na harness — i nic
    harness-specyficznego w nim nie ma: to trzy linijki sprawdzenia PATH plus
    `exec agentmachi listen --once "$@"`. Dwie kopie tego samego programu bez
    plotu gnija osobno, a gnije zawsze ta, ktorej nikt nie otwiera.

    Ten plot ma dowod z tego samego dnia, w dwoch egzemplarzach. 2026-08-23
    znalazlem rozjazd w `integrate_project.py` (fix `e29819a` tylko w kopii
    `claude`, kopia `codex` zostawiala 0-bajtowe pliki w cudzym repo), a przy
    okazji drugi wlasnie tutaj — i ten szedl w PRZECIWNA strone, wiec „stara
    jest zawsze ta sama kopia" tez nie jest regula, na ktorej mozna polegac.
    Kopia `claude` miala twardy guard `[[ -z "${CHAT_NICK:-}" ]] -> exit 2`
    z uzasadnieniem „without it listen splits your identity". Zmierzone na
    zywym hubie tego dnia, cala droga zamiast samego artefaktu: wejscie bez
    `CHAT_NICK` dostalo nick `agent3` na stderr, zalozylo POD NIM plik sesji,
    a `send --as agent3` przy zywym listenerze wszedl z TYM SAMYM
    `instance_id` (`789e95…`, hello seq 59 i 61), nie wyparl listenera
    i zostawil ramke w logu (seq 62). Tozsamosc sie nie rozszczepila —
    guard blokowal sciezke, ktora dziala, i opisywal awarie naprawiona
    w B6/C4.

    Gdy rozjazd stanie sie kiedys CELOWY, ten test sie KASUJE razem
    z uzasadnieniem — tak samo jak blizniaczy plot przy instalatorze."""
    kopie = [korzen / "agentmachi-join" / "scripts" / "codex-wait.sh"
             for korzen in (SKILLS, SKILLS_CODEX)]
    claude, codex = (sciezka.read_bytes() for sciezka in kopie)
    assert claude == codex, (
        "kopie `codex-wait.sh` sie rozjechaly:\n"
        + "".join(difflib.unified_diff(
            claude.decode().splitlines(keepends=True),
            codex.decode().splitlines(keepends=True),
            fromfile=str(kopie[0]), tofile=str(kopie[1]))))
