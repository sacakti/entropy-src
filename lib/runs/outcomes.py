"""
Tell people when runs finish.

The background loop calls `RunOutcomes.collect()` every few seconds. It
finds runs that reached a final state since the last call — local, remote,
multi-node (the whole run, not its segments) and scheduled alike — records
them as reported, and returns them for notifications and e-mail.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from lib.database.connection import DatabaseConnection

from .store import ensure_run_schema

FINISHED = ("completed", "failed", "cancelled")


def ensure_outcomes_schema(connection: DatabaseConnection) -> None:
    if getattr(connection, "_entropy_outcomes_ready", False):
        return
    ensure_run_schema(connection)
    with connection.transaction():
        existed = connection.fetchone(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'run_outcomes_reported'"
        )
        connection.execute("""
            CREATE TABLE IF NOT EXISTS run_outcomes_reported
            (
                job_id      INTEGER PRIMARY KEY,
                reported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """)
        if not existed:
            # Runs that finished before this feature existed are not news.
            connection.execute(
                "INSERT OR IGNORE INTO run_outcomes_reported (job_id)"
                " SELECT id FROM workflow_jobs WHERE state IN ('completed', 'failed', 'cancelled')"
            )
    connection._entropy_outcomes_ready = True


def _duration(started: Optional[str], finished: Optional[str]) -> str:
    try:
        seconds = int(
            (
                datetime.fromisoformat(str(finished)) - datetime.fromisoformat(str(started))
            ).total_seconds()
        )
    except (TypeError, ValueError):
        return ""
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def describe(outcome: Dict[str, Any]) -> Dict[str, str]:
    """Title, message and level for a finished run."""

    kind = "Plugin" if outcome["kind"] == "plugin" else "Workflow"
    state = outcome["state"]
    took = _duration(outcome.get("started_at"), outcome.get("finished_at"))
    title = f"{kind} '{outcome['target']}' {state}"
    if outcome.get("schedule_name"):
        title = (
            f"Schedule '{outcome['schedule_name']}': {kind.lower()} '{outcome['target']}' {state}"
        )
    message = f"Run #{outcome['job_id']} {state}"
    if outcome.get("node"):
        message += f" on {outcome['node']}"
    if took:
        message += f" after {took}"
    message += "."
    level = {"completed": "success", "failed": "error"}.get(state, "warning")
    return {"title": title, "message": message, "level": level}


class RunOutcomes:
    def __init__(self, connection: DatabaseConnection) -> None:
        ensure_outcomes_schema(connection)
        self.connection = connection

    def collect(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Finished runs not reported yet; marks them reported."""

        rows = self.connection.fetchall(
            """
            SELECT j.id AS job_id, j.workflow, j.state, j.user_id, j.username,
                   j.started_at, j.finished_at, j.exit_code,
                   m.kind, m.target, m.node, m.trigger, m.schedule_id, m.project_id,
                   s.name AS schedule_name, s.user_id AS schedule_owner
            FROM workflow_jobs j
            LEFT JOIN run_metadata m ON m.job_id = j.id
            LEFT JOIN schedules s ON s.id = m.schedule_id
            LEFT JOIN run_outcomes_reported r ON r.job_id = j.id
            WHERE r.job_id IS NULL
              AND j.state IN ('completed', 'failed', 'cancelled')
              AND m.parent_job_id IS NULL
            ORDER BY j.id
            LIMIT ?
            """,
            (limit,),
        )
        outcomes = []
        with self.connection.transaction():
            for row in rows:
                self.connection.execute(
                    "INSERT OR IGNORE INTO run_outcomes_reported (job_id) VALUES (?)",
                    (row["job_id"],),
                )
                outcomes.append(
                    {
                        "job_id": row["job_id"],
                        "kind": row["kind"] or "workflow",
                        "target": row["target"] or row["workflow"],
                        "state": row["state"],
                        "user_id": row["user_id"],
                        "username": row["username"],
                        "node": row["node"],
                        "trigger": row["trigger"],
                        "schedule_id": row["schedule_id"],
                        "project_id": row["project_id"],
                        "schedule_name": row["schedule_name"],
                        "schedule_owner": row["schedule_owner"],
                        "started_at": row["started_at"],
                        "finished_at": row["finished_at"],
                        "exit_code": row["exit_code"],
                    }
                )
        # Segments of multi-node runs are never reported on their own.
        with self.connection.transaction():
            self.connection.execute(
                "INSERT OR IGNORE INTO run_outcomes_reported (job_id)"
                " SELECT j.id FROM workflow_jobs j JOIN run_metadata m ON m.job_id = j.id"
                " WHERE m.parent_job_id IS NOT NULL"
                " AND j.state IN ('completed', 'failed', 'cancelled')"
            )
        return outcomes

    @staticmethod
    def recipients(outcome: Dict[str, Any]) -> List[int]:
        """Who hears about it: who started the run and the schedule's owner."""

        users = [outcome.get("user_id"), outcome.get("schedule_owner")]
        return [user for user in dict.fromkeys(users) if user is not None]
