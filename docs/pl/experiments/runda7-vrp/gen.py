"""Generator instancji CVRP. python gen.py SEED N Q ROZKLAD DEPOT > inst.json
ROZKLAD: uniform | klastry ; DEPOT: srodek | rog"""
import json, random, sys

def generuj(seed, n, q, rozklad, depot):
    r = random.Random(seed)
    if rozklad == "uniform":
        pkt = [(r.randint(0, 1000), r.randint(0, 1000)) for _ in range(n)]
    else:
        centra = [(r.randint(100, 900), r.randint(100, 900)) for _ in range(max(3, n // 40))]
        pkt = []
        for _ in range(n):
            cx, cy = r.choice(centra)
            pkt.append((min(1000, max(0, int(r.gauss(cx, 45)))),
                        min(1000, max(0, int(r.gauss(cy, 45))))))
    d = (500, 500) if depot == "srodek" else (0, 0)
    return {"name": f"{rozklad}-{depot}-n{n}-q{q}-s{seed}", "capacity": q,
            "depot": list(d), "customers": [
                {"id": i + 1, "x": x, "y": y, "demand": r.randint(1, 10)}
                for i, (x, y) in enumerate(pkt)]}

if __name__ == "__main__":
    s, n, q, roz, dep = sys.argv[1:]
    print(json.dumps(generuj(int(s), int(n), int(q), roz, dep)))
