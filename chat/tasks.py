"""Kolejka taskow: stany, lease z TTL, CAS, dedup po command_id.

Stany: open -> claimed -> review -> done; odnogi: changes_requested
(-> claimed, ten sam assignee, lease zachowany) i blocked (TTL zamrozony,
poza WIP). Zamrazanie egzekwuje serwer/kolejka, nie klient.
"""
import copy
import json
import math


class TaskError(Exception):
    pass


class Conflict(TaskError):
    pass


class StaleGeneration(TaskError):
    pass


_UNSET = object()  # odroznia "pole nie dotyczy tej operacji" od realnego None


class TaskQueue:
    CARD_REQUIRED_FIELDS = ("goal", "acceptance", "verify", "files", "head", "brief")

    def __init__(self, wip_limit=3, lease_ttl=120.0, dedup_ttl=None):
        self.wip_limit = wip_limit
        self.lease_ttl = lease_ttl
        # dedup_ttl: przyjmowany dla kompatybilnosci wstecznej ze starszym
        # API/planem, NIEUZYWANY w B1 — dedup jest bez TTL (patrz komentarz
        # nad _dedup_get). None = wpisy dedup zyja do kontrolowanej
        # kompakcji; wartosc liczbowa jest akceptowana (nie rzuca), ale nie
        # ma zadnego efektu na retencje.
        self.dedup_ttl = dedup_ttl
        self._tasks = {}      # id -> task dict
        self._results = {}    # command_id -> (fingerprint, deepcopy wyniku)
        self._next_id = 0
        # (Runda 4 #1) osobny sygnal dla serwera: czy OSTATNIA mutacja o danym
        # command_id byla dedup cache-hitem (True) czy faktyczna mutacja
        # (False). Cache-hit to ODPOWIEDZ dla klienta, NIE fakt do logu —
        # serwer appenduje trwaly task_state event TYLKO gdy last_dedup_hit
        # jest False (inaczej replay po restarcie cofalby stan). Ustawiany
        # wylacznie w _dedup_get (jedyna brama hit/miss dla wszystkich mutacji).
        self.last_dedup_hit = False

    # -- dedup ------------------------------------------------------------
    # Wpis dedup to (fingerprint, deepcopy wyniku). Bez TTL w B1: retencja
    # command_id musi zyc co najmniej tyle co task wg speca, a stala TTL
    # tego nie gwarantuje — wpisy zyja do kontrolowanej kompakcji (poza
    # zakresem tego pliku). Fingerprint identyfikuje operacje+argumenty
    # (bez `now`) — ten sam command_id uzyty ponownie dla innej
    # operacji/innych argumentow to bug klienta, nie cichy zwrot
    # poprzedniego wyniku.
    def _dedup_get(self, command_id, fingerprint):
        hit = self._results.get(command_id)
        if hit is None:
            self.last_dedup_hit = False   # miss -> ta operacja bedzie mutacja
            return None
        cached_fingerprint, result = hit
        if cached_fingerprint != fingerprint:
            # reuse command_id z INNA operacja to bug klienta — zostaw
            # last_dedup_hit bez zmiany (i tak rzucamy, serwer nic nie appenduje)
            raise Conflict(
                f"command_id {command_id!r} reuse z inna operacja: "
                f"{cached_fingerprint} != {fingerprint}")
        self.last_dedup_hit = True        # cache-hit -> odpowiedz, nie mutacja
        return copy.deepcopy(result)

    def _dedup_put(self, command_id, fingerprint, result):
        self._results[command_id] = (fingerprint, copy.deepcopy(result))
        return result

    def dedup_fingerprint(self, op, *, card=None, task_id=None, nick=None,
                          generation=None, expected_version=None):
        # (Runda 6) JEDYNE zrodlo prawdy fingerprintu dedup — uzywane i przez
        # mutacje (add/claim/_mutate/approve), i przez serwerowy peek_dedup PRZED
        # deepcopy (short-circuit retry bez kopii calej kolejki). Dla 'add'
        # fingerprint kotwiczy sie w SERIALIZOWANEJ, zwalidowanej karcie; dla
        # reszty w (task_id, nick, generation, expected_version). Zmiana
        # ktoregokolwiek pola = inna komenda (ten sam command_id -> Conflict).
        if op == "add":
            return ("add", self._check_card(card), None, None, None)
        return (op, task_id, nick, generation, expected_version)

    def peek_dedup(self, command_id, fingerprint):
        # (Runda 6) czysty PODGLAD dedup BEZ mutacji i BEZ zmiany last_dedup_hit:
        # deepcopy wyniku TYLKO przy pelnym trafieniu (command_id + zgodny
        # fingerprint). Rozjazd fingerprintu / brak wpisu -> None; wolajacy
        # schodzi wtedy na sciezke klon-mutacja, gdzie klon (majacy ten sam wpis
        # dedup) autorytatywnie zwroci cached ALBO rzuci Conflict. Pozwala
        # pominac deepcopy calej kolejki na najczestszej sciezce (retry).
        hit = self._results.get(command_id)
        if hit is None:
            return None
        cached_fingerprint, result = hit
        if cached_fingerprint != tuple(fingerprint):
            return None
        return copy.deepcopy(result)

    def _check_command_id(self, command_id):
        if not isinstance(command_id, str) or not command_id:
            raise TaskError(f"invalid command_id: {command_id!r}")

    def _check_card(self, card):
        if not isinstance(card, dict):
            raise TaskError(f"invalid card: not a dict: {card!r}")
        missing = [f for f in self.CARD_REQUIRED_FIELDS if f not in card]
        if missing:
            raise TaskError(f"invalid card: missing fields {missing}")
        try:
            return json.dumps(card, sort_keys=True)
        except TypeError as e:
            raise TaskError(f"invalid card: not JSON-serializable: {e}")

    # Wspolny guard pol klienckich w mutacjach. Kazdy parametr domyslnie
    # _UNSET -> pomijany (np. request_changes nie ma nick/generation).
    # generation >= 1 (po hello() w identity.Registry generacja jest zawsze
    # dodatnia — 0 wystepuje tylko przed pierwszym hello, wiec nie jest to
    # legalna generacja klienta w tasks), expected_version >= 1 (wersje
    # taska zaczynaja sie od 1) — ta sama dolna granica, dwa oddzielne pola.
    def _check_inputs(self, nick=_UNSET, generation=_UNSET,
                       expected_version=_UNSET, now=_UNSET):
        if nick is not _UNSET:
            if not isinstance(nick, str) or not nick:
                raise TaskError(f"invalid nick: {nick!r}")
        if generation is not _UNSET:
            if (isinstance(generation, bool) or not isinstance(generation, int)
                    or generation < 1):
                raise TaskError(f"invalid generation: {generation!r}")
        if expected_version is not _UNSET:
            if (isinstance(expected_version, bool)
                    or not isinstance(expected_version, int)
                    or expected_version < 1):
                raise TaskError(f"invalid expected_version: {expected_version!r}")
        if now is not _UNSET:
            # jawnie int|float, bool wykluczony (bool jest podklasa int, a
            # math.isfinite akceptuje kazdy obiekt z __float__ — np.
            # decimal.Decimal — wiec sam isfinite() by tego nie zlapal i
            # dalej w claim/_mutate `now + self.lease_ttl` wywalaloby sie
            # golym TypeError zamiast czytelnym TaskError)
            if (isinstance(now, bool) or not isinstance(now, (int, float))
                    or not math.isfinite(now)):
                raise TaskError(f"invalid now: {now!r}")

    def _get_task(self, task_id):
        if not isinstance(task_id, str) or not task_id:
            raise TaskError(f"invalid task_id: {task_id!r}")
        task = self._tasks.get(task_id)
        if task is None:
            raise TaskError(f"unknown task_id: {task_id!r}")
        return task

    # -- operacje ----------------------------------------------------------
    def add(self, card, command_id, now):
        self._check_command_id(command_id)
        self._check_inputs(now=now)
        fingerprint = self.dedup_fingerprint("add", card=card)  # waliduje karte
        cached = self._dedup_get(command_id, fingerprint)
        if cached is not None:
            return cached
        self._next_id += 1
        task = {"id": f"t{self._next_id}", "card": copy.deepcopy(card),
                "status": "open", "assignee": None, "generation": None,
                "version": 1, "lease_until": None, "frozen": False}
        self._tasks[task["id"]] = task
        return self._dedup_put(command_id, fingerprint, copy.deepcopy(task))

    def get(self, task_id):
        return copy.deepcopy(self._get_task(task_id))

    def _check(self, task, expected_version):
        if task["version"] != expected_version:
            raise Conflict(
                f"{task['id']}: version {task['version']} != {expected_version}")

    def _check_owner(self, task, nick, generation):
        if task["assignee"] != nick or task["generation"] != generation:
            raise StaleGeneration(
                f"{task['id']}: {nick}/gen{generation} nie jest wlascicielem")

    # Wspolny gate WIP dla kazdego przejscia Z POZA licznika WIP
    # ({claimed, review}) DO tego licznika: open->claimed (claim) i
    # blocked->claimed (unblock). Bez tego drugi slot mozna bylo przemycic
    # obchodzac claim: claim(t1)->block(t1) zwalnia slot (blocked jest poza
    # WIP), claim(t2) zajmuje go, unblock(t1) wracal bez sprawdzenia i dawal
    # DWA claimed przy wip_limit=1.
    def _check_wip(self, task_id):
        wip = sum(1 for t in self._tasks.values()
                  if t["status"] in ("claimed", "review"))
        if wip >= self.wip_limit:
            raise Conflict(f"{task_id}: WIP limit ({wip}/{self.wip_limit})")

    def claim(self, task_id, nick, generation, command_id, expected_version, now):
        self._check_command_id(command_id)
        self._check_inputs(nick=nick, generation=generation,
                            expected_version=expected_version, now=now)
        fingerprint = self.dedup_fingerprint(
            "claim", task_id=task_id, nick=nick, generation=generation,
            expected_version=expected_version)
        cached = self._dedup_get(command_id, fingerprint)
        if cached is not None:
            return cached
        task = self._get_task(task_id)
        self._check(task, expected_version)
        if task["status"] != "open":
            raise Conflict(f"{task_id}: status {task['status']}, nie open")
        self._check_wip(task_id)
        task.update(status="claimed", assignee=nick, generation=generation,
                    version=task["version"] + 1,
                    lease_until=now + self.lease_ttl)
        return self._dedup_put(command_id, fingerprint, copy.deepcopy(task))

    def heartbeat(self, task_id, nick, generation, now):
        self._check_inputs(nick=nick, generation=generation, now=now)
        task = self._get_task(task_id)
        self._check_owner(task, nick, generation)
        if task["status"] != "claimed":
            raise TaskError(
                f"{task_id}: status {task['status']}, nie claimed — "
                "heartbeat niedozwolony")
        if task["lease_until"] is not None and task["lease_until"] <= now:
            raise TaskError(
                f"{task_id}: lease wygasl ({task['lease_until']} <= {now}), "
                "oczekuje na expire()")
        task["lease_until"] = now + self.lease_ttl

    def _mutate(self, op, task_id, command_id, expected_version, now,
                owner=None, from_status=None, check_wip=False, **updates):
        self._check_command_id(command_id)
        nick, generation = owner if owner is not None else (None, None)
        if owner is not None:
            self._check_inputs(nick=nick, generation=generation,
                                expected_version=expected_version, now=now)
        else:
            self._check_inputs(expected_version=expected_version, now=now)
        fingerprint = self.dedup_fingerprint(
            op, task_id=task_id, nick=nick, generation=generation,
            expected_version=expected_version)
        cached = self._dedup_get(command_id, fingerprint)
        if cached is not None:
            return cached
        task = self._get_task(task_id)
        self._check(task, expected_version)
        if owner is not None:
            self._check_owner(task, nick, generation)
        if from_status and task["status"] not in from_status:
            raise Conflict(
                f"{task_id}: status {task['status']}, oczekiwano {from_status}")
        # task claimed z wygasla juz dzierzawa nie moze byc mutowany dalej
        # (block/to_review) — musi najpierw przejsc przez expire() i wrocic
        # do open. Sprawdzane atomowo tutaj, nie osobnym wywolaniem.
        if (task["status"] == "claimed" and task["lease_until"] is not None
                and task["lease_until"] <= now):
            raise Conflict(
                f"{task_id}: lease wygasl ({task['lease_until']} <= {now}), "
                "wymagane expire()")
        # unblock (blocked->claimed) wchodzi do licznika WIP z zewnatrz —
        # sam gate WIP co w claim (open->claimed), zeby unblock nie mogl
        # obejsc limitu (patrz komentarz nad _check_wip).
        if check_wip:
            self._check_wip(task_id)
        task.update(version=task["version"] + 1, **updates)
        return self._dedup_put(command_id, fingerprint, copy.deepcopy(task))

    def block(self, task_id, nick, generation, command_id, expected_version, now):
        return self._mutate("block", task_id, command_id, expected_version, now,
                             owner=(nick, generation), from_status=("claimed",),
                             status="blocked", frozen=True)

    def unblock(self, task_id, nick, generation, command_id, expected_version, now):
        return self._mutate("unblock", task_id, command_id, expected_version, now,
                             owner=(nick, generation), from_status=("blocked",),
                             check_wip=True,
                             status="claimed", frozen=False,
                             lease_until=now + self.lease_ttl)

    def to_review(self, task_id, nick, generation, command_id, expected_version, now):
        return self._mutate("to_review", task_id, command_id, expected_version, now,
                             owner=(nick, generation), from_status=("claimed",),
                             status="review", frozen=True)

    def request_changes(self, task_id, command_id, expected_version, now):
        return self._mutate("request_changes", task_id, command_id, expected_version, now,
                             from_status=("review",),
                             status="claimed", frozen=False,
                             lease_until=now + self.lease_ttl)

    def done(self, task_id, nick, generation, command_id, expected_version, now):
        return self._mutate("done", task_id, command_id, expected_version, now,
                             owner=(nick, generation), from_status=("review",),
                             status="done", frozen=False, lease_until=None)

    def approve(self, task_id, approver, command_id, expected_version, now):
        # B1 (SWIADOMA DECYZJA KONTRAKTU): task_approve moze wyslac KTOKOLWIEK
        # POZA assignee — namiastka bramki review przy braku rol uprawnien w
        # B1. "Nie-autor zatwierdza prace autora" jest najblizej semantyce
        # review-gate; docelowo (B2+) approve przejdzie przez bramke matki /
        # uprawnienia. done() (owner-based) zostaje jako prymityw "wlasciciel
        # zamyka" — approve to osobna, swiadoma sciezka.
        self._check_command_id(command_id)
        self._check_inputs(nick=approver, expected_version=expected_version, now=now)
        fingerprint = self.dedup_fingerprint(
            "approve", task_id=task_id, nick=approver,
            expected_version=expected_version)
        cached = self._dedup_get(command_id, fingerprint)
        if cached is not None:
            return cached
        task = self._get_task(task_id)
        self._check(task, expected_version)
        if task["status"] != "review":
            raise Conflict(f"{task_id}: status {task['status']}, oczekiwano review")
        if task["assignee"] == approver:
            raise Conflict(
                f"{task_id}: {approver} jest assignee — approve musi wyslac "
                "ktos inny (B1: approve != assignee)")
        task.update(status="done", version=task["version"] + 1,
                    frozen=False, lease_until=None)
        return self._dedup_put(command_id, fingerprint, copy.deepcopy(task))

    def expire(self, now):
        self._check_inputs(now=now)
        reopened = []
        for task in self._tasks.values():
            if (task["status"] == "claimed" and not task["frozen"]
                    and task["lease_until"] is not None
                    and task["lease_until"] <= now):
                task.update(status="open", assignee=None, generation=None,
                            lease_until=None, version=task["version"] + 1)
                reopened.append(copy.deepcopy(task))
        return reopened

    def offerable(self):
        wip = sum(1 for t in self._tasks.values()
                  if t["status"] in ("claimed", "review"))
        if wip >= self.wip_limit:
            return None
        for task in self._tasks.values():  # dict zachowuje kolejnosc wstawien
            if task["status"] == "open":
                return copy.deepcopy(task)
        return None

    def fingerprint_for(self, command_id):
        # Fingerprint dedup faktycznie uzyty przez ostatnia udana mutacje o
        # tym command_id — serwer wklada go do trwalego eventu, zeby replay
        # mogl bezwalidacyjnie odtworzyc wpis dedup (patrz apply_replayed).
        hit = self._results.get(command_id)
        return list(hit[0]) if hit is not None else None

    def apply_replayed(self, task_state, command_id, fingerprint):
        # SEDNO rundy 3 — replay RESULT-BASED, nie re-execution. Stan taska
        # po mutacji jest zapisany w evencie (task_state) i tu APLIKOWANY
        # WPROST: bez ponownej walidacji WIP/lease/CAS/polityk i bez
        # przeliczania lease_until (odtwarzany HISTORYCZNY, dokladnie taki jak
        # w chwili mutacji). Odtwarzamy tez wpis dedup, zeby retry tego samego
        # command_id po restarcie zwrocil wynik z cache, a nie re-mutowal.
        task = copy.deepcopy(task_state)
        self._tasks[task["id"]] = task
        tid = task.get("id")
        if isinstance(tid, str) and tid.startswith("t") and tid[1:].isdigit():
            self._next_id = max(self._next_id, int(tid[1:]))
        if command_id is not None and fingerprint is not None:
            self._results[command_id] = (tuple(fingerprint), copy.deepcopy(task))

    def dump(self):
        return {"next_id": self._next_id,
                "tasks": copy.deepcopy(list(self._tasks.values())),
                "results": [[command_id, list(fingerprint), copy.deepcopy(result)]
                            for command_id, (fingerprint, result)
                            in self._results.items()]}

    @classmethod
    def restore(cls, data, **kwargs):
        q = cls(**kwargs)
        q._next_id = data["next_id"]
        q._tasks = {t["id"]: t for t in copy.deepcopy(data["tasks"])}
        # fingerprint po podrozy przez JSON to lista — normalizacja do
        # krotki, bo _dedup_get porownuje go z fingerprintem budowanym w
        # add/claim/_mutate (zawsze krotka).
        q._results = {
            command_id: (tuple(fingerprint), copy.deepcopy(result))
            for command_id, fingerprint, result in data.get("results", [])}
        return q
