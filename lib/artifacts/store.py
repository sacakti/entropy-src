"""Persistence for uploaded and server-local project artifacts."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from lib.database.connection import DatabaseConnection


def ensure_artifacts_schema(connection: DatabaseConnection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS artifacts ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,"
        "name TEXT NOT NULL, source TEXT NOT NULL CHECK(source IN ('upload','server_path')),"
        "server_path TEXT, storage_name TEXT, size_bytes INTEGER NOT NULL, sha256 TEXT,"
        "tags TEXT NOT NULL DEFAULT '[]', created_by TEXT NOT NULL,"
        "classification TEXT NOT NULL DEFAULT 'added', origin TEXT, run_id TEXT,"
        "created_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ")"
    )
    columns = {row["name"] for row in connection.fetchall("PRAGMA table_info(artifacts)")}
    if "classification" not in columns:
        connection.execute("ALTER TABLE artifacts ADD COLUMN classification TEXT NOT NULL DEFAULT 'added'")
    if "origin" not in columns:
        connection.execute("ALTER TABLE artifacts ADD COLUMN origin TEXT")
    if "run_id" not in columns:
        connection.execute("ALTER TABLE artifacts ADD COLUMN run_id TEXT")
    connection.execute("CREATE INDEX IF NOT EXISTS artifacts_project_created ON artifacts(project_id, created_at DESC, id DESC)")


class ArtifactStore:
    def __init__(self, connection: DatabaseConnection) -> None:
        self.connection = connection

    def list(self, project_id: int) -> List[Dict[str, Any]]:
        return [dict(row) for row in self.connection.fetchall(
            "SELECT id, project_id, name, source, classification, origin, run_id, server_path, storage_name, size_bytes, sha256, tags, created_by, created_at "
            "FROM artifacts WHERE project_id = ? ORDER BY created_at DESC, id DESC", (project_id,)
        )]

    def get(self, artifact_id: int) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone("SELECT * FROM artifacts WHERE id = ?", (artifact_id,))
        return dict(row) if row else None

    def create(self, project_id: int, name: str, source: str, size_bytes: int, created_by: str,
               *, server_path: Optional[str] = None, storage_name: Optional[str] = None,
               sha256: Optional[str] = None, tags: str = "[]", classification: str = "added",
               origin: Optional[str] = None, run_id: Optional[str] = None) -> Dict[str, Any]:
        with self.connection.transaction():
            cursor = self.connection.execute(
                "INSERT INTO artifacts(project_id,name,source,server_path,storage_name,size_bytes,sha256,tags,created_by,classification,origin,run_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (project_id, name, source, server_path, storage_name, size_bytes, sha256, tags, created_by, classification, origin, run_id),
            )
        return self.get(cursor.lastrowid)  # type: ignore[return-value]

    def set_tags(self, artifact_id: int, tags: str) -> Dict[str, Any]:
        with self.connection.transaction():
            self.connection.execute("UPDATE artifacts SET tags = ? WHERE id = ?", (tags, artifact_id))
        return self.get(artifact_id)  # type: ignore[return-value]

    def delete(self, artifact_id: int) -> None:
        with self.connection.transaction():
            self.connection.execute("DELETE FROM artifacts WHERE id = ?", (artifact_id,))
