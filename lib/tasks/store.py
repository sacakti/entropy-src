"""Persistent, project-scoped task data."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from lib.database.connection import DatabaseConnection


STATUSES = ("todo", "in_progress", "done")


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


class TaskStore:
    def __init__(self, connection: DatabaseConnection) -> None:
        self.connection = connection

    def list(self, project_id: int) -> List[Dict[str, Any]]:
        return [self._full(row) for row in self.connection.fetchall(
            "SELECT * FROM tasks WHERE project_id = ? ORDER BY updated_at DESC, id DESC", (project_id,)
        )]

    def get(self, task_id: int) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone("SELECT * FROM tasks WHERE id = ?", (task_id,))
        return self._full(row) if row else None

    def create(self, project_id: int, title: str, description: str, remarks: str,
               assignee: Optional[str], reminder_at: Optional[str], creator: str) -> Dict[str, Any]:
        with self.connection.transaction():
            cursor = self.connection.execute(
                "INSERT INTO tasks (project_id,title,description,remarks,assignee,reminder_at,creator)"
                " VALUES (?,?,?,?,?,?,?)",
                (project_id, title, description, remarks, assignee, reminder_at, creator),
            )
        return self.get(cursor.lastrowid)  # type: ignore[return-value]

    def update(self, task_id: int, values: Dict[str, Any]) -> Dict[str, Any]:
        allowed = {key: value for key, value in values.items() if key in {
            "title", "description", "remarks", "status", "assignee", "reminder_at"
        }}
        if "reminder_at" in allowed:
            allowed["reminder_sent"] = 0
        assignments = ", ".join(f"{key} = ?" for key in allowed)
        if assignments:
            with self.connection.transaction():
                self.connection.execute(
                    f"UPDATE tasks SET {assignments}, updated_at = datetime('now') WHERE id = ?",
                    (*allowed.values(), task_id),
                )
        return self.get(task_id)  # type: ignore[return-value]

    def add_comment(self, task_id: int, author: str, body: str) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "INSERT INTO task_comments(task_id,author,body) VALUES (?,?,?)", (task_id, author, body)
            )
            self.connection.execute("UPDATE tasks SET updated_at = datetime('now') WHERE id = ?", (task_id,))

    def follow(self, task_id: int, user_id: int, enabled: bool) -> None:
        with self.connection.transaction():
            if enabled:
                self.connection.execute("INSERT OR IGNORE INTO task_followers(task_id,user_id) VALUES (?,?)", (task_id,user_id))
            else:
                self.connection.execute("DELETE FROM task_followers WHERE task_id = ? AND user_id = ?", (task_id,user_id))

    def due_reminders(self) -> List[Dict[str, Any]]:
        return [dict(row) for row in self.connection.fetchall(
            "SELECT t.*, u.email AS assignee_email FROM tasks t"
            " LEFT JOIN users u ON lower(u.username) = lower(t.assignee)"
            " WHERE t.reminder_at IS NOT NULL AND t.reminder_sent = 0"
            " AND datetime(t.reminder_at) <= datetime('now')"
            " ORDER BY t.reminder_at LIMIT 100"
        )]

    def mark_reminder_sent(self, task_id: int) -> None:
        with self.connection.transaction():
            self.connection.execute("UPDATE tasks SET reminder_sent = 1 WHERE id = ?", (task_id,))

    def _full(self, row: Any) -> Dict[str, Any]:
        task = dict(row)
        task["comments"] = [dict(item) for item in self.connection.fetchall(
            "SELECT id,author,body,created_at FROM task_comments WHERE task_id = ? ORDER BY id", (task["id"],)
        )]
        task["follower_ids"] = [item["user_id"] for item in self.connection.fetchall(
            "SELECT user_id FROM task_followers WHERE task_id = ? ORDER BY user_id", (task["id"],)
        )]
        return task
