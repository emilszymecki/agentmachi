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

import hashlib
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


def _odcisk(katalog: Path) -> dict[str, str]:
    """Sciezka wzgledna -> sha256 tresci, dla calego drzewa.

    Pomijane to samo, co pomija `zainstaluj` przy kopiowaniu — inaczej
    swiezo zainstalowana kopia rozniaby sie od paczki o wlasne `.pyc`.
    """
    odcisk: dict[str, str] = {}
    for p in katalog.rglob("*"):
        if p.is_symlink() or not p.is_file():
            continue
        wzgledna = p.relative_to(katalog)
        if "__pycache__" in wzgledna.parts or p.suffix == ".pyc":
            continue
        odcisk[wzgledna.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return odcisk


def rozne_od_pakietu(harness: str, cel: Path) -> list[str]:
    """Nazwy skilli obecnych w `cel`, ktorych tresc ROZNI SIE od paczki.

    Powod istnienia: `zainstaluj` bez `nadpisz` pomija istniejacy katalog
    i nie odroznia "kopia jest ta sama" od "kopia jest o 11 dni stara".
    CLI drukowalo w obu przypadkach `nothing new` i to zdanie bylo
    falszywe w drugim (2026-09-03: dzisiejsza poprawka skilla nie doszla
    do nikogo, bo komenda potwierdzila, ze nie ma czego instalowac).
    Agent moglby zrobic `diff -r` sam, ale nie zrobi tego po zdaniu, ktore
    mu mowi, ze nie ma po co — to jest naprawa komunikatu, nie nowy
    mechanizm.

    Symlinki sa pomijane CELOWO: kto pracuje NAD agentmachi, podpina
    katalog repo i to jego drzewo jest zywym zrodlem, nie paczka
    (patrz `_zajete`). Ostrzeganie przed poprawna konfiguracja byloby
    szumem, ktory nauczy ignorowac ostrzezenie prawdziwe.
    """
    src = zrodlo(harness)
    if not src.is_dir():
        raise FileNotFoundError(
            f"brak skilli w pakiecie: {src} — pakiet zbudowany bez package-data?"
        )

    cel = cel.expanduser()
    rozne: list[str] = []
    for skill in sorted(p for p in src.iterdir() if p.is_dir()):
        docelowy = cel / skill.name
        if docelowy.is_symlink() or not docelowy.is_dir():
            continue
        if _odcisk(skill) != _odcisk(docelowy):
            rozne.append(skill.name)
    return rozne
