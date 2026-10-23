"""
Queries over workflow jobs joined with where and why they ran.
"""

from __future__ import annotations

import json
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
    from lib.authorization.projects import add_project_columns

    with connection.transaction():
        create_run_tables(connection)
        add_project_columns(connection)

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
        "options": _json(value("options")),
        "parent_job_id": value("parent_job_id"),
        # None for runs from before projects (they belong to Default).
        "project_id": value("project_id"),
        # Spans several nodes: the main node runs its segments one by one.
        "coordinated": bool(value("heartbeat_at")),
        "archived": bool(value("is_archived")),
    }


def _json(text: Optional[str]) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


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
        options: Optional[Dict[str, Any]] = None,
        rerun_config: Optional[Dict[str, Any]] = None,
        parent_job_id: Optional[int] = None,
        coordinated: bool = False,
    ) -> None:
        with self.connection.transaction():
            self.connection.execute(
                """
                INSERT OR REPLACE INTO run_metadata
                (job_id, node, kind, target, trigger, schedule_id, created_at,
                 options, rerun_config, parent_job_id, heartbeat_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    node,
                    kind,
                    target,
                    trigger,
                    schedule_id,
                    utcnow(),
                    json.dumps(options) if options is not None else None,
                    json.dumps(rerun_config) if rerun_config is not None else None,
                    parent_job_id,
                    utcnow() if coordinated else None,
                ),
            )

    def heartbeat(self, job_id: int) -> None:
        """A coordinated run's main node is still following it."""

        with self.connection.transaction():
            self.connection.execute(
                "UPDATE run_metadata SET heartbeat_at = ? WHERE job_id = ?",
                (utcnow(), job_id),
            )

    def rerun_config(self, job_id: int) -> Optional[Dict[str, Any]]:
        """Return saved execution inputs without exposing them in run listings."""

        archived = self.is_archived(job_id)
        table = "run_metadata_archive" if archived else "run_metadata"
        row = self.connection.fetchone(
            f"SELECT rerun_config FROM {table} WHERE job_id = ?", (job_id,)
        )
        return _json(row["rerun_config"]) if row is not None else None

    def heartbeat_at(self, job_id: int) -> Optional[str]:
        row = self.connection.fetchone(
            "SELECT heartbeat_at FROM run_metadata WHERE job_id = ?", (job_id,)
        )
        return row["heartbeat_at"] if row is not None else None

    def children(self, job_id: int) -> List[Dict[str, Any]]:
        """The segments of a coordinated run, in order."""

        archived = self.is_archived(job_id)
        rows = self.connection.fetchall(
            self._select(archived) + " WHERE m.parent_job_id = ? ORDER BY j.id",
            (job_id,),
        )
        return [run_payload(row) for row in rows]

    def job_ids(self, job_id: int) -> List[int]:
        """The run and its segments: whose events and logs make up the run."""

        return [job_id] + [child["id"] for child in self.children(job_id)]

    def step_outputs(self, job_id: int) -> Dict[str, Dict[str, Any]]:
        """Outputs of each step of a job, from its plugin results."""

        archived = self.is_archived(job_id)
        rows = self.connection.fetchall(
            f"""
            SELECT node_name, payload FROM workflow_events{'_archive' if archived else ''}
            WHERE job_id = ? AND event_type = 'plugin_result' AND node_type = 'step'
            ORDER BY id
            """,
            (job_id,),
        )
        outputs: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            payload = _json(row["payload"]) or {}
            result = payload.get("result") or {}
            outputs[row["node_name"]] = dict(result.get("outputs") or {})
        return outputs

    def events(
        self,
        job_ids: List[int],
        after: Optional[int],
        limit: int,
        archived: bool = False,
    ) -> List[Dict[str, Any]]:
        """Events of several jobs merged in order (ids are global)."""

        marks = ", ".join("?" for _ in job_ids)
        rows = self.connection.fetchall(
            f"""
            SELECT * FROM workflow_events{'_archive' if archived else ''}
            WHERE job_id IN ({marks}) AND id > ?
            ORDER BY id LIMIT ?
            """,  # nosec B608 - placeholders only
            tuple(job_ids) + (after or 0, limit),
        )
        return [
            {
                "id": row["id"],
                "type": row["event_type"],
                "source": row["source"],
                "level": row["level"],
                "message": row["message"],
                "node_type": row["node_type"],
                "node_id": row["node_id"],
                "node_name": row["node_name"],
                "payload": _json(row["payload"]),
                "created_at": iso_utc(row["created_at"]),
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    _SELECT = """
        SELECT j.*, m.node, m.kind, m.target, m.trigger, m.schedule_id,
               m.options, m.parent_job_id, m.heartbeat_at, m.project_id
        FROM workflow_jobs j
        LEFT JOIN run_metadata m ON m.job_id = j.id
    """

    def _select(self, archived: bool = False) -> str:
        if not archived:
            return self._SELECT
        return self._SELECT.replace("workflow_jobs j", "workflow_jobs_archive j").replace(
            "run_metadata m", "run_metadata_archive m"
        ).replace("m.project_id", "m.project_id, 1 AS is_archived")

    def is_archived(self, job_id: int) -> bool:
        return (
            self.connection.fetchone(
                "SELECT 1 FROM workflow_jobs_archive WHERE id = ?", (job_id,)
            )
            is not None
        )

    def get(self, job_id: int) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone(
            self._SELECT + " WHERE j.id = ?",
            (job_id,),
        )
        if row is None:
            row = self.connection.fetchone(self._select(True) + " WHERE j.id = ?", (job_id,))
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
        project_id: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        if tab == "archived":
            return self._list_archived(search, node, user, limit, offset, project_id)
        # Segments of a multi-node run show up as part of that run.
        where: List[str] = ["m.parent_job_id IS NULL"]
        parameters: List[Any] = []

        if project_id is not None:
            where.append(self._PROJECT_CLAUSE)
            parameters.extend([self._default_project(), project_id])

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

    def _list_archived(
        self,
        search: str,
        node: str,
        user: str,
        limit: int,
        offset: int,
        project_id: Optional[int],
    ) -> Tuple[List[Dict[str, Any]], int]:
        where: List[str] = ["m.parent_job_id IS NULL"]
        parameters: List[Any] = []
        if project_id is not None:
            where.append(self._PROJECT_CLAUSE)
            parameters.extend([self._default_project(), project_id])
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
        clause = " WHERE " + " AND ".join(where)
        total = self.connection.fetchone(
            "SELECT COUNT(*) AS n FROM workflow_jobs_archive j"
            " LEFT JOIN run_metadata_archive m ON m.job_id = j.id"
            + clause,
            tuple(parameters),
        )
        rows = self.connection.fetchall(
            self._select(True) + clause + " ORDER BY j.id DESC LIMIT ? OFFSET ?",
            tuple(parameters) + (limit, offset),
        )
        return [run_payload(row) for row in rows], int(total["n"])

    # Runs without a project (from before projects, or the CLI) are Default's.
    _PROJECT_CLAUSE = "IFNULL(m.project_id, ?) = ?"

    def _default_project(self) -> int:
        from lib.authorization.projects import default_project_id

        return default_project_id(self.connection)

    def set_project(self, job_id: int, project_id: Optional[int]) -> None:
        if project_id is None:
            return
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE run_metadata SET project_id = ? WHERE job_id = ?", (project_id, job_id)
            )

    def counts(self, project_id: Optional[int] = None) -> Dict[str, int]:
        clause, parameters = "", ()
        if project_id is not None:
            clause = " AND " + self._PROJECT_CLAUSE
            parameters = (self._default_project(), project_id)
        rows = self.connection.fetchall(
            "SELECT j.state, COUNT(*) AS n FROM workflow_jobs j"
            " LEFT JOIN run_metadata m ON m.job_id = j.id"
            " WHERE m.parent_job_id IS NULL" + clause + " GROUP BY j.state",
            parameters,
        )
        by_state = {row["state"]: int(row["n"]) for row in rows}

        result = {
            tab: sum(by_state.get(state, 0) for state in states) for tab, states in RUN_TABS.items()
        }
        result["all"] = sum(by_state.values())
        archived_clause, archived_parameters = " WHERE m.parent_job_id IS NULL", ()
        if project_id is not None:
            archived_clause += " AND " + self._PROJECT_CLAUSE
            archived_parameters = (self._default_project(), project_id)
        archived = self.connection.fetchone(
            "SELECT COUNT(*) AS n FROM workflow_jobs_archive j"
            " LEFT JOIN run_metadata_archive m ON m.job_id = j.id"
            + archived_clause,
            archived_parameters,
        )
        result["archived"] = int(archived["n"])
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
            # A coordinated run occupies no node itself; its segments do.
            " WHERE COALESCE(m.node, 'local') = ? AND m.heartbeat_at IS NULL AND j.state IN ("
            + ", ".join("?" for _ in ACTIVE_STATES)
            + ")",
            (node,) + ACTIVE_STATES,
        )
        return int(row["n"])

    def steps(self, job_id: int) -> List[Dict[str, Any]]:
        """
        Step progress derived from lifecycle events, in execution order
        (across the segments of a coordinated run).
        """

        job_ids = self.job_ids(job_id)
        marks = ", ".join("?" for _ in job_ids)
        archived = self.is_archived(job_id)
        table = "workflow_events_archive" if archived else "workflow_events"
        rows = self.connection.fetchall(
            f"""
            SELECT id, event_type, node_id, node_name, payload, created_at
            FROM {table}
            WHERE job_id IN ({marks}) AND node_type = 'step'
              AND event_type LIKE 'step.%'
            ORDER BY id
            """,  # nosec B608 - placeholders only
            tuple(job_ids),
        )

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
