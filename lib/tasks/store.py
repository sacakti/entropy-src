"""Persistent, project-scoped task data."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from typing import Any, Callable, Dict, Iterable, List, Optional, TypeVar, cast

from lib.database.connection import DatabaseConnection
from lib.tasks.recurrence import next_date, next_moment


STATUSES = ("todo", "in_progress", "done", "reopened")
# A closed task never goes back to open; it can only be reopened, with a reason.
CLOSED = "done"
REOPENED = "reopened"
# Offered in every project; imports and project settings may add more.
DEFAULT_TYPES = ("issue", "bug", "task", "story", "improvement", "epic", "incident", "change")
GROUP_KINDS = ("release", "sprint", "epic", "other")
# Most severe first; existing tasks start at the default.
SEVERITIES = ("critical", "high", "medium", "low")
DEFAULT_SEVERITY = "medium"
DEFAULT_PREFIX = "ENTASK"
PREFIX = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")
TYPE_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,29}$")


_Method = TypeVar("_Method", bound=Callable[..., Any])


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class TaskStatusError(ValueError):
    """A status change the task's life cycle does not allow."""


def check_transition(current: str, target: str, reason: Optional[str]) -> None:
    """Closed -> reopened (with a reason) is the only way out of closed."""

    if current == target:
        return
    if current == CLOSED and target != REOPENED:
        raise TaskStatusError("A closed task cannot be moved back; reopen it with a reason.")
    if target == REOPENED and current != CLOSED:
        raise TaskStatusError("Only a closed task can be reopened.")
    if target == REOPENED and not (reason or "").strip():
        raise TaskStatusError("Give a reason to reopen the task.")


def task_key(prefix: str, number: int) -> str:
    """ENTASK-01, ENTASK-02, ... ENTASK-100."""

    return f"{prefix}-{number:02d}"


def normalize_type(value: str) -> str:
    """'Sub-task' -> 'sub-task', 'User Story' -> 'user_story'."""

    return re.sub(r"[^a-z0-9_-]+", "_", value.strip().lower()).strip("_-")[:30] or "issue"


def _columns(connection: DatabaseConnection, table: str) -> set:
    return {row["name"] for row in connection.fetchall(f"PRAGMA table_info({table})")}


def ensure_tasks_schema(connection: DatabaseConnection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS tasks ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,"
        "title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', remarks TEXT NOT NULL DEFAULT '',"
        "status TEXT NOT NULL DEFAULT 'todo', assignee TEXT, creator TEXT NOT NULL,"
        "reminder_at TEXT, reminder_sent INTEGER NOT NULL DEFAULT 0,"
        "created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ")"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS tasks_project_status ON tasks(project_id, status, updated_at)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS task_comments ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,"
        "author TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ")"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS task_followers ("
        "task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,"
        "user_id INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')),"
        "PRIMARY KEY(task_id, user_id)"
        ")"
    )
    ensure_task_extensions(connection)


