"""Publiczny oceniacz CVRP.
  python ocen.py KATALOG_PROJEKTU instancja.json [instancja.json ...]
Uruchamia `python -m vrp <instancja>` w KATALOG_PROJEKTU (limit 12 s),
sprawdza rozwiazanie i liczy punkty: 100 * koszt_bazowy / twoj_koszt,
gdzie koszt_bazowy to zachlanny najblizszy sasiad z ograniczeniem pojemnosci.
Rozwiazanie nieprawidlowe / blad / przekroczony czas = 0 pkt."""
import json, math, subprocess, sys, time

LIMIT = 12.0

def odl(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])

def koszt(inst, trasy):
    pos = {c["id"]: (c["x"], c["y"]) for c in inst["customers"]}
    dep = tuple(inst["depot"])
    k = 0.0
    for t in trasy:
        if not t:
            continue
        p = [dep] + [pos[c] for c in t] + [dep]
        k += sum(odl(p[i], p[i + 1]) for i in range(len(p) - 1))
    return k

def sprawdz(inst, wynik):
    """None gdy OK, inaczej powod."""
    if not isinstance(wynik, dict) or not isinstance(wynik.get("routes"), list):
        return "brak listy routes"
    ids = {c["id"]: c["demand"] for c in inst["customers"]}
    widziane = []
    for t in wynik["routes"]:
        if not isinstance(t, list) or not all(isinstance(c, int) and not isinstance(c, bool) for c in t):
            return "trasa nie jest lista int"
        if any(c not in ids for c in t):
            return "nieznany klient"
        if sum(ids[c] for c in t) > inst["capacity"]:
            return "przekroczona pojemnosc"
        widziane += t
    if sorted(widziane) != sorted(ids):
        return "klient pominiety albo powtorzony"
    return None

def bazowy(inst):
    pos = {c["id"]: (c["x"], c["y"]) for c in inst["customers"]}
    dem = {c["id"]: c["demand"] for c in inst["customers"]}
    zostalo = set(pos)
    dep = tuple(inst["depot"])
    trasy = []
    while zostalo:
        t, lad, gdzie = [], 0, dep
        while True:
            kand = [c for c in zostalo if lad + dem[c] <= inst["capacity"]]
            if not kand:
                break
            c = min(kand, key=lambda c: (odl(gdzie, pos[c]), c))
            t.append(c); lad += dem[c]; gdzie = pos[c]; zostalo.discard(c)
        trasy.append(t)
    return koszt(inst, trasy)

def ocen(projekt, sciezka):
    inst = json.load(open(sciezka))
    t0 = time.monotonic()
    try:
        p = subprocess.run([sys.executable, "-m", "vrp", sciezka], cwd=projekt,
                           capture_output=True, text=True, timeout=LIMIT)
    except subprocess.TimeoutExpired:
        return 0.0, "przekroczony czas", None
    czas = time.monotonic() - t0
    if p.returncode != 0:
        return 0.0, f"kod {p.returncode}: {p.stderr.strip()[-200:]}", czas
    try:
        wynik = json.loads(p.stdout)
    except ValueError:
        return 0.0, "stdout to nie JSON", czas
    blad = sprawdz(inst, wynik)
    if blad:
        return 0.0, blad, czas
    return 100.0 * bazowy(inst) / koszt(inst, wynik["routes"]), "ok", czas

if __name__ == "__main__":
    projekt, *pliki = sys.argv[1:]
    import os
    projekt = os.path.abspath(projekt)
    pkt = []
    for f in pliki:
        s, powod, czas = ocen(projekt, os.path.abspath(f))
        pkt.append(s)
        print(f"{os.path.basename(f):40s} {s:7.2f}  {powod}  {'' if czas is None else f'{czas:.1f}s'}")
    print(f"SREDNIA {sum(pkt) / len(pkt):.2f}")
