"""Wypakowanie skilli z pakietu do katalogu harnessu.

Powod istnienia: skille sa czescia produktu, a nie repozytorium. Dopoki
instalowalo sie je `ln -s <repo>/skills/...`, `pip install agentmachi`
wymagal klonu repo, czyli obietnica "pip install i dziala" konczyla sie
na kroku drugim.

Kopia, nie symlink — pakiet w site-packages jest wymieniany przy
`pip install -U`, wiec symlink do niego i tak nie jest zywym zrodlem.
Kto pracuje NAD agentmachi, dalej podpina symlink do repo recznie; ta
funkcja go nie tyka (patrz `_zajete`).
"""

from __future__ import annotations

import shutil
from pathlib import Path

HARNESSY: dict[str, Path] = {
    "claude": Path("~/.claude/skills"),
    "codex": Path("~/.agents/skills"),
}


def zrodlo(harness: str) -> Path:
    """Katalog skilli danego harnessu wewnatrz zainstalowanego pakietu."""
    if harness not in HARNESSY:
        raise ValueError(
            f"nieznany harness {harness!r}; znane: {', '.join(sorted(HARNESSY))}"
        )
    return Path(__file__).resolve().parent / "skills" / harness


def _zajete(sciezka: Path) -> bool:
    """Czy cel istnieje w jakiejkolwiek postaci — takze jako zerwany symlink.

    `Path.exists()` na zerwanym symlinku zwraca False, a `shutil.copytree`
    i tak sie o niego wywali. Sprawdzamy `is_symlink()` osobno.
    """
    return sciezka.is_symlink() or sciezka.exists()


def zainstaluj(harness: str, cel: Path, nadpisz: bool = False) -> list[str]:
    """Skopiuj skille harnessu do `cel`. Zwroc nazwy tych, ktore trafily.

    Istniejacy katalog albo symlink jest pomijany, chyba ze `nadpisz`.
    """
    src = zrodlo(harness)
    if not src.is_dir():
        raise FileNotFoundError(
            f"brak skilli w pakiecie: {src} — pakiet zbudowany bez package-data?"
        )

    cel = cel.expanduser()
    cel.mkdir(parents=True, exist_ok=True)

    zainstalowane: list[str] = []
    for skill in sorted(p for p in src.iterdir() if p.is_dir()):
        docelowy = cel / skill.name
        if _zajete(docelowy):
            if not nadpisz:
                continue
            if docelowy.is_symlink():
                docelowy.unlink()
            else:
                shutil.rmtree(docelowy)
        shutil.copytree(
            skill, docelowy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
        )
        zainstalowane.append(skill.name)
    return zainstalowane
