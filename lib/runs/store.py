"""
Queries over workflow jobs joined with where and why they ran.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from lib.database.connection import DatabaseConnection
from lib.database.objects.runs import create_run_tables

ACTIVE_STATES = ("queued", "starting", "running", "paused")

# Tab name -> job states shown in it.
RUN_TABS = {
    "active": ACTIVE_STATES,
    "completed": ("completed",),
    "failed": ("failed",),
    "cancelled": ("cancelled",),
}

LOCAL_NODE = "local"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def iso_utc(value: Optional[str]) -> Optional[str]:
    """SQLite 'YYYY-MM-DD HH:MM:SS' (UTC) and naive ISO values as ISO with offset."""

    if not value:
        return value
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def ensure_run_schema(connection: DatabaseConnection) -> None:
    """
    Create the run tables and seed new permissions once per connection.

    Servers upgraded without `ent migrate` still get the schema.
    """

    if getattr(connection, "_entropy_runs_ready", False):
        return

    from lib.authorization.initializer import AuthorizationInitializer

    with connection.transaction():
        create_run_tables(connection)

    # Adds the nodes.* and schedules.* permissions and grants them to admin.
    AuthorizationInitializer(connection).reconcile()

    # Remembered on the connection: ids can be reused by new objects.
    connection._entropy_runs_ready = True


def run_payload(row: Any) -> Dict[str, Any]:
    keys = row.keys()

    def value(name: str, default: Any = None) -> Any:
        return row[name] if name in keys else default

    return {
        "id": row["id"],
        "execution_id": row["execution_id"],
        "workflow": row["workflow"],
        "state": row["state"],
        "pid": row["pid"],
        "user_id": row["user_id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "created_at": iso_utc(row["created_at"]),
        "started_at": iso_utc(row["started_at"]),
        "finished_at": iso_utc(row["finished_at"]),
        "exit_code": row["exit_code"],
        "node": value("node") or LOCAL_NODE,
        "kind": value("kind") or "workflow",
        "target": value("target") or row["workflow"],
        "trigger": value("trigger") or "cli",
        "schedule_id": value("schedule_id"),
    }


class RunStore:
    """Run listings and metadata."""

    def __init__(self, connection: DatabaseConnection) -> None:
        ensure_run_schema(connection)
        self.connection = connection

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def record(
        self,
        job_id: int,
        *,
        node: str,
        kind: str,
        target: str,
        trigger: str,
        schedule_id: Optional[int] = None,
    ) -> None:
        with self.connection.transaction():
            self.connection.execute(
                """
                INSERT OR REPLACE INTO run_metadata
                (job_id, node, kind, target, trigger, schedule_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (job_id, node, kind, target, trigger, schedule_id, utcnow()),
            )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    _SELECT = """
        SELECT j.*, m.node, m.kind, m.target, m.trigger, m.schedule_id
        FROM workflow_jobs j
        LEFT JOIN run_metadata m ON m.job_id = j.id
    """

    def get(self, job_id: int) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone(
            self._SELECT + " WHERE j.id = ?",
            (job_id,),
        )
        return run_payload(row) if row is not None else None

    def list(
        self,
        *,
        tab: str = "all",
        search: str = "",
        node: str = "",
        user: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        where: List[str] = []
        parameters: List[Any] = []

        states = RUN_TABS.get(tab)
        if states:
            where.append("j.state IN (" + ", ".join("?" for _ in states) + ")")
            parameters.extend(states)

        if search.strip():
            pattern = "%" + search.strip().lower() + "%"
            where.append(
                "(LOWER(j.workflow) LIKE ? OR LOWER(COALESCE(m.target, '')) LIKE ?"
                " OR CAST(j.id AS TEXT) = ?)"
            )
            parameters.extend([pattern, pattern, search.strip().lstrip("#")])

        if node.strip():
            where.append("COALESCE(m.node, 'local') = ?")
            parameters.append(node.strip())

        if user.strip():
            where.append("j.username = ?")
            parameters.append(user.strip())

        clause = (" WHERE " + " AND ".join(where)) if where else ""

        total_row = self.connection.fetchone(
            "SELECT COUNT(*) AS n FROM workflow_jobs j"
            " LEFT JOIN run_metadata m ON m.job_id = j.id" + clause,
            tuple(parameters),
        )

        rows = self.connection.fetchall(
            self._SELECT + clause + " ORDER BY j.id DESC LIMIT ? OFFSET ?",
            tuple(parameters) + (limit, offset),
        )

        return [run_payload(row) for row in rows], int(total_row["n"])

    def counts(self) -> Dict[str, int]:
        rows = self.connection.fetchall(
            "SELECT state, COUNT(*) AS n FROM workflow_jobs GROUP BY state",
        )
        by_state = {row["state"]: int(row["n"]) for row in rows}

        result = {
            tab: sum(by_state.get(state, 0) for state in states) for tab, states in RUN_TABS.items()
        }
        result["all"] = sum(by_state.values())
        return result

    def active(self) -> List[Dict[str, Any]]:
        rows = self.connection.fetchall(
            self._SELECT
            + " WHERE j.state IN ("
            + ", ".join("?" for _ in ACTIVE_STATES)
            + ") ORDER BY j.id",
            ACTIVE_STATES,
        )
        return [run_payload(row) for row in rows]

    def running_on(self, node: str) -> int:
        row = self.connection.fetchone(
            "SELECT COUNT(*) AS n FROM workflow_jobs j"
            " LEFT JOIN run_metadata m ON m.job_id = j.id"
            " WHERE COALESCE(m.node, 'local') = ? AND j.state IN ("
            + ", ".join("?" for _ in ACTIVE_STATES)
            + ")",
            (node,) + ACTIVE_STATES,
        )
        return int(row["n"])

    def steps(self, job_id: int) -> List[Dict[str, Any]]:
        """
        Step progress derived from lifecycle events, in execution order.
        """

        rows = self.connection.fetchall(
            """
            SELECT id, event_type, node_id, node_name, payload, created_at
            FROM workflow_events
            WHERE job_id = ? AND node_type = 'step'
              AND event_type LIKE 'step.%'
            ORDER BY id
            """,
            (job_id,),
        )

        import json

        steps: Dict[str, Dict[str, Any]] = {}

        for row in rows:
            key = row["node_id"] or row["node_name"]
            status = row["event_type"].split(".", 1)[1]
            step = steps.setdefault(
                key,
                {
                    "id": row["node_id"],
                    "name": row["node_name"],
                    "status": status,
                    "started_at": None,
                    "finished_at": None,
                    "duration_ms": None,
                },
            )
            step["status"] = status

            if status == "started":
                step["started_at"] = iso_utc(row["created_at"])
            else:
                step["finished_at"] = iso_utc(row["created_at"])

            try:
                payload = json.loads(row["payload"]) if row["payload"] else {}
            except ValueError:
                payload = {}

            if payload.get("duration_ms") is not None:
                step["duration_ms"] = payload["duration_ms"]

        return list(steps.values())
