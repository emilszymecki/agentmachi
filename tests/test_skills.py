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

import re
from pathlib import Path

# Skille mieszkaja pod katalogiem pakietu, bo `package-data` pakuje tylko
# to, co jest WEWNATRZ pakietu — inaczej `pip install agentmachi` daje CLI
# bez skilli, czyli produkt bez sciezki wejscia dla agenta.
SKILLS = Path(__file__).resolve().parent.parent / "agentmachi" / "skills" / "claude"
SKILLS_CODEX = Path(__file__).resolve().parent.parent / "agentmachi" / "skills" / "codex"


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
    assert "take precedence" in tresc, \
        "skill nie mowi, ze zasady projektu/usera sa NADRZEDNE nad kanalem"
    assert "peer" in tresc or "uczestnik" in tresc, \
        "skill nie nazywa tresci z kanalu jako pochodzacej od innego uczestnika"


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
# przy 223 B luzu i przy 800. Wniosek o samym mechanizmie, wart więcej niż
# ta liczba: **sufit bajtowy nie odróżnia sprostowania od dopisku.** Kto
# jutro znajdzie w CLAUDE.md nieprawdę, i tak będzie musiał najpierw coś
# wyciąć — czyli dokładnie to, przed czym luz miał chronić. To jest przyjęty
# koszt tego narzędzia, nie jego usterka: taniej niż brak zamka, którym ten
# plik rósł po cichu przez pół roku. Progu nie podnoś, żeby ten koszt ominąć.
BUDZETY = {
    "CLAUDE.md (doklejane do KAZDEJ sesji w tym repo)":
        (Path(__file__).resolve().parent.parent / "CLAUDE.md", 16384),
    "AGENTS.md (doklejane do KAZDEJ sesji w tym repo)":
        (Path(__file__).resolve().parent.parent / "AGENTS.md", 17408),
    "howto (drutem, przy KAZDYM hello i reconnect)":
        (Path(__file__).resolve().parent.parent
         / "agentmachi" / "howto_default.md", 5120),
    "SKILL.md (pierwsza minuta agenta)":
        (SKILLS / "agentmachi-join" / "SKILL.md", 4096),
    "SKILL.md Codexa (pierwsza minuta agenta)":
        (SKILLS_CODEX / "agentmachi-join" / "SKILL.md", 4096),
}


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


def _przepuszcza(modul, linia, nick="agent_opus", peer="agent_codex"):
    odsiej, budz = modul.zbuduj(nick, peer)
    return (not odsiej(linia)) and bool(budz(linia))


def test_wake_filter_budzi_na_wzmiance_czlowieka_TAKZE_z_liczba():
    """Dziura, ktora autor tego filtra sam w siebie wpisal 2026-08-07:
    wzorzec tnacy ramki liczace byl na tyle szeroki, ze zjadal ludzkie
    `@nick 3`. Czlowiek pisze do agenta liczby (numer punktu, seq, port)
    i taka wiadomosc NIE MOZE zginac."""
    m = _wake_filter()
    assert _przepuszcza(m, "[847] human: @agent_opus ?")
    assert _przepuszcza(m, "[850] human: @agent_opus 3")
    assert _przepuszcza(m, "[851] human: @all cos dla wszystkich")


def test_wake_filter_tnie_ramki_liczace_TYLKO_od_peera():
    """Ruch, ktory obsluguje juz inny proces, nie ma budzic modelu —
    ale wylacznie od wskazanego peera i wylacznie gdy jest GOLA liczba."""
    m = _wake_filter()
    assert not _przepuszcza(m, "[826] agent_codex: 20 @agent_opus")
    assert not _przepuszcza(m, "[827] agent_codex: @agent_opus 19")
    # ta sama liczba w zdaniu to juz wiadomosc, nie ruch w grze
    assert _przepuszcza(m, "[852] agent_codex: @agent_opus mam 7 uwag")
    # bez podanego peera nie wycinamy NICZEGO — brak argumentu nie moze
    # cicho wlaczyc filtrowania czyichkolwiek ramek
    odsiej, budz = m.zbuduj("agent_opus")
    assert not odsiej("[826] agent_codex: 20 @agent_opus")


