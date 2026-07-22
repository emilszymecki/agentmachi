"""Kolejka taskow: stany, lease z TTL, CAS, dedup po command_id.

Stany: open -> claimed -> review -> done; odnogi: changes_requested
(-> claimed, ten sam assignee, lease zachowany) i blocked (TTL zamrozony,
poza WIP). Zamrazanie egzekwuje serwer/kolejka, nie klient.
"""
import copy


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
        fingerprint = ("add", None, None, None, None)
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
