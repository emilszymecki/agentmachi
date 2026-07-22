"""Kolejka taskow: stany, lease z TTL, CAS, dedup po command_id.

Stany: open -> claimed -> review -> done; odnogi: changes_requested
(-> claimed, ten sam assignee, lease zachowany) i blocked (TTL zamrozony,
poza WIP). Zamrazanie egzekwuje serwer/kolejka, nie klient.
"""
import copy
import json


class TaskError(Exception):
    pass


class Conflict(TaskError):
    pass


class StaleGeneration(TaskError):
    pass


class TaskQueue:
    def __init__(self, wip_limit=3, lease_ttl=120.0, dedup_ttl=3600.0):
        self.wip_limit = wip_limit
        self.lease_ttl = lease_ttl
        self.dedup_ttl = dedup_ttl
        self._tasks = {}      # id -> task dict
        self._results = {}    # command_id -> (expires_at, deepcopy wyniku)
        self._next_id = 0

    # -- dedup ------------------------------------------------------------
    # Wpis dedup to (expires_at, fingerprint, deepcopy wyniku). Fingerprint
    # identyfikuje operacje+argumenty (bez `now`) — ten sam command_id
    # uzyty ponownie dla innej operacji/innych argumentow to bug klienta,
    # nie cichy zwrot poprzedniego wyniku.
    def _dedup_get(self, command_id, fingerprint, now):
        hit = self._results.get(command_id)
        if hit is None or hit[0] <= now:
            return None
        cached_fingerprint, result = hit[1], hit[2]
        if cached_fingerprint != fingerprint:
            raise Conflict(
                f"command_id {command_id!r} reuse z inna operacja: "
                f"{cached_fingerprint} != {fingerprint}")
        return copy.deepcopy(result)

    def _dedup_put(self, command_id, fingerprint, result, now):
        self._results[command_id] = (
            now + self.dedup_ttl, fingerprint, copy.deepcopy(result))
        return result

    def _check_command_id(self, command_id):
        if not isinstance(command_id, str) or not command_id:
            raise TaskError(f"invalid command_id: {command_id!r}")

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
        fingerprint = ("add", json.dumps(card, sort_keys=True), None, None, None)
        cached = self._dedup_get(command_id, fingerprint, now)
        if cached is not None:
            return cached
        self._next_id += 1
        task = {"id": f"t{self._next_id}", "card": copy.deepcopy(card),
                "status": "open", "assignee": None, "generation": None,
                "version": 1, "lease_until": None, "frozen": False}
        self._tasks[task["id"]] = task
        return self._dedup_put(command_id, fingerprint, copy.deepcopy(task), now)

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

    def claim(self, task_id, nick, generation, command_id, expected_version, now):
        self._check_command_id(command_id)
        fingerprint = ("claim", task_id, nick, generation, expected_version)
        cached = self._dedup_get(command_id, fingerprint, now)
        if cached is not None:
            return cached
        task = self._get_task(task_id)
        self._check(task, expected_version)
        if task["status"] != "open":
            raise Conflict(f"{task_id}: status {task['status']}, nie open")
        task.update(status="claimed", assignee=nick, generation=generation,
                    version=task["version"] + 1,
                    lease_until=now + self.lease_ttl)
        return self._dedup_put(command_id, fingerprint, copy.deepcopy(task), now)

    def heartbeat(self, task_id, nick, generation, now):
        task = self._get_task(task_id)
        self._check_owner(task, nick, generation)
        if not task["frozen"]:
            task["lease_until"] = now + self.lease_ttl

    def _mutate(self, op, task_id, command_id, expected_version, now,
                owner=None, from_status=None, **updates):
        self._check_command_id(command_id)
        nick, generation = owner if owner is not None else (None, None)
        fingerprint = (op, task_id, nick, generation, expected_version)
        cached = self._dedup_get(command_id, fingerprint, now)
        if cached is not None:
            return cached
        task = self._get_task(task_id)
        self._check(task, expected_version)
        if owner is not None:
            self._check_owner(task, nick, generation)
        if from_status and task["status"] not in from_status:
            raise Conflict(
                f"{task_id}: status {task['status']}, oczekiwano {from_status}")
        task.update(version=task["version"] + 1, **updates)
        return self._dedup_put(command_id, fingerprint, copy.deepcopy(task), now)

    def block(self, task_id, nick, generation, command_id, expected_version, now):
        return self._mutate("block", task_id, command_id, expected_version, now,
                             owner=(nick, generation), from_status=("claimed",),
                             status="blocked", frozen=True)

    def unblock(self, task_id, nick, generation, command_id, expected_version, now):
        return self._mutate("unblock", task_id, command_id, expected_version, now,
                             owner=(nick, generation), from_status=("blocked",),
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

    def expire(self, now):
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

    def dump(self):
        return {"next_id": self._next_id,
                "tasks": copy.deepcopy(list(self._tasks.values()))}

    @classmethod
    def restore(cls, data, **kwargs):
        q = cls(**kwargs)
        q._next_id = data["next_id"]
        q._tasks = {t["id"]: t for t in copy.deepcopy(data["tasks"])}
        return q