def ensure_task_extensions(connection: DatabaseConnection) -> None:
    """Types, keys, external references, groups and attachments (idempotent)."""

    columns = _columns(connection, "tasks")
    for name, definition in (
        ("type", "TEXT NOT NULL DEFAULT 'issue'"),
        ("external_ref", "TEXT"),
        ("number", "INTEGER"),
        ("task_key", "TEXT"),
        ("due_date", "TEXT"),
        # The last due-date alert sent, as "<due date>:<stage>"; see due_alerts().
        ("due_alert", "TEXT"),
        # Optional time of the due date ("HH:MM", as entered): due_date stays a plain date.
        ("due_time", "TEXT"),
        # How the task and its reminder repeat; see lib.tasks.recurrence.
        ("due_repeat", "TEXT"),
        ("reminder_repeat", "TEXT"),
        # The occurrence made when this one closed, so closing it again makes no other.
        ("next_task_id", "INTEGER"),
        ("assigned_by", "TEXT"),
        ("assigned_at", "TEXT"),
        ("severity", f"TEXT NOT NULL DEFAULT '{DEFAULT_SEVERITY}'"),
    ):
        if name not in columns:
            connection.execute(f"ALTER TABLE tasks ADD COLUMN {name} {definition}")
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS tasks_project_key ON tasks(project_id, task_key)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS tasks_project_external ON tasks(project_id, external_ref)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS task_settings ("
        "project_id INTEGER PRIMARY KEY, prefix TEXT NOT NULL DEFAULT 'ENTASK',"
        "next_number INTEGER NOT NULL DEFAULT 1, types TEXT NOT NULL DEFAULT '[]'"
        ")"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS task_groups ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, name TEXT NOT NULL,"
        "kind TEXT NOT NULL DEFAULT 'release', description TEXT NOT NULL DEFAULT '', external_ref TEXT,"
        "created_by TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')),"
        "UNIQUE(project_id, name)"
        ")"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS task_group_members ("
        "group_id INTEGER NOT NULL REFERENCES task_groups(id) ON DELETE CASCADE,"
        "task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,"
        "PRIMARY KEY(group_id, task_id)"
        ")"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS task_attachments ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,"
        "filename TEXT NOT NULL, content_type TEXT, size_bytes INTEGER NOT NULL DEFAULT 0,"
        # A stored file, or (imported from Jira) only a link to the original.
        "storage_name TEXT, url TEXT, uploaded_by TEXT NOT NULL,"
        "created_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ")"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS task_status_history ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,"
        "from_status TEXT, to_status TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', changed_by TEXT NOT NULL,"
        "changed_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ")"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS task_status_history_task ON task_status_history(task_id, id)"
    )
    _backfill_keys(connection)


def _backfill_keys(connection: DatabaseConnection) -> None:
    """Give tasks created before keys existed their ENTASK-n, in creation order."""

    missing = connection.fetchall(
        "SELECT id, project_id FROM tasks WHERE task_key IS NULL ORDER BY project_id, id"
    )
    if not missing:
        return
    with connection.transaction():
        for row in missing:
            prefix, number = _reserve(connection, row["project_id"])
            connection.execute(
                "UPDATE tasks SET number = ?, task_key = ? WHERE id = ?",
                (number, task_key(prefix, number), row["id"]),
            )


def _settings_row(connection: DatabaseConnection, project_id: int) -> Any:
    connection.execute(
        "INSERT OR IGNORE INTO task_settings(project_id, prefix, next_number) VALUES (?, ?, 1)",
        (project_id, DEFAULT_PREFIX),
    )
    return connection.fetchone("SELECT * FROM task_settings WHERE project_id = ?", (project_id,))


def _reserve(connection: DatabaseConnection, project_id: int) -> tuple:
    """The next key of a project (call inside a transaction)."""

    row = _settings_row(connection, project_id)
    prefix, number = row["prefix"], int(row["next_number"])
    # Never reuse a key, also after a prefix change back to an older one.
    while connection.fetchone(
        "SELECT 1 FROM tasks WHERE project_id = ? AND task_key = ?", (project_id, task_key(prefix, number))
    ):
        number += 1
    connection.execute(
        "UPDATE task_settings SET next_number = ? WHERE project_id = ?", (number + 1, project_id)
    )
    return prefix, number


def _ensure_versions(connection: DatabaseConnection) -> None:
    if getattr(connection, "_entropy_task_versions_ready", False):
        return
    with connection.transaction():
        connection.execute(
            "CREATE TABLE IF NOT EXISTS task_versions ("
            "project_id INTEGER PRIMARY KEY, version INTEGER NOT NULL DEFAULT 0)"
        )
    connection._entropy_task_versions_ready = True  # type: ignore[attr-defined]


def task_version(connection: DatabaseConnection, project_id: int) -> int:
    """
    A number that grows whenever the project's tasks change, so an open page can ask "anything
    new?" often and reload only when there is. Reads one row: no TaskStore needed.
    """

    _ensure_versions(connection)
    row = connection.fetchone(
        "SELECT version FROM task_versions WHERE project_id = ?", (project_id,)
    )
    return int(row["version"]) if row else 0


# What a changing method's first argument is, and how to find its project from that.
_PROJECT_OF = {
    "task": "SELECT project_id FROM tasks WHERE id = ?",
    "group": "SELECT project_id FROM task_groups WHERE id = ?",
    "attachment": (
        "SELECT t.project_id FROM task_attachments a JOIN tasks t ON t.id = a.task_id"
        " WHERE a.id = ?"
    ),
}


