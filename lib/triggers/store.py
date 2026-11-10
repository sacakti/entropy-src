"""
Trigger definitions and the history of their firings.

A trigger runs a workflow or a plugin, in its project and as its owner, when:

- `webhook`: someone POSTs to /api/hooks/<hook key> with the trigger's secret token;
- `queue`: a message arrives on its destination of the STOMP broker set in
  Administration -> Settings -> Message queue.

The secret token is shown once when it is made; only its SHA-256 is kept.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from lib.database.connection import DatabaseConnection
from lib.database.objects.settings import SettingsTable

SOURCES = ("webhook", "queue")
KINDS = ("workflow", "plugin")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,79}$")
# A STOMP destination such as /queue/deploy.orders or /topic/releases.
_DESTINATION = re.compile(r"^/(queue|topic)/[A-Za-z0-9._:\-/*>]{1,200}$")
TOKEN_BYTES = 32
# What a firing keeps of the payload, for the history.
PAYLOAD_KEPT = 4000
STATUS_KEY = "triggers.listener"


class TriggerError(ValueError):
    """Invalid trigger input; `status` maps to HTTP."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def ensure_trigger_schema(connection: DatabaseConnection) -> None:
    """Create the trigger tables (idempotent)."""

    if getattr(connection, "_entropy_triggers_ready", False):
        return
    # The queue listener keeps its status in the settings table.
    SettingsTable().create(connection)
    with connection.transaction():
        connection.execute(
            "CREATE TABLE IF NOT EXISTS triggers ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,"
            "name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',"
            "source TEXT NOT NULL, kind TEXT NOT NULL, target TEXT NOT NULL,"
            "node TEXT NOT NULL DEFAULT 'local', parameters TEXT NOT NULL DEFAULT '{}',"
            "use_payload INTEGER NOT NULL DEFAULT 1, destination TEXT,"
            "hook_key TEXT NOT NULL, token_hash TEXT, token_hint TEXT,"
            "enabled INTEGER NOT NULL DEFAULT 1, user_id INTEGER NOT NULL, username TEXT NOT NULL,"
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, last_fired_at TEXT,"
            "UNIQUE (project_id, name), UNIQUE (hook_key)"
            ")"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS trigger_runs ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, trigger_id INTEGER NOT NULL,"
            "job_id INTEGER, source TEXT NOT NULL, error TEXT, payload TEXT,"
            "caller TEXT, created_at TEXT NOT NULL"
            ")"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_trigger_runs_trigger"
            " ON trigger_runs (trigger_id, created_at)"
        )
    connection._entropy_triggers_ready = True  # type: ignore[attr-defined]


def _payload(row: Any) -> Dict[str, Any]:
    try:
        parameters = json.loads(row["parameters"] or "{}")
    except ValueError:
        parameters = {}
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "name": row["name"],
        "description": row["description"],
        "source": row["source"],
        "kind": row["kind"],
        "target": row["target"],
        "node": row["node"],
        "parameters": parameters if isinstance(parameters, dict) else {},
        "use_payload": bool(row["use_payload"]),
        "destination": row["destination"],
        "hook_key": row["hook_key"],
        "token_hint": row["token_hint"],
        "has_token": bool(row["token_hash"]),
        "enabled": bool(row["enabled"]),
        "user_id": row["user_id"],
        "username": row["username"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_fired_at": row["last_fired_at"],
    }


def _run_payload(row: Any) -> Dict[str, Any]:
    keys = row.keys()
    return {
        "id": row["id"],
        "trigger_id": row["trigger_id"],
        "job_id": row["job_id"],
        "source": row["source"],
        "error": row["error"],
        "payload": row["payload"],
        "caller": row["caller"],
        "created_at": row["created_at"],
        # The run's own state, while it is kept.
        "state": (row["state"] if "state" in keys else None) or ("error" if row["error"] else None),
    }


