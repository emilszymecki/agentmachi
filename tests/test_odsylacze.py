"""Odsylacze z dokumentow do kodu: po SYMBOLU, nie po numerze linii.

SECURITY.md nosil ~30 cytatow `plik.py:NNN`. Wlasny naglowek pliku przyznawal,
ze 22 z 26 przesunely sie miedzy dwiema kontrolami; 2026-11-11 odchudzenie
komentarzy przesunelo je wszystkie naraz i zadna suita tego nie widziala.
Nazwa funkcji przezywa edycje, numer linii nie.
"""
import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DOKUMENTY = ["SECURITY.md", "CONTRIBUTING.md", "README.md", "AGENTS.md",
             "docs/philosophy.md"]
PARA = re.compile(r"`((?:agentmachi|tests)/[\w/]+\.py)`\s+`(\w+)`")
NUMER = re.compile(r"`(?:agentmachi|tests)/[\w/]+\.py:\d+")


def _symbole(sciezka):
    nazwy = set()
    for wezel in ast.walk(ast.parse((REPO / sciezka).read_text())):
        if isinstance(wezel, (ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.ClassDef)):
            nazwy.add(wezel.name)
        elif isinstance(wezel, ast.Assign):
            nazwy.update(t.id for t in wezel.targets
                         if isinstance(t, ast.Name))
    return nazwy


@pytest.mark.parametrize("dokument", DOKUMENTY)
def test_dokument_nie_cytuje_numerow_linii(dokument):
    tekst = (REPO / dokument).read_text()
    assert not NUMER.findall(tekst), (
        f"{dokument}: odsylacz po numerze linii zgnije przy najblizszej "
        f"edycji — podaj `plik.py` `symbol`")


def test_kazdy_cytowany_symbol_ISTNIEJE():
    pary = [(d, plik, sym) for d in DOKUMENTY
            for plik, sym in PARA.findall((REPO / d).read_text())]
    assert len(pary) >= 20, "regex nie trafia w odsylacze — test bylby atrapa"
    brak = [(d, plik, sym) for d, plik, sym in pary
            if not (REPO / plik).exists() or sym not in _symbole(plik)]
    assert not brak, f"odsylacze do nieistniejacych symboli: {brak}"
