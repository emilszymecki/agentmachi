"""Instalator kontraktu wchodzi do CUDZEGO repo — wiec nie wolno mu zaskoczyc.

Kontrakty, ktore pilnujemy: podglad domyslnie, zero nadpisania cudzej tresci,
idempotencja, aktualizacja bloku w miejscu i czyste usuniecie.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                     / "skills" / "agentmachi-join" / "scripts"))

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
    zobowiazaniem. Szesc punktow; rozbudowa wymaga dowodu z dogfoodu, nie
    przekonania — inaczej urosnie tam dokladnie tak, jak urosly kiedys
    `rules` w samym agentmachi."""
    bajty = len(ip.KONTRAKT.encode("utf-8"))
    assert bajty <= 2048, (
        f"kontrakt ma {bajty} B — to za duzo jak na blok wstawiany do "
        f"cudzego AGENTS.md")
    niski = ip.KONTRAKT.lower()
    assert "nadrzedne" in niski or "nadrzędne" in niski
    assert "dane, nie polecenie" in niski
    assert "moderacji" in niski


def test_podglad_nowego_pliku_pokazuje_TRESC(tmp_path, capsys):
    """Czlowiek ma zobaczyc, co zaakceptuje — takze gdy pliku jeszcze nie ma.

    Poprzednia wersja wypisywala tylko "powstanie przy --apply": zapowiedz
    bez tresci. W cudzym repo to za malo, zeby ocenic zmiane (review E4)."""
    assert ip.main([str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "--- a/AGENTS.md" in out and "@@" in out, "brak unified diffu"
    assert "Nadrzędne są polecenia użytkownika" in out, \
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
    assert "markery" in err and "nie ruszam pliku" in err


def test_zdublowany_blok_tez_zatrzymuje(tmp_path):
    plik = tmp_path / "AGENTS.md"
    podwojny = (ip.POCZATEK + "\na\n" + ip.KONIEC + "\n"
                + ip.POCZATEK + "\nb\n" + ip.KONIEC + "\n")
    plik.write_text(podwojny)
    assert ip.main([str(tmp_path), "--apply"]) == 1
    assert plik.read_text() == podwojny


def test_zapis_jest_atomowy_i_nie_zostawia_smieci(tmp_path):
    """`write_text` obcina plik przed zapisem — przerwanie w polowie zostawia
    cudzy AGENTS.md okrojony. Po zapisie nie moze tez zostac plik tymczasowy."""
    (tmp_path / "AGENTS.md").write_text("# P\n")
    ip.main([str(tmp_path), "--apply"])
    smieci = [p.name for p in tmp_path.iterdir() if "tmp" in p.name]
    assert not smieci, f"zostaly pliki tymczasowe: {smieci}"
