"""
Cron schedules for workflows and plugins.

A schedule runs as the user who owns it. Every firing is recorded in
schedule_runs; failed ones stay there so they can be retriggered.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from lib.database.connection import DatabaseConnection

from .cron import CronError, CronExpression
from .store import ensure_run_schema, utcnow

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - Python < 3.9
    ZoneInfo = None  # type: ignore[assignment,misc]
    ZoneInfoNotFoundError = Exception  # type: ignore[assignment,misc]

_SCHEDULE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,79}$")

# schedule_runs.state values.
FINISHED_STATES = ("completed", "failed", "cancelled", "error", "retried")
RETRYABLE_STATES = ("failed", "cancelled", "error")

# Permission a schedule owner needs for each kind.
RUN_PERMISSION = {"workflow": "workflows.start", "plugin": "plugins.run"}


class ScheduleError(ValueError):
    """Invalid schedule input; `status` maps to HTTP."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def resolve_timezone(name: str):
    if not name or name.upper() == "UTC" or ZoneInfo is None:
        return timezone.utc
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError) as exc:
        raise ScheduleError(f"Unknown time zone '{name}'.") from exc


def next_run(cron: str, zone: str, after: datetime) -> Optional[datetime]:
    """Next UTC firing of `cron` read as wall-clock time in `zone`."""

    tz = resolve_timezone(zone)
    expression = CronExpression(cron)
    local = after.astimezone(tz).replace(tzinfo=None)

    for _ in range(3):
        candidate = expression.next_after(local)
        if candidate is None:
            return None
        moment = candidate.replace(tzinfo=tz).astimezone(timezone.utc)
        # Wall times repeated or skipped by a DST change can map backwards.
        if moment > after:
            return moment
        local = candidate

    return None


def _payload(row: Any) -> Dict[str, Any]:
    try:
        parameters = json.loads(row["parameters"] or "{}")
    except ValueError:
        parameters = {}

    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "kind": row["kind"],
        "target": row["target"],
        "cron": row["cron"],
        "timezone": row["timezone"],
        "node": row["node"],
        "parameters": parameters,
        "enabled": bool(row["enabled"]),
        "user_id": row["user_id"],
        "username": row["username"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "next_run_at": row["next_run_at"],
        "last_run_at": row["last_run_at"],
    }


def _run_payload(row: Any) -> Dict[str, Any]:
    keys = row.keys()
    return {
        "id": row["id"],
        "schedule_id": row["schedule_id"],
        "schedule": row["schedule_name"] if "schedule_name" in keys else None,
        "job_id": row["job_id"],
        "trigger": row["trigger"],
        "state": row["state"],
        "error": row["error"],
        "retry_of": row["retry_of"],
        "created_at": row["created_at"],
        "finished_at": row["finished_at"],
    }


