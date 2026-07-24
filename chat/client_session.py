"""Sesja klienta: tozsamosc + kursor per hub+nick. Zero sieci.

Kontrakt (wsad b2-task-resumowalny-klient + review-guard codexa):
- plik sesji per (hub, nick): namespace przez bezpieczny slug + hash,
  NIGDY surowy URI/nick w nazwie pliku,
- zapis atomowy (tmp + fsync + os.replace + fsync katalogu), tryb 0600,
- DWA zakresy lockow: krotki state-lock chroni kazde
  read/modify/atomic-replace (send_once i listener wspoldziela go bez
  konfliktu), osobny listener-lock jest lifetime-exclusive per hub+nick
  (drugi listener tego samego huba+nicka = ListenerLockHeld),
- kursor: advance(seq) monotoniczny, wolany PO zastosowaniu ramki;
  cofniecie/duplikat = no-op (zwraca False),
- activation_id: trwaly klucz idempotencji adaptera (seen_activation
  zapisuje i przycina okno), duplikat wybudzenia = suppress,
- fail-closed: uszkodzony/niezgodny plik sesji rzuca SessionError z
  instrukcja naprawy — NIGDY cichy reset kursora do 0,
- migracja: legacy .chat-session.json (wspolny instance_id per klon repo)
  moze byc zrodlem instance_id przy PIERWSZYM utworzeniu sesji, zeby nie
  takeover'owac wlasnego dzialajacego listenera.
"""
import hashlib
import json
import os
import re
import sys
import uuid
from pathlib import Path

# fcntl istnieje tylko na Unixie; klient ma dzialac cross-platform (zlapane,
# gdy PIERWSZY klient Windows padl na `import fcntl` przy ladowaniu modulu —
# `agentmachi listen` umieral, zanim cokolwiek zrobil, mimo ze `--help`
# przechodzil). Oba locki (listener-lock i state-lock) ida przez cienka
# abstrakcje: flock na Unixie, msvcrt.locking na Windows. Semantyka zachowana:
# exclusive lock per plik; wariant non-blocking rzuca BlockingIOError — a
# dokladnie to lapie acquire_listener_lock, zamieniajac na ListenerLockHeld.
if sys.platform == "win32":
    import msvcrt

    def _lock_exclusive(fd, blocking):
        # msvcrt.locking blokuje region od BIEZACEJ pozycji — kotwiczymy go na
        # [0, 1), zeby lock i unlock zawsze celowaly w ten sam bajt (plik locka
        # bywa pusty; Windows dopuszcza lock poza EOF). LK_LOCK ponawia ~10 s i
        # dopiero wtedy rzuca — dla KROTKIEGO state-locka to bezpieczne (lepiej
        # blad niz wieczny deadlock).
        os.lseek(fd, 0, os.SEEK_SET)
        mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
        try:
            msvcrt.locking(fd, mode, 1)
        except OSError as e:
            # zajete w trybie non-blocking -> ujednolicamy do BlockingIOError,
            # tego samego typu, ktory rzuca flock(LOCK_NB) na Unixie.
            raise BlockingIOError(str(e)) from e

    def _unlock(fd):
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass

    def _fsync_dir(path):
        # Windows nie pozwala os.open(katalog) (PermissionError) i nie zna
        # POSIX-owego fsync katalogu: os.replace jest tam atomowe, a trwalosc
        # wpisu daje NTFS. fsync DANYCH pliku (nizej w _atomic_write) zostaje na
        # obu OS — to ON trzyma inwariant "trwalosc przed publikacja", nie
        # fsync katalogu. Zlapane, gdy pierwszy klient Windows padl tu po
        # przejsciu locka (druga warstwa tego samego cross-platform buga).
        pass
else:
    import fcntl

    def _lock_exclusive(fd, blocking):
        flags = fcntl.LOCK_EX if blocking else (fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, flags)   # wariant non-blocking rzuca BlockingIOError

    def _unlock(fd):
        fcntl.flock(fd, fcntl.LOCK_UN)

    def _fsync_dir(path):
        # POSIX: po rename trzeba fsync KATALOGU, zeby nowa nazwa przetrwala
        # pad zasilania (sam fsync pliku nie gwarantuje trwalosci wpisu).
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

SCHEMA = 1
MAX_ACTIVATIONS = 200


class SessionError(Exception):
    pass


class ListenerLockHeld(SessionError):
    pass


def _slug(hub, nick):
    safe_nick = re.sub(r"[^A-Za-z0-9_-]", "_", nick)[:32] or "nick"
    digest = hashlib.sha256(f"{hub}\n{nick}".encode("utf-8")).hexdigest()[:12]
    return f"{safe_nick}-{digest}"


def _atomic_write_0600(path, payload):
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(payload))
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, path)
    _fsync_dir(path.parent)


