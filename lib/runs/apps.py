"""
Live pages of app plugins (interactive runs).

A plugin whose plugin.json declares an "app" runs a loop: it reads the
inputs the user sets on the run screen, publishes its views (tables,
stats, logs, ...) and handles button presses, until the user stops it.

The worker and the web server share this store, as they share prompts:
the run screen writes inputs and button events, the plugin writes views.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from lib.database.connection import DatabaseConnection

# Views are rewritten on every loop; keep one page's data bounded.
MAX_VIEWS_BYTES = 2 * 1024 * 1024

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS run_apps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL,
        step TEXT NOT NULL,
        plugin TEXT NOT NULL,
        definition TEXT NOT NULL,
        inputs TEXT NOT NULL DEFAULT '{}',
        views TEXT NOT NULL DEFAULT '{}',
        state TEXT NOT NULL DEFAULT 'running'
            CHECK(state IN ('running', 'stopping', 'finished')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(job_id, step)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_app_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        app_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        payload TEXT NOT NULL DEFAULT '{}',
        created_by TEXT,
        created_at TEXT NOT NULL,
        consumed INTEGER NOT NULL DEFAULT 0
    )
    """,
)


class AppError(ValueError):
    """An app request that cannot be applied; the message says why."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_schema(connection: DatabaseConnection) -> None:
    for statement in SCHEMA:
        connection.execute(statement)
    connection.execute("CREATE INDEX IF NOT EXISTS run_apps_job ON run_apps(job_id)")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS run_app_events_app ON run_app_events(app_id, consumed)"
    )


def _loads(value: Optional[str]) -> Dict[str, Any]:
    try:
        data = json.loads(value or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _public(row: Any) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "job_id": row["job_id"],
        "step": row["step"],
        "plugin": row["plugin"],
        "definition": _loads(row["definition"]),
        "inputs": _loads(row["inputs"]),
        "views": _loads(row["views"]),
        "state": row["state"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


class AppStore:
    """App sessions of runs: inputs, views, button events and stop requests."""

    def __init__(self, connection: DatabaseConnection) -> None:
        ensure_schema(connection)
        self.connection = connection

    # -- worker side ----------------------------------------------------

    def start(self, job_id: int, step: str, plugin: str, definition: Dict[str, Any]) -> int:
        """Open (or, on a retried step, reopen) the step's app with default inputs."""

        defaults = {
            item["name"]: item["default"]
            for item in definition.get("inputs", [])
            if item.get("type") != "button" and "default" in item
        }
        now = _now()
        with self.connection.transaction():
            self.connection.execute(
                "INSERT INTO run_apps(job_id, step, plugin, definition, inputs, views, state,"
                " created_at, updated_at) VALUES (?, ?, ?, ?, ?, '{}', 'running', ?, ?)"
                " ON CONFLICT(job_id, step) DO UPDATE SET plugin = excluded.plugin,"
                " definition = excluded.definition, views = '{}', state = 'running',"
                " updated_at = excluded.updated_at",
                (job_id, step, plugin, json.dumps(definition), json.dumps(defaults), now, now),
            )
            row = self.connection.fetchone(
                "SELECT id FROM run_apps WHERE job_id = ? AND step = ?", (job_id, step)
            )
        return int(row["id"])

    def inputs(self, app_id: int) -> Dict[str, Any]:
        row = self.connection.fetchone("SELECT inputs FROM run_apps WHERE id = ?", (app_id,))
        return _loads(row["inputs"]) if row else {}

    def state(self, app_id: int) -> str:
        row = self.connection.fetchone("SELECT state FROM run_apps WHERE id = ?", (app_id,))
        return row["state"] if row else "finished"

    def marker(self, app_id: int) -> str:
        """Changes whenever the user changes something (inputs, events, stop)."""

        row = self.connection.fetchone(
            "SELECT a.inputs, a.state,"
            " (SELECT COUNT(*) FROM run_app_events e WHERE e.app_id = a.id AND e.consumed = 0) AS n"
            " FROM run_apps a WHERE a.id = ?",
            (app_id,),
        )
        return f"{row['inputs']}|{row['state']}|{row['n']}" if row else "finished"

    def set_views(self, app_id: int, views: Dict[str, Any]) -> None:
        text = json.dumps(views, default=str)
        if len(text.encode("utf-8")) > MAX_VIEWS_BYTES:
            raise AppError(
                f"The app's views are larger than {MAX_VIEWS_BYTES // (1024 * 1024)} MB; "
                "show fewer rows."
            )
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE run_apps SET views = ?, updated_at = ? WHERE id = ?",
                (text, _now(), app_id),
            )

    def take_events(self, app_id: int, name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Button presses not handled yet (of one button, or all), oldest first."""

        clause = "app_id = ? AND consumed = 0"
        parameters: List[Any] = [app_id]
        if name is not None:
            clause += " AND name = ?"
            parameters.append(name)
        with self.connection.transaction():
            rows = self.connection.fetchall(
                f"SELECT * FROM run_app_events WHERE {clause} ORDER BY id", tuple(parameters)
            )
            if rows:
                marks = ",".join("?" for _ in rows)
                self.connection.execute(
                    f"UPDATE run_app_events SET consumed = 1 WHERE id IN ({marks})",
                    tuple(row["id"] for row in rows),
                )
        return [
            {
                "name": row["name"],
                "payload": _loads(row["payload"]),
                "user": row["created_by"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def finish(self, app_id: int) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE run_apps SET state = 'finished', updated_at = ? WHERE id = ?",
                (_now(), app_id),
            )

    # -- web side -------------------------------------------------------

    def list(self, job_ids: Sequence[int]) -> List[Dict[str, Any]]:
        if not job_ids:
            return []
        marks = ",".join("?" for _ in job_ids)
        rows = self.connection.fetchall(
            f"SELECT * FROM run_apps WHERE job_id IN ({marks}) ORDER BY id", tuple(job_ids)
        )
        return [_public(row) for row in rows]

    def get(self, app_id: int) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone("SELECT * FROM run_apps WHERE id = ?", (app_id,))
        return _public(row) if row else None

    def set_inputs(self, app_id: int, values: Dict[str, Any]) -> Dict[str, Any]:
        """Change some inputs; only the app's declared, non-button inputs are accepted."""

        app = self._running(app_id)
        declared = {
            item["name"]: item
            for item in app["definition"].get("inputs", [])
            if item.get("type") != "button"
        }
        unknown = sorted(set(values) - set(declared))
        if unknown:
            raise AppError(f"Unknown app inputs: {', '.join(unknown)}.")
        for name, value in values.items():
            item = declared[name]
            if (
                item["type"] == "select"
                and value not in (None, "")
                and value not in item.get("choices", [])
            ):
                raise AppError(f"'{value}' is not a choice of {item['label']}.")
            if item["type"] == "toggle" and not isinstance(value, bool):
                raise AppError(f"{item['label']} must be on or off.")
            if (
                item["type"] == "number"
                and value not in (None, "")
                and (isinstance(value, bool) or not isinstance(value, (int, float)))
            ):
                raise AppError(f"{item['label']} must be a number.")
            if (
                item["type"] in ("text", "select", "datetime")
                and value is not None
                and not isinstance(value, str)
            ):
                raise AppError(f"{item['label']} must be text.")
        inputs = {**app["inputs"], **values}
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE run_apps SET inputs = ?, updated_at = ? WHERE id = ?",
                (json.dumps(inputs), _now(), app_id),
            )
        return inputs

    def push_event(self, app_id: int, name: str, payload: Dict[str, Any], user: str) -> None:
        app = self._running(app_id)
        buttons = {
            item["name"]
            for item in app["definition"].get("inputs", [])
            if item.get("type") == "button"
        }
        if name not in buttons:
            raise AppError(f"'{name}' is not a button of this app.")
        with self.connection.transaction():
            self.connection.execute(
                "INSERT INTO run_app_events(app_id, name, payload, created_by, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (app_id, name, json.dumps(payload), user, _now()),
            )

    def request_stop(self, app_id: int) -> None:
        self._running(app_id)
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE run_apps SET state = 'stopping', updated_at = ? WHERE id = ?",
                (_now(), app_id),
            )

    def finish_jobs(self, job_ids: Sequence[int]) -> None:
        """A stopped or ended run leaves no app running."""

        if not job_ids:
            return
        marks = ",".join("?" for _ in job_ids)
        with self.connection.transaction():
            self.connection.execute(
                f"UPDATE run_apps SET state = 'finished', updated_at = ?"
                f" WHERE job_id IN ({marks}) AND state != 'finished'",
                (_now(), *job_ids),
            )

    def _running(self, app_id: int) -> Dict[str, Any]:
        app = self.get(app_id)
        if app is None:
            raise AppError("This app does not exist.")
        if app["state"] != "running":
            raise AppError("The app has stopped.")
        return app
