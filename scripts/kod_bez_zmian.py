#!/usr/bin/env python3
"""Czy zmiana w pliku .py ruszyla WYLACZNIE komentarze i docstringi.

    python3 scripts/kod_bez_zmian.py <rewizja-bazowa> [plik.py ...]

Bez plikow: wszystkie .py zmienione wzgledem rewizji. Porownuje drzewo
skladni z wycietymi docstringami (komentarzy AST nie niesie). Kod wyjscia 1,
gdy ktorykolwiek plik rozni sie kodem. Docstring czytany w kodzie przez
`__doc__` jest KODEM — taki plik jest zglaszany osobno.
"""
import ast
import io
import subprocess
import sys
import tokenize


def _bez_docstringow(zrodlo):
    drzewo = ast.parse(zrodlo)
    for wezel in ast.walk(drzewo):
        if isinstance(wezel, (ast.Module, ast.FunctionDef,
                              ast.AsyncFunctionDef, ast.ClassDef)):
            cialo = wezel.body
            if (cialo and isinstance(cialo[0], ast.Expr)
                    and isinstance(cialo[0].value, ast.Constant)
                    and isinstance(cialo[0].value.value, str)):
                wezel.body = cialo[1:] or [ast.Pass()]
    return ast.dump(drzewo)


def _linie_prozy(zrodlo):
    """Linie zajete przez komentarze i docstringi."""
    linie = set()
    for t in tokenize.generate_tokens(io.StringIO(zrodlo).readline):
        if t.type == tokenize.COMMENT:
            linie.add(t.start[0])
    for wezel in ast.walk(ast.parse(zrodlo)):
        if isinstance(wezel, (ast.Module, ast.FunctionDef,
                              ast.AsyncFunctionDef, ast.ClassDef)):
            c = wezel.body
            if (c and isinstance(c[0], ast.Expr)
                    and isinstance(c[0].value, ast.Constant)
                    and isinstance(c[0].value.value, str)):
                linie.update(range(c[0].lineno, c[0].end_lineno + 1))
    return len(linie)


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          check=True).stdout


def main(argv):
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    baza, pliki = argv[0], argv[1:]
    if not pliki:
        pliki = [p for p in _git("diff", "--name-only", baza, "--",
                                 "*.py").split() if p]
    zle = 0
    for plik in pliki:
        try:
            stare = _git("show", f"{baza}:{plik}")
        except subprocess.CalledProcessError:
            # Pliku nie bylo w rewizji bazowej: caly jest nowym kodem.
            print(f"NOWY     {plik}: nie istnieje w {baza}")
            zle += 1
            continue
        nowe = open(plik, encoding="utf-8").read()
        rowne = _bez_docstringow(stare) == _bez_docstringow(nowe)
        uwaga = "  UWAGA: plik czyta __doc__" if "__doc__" in nowe else ""
        print(f"{'OK      ' if rowne else 'KOD INNY'} {plik}: proza "
              f"{_linie_prozy(stare)} -> {_linie_prozy(nowe)} linii{uwaga}")
        zle += not rowne
    return 1 if zle else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