class Session:
    def __init__(self, hub, nick, base_dir=None, legacy_instance_file=None):
        if not isinstance(hub, str) or not hub:
            raise SessionError(f"invalid hub: {hub!r}")
        if not isinstance(nick, str) or not nick:
            raise SessionError(f"invalid nick: {nick!r}")
        base = Path(base_dir or os.environ.get("CHAT_SESSION_DIR")
                    or Path.home() / ".chat-sessions")
        base.mkdir(parents=True, exist_ok=True)
        os.chmod(base, 0o700)
        slug = _slug(hub, nick)
        self.path = base / f"{slug}.json"
        self._state_lock_path = base / f"{slug}.lock"
        self._listener_lock_path = base / f"{slug}.listener.lock"
        self._listener_lock_fh = None
        self._legacy_instance_file = (
            Path(legacy_instance_file) if legacy_instance_file else None)
        with self._state_lock():
            self._state = self._load_or_create_locked()

    # -- locki ------------------------------------------------------------
    def _state_lock(self):
        return _StateLock(self._state_lock_path)

    def acquire_listener_lock(self):
        """Lifetime-exclusive: dokladnie jeden listener per hub+nick.
        Trzymany przez zycie procesu (fd zostaje otwarty)."""
        fd = os.open(self._listener_lock_path,
                     os.O_WRONLY | os.O_CREAT, 0o600)
        try:
            _lock_exclusive(fd, blocking=False)
        except BlockingIOError:
            os.close(fd)
            raise ListenerLockHeld(
                f"inny listener dla tej sesji juz dziala "
                f"(lock: {self._listener_lock_path})")
        self._listener_lock_fh = fd
        return self

    def release_listener_lock(self):
        if self._listener_lock_fh is not None:
            _unlock(self._listener_lock_fh)
            os.close(self._listener_lock_fh)
            self._listener_lock_fh = None

    # -- stan -------------------------------------------------------------
    def _load_or_create_locked(self):
        if self.path.exists():
            raw = self.path.read_text()
            try:
                state = json.loads(raw)
            except json.JSONDecodeError as e:
                raise SessionError(
                    f"plik sesji {self.path} jest uszkodzony ({e}). "
                    f"Fail-closed: NIE resetuje kursora automatycznie. "
                    f"Naprawa: skasuj {self.path} = swiadomy pelny resync "
                    f"od zera (utracisz kursor, nie tozsamosc huba)."
                ) from e
            if (not isinstance(state, dict)
                    or state.get("schema") != SCHEMA
                    or not isinstance(state.get("instance_id"), str)
                    or not state["instance_id"]
                    or isinstance(state.get("last_applied_seq"), bool)
                    or not isinstance(state.get("last_applied_seq"), int)
                    or state["last_applied_seq"] < 0
                    or not isinstance(state.get("applied_activations"), list)):
                raise SessionError(
                    f"plik sesji {self.path} ma zly schemat (oczekiwany "
                    f"schema={SCHEMA}). Fail-closed. Naprawa: skasuj "
                    f"{self.path} = swiadomy pelny resync.")
            return state
        instance = None
        if (self._legacy_instance_file is not None
                and self._legacy_instance_file.exists()):
            try:
                legacy = json.loads(self._legacy_instance_file.read_text())
                candidate = legacy.get("instance_id")
                if isinstance(candidate, str) and candidate:
                    instance = candidate
            except (json.JSONDecodeError, OSError):
                instance = None  # legacy zepsute -> swieza tozsamosc
        state = {"schema": SCHEMA,
                 "instance_id": instance or str(uuid.uuid4()),
                 "last_applied_seq": 0,
                 "applied_activations": []}
        _atomic_write_0600(self.path, state)
        return state

    @property
    def instance_id(self):
        return self._state["instance_id"]

    @property
    def last_applied_seq(self):
        return self._state["last_applied_seq"]

    def advance(self, seq):
        """Przesun kursor PO zastosowaniu ramki. Monotoniczny: duplikat
        albo cofniecie = False, bez zapisu. Read-modify-write pod lockiem
        (rownolegly send_once tworzacy/odczytujacy plik nie koliduje)."""
        if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
            raise SessionError(f"invalid seq: {seq!r}")
        with self._state_lock():
            disk = self._reload_locked()
            if seq <= disk["last_applied_seq"]:
                self._state = disk
                return False
            disk["last_applied_seq"] = seq
            _atomic_write_0600(self.path, disk)
            self._state = disk
            return True

    def is_activation_applied(self, activation_id):
        """Sam ODCZYT klucza idempotencji: True = juz zastosowana (suppress).
        NICZEGO nie zapisuje — mark_activation() wolaj DOPIERO PO udanym
        apply (crash miedzy apply a mark = retry ponowi apply, at-least-once;
        odwrotna kolejnosc gubi aktywacje bezpowrotnie)."""
        self._check_activation_id(activation_id)
        with self._state_lock():
            disk = self._reload_locked()
            self._state = disk
            return activation_id in disk["applied_activations"]

    def mark_activation(self, activation_id):
        """Zapisz aktywacje jako zastosowana (PO udanym apply); przycina
        okno do MAX_ACTIVATIONS. Idempotentne."""
        self._check_activation_id(activation_id)
        with self._state_lock():
            disk = self._reload_locked()
            if activation_id not in disk["applied_activations"]:
                disk["applied_activations"].append(activation_id)
                del disk["applied_activations"][:-MAX_ACTIVATIONS]
                _atomic_write_0600(self.path, disk)
            self._state = disk

    @staticmethod
    def _check_activation_id(activation_id):
        if not isinstance(activation_id, str) or not activation_id:
            raise SessionError(f"invalid activation_id: {activation_id!r}")

    def _reload_locked(self):
        # pod lockiem: swiezy odczyt z dysku (inny proces mogl zapisac)
        raw = self.path.read_text()
        return json.loads(raw)


class _StateLock:
    """Krotki flock wokol read/modify/atomic-replace pliku sesji."""

    def __init__(self, lock_path):
        self._path = lock_path
        self._fd = None

    def __enter__(self):
        self._fd = os.open(self._path, os.O_WRONLY | os.O_CREAT, 0o600)
        _lock_exclusive(self._fd, blocking=True)
        return self

    def __exit__(self, *exc):
        _unlock(self._fd)
        os.close(self._fd)
        self._fd = None
        return False
