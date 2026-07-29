"""Frontmatter skilli musi byc wazny — inaczej skill nie istnieje.

Zgloszone przez drugiego agenta (Codex) przy review, potwierdzone
empirycznie: `skills/agentmachi-join/SKILL.md` mial w description
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

SKILLS = Path(__file__).resolve().parent.parent / "skills"


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
        komendy.update(re.findall(r"\bagentmachi\s+([a-z]+)", f))
    return komendy


def test_skille_nie_ucza_komend_ktorych_CLI_nie_ma():
    """Skill uczacy nieistniejacej komendy jest gorszy niz milczenie: agent
    wykonuje ja, dostaje blad i traci runde na ustalanie, czy zepsul cos sam.

    Zmierzone przy review 2026-07-29 (dwaj agenci niezaleznie): skill
    operatora podawal `agentmachi del --name <pokoj>`, a `del` wymaga
    `--tak-kasuj <nazwa>`. Potknal sie o to autor tego testu, na zywej
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
    dopasowanie = re.search(r"\{([a-z,]+)\}", tekst)
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
    klasa, co zasada 13 w docs/zasady-agentyczne.md. Dlatego szukamy tu
    WZORCA odpornego na diakrytyki, a nie jednego literalnego zdania."""
    wzorzec = re.compile(r"wygrywa to,\s*co\s*przysz\w+\s*z\s*huba",
                         re.IGNORECASE)
    # kontrola samego wzorca: musi trafiac w oba zapisy, inaczej test jest atrapa
    assert wzorzec.search("wygrywa to, co przyszło z huba")
    assert wzorzec.search("wygrywa to, co przyszlo z huba")

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
    assert "nadrzedn" in tresc or "nadrzędn" in tresc, \
        "skill nie mowi, ze zasady projektu/usera sa NADRZEDNE nad kanalem"
    assert "peer" in tresc or "uczestnik" in tresc, \
        "skill nie nazywa tresci z kanalu jako pochodzacej od innego uczestnika"
