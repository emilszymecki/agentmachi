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
    def _dedup_get(self, command_id, now):
        hit = self._results.get(command_id)
        if hit and hit[0] > now:
            return copy.deepcopy(hit[1])
        return None

    def _dedup_put(self, command_id, result, now):
        self._results[command_id] = (now + self.dedup_ttl, copy.deepcopy(result))
        return result

    # -- operacje ----------------------------------------------------------
    def add(self, card, command_id, now):
        cached = self._dedup_get(command_id, now)
        if cached is not None:
            return cached
        self._next_id += 1
        task = {"id": f"t{self._next_id}", "card": card, "status": "open",
                "assignee": None, "generation": None, "version": 1,
                "lease_until": None, "frozen": False}
        self._tasks[task["id"]] = task
        return self._dedup_put(command_id, copy.deepcopy(task), now)

    def get(self, task_id):
        return copy.deepcopy(self._tasks[task_id])

    def _check(self, task, expected_version):
        if task["version"] != expected_version:
            raise Conflict(
                f"{task['id']}: version {task['version']} != {expected_version}")

    def _check_owner(self, task, nick, generation):
        if task["assignee"] != nick or task["generation"] != generation:
            raise StaleGeneration(
                f"{task['id']}: {nick}/gen{generation} nie jest wlascicielem")

    def claim(self, task_id, nick, generation, command_id, expected_version, now):
        cached = self._dedup_get(command_id, now)
        if cached is not None:
            return cached
        task = self._tasks[task_id]
        self._check(task, expected_version)
        if task["status"] != "open":
            raise Conflict(f"{task_id}: status {task['status']}, nie open")
        task.update(status="claimed", assignee=nick, generation=generation,
                    version=task["version"] + 1,
                    lease_until=now + self.lease_ttl)
        return self._dedup_put(command_id, copy.deepcopy(task), now)

    def heartbeat(self, task_id, nick, generation, now):
        task = self._tasks[task_id]
        self._check_owner(task, nick, generation)
        if not task["frozen"]:
            task["lease_until"] = now + self.lease_ttl
