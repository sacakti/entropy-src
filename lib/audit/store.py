"""
Audit log: who did what, when, from where, and whether it was allowed.

Every change made through the web API (the browser and `ent`) is recorded
by the web layer, as are sign-ins, sign-outs and downloads. Entries are
never changed; housekeeping only removes those older than the retention.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from lib.database.connection import DatabaseConnection

# How long entries are kept unless the settings say otherwise.
DEFAULT_RETENTION_DAYS = 365
OUTCOMES = ("success", "failure", "denied")

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    user_id INTEGER,
    username TEXT,
    address TEXT,
    user_agent TEXT,
    source TEXT NOT NULL DEFAULT 'web',
    category TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT,
    method TEXT,
    path TEXT,
    status INTEGER,
    outcome TEXT NOT NULL CHECK(outcome IN ('success', 'failure', 'denied')),
    project TEXT,
    duration_ms INTEGER,
    details TEXT NOT NULL DEFAULT '{}'
)
"""

# Columns the log may be sorted by; only these reach the SQL.
SORTS = {
    "time": "created_at",
    "user": "LOWER(COALESCE(username, ''))",
    "category": "category",
    "action": "action",
    "outcome": "outcome",
    "project": "LOWER(COALESCE(project, ''))",
}


def ensure_schema(connection: DatabaseConnection) -> None:
    if getattr(connection, "_entropy_audit_ready", False):
        return
    connection.execute(SCHEMA)
    connection.execute("CREATE INDEX IF NOT EXISTS audit_log_time ON audit_log(created_at DESC)")
    connection.execute("CREATE INDEX IF NOT EXISTS audit_log_user ON audit_log(username)")
    connection.execute("CREATE INDEX IF NOT EXISTS audit_log_category ON audit_log(category)")
    # Remembered on the connection: the statements are idempotent anyway.
    setattr(connection, "_entropy_audit_ready", True)  # noqa: B010 - not a declared attribute


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _public(row: Any) -> Dict[str, Any]:
    item = dict(row)
    try:
        item["details"] = json.loads(item.get("details") or "{}")
    except ValueError:
        item["details"] = {}
    return item


class AuditStore:
    """Append-only audit entries with search, export and retention."""

    def __init__(self, connection: DatabaseConnection) -> None:
        ensure_schema(connection)
        self.connection = connection

    def record(
        self,
        *,
        category: str,
        action: str,
        outcome: str = "success",
        username: Optional[str] = None,
        user_id: Optional[int] = None,
        target: Optional[str] = None,
        address: Optional[str] = None,
        user_agent: Optional[str] = None,
        source: str = "web",
        method: Optional[str] = None,
        path: Optional[str] = None,
        status: Optional[int] = None,
        project: Optional[str] = None,
        duration_ms: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> int:
        if outcome not in OUTCOMES:
            outcome = "failure"
        with self.connection.transaction():
            cursor = self.connection.execute(
                "INSERT INTO audit_log(created_at, user_id, username, address, user_agent, source,"
                " category, action, target, method, path, status, outcome, project, duration_ms,"
                " details) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    _now(),
                    user_id,
                    username,
                    (address or "")[:64] or None,
                    (user_agent or "")[:300] or None,
                    source,
                    category,
                    action,
                    (target or "")[:300] or None,
                    method,
                    (path or "")[:500] or None,
                    status,
                    outcome,
                    project,
                    duration_ms,
                    json.dumps(details or {}, default=str)[:20000],
                ),
            )
        return int(cursor.lastrowid)

    def _where(
        self,
        *,
        search: str = "",
        username: str = "",
        category: str = "",
        outcome: str = "",
        project: str = "",
        since: str = "",
        until: str = "",
    ) -> Tuple[str, List[Any]]:
        where: List[str] = []
        parameters: List[Any] = []
        if search.strip():
            pattern = f"%{search.strip().lower()}%"
            where.append(
                "(LOWER(COALESCE(username, '')) LIKE ? OR LOWER(action) LIKE ?"
                " OR LOWER(COALESCE(target, '')) LIKE ? OR LOWER(COALESCE(path, '')) LIKE ?"
                " OR LOWER(COALESCE(address, '')) LIKE ?)"
            )
            parameters.extend([pattern] * 5)
        for column, value in (
            ("username", username),
            ("category", category),
            ("outcome", outcome),
            ("project", project),
        ):
            if value.strip():
                where.append(f"{column} = ?")
                parameters.append(value.strip())
        if since.strip():
            where.append("created_at >= ?")
            parameters.append(since.strip())
        if until.strip():
            where.append("created_at <= ?")
            parameters.append(until.strip())
        return (" WHERE " + " AND ".join(where)) if where else "", parameters

    def search(
        self,
        *,
        limit: int = 25,
        offset: int = 0,
        sort: str = "time",
        order: str = "desc",
        **filters: str,
    ) -> Tuple[List[Dict[str, Any]], int]:
        clause, parameters = self._where(**filters)
        total = self.connection.fetchone(
            "SELECT COUNT(*) AS n FROM audit_log" + clause, tuple(parameters)
        )
        column = SORTS.get(sort, SORTS["time"])
        direction = "ASC" if order == "asc" else "DESC"
        rows = self.connection.fetchall(
            f"SELECT * FROM audit_log{clause} ORDER BY {column} {direction}, id DESC"
            " LIMIT ? OFFSET ?",
            (*parameters, limit, offset),
        )
        return [_public(row) for row in rows], int(total["n"])

    def export(self, *, limit: int = 100000, **filters: str) -> Iterable[Dict[str, Any]]:
        clause, parameters = self._where(**filters)
        rows = self.connection.fetchall(
            f"SELECT * FROM audit_log{clause} ORDER BY created_at DESC, id DESC LIMIT ?",
            (*parameters, limit),
        )
        return [_public(row) for row in rows]

    def facets(self) -> Dict[str, List[str]]:
        """Values to filter by: users, categories and projects that occur in the log."""

        def values(column: str) -> List[str]:
            return [
                row["v"]
                for row in self.connection.fetchall(
                    f"SELECT DISTINCT {column} AS v FROM audit_log"
                    f" WHERE {column} IS NOT NULL AND {column} != '' ORDER BY LOWER({column})"
                )
            ]

        return {
            "users": values("username"),
            "categories": values("category"),
            "projects": values("project"),
        }

    def purge(self, older_than_days: int) -> int:
        """Remove entries older than the retention; returns how many."""

        cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, older_than_days))).isoformat()
        with self.connection.transaction():
            cursor = self.connection.execute(
                "DELETE FROM audit_log WHERE created_at < ?", (cutoff,)
            )
        return int(cursor.rowcount or 0)
