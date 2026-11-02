"""`agentmachi listen --wake`: nasluch, ktorego KAZDA linia stdout to powod,
zeby obudzic agenta. Pod `Monitor` Claude Code (stdout = zdarzenie).

Do 2026-11-02 to samo robil skrypt w skillu, skladany przez agenta w potok
`listen --json 2>&1 | python3 -u <skill>/scripts/wake_filter.py <nick>`.
Piec rzeczy do zapamietania, kopia skilla rozjezdzajaca sie z paczka
(7d92bd7), osobna galaz na zle zlozony potok — i filtr, ktory nie wiedzial,
ze hub nadal agentowi INNY nick. Dwa niezalezne przebiegi dogfoodu (ka, kb)
wskazaly to jako ciecie nr 1. Historia regul ponizej: docs/pl/zasady-
agentyczne.md (wake_filter) i testy w tests/test_skills.py.

Co budzi:
- diagnostyka klienta (`[hub]`, `[kick]`, `[nick]`, `[read]`, `[resync]`,
  `[warning]`) i kazda linia, ktora nie jest ramka JSON (traceback),
- `[reconnect]` RAZ na awarie — martwy hub to inaczej ~120 wybudzen na
  godzine; koniec awarii melduje `[hub] back`,
- ramki `kick`/`takeover`/`error`,
- chat z wzmianka `@<nick>` albo `@all` — nie wlasny.
Nie budzi: `session_metadata`/`resync_state` (niosa howto i board, a w nich
slowa lapiace wzmianki) — poza jedna linia o ZASADACH pokoju, ktore jada
tylko tam; rozmowa bez wzmianki, wlasne ramki z backlogu.
"""
import contextlib
import json
import re
import sys

DIAGNOSTYKA = re.compile(r"^\[(hub|kick|nick|read|resync|warning)\]")
NADANY = re.compile(r"^\[hub\] assigned nick: (\S+)")
PODMIENIONY = re.compile(r"^\[nick\] .* coming up as '([^']+)'")
TYPY_BUDZACE = frozenset({"kick", "takeover", "error"})
TYPY_CICHE = frozenset({"session_metadata", "resync_state"})
KONIEC = ("[listen] LISTENER ENDED — the stream closed, you are NOT on the "
          "channel any more; re-arm the listener before answering anybody")


def zbuduj(nick):
    """`decyduj(linia) -> bool | str` (str = linia zastepcza). `nick` moze byc None (hub go nada) —
    filtr przejmuje nick z `[hub] assigned nick` i `[nick] ... coming up
    as`, bo to WLASNE linie klienta, a nie zgadywanie."""
    stan = {"nick": None, "wzmianka": None, "awaria": False, "zasady": None}

    def ustaw(nowy):
        stan["nick"] = nowy
        stan["wzmianka"] = (re.compile(rf"@{re.escape(nowy)}\b|@all\b")
                            if nowy else re.compile(r"@all\b"))

    ustaw(nick)

    def _zasady(meta):
        """Zasady pokoju jada tylko w tej (cichej) ramce. Zamiast niej:
        jedna linia, gdy sa i gdy sie zmienily (rules_hash)."""
        tresc = meta.get("rules")
        if not isinstance(tresc, str) or not tresc.strip():
            return False
        if meta.get("rules_hash") == stan["zasady"]:
            return False
        stan["zasady"] = meta.get("rules_hash")
        kto = f" --nick {stan['nick']}" if stan["nick"] else ""
        return (f"[hub] this room has rules ({len(tresc.encode())} B) — they "
                f"apply here: agentmachi board{kto} --rules")

    def decyduj(linia):
        linia = linia.rstrip("\n")
        if not linia.strip():
            return False
        if linia.startswith("[reconnect]"):
            if stan["awaria"]:
                return False
            stan["awaria"] = True
            return True
        stan["awaria"] = False
        nowy = NADANY.match(linia) or PODMIENIONY.match(linia)
        if nowy:
            ustaw(nowy.group(1))
        if DIAGNOSTYKA.match(linia):
            return True
        try:
            ramka = json.loads(linia)
        except (ValueError, TypeError):
            return True
        if not isinstance(ramka, dict):
            return True
        typ = ramka.get("type")
        if typ == "session_metadata":
            return _zasady(ramka)
        if typ in TYPY_CICHE:
            return False
        if stan["nick"] and ramka.get("from") == stan["nick"]:
            return False
        if typ in TYPY_BUDZACE:
            return True
        tresc = ramka.get("text")
        return isinstance(tresc, str) and bool(stan["wzmianka"].search(tresc))

    return decyduj


class _Strumien:
    """Strumien tnacy na linie: budzace -> `wyjscie`, kazda -> `kopia`."""

    def __init__(self, decyduj, wyjscie, kopia=None):
        self._decyduj, self._wyjscie, self._kopia = decyduj, wyjscie, kopia
        self._bufor = ""
        self.encoding = getattr(wyjscie, "encoding", "utf-8")

    def write(self, tekst):
        self._bufor += tekst
        while "\n" in self._bufor:
            linia, self._bufor = self._bufor.split("\n", 1)
            self._linia(linia)
        return len(tekst)

    def _linia(self, linia):
        if self._kopia is not None:
            self._kopia.write(linia + "\n")
            self._kopia.flush()
        wynik = self._decyduj(linia)
        if wynik:
            self._wyjscie.write((wynik if isinstance(wynik, str) else linia)
                                + "\n")
            self._wyjscie.flush()

    def flush(self):
        if self._bufor:
            linia, self._bufor = self._bufor, ""
            self._linia(linia)

    def isatty(self):
        return False


@contextlib.contextmanager
def uzbroj(nick):
    """Podmienia stdout/stderr procesu na filtr. stderr idzie TAKZE dalej
    na prawdziwy stderr (harness trzyma go w pliku — tam szuka sie
    przyczyn). Na wyjsciu — takze przez wyjatek — `LISTENER ENDED` na
    stdout: koniec nasluchu musi byc zdarzeniem, nie cisza."""
    wyjscie, blad = sys.stdout, sys.stderr
    decyduj = zbuduj(nick)
    sys.stdout = _Strumien(decyduj, wyjscie)
    sys.stderr = _Strumien(decyduj, wyjscie, kopia=blad)
    try:
        yield
    finally:
        for strumien in (sys.stdout, sys.stderr):
            if isinstance(strumien, _Strumien):
                strumien.flush()
        sys.stdout, sys.stderr = wyjscie, blad
        print(KONIEC, flush=True)
