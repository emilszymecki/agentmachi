"""Instalator skilli — bez niego `pip install agentmachi` daje CLI bez
sciezki wejscia dla agenta, wiec produkt nie dziala bez klonu repo."""

from pathlib import Path

import pytest

from agentmachi import skills_install


def test_zrodlo_wskazuje_na_skille_w_pakiecie():
    zrodlo = skills_install.zrodlo("claude")
    assert zrodlo.is_dir()
    assert (zrodlo / "agentmachi-join" / "SKILL.md").is_file()


def test_zainstaluj_kopiuje_oba_skille(tmp_path):
    cel = tmp_path / "skills"
    zainstalowane = skills_install.zainstaluj("claude", cel)
    assert sorted(zainstalowane) == ["agentmachi", "agentmachi-join"]
    assert (cel / "agentmachi-join" / "SKILL.md").is_file()
    assert (cel / "agentmachi-join" / "scripts" / "integrate_project.py").is_file()


def test_zainstaluj_nie_nadpisuje_bez_zgody(tmp_path):
    cel = tmp_path / "skills"
    skills_install.zainstaluj("claude", cel)
    (cel / "agentmachi-join" / "SKILL.md").write_text("moja wersja")

    zainstalowane = skills_install.zainstaluj("claude", cel)

    assert zainstalowane == []
    assert (cel / "agentmachi-join" / "SKILL.md").read_text() == "moja wersja"


def test_zainstaluj_nadpisuje_gdy_poproszono(tmp_path):
    cel = tmp_path / "skills"
    skills_install.zainstaluj("claude", cel)
    (cel / "agentmachi-join" / "SKILL.md").write_text("moja wersja")

    zainstalowane = skills_install.zainstaluj("claude", cel, nadpisz=True)

    assert "agentmachi-join" in zainstalowane
    assert (cel / "agentmachi-join" / "SKILL.md").read_text() != "moja wersja"


def test_nieznany_harness_odrzucony(tmp_path):
    with pytest.raises(ValueError):
        skills_install.zainstaluj("emacs", tmp_path)


def test_symlink_w_celu_nie_jest_po_cichu_zastepowany(tmp_path):
    """Kto pracuje NAD agentmachi, ma symlink do repo. Instalator nie ma
    prawa podmienic go na kopie bez `nadpisz` — inaczej edycje w repo
    przestaja dzialac, a czlowiek nie dostaje o tym slowa."""
    cel = tmp_path / "skills"
    cel.mkdir()
    repo = tmp_path / "repo-skill"
    repo.mkdir()
    (cel / "agentmachi-join").symlink_to(repo, target_is_directory=True)

    zainstalowane = skills_install.zainstaluj("claude", cel)

    assert "agentmachi-join" not in zainstalowane
    assert (cel / "agentmachi-join").is_symlink()


def test_cli_install_skills_do_wskazanego_katalogu(tmp_path, capsys):
    from agentmachi import cli

    rc = cli.main(
        ["install-skills", "--harness", "claude", "--dest", str(tmp_path / "s")]
    )

    assert rc == 0
    assert (tmp_path / "s" / "agentmachi-join" / "SKILL.md").is_file()
    assert "agentmachi-join" in capsys.readouterr().out
