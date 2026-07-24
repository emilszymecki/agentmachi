# chat/store.py
"""Trwaly log zdarzen pokoju: room_seq, snapshot, kompakcja.

Kolejnosc trwalosci (spec): przy mutacji najpierw trwaly event, potem
publikacja; przy kompakcji najpierw snapshot (tmp+rename), potem usuniecie
przykrytych eventow. events_after zwraca None gdy kursor wypada przed
snapshot_seq — jawny resync_required, nigdy cichy partial replay.

Polityka snapshotow (kiedy i jak czesto kompaktowac) nalezy do serwera;
EventLog dostarcza tylko mechanizm (save_snapshot/load_snapshot).
"""
import json
import os
from pathlib import Path


def _reject_json_constant(value):
    raise ValueError(f"invalid JSON constant in storage: {value}")


class ForeignWriterError(RuntimeError):
    """Ktos inny pisze do naszego events.jsonl — split-brain.

    Zmierzone dwukrotnie na produkcji: `pkill` nie ubil starego huba, drugi
    `serve` wstal obok i oba procesy trzymaly ten sam katalog danych. Gdy
    starszy dostal SIGTERM, jego `stop()` zrobil snapshot ze SWOIM
    (nieaktualnym) stanem i przepisal events.jsonl — kasujac wszystko, co
    w miedzyczasie zapisal nowszy proces. Kompakcja jest jedyna operacja,
    ktora przepisuje log w calosci, wiec to tutaj musi stanac zapora."""


# F1 (B5): typy ramek, ktore sa PAMIECIA kanalu i nie podlegaja kompakcji.
# Reszta (hello/status/task_*) ma swoj stan w snapshocie i moze zniknac.
# F3 (B5): takeover jest czescia PAMIECI kanalu, nie stanem maszyny — stan
# mowi "kto jest teraz", a slad odpowiada na pytanie "dlaczego kolega
# zamilkl". Kompakcja go wiec nie rusza, tak jak rozmowy.
CONVERSATION_TYPES = frozenset({"chat", "takeover", "kick"})
CONVERSATION_LIMIT = 200      # ile ostatnich ramek rozmowy serwujemy
# Ile ramek rozmowy przezywa kompakcje. Kanal to DYSKUSJA, nie archiwum:
# trzymamy okno wznowienia (zeby wracajacy agent nie stracil watku), a nie
# cala historie. Twarda wiedza mieszka w plikach .md pisanych swiadomie —
# log ma byc buforem, nie baza wiedzy (korekta F1 po uwadze operatora).
CONVERSATION_KEEP = 500


def _strict_json_loads(data):
    return json.loads(data, parse_constant=_reject_json_constant)


