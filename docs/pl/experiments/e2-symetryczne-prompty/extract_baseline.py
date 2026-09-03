#!/usr/bin/env python3
"""Odtwarza baseline-e1/przypadek-{1..4}.txt z dowolnego logu zawierającego
ramkę `seq 625` pokoju `interwizja` — czterech promptów przebiegu E1.

    python3 extract_baseline.py <log.jsonl> [katalog-wyjściowy]

Log może być hubowym `events.jsonl` albo wyjściem `agentmachi listen --json`:
skrypt czyta linie JSON i bierze tę z `seq == 625`. Pliki są SKŁADANE, nie
wycinane w całości: polecenie jest w ramce jako cytat (wcięty, w cudzysłowie),
materiały jako bloki między `---`. Reguła składania jest ta sama dla wszystkich
ośmiu plików (E1 i E2), więc w `diff` E1->E2 się skraca.

Weryfikacja bazy = uruchomić to na SWOIM logu i zrobić `diff -r` wobec
`baseline-e1/`. Porównywanie bajtów ramki z plikiem nie zadziała i nie o to
chodzi.
"""
import hashlib
import json
import os
import re
import sys

SEQ = 625


def frame_text(path):
    found = None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("seq") == SEQ:
                found = d.get("text")
    if found is None:
        sys.exit("nie ma ramki seq %d w %s" % (SEQ, path))
    return found


def command_of(text):
    m = re.search(r"dosłownie:\n(.*?)\n\nZwróć", text, re.S)
    if not m:
        sys.exit("nie znaleziono bloku polecenia")
    lines = [l.strip() for l in m.group(1).split("\n")]
    lines[0] = lines[0].lstrip('"')
    lines[-1] = lines[-1].rstrip('"')
    return "\n".join(lines)


def materials_of(text):
    out = {}
    for n in (1, 2, 3, 4):
        m = re.search(r"=+ PROMPT %d =+\n---\n(.*?)\n---" % n, text, re.S)
        if not m:
            sys.exit("nie znaleziono materiału przypadku %d" % n)
        out[n] = m.group(1)
    return out


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    text = frame_text(argv[1])
    outdir = argv[2] if len(argv) > 2 else "."
    command = command_of(text)
    materials = materials_of(text)
    os.makedirs(outdir, exist_ok=True)
    for n in (1, 2, 3, 4):
        body = command + "\n\n" + materials[n] + "\n"
        path = os.path.join(outdir, "przypadek-%d.txt" % n)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        print("%s  %s" % (hashlib.sha256(body.encode("utf-8")).hexdigest(), path))


if __name__ == "__main__":
    main(sys.argv)