class TriggerStore:
    """Trigger definitions and their firings."""

    def __init__(self, connection: DatabaseConnection) -> None:
        ensure_trigger_schema(connection)
        self.connection = connection

    # ------------------------------------------------------------------
    # Definitions
    # ------------------------------------------------------------------

    def list(self, project_id: Optional[int] = None) -> List[Dict[str, Any]]:
        if project_id is None:
            rows = self.connection.fetchall("SELECT * FROM triggers ORDER BY name COLLATE NOCASE")
        else:
            rows = self.connection.fetchall(
                "SELECT * FROM triggers WHERE project_id = ? ORDER BY name COLLATE NOCASE",
                (project_id,),
            )
        triggers = [_payload(row) for row in rows]
        counts = {
            row["trigger_id"]: (int(row["total"]), int(row["failed"] or 0))
            for row in self.connection.fetchall(
                "SELECT trigger_id, COUNT(*) AS total,"
                " SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) AS failed"
                " FROM trigger_runs GROUP BY trigger_id"
            )
        }
        for trigger in triggers:
            total, failed = counts.get(trigger["id"], (0, 0))
            trigger["fired"] = total
            trigger["failed_to_start"] = failed
        return triggers

    def get(self, trigger_id: int) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone("SELECT * FROM triggers WHERE id = ?", (trigger_id,))
        return _payload(row) if row is not None else None

    def by_hook_key(self, hook_key: str) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone(
            "SELECT * FROM triggers WHERE hook_key = ? AND source = 'webhook'", (hook_key,)
        )
        return _payload(row) if row is not None else None

    def check_token(self, trigger_id: int, token: str) -> bool:
        row = self.connection.fetchone(
            "SELECT token_hash FROM triggers WHERE id = ?", (trigger_id,)
        )
        stored = str(row["token_hash"] or "") if row is not None else ""
        return bool(stored and token) and hmac.compare_digest(stored, token_hash(token))

    def enabled_queue_triggers(self) -> List[Dict[str, Any]]:
        rows = self.connection.fetchall(
            "SELECT * FROM triggers WHERE source = 'queue' AND enabled = 1 ORDER BY id"
        )
        return [_payload(row) for row in rows]

    @staticmethod
    def validate(data: Dict[str, Any]) -> Dict[str, Any]:
        name = str(data.get("name") or "").strip()
        if not _NAME.match(name):
            raise TriggerError(
                "Name must start with a letter or digit and use letters, digits, spaces,"
                " '.', '_' or '-' (max 80)."
            )
        source = data.get("source")
        if source not in SOURCES:
            raise TriggerError("Source must be webhook or queue.")
        kind = data.get("kind")
        if kind not in KINDS:
            raise TriggerError("Kind must be workflow or plugin.")
        target = str(data.get("target") or "").strip()
        if not target:
            raise TriggerError(f"Choose a {kind} to run.")
        destination = str(data.get("destination") or "").strip() or None
        if source == "queue":
            if destination is None or not _DESTINATION.match(destination):
                raise TriggerError(
                    "Give the queue destination, e.g. /queue/deploy.orders or /topic/releases."
                )
        else:
            destination = None
        parameters = data.get("parameters") or {}
        if not isinstance(parameters, dict):
            raise TriggerError("Parameters must be an object.")
        return {
            "name": name,
            "description": str(data.get("description") or "").strip()[:500],
            "source": source,
            "kind": kind,
            "target": target,
            "node": str(data.get("node") or "local").strip() or "local",
            "parameters": parameters,
            "use_payload": bool(data.get("use_payload", True)),
            "destination": destination,
            "enabled": bool(data.get("enabled", True)),
        }

    def name_taken(self, name: str, project_id: int, exclude: Optional[int] = None) -> bool:
        row = self.connection.fetchone(
            "SELECT id FROM triggers WHERE name = ? COLLATE NOCASE AND project_id = ?"
            " AND id IS NOT ?",
            (name, project_id, exclude),
        )
        return row is not None

    def create(
        self,
        data: Dict[str, Any],
        user_id: int,
        username: str,
        project_id: int,
    ) -> Dict[str, Any]:
        """The new trigger, and for a webhook its secret token (shown only now)."""

        values = self.validate(data)
        if self.name_taken(values["name"], project_id):
            raise TriggerError(f"A trigger named '{values['name']}' already exists.", 409)
        now = _now()
        token = secrets.token_urlsafe(TOKEN_BYTES) if values["source"] == "webhook" else None
        with self.connection.transaction():
            cursor = self.connection.execute(
                "INSERT INTO triggers (project_id, name, description, source, kind, target, node,"
                " parameters, use_payload, destination, hook_key, token_hash, token_hint, enabled,"
                " user_id, username, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    values["name"],
                    values["description"],
                    values["source"],
                    values["kind"],
                    values["target"],
                    values["node"],
                    json.dumps(values["parameters"]),
                    int(values["use_payload"]),
                    values["destination"],
                    secrets.token_urlsafe(16),
                    token_hash(token) if token else None,
                    token[-4:] if token else None,
                    int(values["enabled"]),
                    user_id,
                    username,
                    now,
                    now,
                ),
            )
            trigger_id = int(cursor.lastrowid or 0)
        trigger = self.get(trigger_id) or {}
        return {"trigger": trigger, "token": token}

    def update(self, trigger_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        current = self.get(trigger_id)
        if current is None:
            raise TriggerError("Trigger not found.", 404)
        values = self.validate({**current, **data})
        if self.name_taken(values["name"], current["project_id"], exclude=trigger_id):
            raise TriggerError(f"A trigger named '{values['name']}' already exists.", 409)
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE triggers SET name = ?, description = ?, source = ?, kind = ?, target = ?,"
                " node = ?, parameters = ?, use_payload = ?, destination = ?, enabled = ?,"
                " updated_at = ? WHERE id = ?",
                (
                    values["name"],
                    values["description"],
                    values["source"],
                    values["kind"],
                    values["target"],
                    values["node"],
                    json.dumps(values["parameters"]),
                    int(values["use_payload"]),
                    values["destination"],
                    int(values["enabled"]),
                    _now(),
                    trigger_id,
                ),
            )
        updated = self.get(trigger_id) or {}
        if updated.get("source") == "webhook" and not updated.get("has_token"):
            # A queue trigger turned into a webhook needs a token: make one.
            return {"trigger": self.get(trigger_id) or {}, "token": self.new_token(trigger_id)}
        return {"trigger": updated, "token": None}

    def new_token(self, trigger_id: int) -> str:
        """A new secret token for a webhook trigger; the old one stops working."""

        token = secrets.token_urlsafe(TOKEN_BYTES)
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE triggers SET token_hash = ?, token_hint = ?, updated_at = ? WHERE id = ?",
                (token_hash(token), token[-4:], _now(), trigger_id),
            )
        return token

    def delete(self, trigger_ids: List[int]) -> int:
        deleted = 0
        with self.connection.transaction():
            for trigger_id in trigger_ids:
                self.connection.execute(
                    "DELETE FROM trigger_runs WHERE trigger_id = ?", (trigger_id,)
                )
                cursor = self.connection.execute("DELETE FROM triggers WHERE id = ?", (trigger_id,))
                deleted += max(int(cursor.rowcount or 0), 0)
        return deleted

    # ------------------------------------------------------------------
    # Firings
    # ------------------------------------------------------------------

    def add_run(
        self,
        trigger_id: int,
        *,
        source: str,
        job_id: Optional[int],
        error: Optional[str],
        payload: Optional[str],
        caller: Optional[str],
    ) -> Dict[str, Any]:
        now = _now()
        with self.connection.transaction():
            cursor = self.connection.execute(
                "INSERT INTO trigger_runs (trigger_id, job_id, source, error, payload, caller,"
                " created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    trigger_id,
                    job_id,
                    source,
                    error,
                    payload[:PAYLOAD_KEPT] if payload else None,
                    caller,
                    now,
                ),
            )
            run_id = int(cursor.lastrowid or 0)
            self.connection.execute(
                "UPDATE triggers SET last_fired_at = ? WHERE id = ?", (now, trigger_id)
            )
        row = self.connection.fetchone("SELECT * FROM trigger_runs WHERE id = ?", (run_id,))
        return _run_payload(row)

    def runs(self, trigger_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        try:
            rows = self.connection.fetchall(
                "SELECT r.*, j.state AS state FROM trigger_runs r"
                " LEFT JOIN workflow_jobs j ON j.id = r.job_id"
                " WHERE r.trigger_id = ? ORDER BY r.id DESC LIMIT ?",
                (trigger_id, limit),
            )
        except Exception:  # noqa: BLE001 - no runs table yet: the firings alone
            rows = self.connection.fetchall(
                "SELECT * FROM trigger_runs WHERE trigger_id = ? ORDER BY id DESC LIMIT ?",
                (trigger_id, limit),
            )
        return [_run_payload(row) for row in rows]

    # ------------------------------------------------------------------
    # Queue listener status (written by the background process)
    # ------------------------------------------------------------------

    def set_listener_status(self, state: str, detail: str) -> None:
        value = json.dumps({"state": state, "detail": detail, "at": _now()})
        with self.connection.transaction():
            self.connection.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                (STATUS_KEY, value, _now()),
            )

    def listener_status(self) -> Dict[str, Any]:
        row = self.connection.fetchone("SELECT value FROM settings WHERE key = ?", (STATUS_KEY,))
        try:
            value = json.loads(row["value"]) if row is not None and row["value"] else None
        except ValueError:
            value = None
        return value if isinstance(value, dict) else {"state": "off", "detail": "", "at": None}
