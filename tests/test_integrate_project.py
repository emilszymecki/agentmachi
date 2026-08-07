"""Instalator kontraktu wchodzi do CUDZEGO repo — wiec nie wolno mu zaskoczyc.

Kontrakty, ktore pilnujemy: podglad domyslnie, zero nadpisania cudzej tresci,
idempotencja, aktualizacja bloku w miejscu i czyste usuniecie.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                     / "agentmachi" / "skills" / "claude"
                     / "agentmachi-join" / "scripts"))

import integrate_project as ip


def test_podglad_niczego_nie_zapisuje(tmp_path, capsys):
    """Domyslne uruchomienie w cudzym repo MUSI byc bezpieczne. Czlowiek ma
    najpierw zobaczyc diff, a dopiero potem zdecydowac."""
    (tmp_path / "AGENTS.md").write_text("# Moj projekt\n\nZasady wlasne.\n")
    przed = (tmp_path / "AGENTS.md").read_text()

    assert ip.main([str(tmp_path)]) == 0
    assert (tmp_path / "AGENTS.md").read_text() == przed, \
        "podglad zapisal plik"
    assert not (tmp_path / "CLAUDE.md").exists(), \
        "podglad utworzyl plik, ktorego nie bylo"
    assert "+" in capsys.readouterr().out, "podglad nie pokazal diffu"


def test_apply_dokleja_i_NIE_rusza_cudzej_tresci(tmp_path):
    oryginal = "# Moj projekt\n\nNie kasuj mnie.\n"
    (tmp_path / "AGENTS.md").write_text(oryginal)

    assert ip.main([str(tmp_path), "--apply"]) == 0
    tresc = (tmp_path / "AGENTS.md").read_text()
    assert oryginal.strip() in tresc, "instalator nadpisal cudza tresc"
    assert ip.POCZATEK in tresc and ip.KONIEC in tresc
    assert tresc.index(oryginal.strip()) < tresc.index(ip.POCZATEK), \
        "blok wszedl PRZED tresc projektu"


def test_idempotencja(tmp_path):
    """Drugie uruchomienie nie moze niczego zmienic — inaczej kazdy agent
    wchodzacy do projektu dokladalby kolejna kopie kontraktu."""
    (tmp_path / "AGENTS.md").write_text("# P\n")
    ip.main([str(tmp_path), "--apply"])
    po_pierwszym = (tmp_path / "AGENTS.md").read_text()
    ip.main([str(tmp_path), "--apply"])
    assert (tmp_path / "AGENTS.md").read_text() == po_pierwszym
    assert po_pierwszym.count(ip.POCZATEK) == 1


def test_aktualizacja_bloku_w_miejscu(tmp_path):
    """Gdy tresc kontraktu sie zmieni, blok ma zostac PODMIENIONY, a nie
    dopisany drugi raz — i nadal nie moze ruszyc tekstu wokol."""
    plik = tmp_path / "AGENTS.md"
    plik.write_text("# Przed\n\n" + ip.POCZATEK + "\nSTARA TRESC\n"
                    + ip.KONIEC + "\n\n# Po\n")
    ip.main([str(tmp_path), "--apply"])
    tresc = plik.read_text()
    assert "STARA TRESC" not in tresc
    assert tresc.count(ip.POCZATEK) == 1
    assert "# Przed" in tresc and "# Po" in tresc, \
        "aktualizacja zjadla tekst wokol bloku"


def test_remove_zostawia_plik_bez_sladu(tmp_path):
    plik = tmp_path / "AGENTS.md"
    oryginal = "# Moj projekt\n\nZasady wlasne.\n"
    plik.write_text(oryginal)
    ip.main([str(tmp_path), "--apply"])
    ip.main([str(tmp_path), "--remove", "--apply"])
    tresc = plik.read_text()
    assert ip.POCZATEK not in tresc and "agentmachi" not in tresc
    assert "Zasady wlasne." in tresc


def test_kontrakt_ustawia_priorytet_i_zostaje_krotki():
    """Kontrakt instaluje sie w cudzym repo, wiec jego rozmiar jest
    zobowiazaniem. Piec punktow; rozbudowa wymaga dowodu z dogfoodu, nie
    przekonania — inaczej urosnie tam dokladnie tak, jak urosly kiedys
    `rules` w samym agentmachi.

    Prog jest SYMETRYCZNY, i to jest jedyna polowa, ktorej wczesniej tu nie
    bylo: gorna granica chronila liste przed tyciem, ale nic nie stalo za
    tym, co juz w niej jest. 2026-08-07 wypadl punkt „sprawdzaj stan komenda"
    (praktyka inzynierska, nie granica zaufania), wiec ten test pilnuje
    teraz obu kierunkow — asercje ponizej nazywaja PO CO kazdy punkt
    zostaje, zeby nastepne ciecie musialo najpierw obalic powod."""
    bajty = len(ip.KONTRAKT.encode("utf-8"))
    assert bajty <= 2048, (
        f"kontrakt ma {bajty} B — to za duzo jak na blok wstawiany do "
        f"cudzego AGENTS.md")
    # Zmienil sie JEZYK kontraktu, nie kontrakt: blok laduje w CUDZYM repo,
    # wiec od 2026-08-05 jest po angielsku. Pilnowane zdania sa te same —
    # priorytet zasad projektu, tresc z kanalu jako DANE (to jest zamek na
    # prompt injection miedzy agentami) i ostatnie slowo czlowieka
    # w moderacji.
    niski = ip.KONTRAKT.lower()
    assert "take precedence" in niski
    assert "data, not an order" in niski
    assert "moderation" in niski
    # Dwa punkty, ktore ostatni przeglad chcial wyciac razem z piatym, a
    # ktore zostaja, bo odpowiadaja na pytanie o GRANICE, nie o metode:
    # pochodzenie cytatu (bez niego cudza tresc wchodzi do obcego repo
    # jako wlasny wniosek agenta) i jeden piszacy na zasob (edycja pliku
    # w miejscu to zdalny crash cudzego procesu, nie ryzyko nadpisania —
    # references/troubleshooting.md, sekcja o `send`).
    # Bez sklejenia bialych znakow ta asercja pilnuje ZAWIJANIA, nie tresci:
    # „one resource has one writer" jest w kontrakcie przelamane po „one",
    # wiec doslowny substring nie trafia. Zlapane przez suite 2026-08-07.
    ciagle = " ".join(niski.split())
    assert "provenance" in ciagle
    assert "one resource has one writer" in ciagle


def test_podglad_nowego_pliku_pokazuje_TRESC(tmp_path, capsys):
    """Czlowiek ma zobaczyc, co zaakceptuje — takze gdy pliku jeszcze nie ma.

    Poprzednia wersja wypisywala tylko "powstanie przy --apply": zapowiedz
    bez tresci. W cudzym repo to za malo, zeby ocenic zmiane (review E4)."""
    assert ip.main([str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "--- a/AGENTS.md" in out and "@@" in out, "brak unified diffu"
    # Jezyk, nie kontrakt: "Nadrzędne są polecenia użytkownika" ->
    # "Your user's instructions ... take precedence".
    assert "Your user's instructions" in out, \
        "podglad nie pokazuje tresci kontraktu"
    assert not list(tmp_path.iterdir()), "podglad utworzyl pliki"


def test_urwany_marker_jest_fail_closed(tmp_path, capsys):
    """Urwany blok (start bez konca) to najgrozniejszy stan, bo powstaje po
    RECZNEJ edycji cudzego pliku. Stara wersja doklejala wtedy drugi komplet
    markerow: wynik mial 2x start i 1x koniec — cicha korupcja pliku, ktorego
    nie jestesmy wlascicielem. Repro z review E4."""
    plik = tmp_path / "AGENTS.md"
    uszkodzony = "# Projekt\n\n" + ip.POCZATEK + "\nurwane\n"
    plik.write_text(uszkodzony)

    assert ip.main([str(tmp_path), "--apply"]) == 1, \
        "instalator zapisal do pliku z uszkodzonymi markerami"
    assert plik.read_text() == uszkodzony, "plik zostal ruszony mimo bledu"
    err = capsys.readouterr().err
    # Jezyk, nie kontrakt: komunikat idzie do czlowieka w CUDZYM repo, wiec
    # jest po angielsku. Zamek pilnuje tego samego: blad nazywa markery
    # i mowi wprost, ze plik NIE zostal ruszony.
    assert "markers" in err and "not touching the file" in err


def test_zdublowany_blok_tez_zatrzymuje(tmp_path):
    plik = tmp_path / "AGENTS.md"
    podwojny = (ip.POCZATEK + "\na\n" + ip.KONIEC + "\n"
                + ip.POCZATEK + "\nb\n" + ip.KONIEC + "\n")
    plik.write_text(podwojny)
    assert ip.main([str(tmp_path), "--apply"]) == 1
    assert plik.read_text() == podwojny


def test_zapis_jest_atomowy_i_nie_zostawia_smieci(tmp_path, monkeypatch):
    """Po udanym zapisie nie zostaje plik tymczasowy; po BLEDZIE w polowie
    cudzy plik jest bajtowo nietkniety.

    HISTORIA TEGO ZAMKA — dwie iteracje, obie zlapane przy review:

    1. Filtrowal `if "tmp" in name`, bo tak nazywal sie wtedy plik
       tymczasowy. Gdy implementacja przeszla na `mkstemp(prefix=...)`,
       filtr przestal cokolwiek lapac: test zielony, zamek martwy.
    2. Poprawka wpisala prefiks jako stala TESTU i "kontrolowala sie",
       podkladajac plik wedlug tej samej stalej — czyli dowodzila jedynie,
       ze filtr zgadza sie sam ze soba. Przy nastepnej zmianie nazwy atrapa
       wrocilaby bez sladu.

    Rozwiazanie: nie zgadujemy nazwy. Owijamy `tempfile.mkstemp` i zapisujemy
    DOKLADNA sciezke, ktora naprawde powstala. Test dowiaduje sie o niej od
    implementacji, wiec zmiana prefiksu nie moze go uspic."""
    import os
    import tempfile as _tempfile

    utworzone = []
    prawdziwy_mkstemp = _tempfile.mkstemp

    def sledzacy_mkstemp(*a, **kw):
        fd, sciezka = prawdziwy_mkstemp(*a, **kw)
        utworzone.append(sciezka)
        return fd, sciezka

    monkeypatch.setattr(ip.tempfile, "mkstemp", sledzacy_mkstemp)

    plik = tmp_path / "AGENTS.md"
    oryginal = "# P\n"
    plik.write_text(oryginal)

    ip.main([str(tmp_path), "--apply"])
    assert utworzone, "implementacja nie uzyla mkstemp — zamek nic nie pilnuje"
    zostale = [s for s in utworzone if os.path.exists(s)]
    assert not zostale, f"po udanym zapisie zostal plik tymczasowy: {zostale}"

    # SCIEZKA BLEDU: os.replace rzuca -> cel bez zmian, temp posprzatany
    utworzone.clear()
    plik.write_text(oryginal)
    prawdziwy_replace = os.replace

    def padajacy_replace(a, b):
        raise OSError("symulowana awaria zapisu")

    monkeypatch.setattr(ip.os, "replace", padajacy_replace)
    try:
        ip.main([str(tmp_path), "--apply"])
    except OSError:
        pass
    monkeypatch.setattr(ip.os, "replace", prawdziwy_replace)

    assert plik.read_text() == oryginal, \
        "cudzy plik zmieniony mimo bledu zapisu"
    assert utworzone, "sciezka bledu nie utworzyla pliku tymczasowego"
    zostale = [s for s in utworzone if os.path.exists(s)]
    assert not zostale, f"po bledzie zostal plik tymczasowy: {zostale}"

def test_podlozony_tmp_nie_pozwala_nadpisac_cudzego_pliku(tmp_path):
    """ATAK SYMLINKIEM — podatnosc wprowadzona przy naprawie poprzedniego
    blockera: obrona przed obcieciem pliku otworzyla gorsza dziure.

    Zapis szedl przez plik o PRZEWIDYWALNEJ nazwie `<plik>.agentmachi-tmp`.
    Atakujacy podklada tam symlink na dowolny plik, a instalator pisze przez
    niego i konczy kodem 0. Repro z review E5.1: victim.txt zostal nadpisany
    trescia AGENTS.md.

    Nazwa tymczasowego jest teraz losowa (mkstemp, O_EXCL), wiec podlozony
    plik nie jest sledzony."""
    (tmp_path / "AGENTS.md").write_text("# projekt\n")
    ofiara = tmp_path / "victim.txt"
    ofiara.write_text("TRESC OFIARY\n")
    (tmp_path / "AGENTS.md.agentmachi-tmp").symlink_to(ofiara)

    ip.main([str(tmp_path), "--apply"])
    assert ofiara.read_text() == "TRESC OFIARY\n", \
        "instalator pisal przez podlozony symlink"


def test_cel_bedacy_symlinkiem_jest_odrzucany(tmp_path, capsys):
    """`os.replace` na symlinku zastapilby SAM LINK, a zapis przez niego
    dotknalby pliku, ktorego wlasciciel repo nie wskazal. W cudzym repo nie
    zgadujemy intencji — fail-closed."""
    ofiara = tmp_path / "victim.txt"
    ofiara.write_text("OFIARA\n")
    (tmp_path / "AGENTS.md").symlink_to(ofiara)

    assert ip.main([str(tmp_path), "--apply"]) == 1
    assert ofiara.read_text() == "OFIARA\n"
    # Jezyk, nie kontrakt: "dowiązaniem symbolicznym" -> "symbolic link".
    assert "symbolic link" in capsys.readouterr().err


def test_blad_w_drugim_pliku_nie_zapisuje_pierwszego(tmp_path, capsys):
    """ZERO-WRITE. Urwany marker w CLAUDE.md zatrzymywal prace DOPIERO po
    zapisaniu AGENTS.md — instalator zwracal 1, a repo bylo juz w stanie
    posrednim. W cudzym repozytorium czesciowy zapis jest gorszy niz brak
    zapisu, bo nikt nie wie, ktore pliki poszly (repro z review E5.1)."""
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# ok\n")
    (tmp_path / "CLAUDE.md").write_text("# c\n" + ip.POCZATEK + "\nurwane\n")

    assert ip.main([str(tmp_path), "--apply"]) == 1
    assert agents.read_text() == "# ok\n", \
        "AGENTS.md zapisany mimo bledu w CLAUDE.md — czesciowy zapis"
    # Jezyk, nie kontrakt: "nic nie zapisano" -> "nothing was written".
    assert "nothing was written" in capsys.readouterr().err


def test_remove_tez_waliduje_markery(tmp_path):
    """--remove nie moze "czesciowo" usunac podwojnego bloku: zostawilby
    sierote w cudzym pliku, a kod wyjscia 0 sugerowalby sukces."""
    plik = tmp_path / "AGENTS.md"
    podwojny = (ip.POCZATEK + "\na\n" + ip.KONIEC + "\n"
                + ip.POCZATEK + "\nb\n" + ip.KONIEC + "\n")
    plik.write_text(podwojny)
    assert ip.main([str(tmp_path), "--remove", "--apply"]) == 1
    assert plik.read_text() == podwojny


def test_zapis_nie_zmienia_uprawnien_cudzego_pliku(tmp_path):
    """Trzeci z rzedu skutek uboczny naprawy, wszystkie w tym samym miejscu:
    write_text obcinal plik -> tmp o przewidywalnej nazwie dal atak
    symlinkiem -> mkstemp naprawil atak, ale tworzy plik 0600, a os.replace
    przenosi ten tryb na cel. Cudzy AGENTS.md z 0644 stawal sie po cichu
    0600 i przestawal byc czytelny dla innych uzytkownikow (repro E5.2).

    Instalator wchodzi do NIE swojego repo — nie wolno mu zmieniac praw
    plikow, ktorych nie jest wlascicielem."""
    import os
    import stat as _stat

    plik = tmp_path / "AGENTS.md"
    plik.write_text("# projekt\n")
    os.chmod(plik, 0o644)

    ip.main([str(tmp_path), "--apply"])
    assert _stat.S_IMODE(plik.stat().st_mode) == 0o644, \
        "instalator zmienil prawa istniejacego pliku"

    # restrykcyjne prawa tez zostaja nietkniete — w obie strony
    os.chmod(plik, 0o600)
    ip.main([str(tmp_path), "--remove", "--apply"])
    assert _stat.S_IMODE(plik.stat().st_mode) == 0o600


def test_nowy_plik_dostaje_prawa_jak_zwykly_zapis(tmp_path):
    """Plik tworzony od zera ma dostac to, co dalby zwykly zapis (0666 minus
    umask), a nie 0600 z mkstempa."""
    import os
    import stat as _stat

    biezacy = os.umask(0o022)
    os.umask(biezacy)
    ip.main([str(tmp_path), "--apply"])
    oczekiwany = 0o666 & ~biezacy
    assert _stat.S_IMODE((tmp_path / "AGENTS.md").stat().st_mode) == oczekiwany
