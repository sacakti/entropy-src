"""
Background duties of the main node: fire schedules, sample node metrics,
fail runs whose worker died and archive old runs.

Only one process per Entropy home runs them (an exclusive file lock), so
several web server workers never fire a schedule twice.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

try:
    import fcntl
except ImportError:  # pragma: no cover - non-Unix
    fcntl = None  # type: ignore[assignment]

from .housekeeping import Housekeeping
from .nodes import LocalMetrics, NodeStore, agent_up
from .outcomes import RunOutcomes, describe
from .schedules import RUN_PERMISSION, ScheduleStore, schedule_owner
from .service import RunError, RunService
from .store import LOCAL_NODE

LOGGER = logging.getLogger("entropy.runs")

TICK_SECONDS = 5
METRICS_SECONDS = 30
RECONCILE_SECONDS = 15
HOUSEKEEPING_SECONDS = 3600


class RunsBackground:
    """A daemon thread performing periodic run duties."""

    def __init__(self, context: Any) -> None:
        self._context = context
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock_file = None
        self._last: Dict[str, float] = {}
        self._metrics: Optional[LocalMetrics] = None
        self.latest_local: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _acquire(self) -> bool:
        if fcntl is None:
            return True
        path = Path(self._context.bootstrap.home) / "runs" / "background.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("w")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self._lock_file = handle
        return True

    def start(self) -> bool:
        if not self._acquire():
            LOGGER.info("Run scheduler is active in another process.")
            return False

        self._thread = threading.Thread(target=self._loop, name="entropy-runs", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        if self._lock_file is not None:
            self._lock_file.close()
            self._lock_file = None

    # ------------------------------------------------------------------
    # Loop
    # ------------------------------------------------------------------

    def _due(self, name: str, every: float) -> bool:
        now = time.monotonic()
        if now - self._last.get(name, -every) >= every:
            self._last[name] = now
            return True
        return False

    def _safely(self, name: str, duty: Callable[[], Any]) -> None:
        try:
            duty()
        except Exception:  # noqa: BLE001 - one failing duty must not stop the rest
            LOGGER.exception("Run duty '%s' failed.", name)

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self._due("reconcile", RECONCILE_SECONDS):
                self._safely("reconcile", self.reconcile)
            self._safely("schedules", self.fire_schedules)
            self._safely("outcomes", self.report_outcomes)
            if self._due("metrics", METRICS_SECONDS):
                self._safely("metrics", self.sample_metrics)
            if self._due("housekeeping", HOUSEKEEPING_SECONDS):
                self._safely("housekeeping", self.housekeeping)
            self._stop.wait(TICK_SECONDS)

    # ------------------------------------------------------------------
    # Duties
    # ------------------------------------------------------------------

    @property
    def _connection(self):
        return self._context.database_manager.connection

    def reconcile(self) -> None:
        from lib.nodes.dispatch import NodeDispatcher

        RunService(self._context).reconcile()
        NodeDispatcher(self._context).reconcile()

    def fire_schedules(self) -> None:
        store = ScheduleStore(self._connection)

        # Finished schedule runs are reported with every other run
        # (report_outcomes); this only records their state.
        store.sync()

        now = datetime.now(timezone.utc)
        for schedule in store.due(now):
            # Advance first: a failing start must not refire every tick.
            store.advance(schedule, now)
            fire(self._context, store, schedule, trigger="schedule")

    def report_outcomes(self) -> None:
        """Notify (and e-mail) the people concerned when runs finish."""

        for outcome in RunOutcomes(self._connection).collect():
            text = describe(outcome)
            message = text["message"]
            if outcome.get("schedule_id") and outcome["state"] != "completed":
                message += " Retrigger it from Schedulers."
            # The web UI opens the run from a notification whose source names it.
            source = f"run:{outcome['job_id']}"
            for user_id in RunOutcomes.recipients(outcome):
                self._notify(user_id, text["title"], message, text["level"], source)

    def sample_metrics(self) -> None:
        nodes = NodeStore(self._connection)
        if self._metrics is None:
            self._metrics = LocalMetrics(Path(self._context.bootstrap.home))

        metrics = self._metrics.collect()
        node = nodes.get(LOCAL_NODE)
        metrics["agent_up"] = bool(node and agent_up(node))
        metrics["running_jobs"] = RunService(self._context).store.running_on(LOCAL_NODE)
        nodes.touch(LOCAL_NODE)
        nodes.add_sample(LOCAL_NODE, metrics)
        self.latest_local = metrics

    def housekeeping(self) -> None:
        service = RunService(self._context)
        result = Housekeeping(self._connection).run(
            plugin_runs=service.plugin_run_directory(),
            worker_logs=service.log_path(0).parent,
        )
        if any(result.values()):
            LOGGER.info("Run housekeeping: %s", result)

    def _notify(
        self, user_id: int, title: str, message: str, level: str, source: str = "schedules"
    ) -> None:
        from lib.database.repositories.notifications import notify_user

        notify_user(self._context, user_id, title, message, level, source)


def fire(
    context: Any,
    store: ScheduleStore,
    schedule: Dict[str, Any],
    *,
    trigger: str,
    user: Any = None,
    retry_of: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Start one run of a schedule and record it.

    Scheduled firings run as the schedule's owner; manual triggers and
    retries run as `user`. Failures to start are recorded, never raised.
    """

    actor = user or schedule_owner(store.connection, schedule["user_id"])
    error = None
    job_id = None

    if actor is None:
        error = f"Owner '{schedule['username']}' no longer exists or is disabled."
    elif context.authorization is None or not context.authorization.has_permission(
        actor.id, RUN_PERMISSION[schedule["kind"]]
    ):
        error = f"'{actor.username}' is not allowed to run this {schedule['kind']}."
    else:
        service = RunService(context)
        start = service.start_workflow if schedule["kind"] == "workflow" else service.start_plugin
        parameters = schedule["parameters"] or {}
        keyword = "variables" if schedule["kind"] == "workflow" else "arguments"
        try:
            run = start(
                actor,
                schedule["target"],
                node=schedule["node"],
                trigger=trigger,
                schedule_id=schedule["id"],
                **{keyword: parameters},
            )
            job_id = run.get("id")
        except RunError as exc:
            error = str(exc)
        except Exception as exc:  # noqa: BLE001 - record any start failure
            error = str(exc) or exc.__class__.__name__

    record = store.add_run(
        schedule["id"],
        trigger=trigger,
        job_id=job_id,
        error=error,
        retry_of=retry_of,
    )

    if error:
        from lib.database.repositories.notifications import notify_user

        notify_user(
            context,
            schedule["user_id"],
            f"Schedule '{schedule['name']}' could not start",
            error,
            "error",
            "schedules",
        )

    return record