def test_wake_filter_tnie_session_metadata_PO_TYPIE_nie_po_slowach():
    """Ta ramka niesie howto, a w howto siedza slowa lapiace wzmianki
    (`@all`, `takeover`, `4003`). Filtr slowny przepuszczal ja w calosci —
    zmierzone na zywym pokoju, trzy tokeny przebily naraz. I dzieje sie to
    tylko przy reconnekcie, czyli w jedynym momencie, gdy ona przychodzi."""
    m = _wake_filter()
    ramka = ('{"type": "session_metadata", "howto": "@all budzi wszystkich, '
             'takeover opisany nizej, kod 4003 to kick"}')
    assert not _przepuszcza(m, ramka)


def test_wake_filter_budzi_na_AWARIACH_bo_cisza_nie_jest_sukcesem():
    """Bez tych wzorcow agent spi tak samo spokojnie, gdy hub go odrzucil,
    jak gdy kanal jest pusty."""
    m = _wake_filter()
    for linia in ("[reconnect] connection dropped; retrying in 1s",
                  "[hub] assigned nick: agent7",
                  '{"type": "error", "text": "nick zajety"}',
                  "REJECTED: bad token",
                  "[nick] zmiana nicka"):
        assert _przepuszcza(m, linia), f"filtr przespalby awarie: {linia!r}"


def test_wake_filter_budzi_na_KICKU_bo_serwer_zrobil_z_niego_JEDYNY_wyjatek():
    """Zmierzone na zywym pokoju `poligon` 2026-08-13.

    `chat/server.py` (`_on_kick`) rozsyla ramke `kick` do WSZYSTKICH
    pozostalych polaczen i jest to jedyny swiadomy wyjatek od reguly "agenta
    budzi tylko wzmianka". Komentarz w serwerze uzasadnia go zdaniem: agent,
    ktory wlasnie uzgodnil podzial pracy z wyrzuconym, musi wiedziec, ze
    partner zniknal, bo inaczej czeka na robote, ktorej nikt nie zrobi.
    Ten filtr wyrzucal te ramke na wejsciu, czyli kasowal wyjatek, dla
    ktorego serwer zlamal wlasna regule.

    Skutek byl dokladnie ten, ktory serwer przewidzial. Po `/kick beta`
    (seq 18) `alfa` pisala `@beta` w seq 20, 24 i 27, oddala polowe pracy
    nieobecnemu i zapisala w README, ze jest zrobiona. Produkt nie startowal
    (`ModuleNotFoundError: No module named 'contract'`), a na kanale nie
    padla o tym ani jedna ramka. Wyrzucona strona zachowala sie poprawnie —
    jej klient wypisal `[kick]` i zakonczyl proces. Awaria jest
    JEDNOSTRONNA: zawodzi ten, ktory zostaje, czyli ten, ktory pisze potem
    dokumentacje.

    Dlaczego 649 zielonych testow tego nie widzialo: kazdy sprawdza, ze
    ramka WYCHODZI z huba. Zaden nie sprawdzal, czy po drugiej stronie drutu
    cokolwiek ja przyjmuje.

    Ramka `kick` nie ma pola `text`, wiec `_print_event` (send.py:193)
    drukuje ja calym JSON-em — stad wzorzec po TYPIE, tak samo jak przy
    `"type": "error"`. Drugi wzorzec lapie linie stderr wyrzucanego, bo
    zalecany potok laczy strumienie (`2>&1`)."""
    m = _wake_filter()
    assert _przepuszcza(m, '{"type": "kick", "from": "server", "ts": 1.0, '
                           '"target": "beta", "by": "human", "seq": 18}')
    assert _przepuszcza(m, "[kick] kicked off the channel by a moderator - "
                           "ending the listen. To come back, start it again.")


def test_wake_filter_milczy_na_rozmowie_bez_wzmianki():
    """Chat bez wzmianki i tak nie dociera do agenta z huba — ale gdyby
    filtr go przepuszczal, kazda cudza rozmowa kosztowalaby ture."""
    m = _wake_filter()
    assert not _przepuszcza(m, "[853] ktos: zwykla rozmowa bez wzmianki")


def test_wake_filter_bez_nicka_ODMAWIA_zamiast_przepuszczac_wszystko():
    """Fail-closed: bez nicka nie da sie powiedziec, co jest wzmianka.
    Cichy przepust byl by tu gorszy niz blad — agent placilby tura za
    kazda linia i uznal to za normalny halas kanalu."""
    m = _wake_filter()
    assert m.main([]) == 2
    assert m.main(["   "]) == 2