def _touches(kind: str) -> Callable[[_Method], _Method]:
    """
    Mark a method that changes what a project's task page shows. The version moves after the
    write, so whoever sees the new version also sees the change.
    """

    def decorate(method: _Method) -> _Method:
        @wraps(method)
        def wrapper(self: "TaskStore", first: Any, *arguments: Any, **options: Any) -> Any:
            # Looked up first: a delete removes what the project is found through.
            project_id = first if kind == "project" else self._project_of(kind, first)
            result = method(self, first, *arguments, **options)
            if project_id is not None:
                self._touch(int(project_id))
            return result

        return cast(_Method, wrapper)

    return decorate


class TaskStore:
    def __init__(self, connection: DatabaseConnection) -> None:
        self.connection = connection
        ensure_task_extensions(connection)

    # Live updates ------------------------------------------------------

    def _project_of(self, kind: str, identifier: int) -> Optional[int]:
        row = self.connection.fetchone(_PROJECT_OF[kind], (identifier,))
        return row["project_id"] if row else None

    def _touch(self, project_id: int) -> None:
        _ensure_versions(self.connection)
        with self.connection.transaction():
            self.connection.execute(
                "INSERT INTO task_versions (project_id, version) VALUES (?, 1)"
                " ON CONFLICT (project_id) DO UPDATE SET version = version + 1",
                (project_id,),
            )

    # Settings ----------------------------------------------------------

    def settings(self, project_id: int) -> Dict[str, Any]:
        with self.connection.transaction():
            row = _settings_row(self.connection, project_id)
        custom = [name for name in json.loads(row["types"] or "[]") if name not in DEFAULT_TYPES]
        used = [
            item["type"]
            for item in self.connection.fetchall(
                "SELECT DISTINCT type FROM tasks WHERE project_id = ? ORDER BY type", (project_id,)
            )
        ]
        types = list(DEFAULT_TYPES) + [name for name in dict.fromkeys(custom + used) if name not in DEFAULT_TYPES]
        return {
            "prefix": row["prefix"],
            "next_key": task_key(row["prefix"], int(row["next_number"])),
            "types": types,
            "custom_types": custom,
        }

    @_touches("project")
    def update_settings(self, project_id: int, prefix: Optional[str], types: Optional[List[str]]) -> Dict[str, Any]:
        with self.connection.transaction():
            _settings_row(self.connection, project_id)
            if prefix is not None:
                self.connection.execute(
                    "UPDATE task_settings SET prefix = ? WHERE project_id = ?", (prefix, project_id)
                )
            if types is not None:
                self.connection.execute(
                    "UPDATE task_settings SET types = ? WHERE project_id = ?",
                    (json.dumps([name for name in dict.fromkeys(types) if name not in DEFAULT_TYPES]), project_id),
                )
        return self.settings(project_id)

    @_touches("project")
    def add_types(self, project_id: int, names: Iterable[str]) -> None:
        current = self.settings(project_id)
        extra = [name for name in names if name not in current["types"]]
        if extra:
            self.update_settings(project_id, None, current["custom_types"] + extra)

    # Tasks -------------------------------------------------------------

    def list(self, project_id: int) -> List[Dict[str, Any]]:
        return [self._full(row) for row in self.connection.fetchall(
            "SELECT * FROM tasks WHERE project_id = ? ORDER BY updated_at DESC, id DESC", (project_id,)
        )]

    def get(self, task_id: int) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone("SELECT * FROM tasks WHERE id = ?", (task_id,))
        return self._full(row) if row else None

    def find_external(self, project_id: int, external_ref: str) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone(
            "SELECT id FROM tasks WHERE project_id = ? AND external_ref = ? COLLATE NOCASE ORDER BY id LIMIT 1",
            (project_id, external_ref),
        )
        return self.get(row["id"]) if row else None

    @_touches("project")
    def create(self, project_id: int, title: str, description: str, remarks: str,
               assignee: Optional[str], reminder_at: Optional[str], creator: str,
               *, type: str = "issue", external_ref: Optional[str] = None,
               status: str = "todo", group_ids: Iterable[int] = (),
               created_at: Optional[str] = None, due_date: Optional[str] = None,
               severity: str = DEFAULT_SEVERITY, due_time: Optional[str] = None,
               due_repeat: Optional[str] = None,
               reminder_repeat: Optional[str] = None) -> Dict[str, Any]:
        with self.connection.transaction():
            prefix, number = _reserve(self.connection, project_id)
            cursor = self.connection.execute(
                "INSERT INTO tasks (project_id,title,description,remarks,assignee,reminder_at,creator,"
                "type,external_ref,status,number,task_key,due_date,severity,assigned_by,assigned_at,"
                "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
                "CASE WHEN ? IS NULL THEN NULL ELSE COALESCE(?, datetime('now')) END,"
                "COALESCE(?, datetime('now')),COALESCE(?, datetime('now')))",
                (project_id, title, description, remarks, assignee, reminder_at, creator,
                 type, external_ref, status, number, task_key(prefix, number), due_date, severity,
                 creator if assignee else None, assignee, created_at, created_at, created_at),
            )
            task_id = cursor.lastrowid
            if due_time or due_repeat or reminder_repeat:
                self.connection.execute(
                    "UPDATE tasks SET due_time = ?, due_repeat = ?, reminder_repeat = ? WHERE id = ?",
                    (due_time, due_repeat, reminder_repeat, task_id),
                )
            self._set_groups(task_id, group_ids)
            self._record_status(task_id, None, status, creator, "", created_at)
        return self.get(task_id)  # type: ignore[arg-type,return-value]

    @_touches("task")
    def update(self, task_id: int, values: Dict[str, Any], actor: str = "system",
               reason: Optional[str] = None) -> Dict[str, Any]:
        """Change a task; a status change is checked and kept in its history."""

        allowed = {key: value for key, value in values.items() if key in {
            "title", "description", "remarks", "status", "assignee", "reminder_at", "type",
            "external_ref", "due_date", "severity", "due_time", "due_repeat", "reminder_repeat",
        }}
        if "reminder_at" in allowed:
            allowed["reminder_sent"] = 0
        if "assignee" in allowed:
            row = self.connection.fetchone("SELECT assignee FROM tasks WHERE id = ?", (task_id,))
            if row is not None and (row["assignee"] or "") != (allowed["assignee"] or ""):
                # Who handed the task over, and when (cleared when unassigned).
                allowed["assigned_by"] = actor if allowed["assignee"] else None
                allowed["assigned_at"] = _utc_now() if allowed["assignee"] else None
        previous = None
        if "status" in allowed:
            row = self.connection.fetchone("SELECT status FROM tasks WHERE id = ?", (task_id,))
            previous = row["status"] if row else None
            if previous == allowed["status"]:
                allowed.pop("status")
            elif previous is not None:
                check_transition(previous, allowed["status"], reason)
        assignments = ", ".join(f"{key} = ?" for key in allowed)
        with self.connection.transaction():
            if "status" in allowed:
                self._record_status(task_id, previous, allowed["status"], actor, (reason or "").strip())
            if assignments:
                self.connection.execute(
                    f"UPDATE tasks SET {assignments}, updated_at = datetime('now') WHERE id = ?",
                    (*allowed.values(), task_id),
                )
            if "group_ids" in values:
                self._set_groups(task_id, values["group_ids"] or [])
                self.connection.execute("UPDATE tasks SET updated_at = datetime('now') WHERE id = ?", (task_id,))
        return self.get(task_id)  # type: ignore[return-value]

    @_touches("task")
    def delete(self, task_id: int) -> List[Dict[str, Any]]:
        """Remove a task; returns its stored attachments so their files can be deleted."""

        attachments = self.attachments(task_id)
        with self.connection.transaction():
            for table in ("task_comments", "task_followers", "task_group_members", "task_attachments",
                          "task_status_history"):
                self.connection.execute(f"DELETE FROM {table} WHERE task_id = ?", (task_id,))
            self.connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return attachments

    def _record_status(self, task_id: int, previous: Optional[str], status: str, actor: str,
                       reason: str, at: Optional[str] = None) -> None:
        self.connection.execute(
            "INSERT INTO task_status_history(task_id,from_status,to_status,reason,changed_by,changed_at)"
            " VALUES (?,?,?,?,?,COALESCE(?, datetime('now')))",
            (task_id, previous, status, reason, actor, at),
        )

    def status_history(self, task_id: int) -> List[Dict[str, Any]]:
        return [dict(row) for row in self.connection.fetchall(
            "SELECT from_status,to_status,reason,changed_by,changed_at FROM task_status_history"
            " WHERE task_id = ? ORDER BY id", (task_id,)
        )]

    def follower_contacts(self, task_id: int) -> List[Dict[str, Any]]:
        return [dict(row) for row in self.connection.fetchall(
            "SELECT u.id, u.username, u.email FROM task_followers f JOIN users u ON u.id = f.user_id"
            " WHERE f.task_id = ? AND u.is_active = 1", (task_id,)
        )]

    def _set_groups(self, task_id: int, group_ids: Iterable[int]) -> None:
        self.connection.execute("DELETE FROM task_group_members WHERE task_id = ?", (task_id,))
        for group_id in dict.fromkeys(group_ids):
            self.connection.execute(
                "INSERT OR IGNORE INTO task_group_members(group_id, task_id) VALUES (?, ?)", (group_id, task_id)
            )

    @_touches("task")
    def add_comment(self, task_id: int, author: str, body: str, created_at: Optional[str] = None) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "INSERT INTO task_comments(task_id,author,body,created_at) VALUES (?,?,?,COALESCE(?, datetime('now')))",
                (task_id, author, body, created_at),
            )
            self.connection.execute("UPDATE tasks SET updated_at = datetime('now') WHERE id = ?", (task_id,))

    def has_comment(self, task_id: int, author: str, body: str) -> bool:
        return self.connection.fetchone(
            "SELECT 1 FROM task_comments WHERE task_id = ? AND author = ? AND body = ?", (task_id, author, body)
        ) is not None

    @_touches("task")
    def follow(self, task_id: int, user_id: int, enabled: bool) -> None:
        with self.connection.transaction():
            if enabled:
                self.connection.execute("INSERT OR IGNORE INTO task_followers(task_id,user_id) VALUES (?,?)", (task_id,user_id))
            else:
                self.connection.execute("DELETE FROM task_followers WHERE task_id = ? AND user_id = ?", (task_id,user_id))

    # Groups ------------------------------------------------------------

    def groups(self, project_id: int) -> List[Dict[str, Any]]:
        return [dict(row) for row in self.connection.fetchall(
            "SELECT g.*, (SELECT COUNT(*) FROM task_group_members m WHERE m.group_id = g.id) AS task_count"
            " FROM task_groups g WHERE g.project_id = ? ORDER BY g.created_at DESC, g.id DESC",
            (project_id,),
        )]

    def get_group(self, group_id: int) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone("SELECT * FROM task_groups WHERE id = ?", (group_id,))
        return dict(row) if row else None

    def group_by_name(self, project_id: int, name: str) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone(
            "SELECT * FROM task_groups WHERE project_id = ? AND name = ? COLLATE NOCASE", (project_id, name)
        )
        return dict(row) if row else None

    @_touches("project")
    def create_group(self, project_id: int, name: str, kind: str, description: str,
                     external_ref: Optional[str], created_by: str) -> Dict[str, Any]:
        with self.connection.transaction():
            cursor = self.connection.execute(
                "INSERT INTO task_groups(project_id,name,kind,description,external_ref,created_by)"
                " VALUES (?,?,?,?,?,?)",
                (project_id, name, kind, description, external_ref, created_by),
            )
        return self.get_group(cursor.lastrowid)  # type: ignore[arg-type,return-value]

    @_touches("group")
    def update_group(self, group_id: int, values: Dict[str, Any]) -> Dict[str, Any]:
        allowed = {key: value for key, value in values.items() if key in {"name", "kind", "description", "external_ref"}}
        if allowed:
            with self.connection.transaction():
                self.connection.execute(
                    f"UPDATE task_groups SET {', '.join(f'{key} = ?' for key in allowed)} WHERE id = ?",
                    (*allowed.values(), group_id),
                )
        return self.get_group(group_id)  # type: ignore[return-value]

    @_touches("group")
    def delete_group(self, group_id: int) -> None:
        with self.connection.transaction():
            self.connection.execute("DELETE FROM task_group_members WHERE group_id = ?", (group_id,))
            self.connection.execute("DELETE FROM task_groups WHERE id = ?", (group_id,))

    def group_task_ids(self, group_id: int) -> List[int]:
        """Ids of the tasks in a group, oldest first."""

        rows = self.connection.fetchall(
            "SELECT task_id FROM task_group_members WHERE group_id = ? ORDER BY task_id",
            (group_id,),
        )
        return [int(row["task_id"]) for row in rows]

    @_touches("group")
    def add_to_group(self, group_id: int, task_ids: Iterable[int]) -> None:
        with self.connection.transaction():
            for task_id in task_ids:
                self.connection.execute(
                    "INSERT OR IGNORE INTO task_group_members(group_id, task_id) VALUES (?, ?)", (group_id, task_id)
                )

    # Attachments -------------------------------------------------------

    def attachments(self, task_id: int) -> List[Dict[str, Any]]:
        return [dict(row) for row in self.connection.fetchall(
            "SELECT * FROM task_attachments WHERE task_id = ? ORDER BY id", (task_id,)
        )]

    def get_attachment(self, attachment_id: int) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone("SELECT * FROM task_attachments WHERE id = ?", (attachment_id,))
        return dict(row) if row else None

    @_touches("task")
    def add_attachment(self, task_id: int, filename: str, content_type: Optional[str], size: int,
                       uploaded_by: str, storage_name: Optional[str] = None, url: Optional[str] = None,
                       created_at: Optional[str] = None) -> Dict[str, Any]:
        with self.connection.transaction():
            cursor = self.connection.execute(
                "INSERT INTO task_attachments(task_id,filename,content_type,size_bytes,storage_name,url,uploaded_by,created_at)"
                " VALUES (?,?,?,?,?,?,?,COALESCE(?, datetime('now')))",
                (task_id, filename, content_type, size, storage_name, url, uploaded_by, created_at),
            )
            self.connection.execute("UPDATE tasks SET updated_at = datetime('now') WHERE id = ?", (task_id,))
        return self.get_attachment(cursor.lastrowid)  # type: ignore[arg-type,return-value]

    @_touches("attachment")
    def rename_attachment(self, attachment_id: int, filename: str) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE task_attachments SET filename = ? WHERE id = ?", (filename, attachment_id)
            )

    @_touches("attachment")
    def delete_attachment(self, attachment_id: int) -> None:
        with self.connection.transaction():
            self.connection.execute("DELETE FROM task_attachments WHERE id = ?", (attachment_id,))

    # Reminders ---------------------------------------------------------

    def create_next_occurrence(self, task_id: int, today: date, actor: str) -> Optional[Dict[str, Any]]:
        """
        A closed repeating task's next occurrence: the same work, due next time, for the same
        people. None when it does not repeat, or this occurrence already made its next one.
        """

        task = self.get(task_id)
        if not task or not task.get("due_repeat") or not task.get("due_date") or task.get("next_task_id"):
            return None
        due = date.fromisoformat(str(task["due_date"])[:10])
        upcoming = next_date(due, task["due_repeat"], today)
        reminder = None
        if task.get("reminder_at"):
            # The same distance ahead of the due date, including when that is in the past.
            current = datetime.fromisoformat(str(task["reminder_at"]).replace("Z", "+00:00"))
            reminder = (current + (upcoming - due)).isoformat()
        created = self.create(
            task["project_id"], task["title"], task["description"], task["remarks"], task["assignee"],
            reminder, actor, type=task["type"], external_ref=task.get("external_ref"),
            group_ids=task["group_ids"], due_date=upcoming.isoformat(),
            severity=task.get("severity") or DEFAULT_SEVERITY, due_time=task.get("due_time"),
            due_repeat=task["due_repeat"], reminder_repeat=task.get("reminder_repeat"),
        )
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE tasks SET next_task_id = ? WHERE id = ?", (created["id"], task_id)
            )
            for user_id in task.get("follower_ids") or []:
                self.connection.execute(
                    "INSERT OR IGNORE INTO task_followers(task_id,user_id) VALUES (?, ?)",
                    (created["id"], user_id),
                )
        return self.get(created["id"])

    @_touches("task")
    def advance_reminder(self, task_id: int, rule: str, now: datetime) -> None:
        """A repeating reminder has fired: set it for next time."""

        row = self.connection.fetchone("SELECT reminder_at FROM tasks WHERE id = ?", (task_id,))
        if row is None or not row["reminder_at"]:
            return
        current = datetime.fromisoformat(str(row["reminder_at"]).replace("Z", "+00:00"))
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        upcoming = next_moment(current, rule, now)
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE tasks SET reminder_at = ?, reminder_sent = 0 WHERE id = ?",
                (upcoming.isoformat(), task_id),
            )

    def due_reminders(self) -> List[Dict[str, Any]]:
        return [dict(row) for row in self.connection.fetchall(
            "SELECT t.*, u.email AS assignee_email, u.id AS assignee_id FROM tasks t"
            " LEFT JOIN users u ON lower(u.username) = lower(t.assignee)"
            " WHERE t.reminder_at IS NOT NULL AND t.reminder_sent = 0"
            " AND datetime(t.reminder_at) <= datetime('now')"
            " ORDER BY t.reminder_at LIMIT 100"
        )]

    def mark_reminder_sent(self, task_id: int) -> None:
        with self.connection.transaction():
            self.connection.execute("UPDATE tasks SET reminder_sent = 1 WHERE id = ?", (task_id,))

    def due_alerts(self, today: date) -> List[Dict[str, Any]]:
        """
        Open tasks due tomorrow, today or earlier that have not had this stage's alert,
        each with its `due_stage` and `due_alert_key`. A new due date alerts again.
        """

        rows = self.connection.fetchall(
            "SELECT t.*, u.id AS assignee_id FROM tasks t"
            " LEFT JOIN users u ON lower(u.username) = lower(t.assignee)"
            " WHERE t.due_date IS NOT NULL AND t.status <> ? AND date(t.due_date) <= date(?)"
            " ORDER BY t.due_date, t.id",
            (CLOSED, (today + timedelta(days=1)).isoformat()),
        )
        alerts = []
        for row in rows:
            task = dict(row)
            due = date.fromisoformat(str(task["due_date"])[:10])
            stage = "overdue" if due < today else "today" if due == today else "tomorrow"
            key = f"{due.isoformat()}:{stage}"
            if task.get("due_alert") != key:
                alerts.append({**task, "due_stage": stage, "due_alert_key": key})
        return alerts

    def mark_due_alert(self, task_id: int, key: str) -> None:
        with self.connection.transaction():
            self.connection.execute("UPDATE tasks SET due_alert = ? WHERE id = ?", (key, task_id))

    def watcher_ids(self, task: Dict[str, Any]) -> List[int]:
        """Who hears about changes to a task: its active followers and assignee."""

        row = None
        if task.get("assignee"):
            row = self.connection.fetchone(
                "SELECT id FROM users WHERE lower(username) = lower(?) AND is_active = 1",
                (task["assignee"],),
            )
        return self.alert_recipients({**task, "assignee_id": row["id"] if row else None})

    def alert_recipients(self, task: Dict[str, Any]) -> List[int]:
        """Who hears about a reminder or due date: the assignee and the followers."""

        followers = [item["id"] for item in self.follower_contacts(task["id"])]
        assignee = task.get("assignee_id")
        return list(dict.fromkeys(([assignee] if assignee else []) + followers))

    def _full(self, row: Any) -> Dict[str, Any]:
        task = dict(row)
        task["key"] = task.pop("task_key", None)
        task["comments"] = [dict(item) for item in self.connection.fetchall(
            "SELECT id,author,body,created_at FROM task_comments WHERE task_id = ? ORDER BY id", (task["id"],)
        )]
        task["follower_ids"] = [item["user_id"] for item in self.connection.fetchall(
            "SELECT user_id FROM task_followers WHERE task_id = ? ORDER BY user_id", (task["id"],)
        )]
        task["group_ids"] = [item["group_id"] for item in self.connection.fetchall(
            "SELECT group_id FROM task_group_members WHERE task_id = ? ORDER BY group_id", (task["id"],)
        )]
        task["history"] = self.status_history(task["id"])
        task["attachments"] = [
            {key: value for key, value in item.items() if key != "storage_name"}
            for item in self.attachments(task["id"])
        ]
        return task
