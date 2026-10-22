"""
Keeping entropy.db safe.

- One server per database: the web server holds an exclusive lock on
  `entropy.db.lock` while it runs; a second one refuses to start. Workers
  and the command line still use the database (SQLite serialises them).
- A guard: `.entropy.db.guard` is a hard link to the same data. Deleting
  entropy.db then removes only a name; the server puts it back within
  seconds (and any process that finds it missing does so before opening),
  with nothing lost.
- Backups: consistent online copies (SQLite's backup API), each checked
  with `PRAGMA integrity_check` before it is kept, in a folder that can be
  on another disk, rotated by count.
- Recovery: the server checks the database when it starts; a damaged one
  is moved aside and the newest good backup takes its place. A process
  never creates an empty database while a guard or backup exists: that
  would hide everyone's data behind a fresh file.

Settings live next to the database in `database-safety.json` (not in the
database, which they must survive), or in ENTROPY_DB_BACKUP_DIR.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

LOGGER = logging.getLogger("entropy.database")

DEFAULTS = {"backup_dir": "", "interval_hours": 6, "keep": 28}
BACKUP_PREFIX = "entropy-"
WATCH_SECONDS = 5


class DatabaseLockedError(RuntimeError):
    """Another Entropy server already runs with this database."""


class DatabaseSafetyError(RuntimeError):
    """A safety action could not be done; the message says why."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def check_file(path: Path, quick: bool = False) -> str:
    """'ok', or what SQLite reports wrong with a database file."""

    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return str(exc)
    try:
        pragma = "quick_check" if quick else "integrity_check"
        rows = connection.execute(f"PRAGMA {pragma}").fetchall()
        result = "; ".join(str(row[0]) for row in rows[:5])
        if result == "ok":
            # A file of zeros or another format passes the pragma vacuously.
            connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
        return result
    except sqlite3.Error as exc:
        return str(exc)
    finally:
        connection.close()


