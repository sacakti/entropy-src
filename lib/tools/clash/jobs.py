"""
A database comparison running in the background, so it can report how far it has come and
outlive the request and the page that started it.

Jobs live in this server's memory, like a database switch's progress: a restart ends them.
A person has one job per project: their latest, kept for a day so its result and report can
be fetched. The credentials are dropped as soon as a job ends.
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from lib.tools.clash.database import (
    CompareProgress,
    CompareStopped,
    DatabaseCompareError,
    Endpoint,
    Runner,
    _on_both,
    compare,
    estimate_data,
    read_tables,
    run_sqlplus,
)

LOGGER = logging.getLogger("entropy.clash")

ANALYZING = "analyzing"
WAITING = "waiting"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
STOPPED = "stopped"
ACTIVE_STATES = (ANALYZING, WAITING, RUNNING)

KEEP_FINISHED_SECONDS = 24 * 60 * 60
# Credentials stay in memory while a job waits for an answer, so not for long.
KEEP_WAITING_SECONDS = 60 * 60

# (user id, title, message, level, source)
Notify = Callable[[int, str, str, str, str], None]


class CompareBusy(DatabaseCompareError):
    """This person already has a comparison under way in this project."""


def summarize(result: Dict[str, Any]) -> Dict[str, Dict[str, int]]:
    """How many objects and tables ended in each status."""

    return {
        name: dict(Counter(item["status"] for item in result[name]))
        for name in ("ddl", "data")
        if result.get(name) is not None
    }


def _outcome(result: Dict[str, Any]) -> str:
    counts: Counter = Counter()
    for section in summarize(result).values():
        counts.update(section)

    found = counts["different"] + counts["only_left"] + counts["only_right"]
    unchecked = counts["error"] + counts["not_compared"]
    parts = [f"{found:,} difference{'' if found == 1 else 's'}"]
    if unchecked:
        parts.append(f"{unchecked:,} not checked")
    return f"{result['left']} and {result['right']}: {', '.join(parts)}."


class CompareJob(CompareProgress):
    """One comparison. Its answers to `brief` and `snapshot` hold no credentials."""

    def __init__(
        self,
        *,
        user_id: int,
        project_id: int,
        left: Endpoint,
        right: Endpoint,
        sides: Dict[str, Any],
        include_ddl: bool,
        include_data: bool,
        name_filter: Optional[str],
        object_types: Optional[Sequence[str]],
        run: Runner,
        notify: Optional[Notify],
    ) -> None:
        self.id = secrets.token_hex(16)
        self.user_id = user_id
        self.project_id = project_id
        self.sides = sides
        self.name_filter = name_filter
        self.object_types = list(object_types) if object_types else None
        self.include_ddl = include_ddl
        self.include_data = include_data
        self.left_label = left.label
        self.right_label = right.label
        self.result: Optional[Dict[str, Any]] = None

        self._left: Optional[Endpoint] = left
        self._right: Optional[Endpoint] = right
        self._run = run
        self._notify = notify
        self._tables: Optional[Tuple[Dict[str, Any], Dict[str, Any]]] = None
        self._skip: List[str] = []
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stop = threading.Event()

        now = time.monotonic()
        self._started = now
        self._touched = now
        self._ended: Optional[float] = None
        self._state = ANALYZING
        self._phase = "analyze"
        self._current: Optional[str] = None
        self._done = 0
        self._total = 0
        self._rows_done = 0
        self._rows_total = 0
        self._error: Optional[str] = None
        self._estimate: Optional[Dict[str, Any]] = None
        self._summary: Optional[Dict[str, Dict[str, int]]] = None

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------

    def begin(self, phase: str, total: int, rows_total: int = 0) -> None:
        with self._lock:
            self._phase, self._total, self._done = phase, total, 0
            self._rows_total, self._rows_done = rows_total, 0
            self._current = None
            self._touched = time.monotonic()

    def step(self, current: str) -> None:
        if self._stop.is_set():
            raise CompareStopped("The comparison was stopped.")
        with self._lock:
            self._current = current
            self._touched = time.monotonic()

    def advance(self, items: int, rows: int = 0) -> None:
        with self._lock:
            self._done += items
            self._rows_done += rows
            self._touched = time.monotonic()

    # ------------------------------------------------------------------
    # What can be asked
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def active(self) -> bool:
        return self.state in ACTIVE_STATES

    def brief(self) -> Dict[str, Any]:
        """What Vision shows: small, as every open page may read it."""

        with self._lock:
            return {
                "id": self.id,
                "state": self._state,
                "phase": self._phase,
                "left": self.left_label,
                "right": self.right_label,
                "current": self._current,
                "done": self._done,
                "total": self._total,
                "stopping": self._stop.is_set() and self._state in ACTIVE_STATES,
            }

    def snapshot(self) -> Dict[str, Any]:
        """Everything the page shows, except the result."""

        brief = self.brief()
        with self._lock:
            end = self._ended if self._ended is not None else time.monotonic()
            return {
                **brief,
                "rows_done": self._rows_done,
                "rows_total": self._rows_total,
                "elapsed_seconds": int(end - self._started),
                "quiet_seconds": int(end - self._touched),
                "error": self._error,
                # What to skip is the server's to remember, not the page's to send.
                "estimate": (
                    {key: value for key, value in self._estimate.items() if key != "skippable"}
                    if self._estimate
                    else None
                ),
                "summary": self._summary,
                "sides": self.sides,
                "ddl": self.include_ddl,
                "data": self.include_data,
                "name_filter": self.name_filter,
                "object_types": self.object_types,
                "skipped": len(self._skip),
            }

    # ------------------------------------------------------------------
    # Moving it along
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._spawn(self._analyze)

    def confirm(self, skip_large: bool) -> None:
        """The person agreed to compare, with or without the large tables."""

        with self._lock:
            if self._state != WAITING:
                raise DatabaseCompareError("This comparison is not waiting for an answer.")
            self._state = RUNNING
            self._touched = time.monotonic()
            if skip_large and self._estimate:
                self._skip = list(self._estimate["skippable"])
        self._spawn(self._compare)

    def stop(self) -> None:
        """Waiting: ends now. Running: ends when the current batch does."""

        self._stop.set()
        with self._lock:
            waiting = self._state == WAITING
        if waiting:
            self._finish(STOPPED)

    def expire_if_unanswered(self, now: float) -> None:
        with self._lock:
            unanswered = self._state == WAITING and now - self._touched > KEEP_WAITING_SECONDS
        if unanswered:
            self._finish(STOPPED, "Nobody answered, so the comparison did not start.")

    def expired(self, now: float) -> bool:
        with self._lock:
            return self._ended is not None and now - self._ended > KEEP_FINISHED_SECONDS

    def wait(self, timeout: float = 30) -> None:
        """Wait for the current background step; for tests."""

        if self._thread:
            self._thread.join(timeout)

    # ------------------------------------------------------------------
    # Background work
    # ------------------------------------------------------------------

    def _spawn(self, target: Callable[[], None]) -> None:
        def work() -> None:
            try:
                target()
            except CompareStopped:
                self._finish(STOPPED)
            except DatabaseCompareError as exc:
                self._finish(FAILED, str(exc))
            except Exception:  # the thread is the last place this can be reported from
                LOGGER.exception("Database comparison %s failed.", self.id)
                self._finish(FAILED, "The comparison failed unexpectedly: see the server log.")

        self._thread = threading.Thread(target=work, name=f"clash-{self.id[:8]}", daemon=True)
        self._thread.start()

    def _analyze(self) -> None:
        assert self._left and self._right  # nosec B101 - only dropped when the job ends
        if self.include_data:
            self._tables = _on_both(
                self._left,
                self._right,
                lambda side: read_tables(side, self.name_filter, self._run),
            )
            if self._stop.is_set():
                raise CompareStopped("The comparison was stopped.")
            estimate = estimate_data(*self._tables)
            with self._lock:
                self._estimate = estimate
                self._touched = time.monotonic()
                if estimate["needs_consent"]:
                    self._state = WAITING
                    return
                self._state = RUNNING
        else:
            with self._lock:
                self._state = RUNNING
        self._compare()

    def _compare(self) -> None:
        assert self._left and self._right  # nosec B101 - only dropped when the job ends
        result = compare(
            self._left,
            self._right,
            include_ddl=self.include_ddl,
            include_data=self.include_data,
            name_filter=self.name_filter,
            object_types=self.object_types,
            run=self._run,
            tables=self._tables,
            skip_tables=self._skip,
            progress=self,
        )
        self.result = result
        with self._lock:
            self._summary = summarize(result)
        self._finish(DONE)

    def _finish(self, state: str, error: Optional[str] = None) -> None:
        with self._lock:
            if self._state not in ACTIVE_STATES:
                return
            self._state, self._error = state, error
            self._current = None
            self._ended = time.monotonic()
            self._left = self._right = None
            self._tables = None

        if not self._notify:
            return

        source = f"clash:{self.id}"
        if state == DONE and self.result:
            self._notify(
                self.user_id,
                "Database compare finished",
                _outcome(self.result),
                "success",
                source,
            )
        elif state == FAILED:
            self._notify(self.user_id, "Database compare failed", error or "", "error", source)


class CompareJobs:
    """The jobs of this server."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[Tuple[int, int], CompareJob] = {}

    def start(
        self,
        *,
        user_id: int,
        project_id: int,
        left: Endpoint,
        right: Endpoint,
        sides: Dict[str, Any],
        include_ddl: bool = True,
        include_data: bool = True,
        name_filter: Optional[str] = None,
        object_types: Optional[Sequence[str]] = None,
        run: Runner = run_sqlplus,
        notify: Optional[Notify] = None,
    ) -> CompareJob:
        """Start a comparison in place of this person's finished one in this project."""

        job = CompareJob(
            user_id=user_id,
            project_id=project_id,
            left=left,
            right=right,
            sides=sides,
            include_ddl=include_ddl,
            include_data=include_data,
            name_filter=name_filter,
            object_types=object_types,
            run=run,
            notify=notify,
        )

        with self._lock:
            self._prune()
            current = self._jobs.get((user_id, project_id))
            if current and current.active:
                raise CompareBusy("You already have a comparison under way in this project.")
            self._jobs[(user_id, project_id)] = job

        job.start()
        return job

    def current(self, user_id: int, project_id: int) -> Optional[CompareJob]:
        """This person's latest comparison in this project."""

        with self._lock:
            self._prune()
            return self._jobs.get((user_id, project_id))

    def _prune(self) -> None:
        now = time.monotonic()
        for key, job in list(self._jobs.items()):
            job.expire_if_unanswered(now)
            if job.expired(now):
                del self._jobs[key]


JOBS = CompareJobs()
