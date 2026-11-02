"""workspace_now: fakty z gita, ktore klient `listen` wysyla na board sam."""
import subprocess

import send


def _repo(tmp_path, nazwa="repo-wt-x"):
    d = tmp_path / nazwa
    d.mkdir()
    for args in (["init", "-q", "-b", "glowna"],
                 ["-c", "user.email=a@b", "-c", "user.name=a",
                  "commit", "-q", "--allow-empty", "-m", "x"]):
        subprocess.run(["git", *args], cwd=d, check=True)
    return d


def test_galaz_worktree_i_head_bez_sciezki(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENTMACHI_NO_WORKSPACE", raising=False)
    d = _repo(tmp_path)
    ws = send.workspace_now(cwd=d)
    assert ws["worktree"] == "repo-wt-x"      # nazwa, nie sciezka
    assert ws["branch"] == "glowna"
    assert len(ws["head"]) >= 4


def test_detached_to_brak_branch_a_nie_napis_HEAD(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENTMACHI_NO_WORKSPACE", raising=False)
    d = _repo(tmp_path)
    subprocess.run(["git", "switch", "-q", "--detach"], cwd=d, check=True)
    ws = send.workspace_now(cwd=d)
    assert "branch" not in ws


def test_poza_repo_i_opt_out_nic_nie_wysylaja(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENTMACHI_NO_WORKSPACE", raising=False)
    assert send.workspace_now(cwd=tmp_path) is None
    d = _repo(tmp_path)
    monkeypatch.setenv("AGENTMACHI_NO_WORKSPACE", "1")
    assert send.workspace_now(cwd=d) is None


def test_AGENTMACHI_WORKSPACE_wskazuje_katalog_pracy_inny_niz_nasluchu(
        tmp_path, monkeypatch):
    # Nasluch stoi w jednym katalogu, praca idzie w drugim — bez wskazania
    # board pokazalby katalog nasluchu jako miejsce pracy.
    monkeypatch.delenv("AGENTMACHI_NO_WORKSPACE", raising=False)
    praca = _repo(tmp_path, "repo-wt-praca")
    monkeypatch.chdir(tmp_path)               # cwd nasluchu: poza repo
    monkeypatch.setenv("AGENTMACHI_WORKSPACE", str(praca))
    assert send.workspace_now()["worktree"] == "repo-wt-praca"


def test_stary_hub_bez_klucza_workspace_nie_dostaje_ramki():
    # stary hub odbilby nieznany typ errorem, a error budzi agenta
    stary = {"participants": [{"nick": "a", "status": None}]}
    nowy = {"participants": [{"nick": "a", "workspace": None}]}
    assert not send._hub_przyjmuje_workspace(stary)
    assert send._hub_przyjmuje_workspace(nowy)


def test_dluga_nazwa_katalogu_przycieta_widocznie_i_zgodna_z_protokolem(
        tmp_path, monkeypatch):
    # review codex P2: legalny katalog 101 znakow dawal ramke odbijana
    # przez wlasny protokol przy kazdym hello.
    from chat import protocol
    monkeypatch.delenv("AGENTMACHI_NO_WORKSPACE", raising=False)
    d = _repo(tmp_path, "k" * 101)
    ws = send.workspace_now(cwd=d)
    assert len(ws["worktree"]) == 100 and ws["worktree"].endswith("…")
    ramka = {"type": "workspace", "from": "a", "ts": 0.0, **ws}
    assert protocol.validate(ramka) is None
