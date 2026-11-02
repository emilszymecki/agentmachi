"""Ukryte testy akceptacyjne kroniki. Uruchom:
KRONIKA_DIR=<katalog projektu> pytest -v test_akceptacja.py

Oczekiwane wartosci wyprowadzone ze STALYCH ponizej, nie z uruchomienia
czegokolwiek. Fixture (czas autora = czas commitera, lokalnie autora):
 c1 A 2026-01-05 10:00 +0200 Mon  add a.txt(3), "dir/plik ze spacją.txt"(2)
 c2 B 2026-01-06 23:30 -0500 Tue  a.txt +1; add bin.dat (binarny)  msg z \\n i "
 c3 A 2026-01-07 08:15 +0200 Wed  rename a.txt -> b.txt (bez zmiany tresci)
 c4 C 2026-01-08 12:00 +0000 Thu  [feature od c3] b.txt: linia1 zmieniona (+1 -1)
 c5 B 2026-01-09 09:00 -0500 Fri  [main] plik ze spacją +2 -1
 c6 A 2026-01-10 18:45 +0200 Sat  merge --no-ff feature
 c7 A 2026-01-11 07:05 +0200 Sun  bin.dat zmiana binarna; plik ze spacją +1
"""
import json, os, subprocess, sys
from pathlib import Path
import pytest

KRONIKA = Path(os.environ["KRONIKA_DIR"]).resolve()
SPACJA = "dir/plik ze spacją.txt"
A = ("Zażółć Gęślą", "zg@example.com", "+0200")
B = ("Bob Builder", "bob@example.com", "-0500")
C = ("Ćma", "cma@example.com", "+0000")
ENV = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
       "LC_ALL": "C.UTF-8"}


def _git(repo, *args, kto=None, kiedy=None):
    env = dict(ENV)
    if kto:
        env.update(GIT_AUTHOR_NAME=kto[0], GIT_AUTHOR_EMAIL=kto[1],
                   GIT_COMMITTER_NAME=kto[0], GIT_COMMITTER_EMAIL=kto[1],
                   GIT_AUTHOR_DATE=f"{kiedy} {kto[2]}",
                   GIT_COMMITTER_DATE=f"{kiedy} {kto[2]}")
    subprocess.run(["git", "-C", str(repo), *args], env=env, check=True,
                   capture_output=True)


def _zbuduj(repo):
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "dir").mkdir()
    (repo / "a.txt").write_text("l1\nl2\nl3\n")
    (repo / SPACJA).write_text("s1\ns2\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "start", kto=A, kiedy="2026-01-05T10:00:00")
    (repo / "a.txt").write_text("l1\nl2\nl3\nl4\n")
    (repo / "bin.dat").write_bytes(bytes(range(256)))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", 'dodaj "binarny"\n\ndruga linia', kto=B,
         kiedy="2026-01-06T23:30:00")
    _git(repo, "mv", "a.txt", "b.txt")
    _git(repo, "commit", "-q", "-m", "zmiana nazwy", kto=A, kiedy="2026-01-07T08:15:00")
    _git(repo, "checkout", "-q", "-b", "feature")
    (repo / "b.txt").write_text("L1\nl2\nl3\nl4\n")
    _git(repo, "commit", "-q", "-am", "feature", kto=C, kiedy="2026-01-08T12:00:00")
    _git(repo, "checkout", "-q", "main")
    (repo / SPACJA).write_text("s1\nx2\nx3\n")
    _git(repo, "commit", "-q", "-am", "main", kto=B, kiedy="2026-01-09T09:00:00")
    _git(repo, "merge", "-q", "--no-ff", "feature", "-m", "merge", kto=A,
         kiedy="2026-01-10T18:45:00")
    (repo / "bin.dat").write_bytes(bytes(reversed(range(256))))
    (repo / SPACJA).write_text("s1\nx2\nx3\nx4\n")
    _git(repo, "commit", "-q", "-am", "bin", kto=A, kiedy="2026-01-11T07:05:00")
    return repo


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    return _zbuduj(tmp_path_factory.mktemp("fx") / "fixture-repo")


def _run(*args):
    return subprocess.run([sys.executable, "-m", "kronika", *map(str, args)],
                          cwd=KRONIKA, env=ENV, capture_output=True, text=True,
                          timeout=60)


def _json(*args):
    p = _run(*args, "--json")
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def test_liczby_commitow_i_merge(repo):
    d = _json(repo)
    assert (d["commits"], d["merges"]) == (7, 1)


def test_pierwsza_i_ostatnia_data(repo):
    d = _json(repo)
    assert (d["first"], d["last"]) == ("2026-01-05", "2026-01-11")


def test_autorzy_kolejnosc_i_liczby(repo):
    d = _json(repo)
    assert d["authors"] == [
        {"name": A[0], "email": A[1], "commits": 4, "added": 6, "deleted": 0},
        {"name": B[0], "email": B[1], "commits": 2, "added": 3, "deleted": 1},
        {"name": C[0], "email": C[1], "commits": 1, "added": 1, "deleted": 1},
    ]


def test_pliki_przemianowanie_binarny_spacja_kolejnosc(repo):
    d = _json(repo)
    assert d["files"] == [
        {"path": SPACJA, "commits": 3, "added": 5, "deleted": 1},
        {"path": "a.txt", "commits": 2, "added": 4, "deleted": 0},
        {"path": "b.txt", "commits": 2, "added": 1, "deleted": 1},
        {"path": "bin.dat", "commits": 2, "added": 0, "deleted": 0},
    ]


def test_top_obcina(repo):
    d = _json(repo, "--top", "2")
    assert [f["path"] for f in d["files"]] == [SPACJA, "a.txt"]


def test_dzien_tygodnia_w_strefie_autora(repo):
    d = _json(repo)
    assert d["by_weekday"] == {k: 1 for k in
                               ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")}


def test_godzina_w_strefie_autora(repo):
    d = _json(repo)
    oczekiwane = {str(h): 0 for h in range(24)}
    for h in (10, 23, 8, 12, 9, 18, 7):
        oczekiwane[str(h)] = 1
    assert d["by_hour"] == oczekiwane


def test_puste_repo(tmp_path):
    pusty = tmp_path / "pusty"
    pusty.mkdir()
    _git(pusty, "init", "-q", "-b", "main")
    d = _json(pusty)
    assert d["commits"] == 0 and d["merges"] == 0
    assert d["first"] is None and d["last"] is None
    assert d["authors"] == [] and d["files"] == []
    assert set(d["by_weekday"]) == {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
    assert set(d["by_hour"]) == {str(h) for h in range(24)}
    assert not any(d["by_weekday"].values()) and not any(d["by_hour"].values())


def test_nie_repo_kod_2(tmp_path):
    p = _run(tmp_path, "--json")
    assert p.returncode == 2 and p.stdout == "" and p.stderr.strip()


def test_nieistniejaca_sciezka_kod_2(tmp_path):
    p = _run(tmp_path / "nie-ma", "--json")
    assert p.returncode == 2 and p.stdout == "" and p.stderr.strip()


def test_markdown(repo):
    p = _run(repo)
    assert p.returncode == 0, p.stderr
    linie = p.stdout.splitlines()
    assert linie[0] == "# Kronika: fixture-repo"
    for naglowek in ("## Autorzy", "## Najgorętsze pliki", "## Rytm"):
        assert naglowek in linie
    assert any(A[0] in l and "4" in l for l in linie if l.startswith("|"))
    assert any(SPACJA in l and "3" in l for l in linie if l.startswith("|"))