class ScheduleStore:
    """Schedule definitions and their run history."""

    def __init__(self, connection: DatabaseConnection) -> None:
        ensure_run_schema(connection)
        self.connection = connection

    # ------------------------------------------------------------------
    # Definitions
    # ------------------------------------------------------------------

    def list(self) -> List[Dict[str, Any]]:
        rows = self.connection.fetchall("SELECT * FROM schedules ORDER BY name COLLATE NOCASE")
        schedules = [_payload(row) for row in rows]

        # Latest run per schedule, for the list's status column.
        latest = self.connection.fetchall("""
            SELECT r.* FROM schedule_runs r
            JOIN (SELECT schedule_id, MAX(id) AS id FROM schedule_runs GROUP BY schedule_id) l
              ON l.id = r.id
            """)
        by_schedule = {row["schedule_id"]: _run_payload(row) for row in latest}
        failures = self.connection.fetchall(
            "SELECT schedule_id, COUNT(*) AS n FROM schedule_runs"
            " WHERE state IN ('failed', 'cancelled', 'error') GROUP BY schedule_id"
        )
        failed_counts = {row["schedule_id"]: int(row["n"]) for row in failures}

        for schedule in schedules:
            schedule["last_run"] = by_schedule.get(schedule["id"])
            schedule["failed_runs"] = failed_counts.get(schedule["id"], 0)

        return schedules

    def get(self, schedule_id: int) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
        return _payload(row) if row is not None else None

    @staticmethod
    def validate(data: Dict[str, Any]) -> Dict[str, Any]:
        name = str(data.get("name") or "").strip()
        if not _SCHEDULE_NAME.match(name):
            raise ScheduleError(
                "Name must start with a letter or digit and use letters, digits, spaces,"
                " '.', '_' or '-' (max 80)."
            )

        kind = data.get("kind")
        if kind not in ("workflow", "plugin"):
            raise ScheduleError("Kind must be workflow or plugin.")

        target = str(data.get("target") or "").strip()
        if not target:
            raise ScheduleError(f"Choose a {kind} to run.")

        cron = " ".join(str(data.get("cron") or "").split())
        try:
            CronExpression(cron)
        except CronError as exc:
            raise ScheduleError(str(exc)) from exc

        zone = str(data.get("timezone") or "UTC").strip()
        resolve_timezone(zone)

        parameters = data.get("parameters") or {}
        if not isinstance(parameters, dict):
            raise ScheduleError("Parameters must be an object.")

        return {
            "name": name,
            "description": str(data.get("description") or "").strip()[:500],
            "kind": kind,
            "target": target,
            "cron": cron,
            "timezone": zone,
            "node": str(data.get("node") or "local").strip(),
            "parameters": parameters,
            "enabled": bool(data.get("enabled", True)),
        }

    def _name_taken(self, name: str, exclude: Optional[int] = None) -> bool:
        row = self.connection.fetchone(
            "SELECT id FROM schedules WHERE name = ? COLLATE NOCASE AND id IS NOT ?",
            (name, exclude),
        )
        return row is not None

    def create(self, data: Dict[str, Any], user_id: int, username: str) -> Dict[str, Any]:
        values = self.validate(data)
        if self._name_taken(values["name"]):
            raise ScheduleError(f"A schedule named '{values['name']}' already exists.", 409)

        now = datetime.now(timezone.utc)
        upcoming = next_run(values["cron"], values["timezone"], now)

        with self.connection.transaction():
            cursor = self.connection.execute(
                """
                INSERT INTO schedules
                (name, description, kind, target, cron, timezone, node, parameters,
                 enabled, user_id, username, created_at, updated_at, next_run_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    values["name"],
                    values["description"],
                    values["kind"],
                    values["target"],
                    values["cron"],
                    values["timezone"],
                    values["node"],
                    json.dumps(values["parameters"]),
                    int(values["enabled"]),
                    user_id,
                    username,
                    now.isoformat(),
                    now.isoformat(),
                    upcoming.isoformat() if upcoming else None,
                ),
            )
            schedule_id = cursor.lastrowid

        return self.get(int(schedule_id)) or {}

    def update(self, schedule_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        current = self.get(schedule_id)
        if current is None:
            raise ScheduleError("Schedule not found.", 404)

        values = self.validate({**current, **data})
        if self._name_taken(values["name"], schedule_id):
            raise ScheduleError(f"A schedule named '{values['name']}' already exists.", 409)

        now = datetime.now(timezone.utc)
        upcoming = next_run(values["cron"], values["timezone"], now)

        with self.connection.transaction():
            self.connection.execute(
                """
                UPDATE schedules
                SET name = ?, description = ?, kind = ?, target = ?, cron = ?,
                    timezone = ?, node = ?, parameters = ?, enabled = ?,
                    updated_at = ?, next_run_at = ?
                WHERE id = ?
                """,
                (
                    values["name"],
                    values["description"],
                    values["kind"],
                    values["target"],
                    values["cron"],
                    values["timezone"],
                    values["node"],
                    json.dumps(values["parameters"]),
                    int(values["enabled"]),
                    now.isoformat(),
                    upcoming.isoformat() if upcoming else None,
                    schedule_id,
                ),
            )

        return self.get(schedule_id) or {}

    def delete(self, schedule_ids: List[int]) -> int:
        if not schedule_ids:
            return 0
        marks = ", ".join("?" for _ in schedule_ids)
        with self.connection.transaction():
            # Foreign keys are not enforced: remove dependents explicitly.
            self.connection.execute(
                f"DELETE FROM schedule_runs WHERE schedule_id IN ({marks})",  # nosec B608
                tuple(schedule_ids),
            )
            cursor = self.connection.execute(
                f"DELETE FROM schedules WHERE id IN ({marks})",  # nosec B608
                tuple(schedule_ids),
            )
        return cursor.rowcount

    def due(self, now: datetime) -> List[Dict[str, Any]]:
        rows = self.connection.fetchall(
            "SELECT * FROM schedules"
            " WHERE enabled = 1 AND next_run_at IS NOT NULL AND next_run_at <= ?",
            (now.isoformat(),),
        )
        return [_payload(row) for row in rows]

    def advance(self, schedule: Dict[str, Any], now: datetime) -> None:
        upcoming = next_run(schedule["cron"], schedule["timezone"], now)
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE schedules SET next_run_at = ?, last_run_at = ? WHERE id = ?",
                (upcoming.isoformat() if upcoming else None, now.isoformat(), schedule["id"]),
            )

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    def add_run(
        self,
        schedule_id: int,
        *,
        trigger: str,
        job_id: Optional[int] = None,
        error: Optional[str] = None,
        retry_of: Optional[int] = None,
    ) -> Dict[str, Any]:
        now = utcnow()
        state = "error" if error else "running"
        with self.connection.transaction():
            cursor = self.connection.execute(
                """
                INSERT INTO schedule_runs
                (schedule_id, job_id, trigger, state, error, retry_of, created_at, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (schedule_id, job_id, trigger, state, error, retry_of, now, now if error else None),
            )
        return self.get_run(int(cursor.lastrowid)) or {}

    def get_run(self, run_id: int) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone(
            "SELECT r.*, s.name AS schedule_name FROM schedule_runs r"
            " LEFT JOIN schedules s ON s.id = r.schedule_id WHERE r.id = ?",
            (run_id,),
        )
        return _run_payload(row) if row is not None else None

    def runs(
        self,
        *,
        schedule_id: Optional[int] = None,
        failed_only: bool = False,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        where = []
        parameters: List[Any] = []
        if schedule_id is not None:
            where.append("r.schedule_id = ?")
            parameters.append(schedule_id)
        if failed_only:
            where.append("r.state IN ('failed', 'cancelled', 'error')")
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        rows = self.connection.fetchall(
            "SELECT r.*, s.name AS schedule_name FROM schedule_runs r"
            " LEFT JOIN schedules s ON s.id = r.schedule_id"
            + clause
            + " ORDER BY r.id DESC LIMIT ?",
            tuple(parameters) + (limit,),
        )
        return [_run_payload(row) for row in rows]

    def sync(self) -> List[Dict[str, Any]]:
        """
        Copy finished job states onto running schedule runs.

        Returns the runs that just finished unsuccessfully.
        """

        rows = self.connection.fetchall("""
            SELECT r.id, j.state, j.finished_at
            FROM schedule_runs r
            JOIN workflow_jobs j ON j.id = r.job_id
            WHERE r.state = 'running'
              AND j.state IN ('completed', 'failed', 'cancelled')
            """)
        failed = []
        for row in rows:
            with self.connection.transaction():
                self.connection.execute(
                    "UPDATE schedule_runs SET state = ?, finished_at = ? WHERE id = ?",
                    (row["state"], row["finished_at"] or utcnow(), row["id"]),
                )
            if row["state"] != "completed":
                run = self.get_run(row["id"])
                if run:
                    failed.append(run)
        return failed

    def mark_retried(self, run_id: int) -> None:
        """Keep a retriggered failure for history, out of the retry list."""

        with self.connection.transaction():
            self.connection.execute(
                "UPDATE schedule_runs SET state = 'retried' WHERE id = ?",
                (run_id,),
            )

    def dismiss(self, run_ids: List[int]) -> int:
        """Forget failed runs (after fixing or deciding not to retry)."""

        if not run_ids:
            return 0
        marks = ", ".join("?" for _ in run_ids)
        with self.connection.transaction():
            cursor = self.connection.execute(
                f"DELETE FROM schedule_runs WHERE id IN ({marks})"  # nosec B608
                " AND state IN ('failed', 'cancelled', 'error')",
                tuple(run_ids),
            )
        return cursor.rowcount


def schedule_owner(connection: DatabaseConnection, user_id: int):
    """The schedule owner as a user-like object, or None when gone/disabled."""

    row = connection.fetchone(
        "SELECT id, username, full_name, is_active FROM users WHERE id = ?",
        (user_id,),
    )
    if row is None or not row["is_active"]:
        return None
    return SimpleNamespace(id=row["id"], username=row["username"], full_name=row["full_name"])
