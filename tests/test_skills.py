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

BUDZETY = {
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
