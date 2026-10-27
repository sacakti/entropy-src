"""Persistence for releases, their linked tasks and promotion batches."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from lib.database.connection import DatabaseConnection


RELEASE_STAGES = ("workflow_queue", "workflow_done", "task_queue", "completed")


def ensure_releases_schema(connection: DatabaseConnection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS releases ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,"
        "name TEXT NOT NULL, version TEXT NOT NULL DEFAULT '', environment TEXT NOT NULL DEFAULT '',"
        "description TEXT NOT NULL DEFAULT '', workflow_name TEXT NOT NULL, workflow_job_id INTEGER,"
        "stage TEXT NOT NULL DEFAULT 'workflow_queue', created_by TEXT NOT NULL,"
        "created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ")"
    )
    columns = {row["name"] for row in connection.fetchall("PRAGMA table_info(releases)")}
    if "tags" not in columns:
        connection.execute("ALTER TABLE releases ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'")
    if "archived_at" not in columns:
        connection.execute("ALTER TABLE releases ADD COLUMN archived_at TEXT")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS releases_project_stage ON releases(project_id, stage, updated_at)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS release_tasks ("
        "release_id INTEGER NOT NULL REFERENCES releases(id) ON DELETE CASCADE,"
        "task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,"
        "PRIMARY KEY(release_id, task_id)"
        ")"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS release_promotions ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,"
        "target_environment TEXT NOT NULL, workflow_name TEXT NOT NULL, workflow_job_id INTEGER,"
        "status TEXT NOT NULL DEFAULT 'queued', created_by TEXT NOT NULL,"
        "created_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ")"
    )
    promotion_columns = {row["name"] for row in connection.fetchall("PRAGMA table_info(release_promotions)")}
    if "promotion_number" not in promotion_columns:
        connection.execute("ALTER TABLE release_promotions ADD COLUMN promotion_number TEXT")
    if "archived_at" not in promotion_columns:
        connection.execute("ALTER TABLE release_promotions ADD COLUMN archived_at TEXT")
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS release_promotions_number "
        "ON release_promotions(promotion_number) WHERE promotion_number IS NOT NULL"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS release_promotion_items ("
        "promotion_id INTEGER NOT NULL REFERENCES release_promotions(id) ON DELETE CASCADE,"
        "release_id INTEGER NOT NULL REFERENCES releases(id) ON DELETE CASCADE,"
        "PRIMARY KEY(promotion_id, release_id)"
        ")"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS release_environments ("
        "name TEXT PRIMARY KEY COLLATE NOCASE, created_by TEXT NOT NULL,"
        "created_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ")"
    )
    connection.execute(
        "INSERT OR IGNORE INTO release_environments(name,created_by) "
        "SELECT DISTINCT environment,'system' FROM releases "
        "WHERE trim(environment) <> ''"
    )
    connection.execute(
        "INSERT OR IGNORE INTO release_environments(name,created_by) "
        "SELECT DISTINCT target_environment,'system' FROM release_promotions "
        "WHERE trim(target_environment) <> ''"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS release_artifacts ("
        "release_id INTEGER NOT NULL REFERENCES releases(id) ON DELETE CASCADE,"
        "artifact_id INTEGER NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,"
        "PRIMARY KEY(release_id, artifact_id)"
        ")"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS release_housekeeping ("
        "project_id INTEGER PRIMARY KEY, rules TEXT NOT NULL DEFAULT '[]',"
        "updated_by TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ")"
    )


class ReleaseStore:
    def __init__(self, connection: DatabaseConnection) -> None:
        from lib.tasks.store import ensure_tasks_schema

        self.connection = connection
        # Linked tasks are read with their newer columns (keys, references, assignment).
        ensure_tasks_schema(connection)

    def list(self, project_id: int, include_archived: bool = False) -> List[Dict[str, Any]]:
        archived_filter = "" if include_archived else " AND archived_at IS NULL"
        rows = self.connection.fetchall(
            f"SELECT * FROM releases WHERE project_id = ?{archived_filter} ORDER BY id DESC", (project_id,)
        )
        return [self._full(row) for row in rows]

    def get(self, release_id: int) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone("SELECT * FROM releases WHERE id = ?", (release_id,))
        return self._full(row) if row else None

    def create(self, project_id: int, name: str, version: str, environment: str,
               description: str, workflow_name: str, created_by: str, tags: str = "[]") -> Dict[str, Any]:
        with self.connection.transaction():
            cursor = self.connection.execute(
                "INSERT INTO releases(project_id,name,version,environment,description,workflow_name,created_by,tags)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (project_id, name, version, environment, description, workflow_name, created_by, tags),
            )
        return self.get(cursor.lastrowid)  # type: ignore[return-value]

    def update(self, release_id: int, values: Dict[str, Any]) -> Dict[str, Any]:
        allowed = {key: value for key, value in values.items() if key in {
            "name", "version", "environment", "description", "workflow_name", "stage", "tags"
        }}
        if allowed:
            assignments = ", ".join(f"{key} = ?" for key in allowed)
            with self.connection.transaction():
                self.connection.execute(
                    f"UPDATE releases SET {assignments}, updated_at = datetime('now') WHERE id = ?",
                    (*allowed.values(), release_id),
                )
        return self.get(release_id)  # type: ignore[return-value]

    def set_run(self, release_id: int, job_id: int) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE releases SET workflow_job_id = ?, updated_at = datetime('now') WHERE id = ?",
                (job_id, release_id),
            )

    def link_task(self, release_id: int, task_id: int) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "INSERT OR IGNORE INTO release_tasks(release_id,task_id) VALUES (?,?)", (release_id, task_id)
            )

    def unlink_task(self, release_id: int, task_id: int) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "DELETE FROM release_tasks WHERE release_id = ? AND task_id = ?", (release_id, task_id)
            )

    def create_promotion(self, project_id: int, release_ids: List[int], target_environment: str,
                         workflow_name: str, created_by: str, promotion_number: Optional[str] = None) -> int:
        with self.connection.transaction():
            cursor = self.connection.execute(
                "INSERT INTO release_promotions(project_id,target_environment,workflow_name,created_by,promotion_number)"
                " VALUES(?,?,?,?,?)", (project_id, target_environment, workflow_name, created_by, promotion_number),
            )
            promotion_id = cursor.lastrowid
            if not promotion_number:
                promotion_number = f"PROMO-{int(promotion_id):06d}"
                self.connection.execute(
                    "UPDATE release_promotions SET promotion_number = ? WHERE id = ?",
                    (promotion_number, promotion_id),
                )
            for release_id in release_ids:
                self.connection.execute(
                    "INSERT INTO release_promotion_items(promotion_id,release_id) VALUES(?,?)",
                    (promotion_id, release_id),
                )
        return int(promotion_id)

    def set_promotion_run(self, promotion_id: int, job_id: int) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE release_promotions SET workflow_job_id = ?, status = 'running' WHERE id = ?",
                (job_id, promotion_id),
            )

    def set_promotion_workflow(self, promotion_id: int, workflow_name: str) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE release_promotions SET workflow_name = ? WHERE id = ?",
                (workflow_name, promotion_id),
            )

    def link_artifacts(self, release_id: int, artifact_ids: List[int]) -> None:
        with self.connection.transaction():
            for artifact_id in artifact_ids:
                self.connection.execute(
                    "INSERT OR IGNORE INTO release_artifacts(release_id,artifact_id) VALUES (?,?)",
                    (release_id, artifact_id),
                )

    def promotions(self, project_id: int, include_archived: bool = False) -> List[Dict[str, Any]]:
        archived_filter = "" if include_archived else " AND archived_at IS NULL"
        items = self.connection.fetchall(
            f"SELECT * FROM release_promotions WHERE project_id = ?{archived_filter} ORDER BY id DESC", (project_id,)
        )
        result = []
        for row in items:
            promotion = dict(row)
            promotion["releases"] = [dict(item) for item in self.connection.fetchall(
                "SELECT r.id,r.name,r.version,r.environment,r.stage FROM releases r"
                " JOIN release_promotion_items i ON i.release_id = r.id"
                " WHERE i.promotion_id = ? ORDER BY r.id", (row["id"],)
            )]
            result.append(promotion)
        return result

    def _full(self, row: Any) -> Dict[str, Any]:
        release = dict(row)
        release["tasks"] = [dict(item) for item in self.connection.fetchall(
            "SELECT t.id,t.task_key AS key,t.type,t.title,t.description,t.remarks,t.status,t.assignee,"
            "t.assigned_by,t.assigned_at,t.external_ref,t.due_date,t.created_at,t.updated_at,"
            "(SELECT COUNT(*) FROM task_attachments a WHERE a.task_id = t.id) AS attachment_count,"
            "(SELECT group_concat(g.name, ', ') FROM task_group_members m JOIN task_groups g ON g.id = m.group_id"
            " WHERE m.task_id = t.id) AS group_names FROM tasks t"
            " JOIN release_tasks rt ON rt.task_id = t.id"
            " WHERE rt.release_id = ? ORDER BY t.id", (release["id"],)
        )]
        for task in release["tasks"]:
            task["comments"] = [dict(comment) for comment in self.connection.fetchall(
                "SELECT author,body,created_at FROM task_comments WHERE task_id = ? ORDER BY id", (task["id"],)
            )]
        try:
            import json
            release["tags"] = json.loads(release.get("tags") or "[]")
        except (TypeError, ValueError):
            release["tags"] = []
        release["artifacts"] = [dict(item) for item in self.connection.fetchall(
            "SELECT a.id,a.name,a.source,a.size_bytes,a.tags,a.created_at FROM artifacts a"
            " JOIN release_artifacts ra ON ra.artifact_id = a.id WHERE ra.release_id = ? ORDER BY a.name COLLATE NOCASE",
            (release["id"],),
        )]
        return release