class DatabaseSafety:
    def __init__(self, database: Path) -> None:
        self.database = Path(database)
        self.directory = self.database.parent
        self.guard = self.directory / f".{self.database.name}.guard"
        self.lock_file = self.directory / f"{self.database.name}.lock"
        self.config_file = self.directory / "database-safety.json"
        self._lock_handle: Any = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._last_backup = 0.0
        self.events: List[Dict[str, str]] = []

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def settings(self) -> Dict[str, Any]:
        values = dict(DEFAULTS)
        try:
            stored = json.loads(self.config_file.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                values.update({k: stored[k] for k in DEFAULTS if k in stored})
        except (OSError, ValueError):
            pass
        environment = os.environ.get("ENTROPY_DB_BACKUP_DIR", "").strip()
        if environment:
            values["backup_dir"] = environment
        return values

    def save_settings(self, changes: Dict[str, Any]) -> Dict[str, Any]:
        values = {**self.settings(), **{k: v for k, v in changes.items() if k in DEFAULTS}}
        try:
            values["interval_hours"] = float(values["interval_hours"])
            values["keep"] = int(values["keep"])
        except (TypeError, ValueError):
            raise DatabaseSafetyError("Interval and number kept must be numbers.") from None
        if not 0.25 <= values["interval_hours"] <= 168:
            raise DatabaseSafetyError("Back up every 15 minutes to every 7 days.")
        if not 1 <= values["keep"] <= 1000:
            raise DatabaseSafetyError("Keep between 1 and 1000 backups.")
        folder = str(values["backup_dir"] or "").strip()
        if folder:
            path = Path(folder).expanduser()
            if not path.is_absolute():
                raise DatabaseSafetyError("The backup folder must be an absolute path.")
            try:
                path.mkdir(parents=True, exist_ok=True)
                probe = path / ".entropy-write-test"
                probe.write_text("ok")
                probe.unlink()
            except OSError as exc:
                raise DatabaseSafetyError(f"Entropy cannot write to {path}: {exc}") from None
        values["backup_dir"] = folder
        temporary = self.config_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(values, indent=2), encoding="utf-8")
        os.replace(temporary, self.config_file)
        return values

    @property
    def backup_dir(self) -> Path:
        folder = str(self.settings()["backup_dir"] or "").strip()
        return Path(folder).expanduser() if folder else self.directory / "backups"

    # ------------------------------------------------------------------
    # Presence (any process, before it opens the database)
    # ------------------------------------------------------------------

    def ensure_present(self) -> Optional[str]:
        """
        Put a missing database back: from the guard (same data), else from
        the newest good backup. Returns what was done, or None.
        """

        if self.database.exists():
            return None
        with self._recovery_lock():
            if self.database.exists():
                return None
            if self.guard.exists():
                os.link(self.guard, self.database)
                return self._note(
                    "restored", "entropy.db was missing; put back from its guard (nothing lost)."
                )
            backup = self.latest_good_backup()
            if backup is not None:
                self._copy_into_place(backup)
                return self._note(
                    "restored",
                    f"entropy.db was missing; restored from backup {backup.name}. "
                    "Changes after that backup are lost.",
                )
        return None

    def refresh_guard(self) -> None:
        """Make the guard a hard link to the current database file."""

        if not self.database.exists():
            return
        try:
            if self.guard.exists():
                if os.path.samefile(self.guard, self.database):
                    return
                self.guard.unlink()
            os.link(self.database, self.guard)
        except OSError as exc:
            # Some file systems have no hard links; backups still protect the data.
            LOGGER.warning("Cannot keep a guard link for %s: %s", self.database, exc)

    # ------------------------------------------------------------------
    # Server lock
    # ------------------------------------------------------------------

    def acquire_server_lock(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        # Held open for the server's lifetime: closing it releases the lock.
        handle = open(self.lock_file, "a+")  # noqa: SIM115
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.seek(0)
            owner = handle.read().strip() or "another process"
            handle.close()
            raise DatabaseLockedError(
                f"Another Entropy server ({owner}) already runs with {self.database}. Stop it "
                "first, or give this one its own Entropy home."
            ) from None
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid {os.getpid()} since {_now().isoformat(timespec='seconds')}")
        handle.flush()
        self._lock_handle = handle

    def release_server_lock(self) -> None:
        if self._lock_handle is not None:
            self._lock_handle.close()
            self._lock_handle = None

    # ------------------------------------------------------------------
    # Backups
    # ------------------------------------------------------------------

    def backups(self) -> List[Dict[str, Any]]:
        folder = self.backup_dir
        if not folder.is_dir():
            return []
        found = []
        for path in sorted(folder.glob(f"{BACKUP_PREFIX}*.db"), reverse=True):
            stat = path.stat()
            found.append(
                {
                    "name": path.name,
                    "size": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                }
            )
        return found

    def latest_good_backup(self) -> Optional[Path]:
        for entry in self.backups():
            path = self.backup_dir / entry["name"]
            if check_file(path, quick=True) == "ok":
                return path
            LOGGER.error("Backup %s is damaged; trying an older one.", path)
        return None

    def backup(self, connection: sqlite3.Connection, reason: str = "scheduled") -> Dict[str, Any]:
        """A checked, consistent copy of the live database."""

        folder = self.backup_dir
        folder.mkdir(parents=True, exist_ok=True)
        stamp = _now().strftime("%Y%m%d-%H%M%S")
        target = folder / f"{BACKUP_PREFIX}{stamp}-{reason}.db"
        partial = target.with_suffix(".partial")
        destination = sqlite3.connect(partial)
        try:
            connection.backup(destination)
        finally:
            destination.close()
        result = check_file(partial)
        if result != "ok":
            partial.unlink(missing_ok=True)
            raise DatabaseSafetyError(f"The backup did not pass its check: {result}")
        os.replace(partial, target)
        self._last_backup = time.time()
        self._rotate()
        return {
            "name": target.name,
            "size": target.stat().st_size,
            "created_at": _now().isoformat(),
        }

    def _rotate(self) -> None:
        keep = int(self.settings()["keep"])
        for entry in self.backups()[keep:]:
            (self.backup_dir / entry["name"]).unlink(missing_ok=True)

    def backup_path(self, name: str) -> Path:
        path = (self.backup_dir / name).resolve()
        if (
            path.parent != self.backup_dir.resolve()
            or not name.startswith(BACKUP_PREFIX)
            or not path.is_file()
        ):
            raise DatabaseSafetyError(f"No backup named {name}.")
        return path

    # ------------------------------------------------------------------
    # Restore (server stopped) and repair
    # ------------------------------------------------------------------

    def restore(self, name: str) -> str:
        """Replace the database with a backup; the current file is kept aside."""

        source = self.backup_path(name)
        result = check_file(source)
        if result != "ok":
            raise DatabaseSafetyError(f"Backup {name} is damaged: {result}")
        with self._recovery_lock():
            kept = self._move_aside("replaced")
            self._copy_into_place(source)
        return f"Restored {name}." + (
            f" The previous database is kept as {kept.name}." if kept else ""
        )

    def _move_aside(self, why: str) -> Optional[Path]:
        if not self.database.exists():
            return None
        stamp = _now().strftime("%Y%m%d-%H%M%S")
        target = self.directory / f"{self.database.name}.{why}-{stamp}"
        os.replace(self.database, target)
        for suffix in ("-journal", "-wal", "-shm"):
            side = self.directory / f"{self.database.name}{suffix}"
            if side.exists():
                os.replace(side, self.directory / f"{target.name}{suffix}")
        if self.guard.exists():
            self.guard.unlink()
        return target

    def _copy_into_place(self, source: Path) -> None:
        partial = self.directory / f".{self.database.name}.restoring"
        shutil.copy2(source, partial)
        os.replace(partial, self.database)
        self.refresh_guard()

    # ------------------------------------------------------------------
    # Server start and watch
    # ------------------------------------------------------------------

    def server_start(self, reopen: Callable[[], None], close: Callable[[], None]) -> Optional[str]:
        """
        Lock, check and (if damaged) restore before the server serves
        anyone. `close` / `reopen` close and open the shared connection.
        """

        self.acquire_server_lock()
        done = self.ensure_present()
        if self.database.exists():
            result = check_file(self.database, quick=True)
            if result != "ok":
                LOGGER.critical("entropy.db is damaged (%s).", result)
                backup = self.latest_good_backup()
                if backup is None:
                    raise DatabaseSafetyError(
                        f"entropy.db is damaged ({result}) and there is no good backup to restore. "
                        "Restore one with 'ent database restore', or recover the file."
                    )
                close()
                with self._recovery_lock():
                    kept = self._move_aside("damaged")
                    self._copy_into_place(backup)
                reopen()
                done = self._note(
                    "restored",
                    f"entropy.db was damaged ({result}); restored from {backup.name}. The damaged "
                    f"file is kept as {kept.name if kept else '-'}.",
                )
        self.refresh_guard()
        return done

    def start_watch(
        self,
        connection: Callable[[], sqlite3.Connection],
        reopen: Callable[[], None],
        notify: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Watch for deletion and run scheduled backups (a server thread)."""

        def loop() -> None:
            while not self._stop.wait(WATCH_SECONDS):
                try:
                    message = self._watch_once(connection, reopen)
                    if message and notify:
                        notify(message)
                except Exception:  # never let the watcher die
                    LOGGER.exception("Database watch failed.")

        newest = self.backups()
        if newest:
            self._last_backup = datetime.fromisoformat(newest[0]["created_at"]).timestamp()
        self._thread = threading.Thread(target=loop, name="entropy-database-safety", daemon=True)
        self._thread.start()

    def stop_watch(self) -> None:
        self._stop.set()
        self.release_server_lock()

    def _watch_once(
        self, connection: Callable[[], sqlite3.Connection], reopen: Callable[[], None]
    ) -> Optional[str]:
        message = None
        if not self.database.exists():
            if self.guard.exists():
                message = self.ensure_present()
            else:
                # Both names are gone; the open connection still has the data.
                with self._recovery_lock():
                    partial = self.directory / f".{self.database.name}.rebuilding"
                    destination = sqlite3.connect(partial)
                    try:
                        connection().backup(destination)
                    finally:
                        destination.close()
                    os.replace(partial, self.database)
                reopen()
                self.refresh_guard()
                message = self._note(
                    "restored",
                    "entropy.db and its guard were deleted; rebuilt from the open database "
                    "(nothing lost).",
                )
        elif not self.guard.exists() or not os.path.samefile(self.guard, self.database):
            self.refresh_guard()
        interval = float(self.settings()["interval_hours"]) * 3600
        if time.time() - self._last_backup >= interval:
            self.backup(connection())
        return message

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @contextmanager
    def _recovery_lock(self) -> Iterator[None]:
        """Serialise recovery between processes."""

        self.directory.mkdir(parents=True, exist_ok=True)
        with open(self.directory / f".{self.database.name}.recovery", "a+") as handle:
            if os.name != "nt":
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield

    def _note(self, kind: str, message: str) -> str:
        LOGGER.warning(message)
        self.events.insert(0, {"kind": kind, "message": message, "at": _now().isoformat()})
        del self.events[20:]
        return message

    def status(self) -> Dict[str, Any]:
        exists = self.database.exists()
        backups = self.backups()
        guarded = exists and self.guard.exists() and os.path.samefile(self.guard, self.database)
        return {
            "database": str(self.database),
            "size": self.database.stat().st_size if exists else 0,
            "guarded": guarded,
            "locked": self._lock_handle is not None,
            "backup_dir": str(self.backup_dir),
            "settings": self.settings(),
            "backups": backups,
            "last_backup": backups[0]["created_at"] if backups else None,
            "events": self.events,
        }