class EventLog:
    def __init__(self, dirpath):
        self.dir = Path(dirpath)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.dir / "events.jsonl"
        self.snapshot_path = self.dir / "snapshot.json"
        self.snapshot_seq = 0
        self._events = []  # [{seq, ...frame}] tylko > snapshot_seq
        if self.snapshot_path.exists():
            data = _strict_json_loads(self.snapshot_path.read_text())
            self.snapshot_seq = data["snapshot_seq"]
        self.last_seq = self.snapshot_seq
        if self.events_path.exists():
            raw = self.events_path.read_bytes()
            n = len(raw)
            pos = 0
            good_end_offset = 0  # offset za ostatnia poprawna linia (do przyciecia)
            needs_trailing_newline = False  # ostatnia linia OK, ale bez \n
            while pos < n:
                nl_idx = raw.find(b"\n", pos)
                if nl_idx == -1:
                    line_bytes = raw[pos:]
                    has_newline = False
                    line_end = n
                else:
                    line_bytes = raw[pos:nl_idx]
                    has_newline = True
                    line_end = nl_idx + 1
                is_last_chunk = line_end == n
                stripped = line_bytes.strip()
                if stripped:
                    try:
                        e = _strict_json_loads(stripped)
                    except ValueError as exc:
                        if is_last_chunk and not has_newline:
                            # json.dumps nigdy nie wstawia \n w srodku zapisu,
                            # a koncowy \n dopisujemy osobno PO tresci — wiec
                            # brak \n na koncu ostatniej linii jednoznacznie
                            # oznacza urwany zapis w trakcie crashu (torn
                            # tail), nie korupcje. Tolerujemy: przycinamy
                            # plik do offsetu ostatniej poprawnej linii
                            # (ponizej pentli) i jedziemy dalej.
                            break
                        raise ValueError(
                            f"events.jsonl uszkodzony w linii zaczynajacej sie "
                            f"na offsecie {pos} bajtow — linia zakonczona "
                            "znakiem nowej linii (albo nie jest ostatnia w "
                            "pliku), to korupcja, nie urwany ogon po crashu"
                        ) from exc
                    else:
                        if e["seq"] > self.snapshot_seq:
                            self._events.append(e)
                            self.last_seq = e["seq"]
                        if is_last_chunk and not has_newline:
                            # kompletny, poprawny JSON, ale bez konczacego \n:
                            # syscall zdazyl zapisac tresc, crash przed
                            # dopisaniem \n. Event jest juz przyjety wyzej —
                            # tylko dopisujemy brakujacy \n na dysku (nizej),
                            # zeby kolejny append (tryb "a") nie skleil sie
                            # z ta linia w jeden nieparsowalny rekord.
                            needs_trailing_newline = True
                pos = line_end
                good_end_offset = pos
            if needs_trailing_newline:
                with self.events_path.open("ab") as f:
                    f.write(b"\n")
                    f.flush()
                    os.fsync(f.fileno())
            if good_end_offset < n:
                # truncate zamiast open("w")+rewrite: crash w trakcie naprawy
                # nie moze skasowac juz-przyjetego zdrowego prefiksu, bo
                # truncate tylko obcina ogon pliku, nigdy go nie przepisuje
                with self.events_path.open("r+b") as f:
                    f.truncate(good_end_offset)
                    f.flush()
                    os.fsync(f.fileno())

    def append(self, frame):
        seq = self.last_seq + 1
        event = {**frame, "seq": seq}
        # Serializacja PRZED otwarciem pliku: NaN/Infinity ani inny obiekt
        # niezgodny z JSON-em nie moze zostawic czesciowego rekordu ani podbic
        # room_seq. allow_nan=False jest defense-in-depth za strict inbound.
        payload = json.dumps(event, allow_nan=False) + "\n"
        with self.events_path.open("a") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        # last_seq/_events aktualizowane DOPIERO po udanym zapisie — nieudany
        # zapis (wyjatek powyzej) nie podbija numeracji i nie zostawia dziury
        self.last_seq = seq
        self._events.append(event)
        return self.last_seq

    def events_after(self, seq):
        if seq < self.snapshot_seq:
            return None  # resync_required
        return [e for e in self._events if e["seq"] > seq]

    def conversation_after(self, seq, limit=CONVERSATION_LIMIT):
        """F1 (B5): rozmowa o seq > podanym, prosto z dysku.

        Kanal JEST pamiecia agenta — inaczej niz stan maszyny (queue,
        registry), ktory da sie odtworzyc ze snapshotu, rozmowy nie da sie
        odtworzyc z niczego. Dlatego kompakcja jej nie rusza (save_snapshot
        nizej), a tu podajemy ja niezaleznie od kursora i snapshot_seq.
        Czytamy z pliku, nie z RAM: log rozmowy rosnie liniowo z historia
        projektu i nie ma powodu trzymac go w pamieci huba (zmierzone:
        22 ms dla 10k ramek). limit=None oddaje calosc; domyslnie tniemy
        NAJSTARSZE, bo agent potrzebuje swiezego kontekstu."""
        if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
            raise ValueError(f"conversation_after: zly seq: {seq!r}")
        if limit is not None and (not isinstance(limit, int) or limit <= 0):
            raise ValueError(f"conversation_after: zly limit: {limit!r}")
        out = []
        if not self.events_path.exists():
            return out
        with self.events_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = _strict_json_loads(line)
                except ValueError:
                    # urwany ogon po crashu jest naprawiany w __init__;
                    # tutaj pomijamy, zeby odczyt pamieci nigdy nie wywrocil
                    # obslugi hello.
                    continue
                if e.get("type") in CONVERSATION_TYPES and e.get("seq", 0) > seq:
                    out.append(e)
        return out[-limit:] if limit is not None else out

    def _max_seq_on_disk(self):
        top = 0
        if not self.events_path.exists():
            return top
        with self.events_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = _strict_json_loads(line)
                except ValueError:
                    continue
                top = max(top, e.get("seq", 0))
        return top

    def save_snapshot(self, state):
        # F7: nie przepisuj logu, ktorego nie jestes jedynym autorem. Seq na
        # dysku wyzszy niz nasz last_seq oznacza, ze pisal tam inny proces —
        # kompakcja skasowalaby jego ramki. Fail-fast zostawia plik nietkniety.
        disk_top = self._max_seq_on_disk()
        if disk_top > self.last_seq:
            raise ForeignWriterError(
                f"events.jsonl ma seq {disk_top} > naszego {self.last_seq}: "
                f"do katalogu {self.dir} pisze inny proces huba. Kompakcja "
                f"przerwana, zeby nie skasowac cudzych ramek. Zatrzymaj "
                f"nadmiarowy hub (agentmachi list / agentmachi stop).")
        seq = self.last_seq
        tmp = self.dir / "snapshot.json.tmp"
        # Najpierw zwaliduj/serializuj calosc. Blad (np. NaN w stanie) zostawia
        # poprzedni snapshot i jego etykiete nietkniete.
        payload = json.dumps(
            {"snapshot_seq": seq, "state": state}, allow_nan=False)
        with tmp.open("w") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        # os.replace (Path.replace), nie rename: nadpisuje istniejacy cel
        # atomowo na Unix I Windows. rename na Windows rzucal FileExistsError
        # (WinError 183), gdy snapshot.json juz istnial — hub padal w teardown
        # na Windows (zlapane przez codeksa). Atomowosc zachowana na obu OS.
        tmp.replace(self.snapshot_path)  # atomowo; dopiero teraz kompakcja
        self.snapshot_seq = seq
        # F1 (B5): rozmowa NIE podlega kompakcji. Stan maszyny odtwarza sie
        # ze snapshotu, rozmowy nie odtworzy nic — a to ona jest pamiecia
        # agentow. Czytamy zachowana historie z dysku PRZED nadpisaniem
        # pliku (poprzednie kompakcje juz ja tam zostawily) i skladamy z
        # ogonem po snapshocie. Kompaktujemy wylacznie ramki sluzbowe.
        conversation = self.conversation_after(0, limit=CONVERSATION_KEEP)
        self._events = [e for e in self._events if e["seq"] > seq]
        tail_seqs = {e["seq"] for e in self._events}
        # Ogon po snapshocie to stan biezacy — nigdy go nie przycinamy;
        # okno dotyczy wylacznie HISTORII sprzed snapshot_seq.
        keep = [e for e in conversation if e["seq"] not in tail_seqs]
        keep.extend(self._events)
        keep.sort(key=lambda e: e["seq"])
        events_tmp = self.dir / "events.jsonl.tmp"
        with events_tmp.open("w") as f:
            for e in keep:
                f.write(json.dumps(e, allow_nan=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        events_tmp.replace(self.events_path)  # atomowo (os.replace: nadpisuje na Unix I Windows; rename rzucal WinError 183); crash w polowie nie obcina eventow

    def load_snapshot(self):
        if not self.snapshot_path.exists():
            return None
        data = _strict_json_loads(self.snapshot_path.read_text())
        return data["state"], data["snapshot_seq"]

    def replay(self):
        return list(self._events)
