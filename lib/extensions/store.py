"""
Installed extension versions (one row per library version).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from packaging.utils import canonicalize_name


def ensure_schema(connection: Any) -> None:
    if getattr(connection, "_entropy_extension_versions_ready", False):
        return
    with connection.transaction():
        connection.execute("""
            CREATE TABLE IF NOT EXISTS extension_versions
            (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                canonical     TEXT NOT NULL,
                version       TEXT NOT NULL,
                source        TEXT NOT NULL,
                origin        TEXT,
                summary       TEXT,
                packages      TEXT NOT NULL DEFAULT '[]',
                shared        TEXT NOT NULL DEFAULT '[]',
                size          INTEGER NOT NULL DEFAULT 0,
                installed_by  TEXT,
                installed_at  TEXT NOT NULL,
                UNIQUE (canonical, version)
            )
            """)
    connection._entropy_extension_versions_ready = True


def _row(row: Any) -> Dict[str, Any]:
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "canonical": row["canonical"],
        "version": row["version"],
        "source": row["source"],
        "origin": row["origin"],
        "summary": row["summary"] or "",
        # Everything installed with it (the library and its dependencies).
        "packages": json.loads(row["packages"] or "[]"),
        # Dependencies left out because Entropy has the same version.
        "shared": json.loads(row["shared"] or "[]"),
        "size": int(row["size"] or 0),
        "installed_by": row["installed_by"],
        "installed_at": row["installed_at"],
    }


class ExtensionStore:
    def __init__(self, connection: Any) -> None:
        ensure_schema(connection)
        self.connection = connection

    def list(self) -> List[Dict[str, Any]]:
        rows = self.connection.fetchall(
            "SELECT * FROM extension_versions ORDER BY canonical, installed_at"
        )
        return [_row(row) for row in rows]

    def versions(self, name: str) -> List[Dict[str, Any]]:
        rows = self.connection.fetchall(
            "SELECT * FROM extension_versions WHERE canonical = ?", (canonicalize_name(name),)
        )
        return [_row(row) for row in rows]

    def get(self, name: str, version: str) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone(
            "SELECT * FROM extension_versions WHERE canonical = ? AND version = ?",
            (canonicalize_name(name), version),
        )
        return _row(row) if row else None

    def add(
        self,
        *,
        name: str,
        version: str,
        source: str,
        origin: str,
        summary: str,
        packages: List[str],
        shared: List[str],
        size: int,
        installed_by: str,
    ) -> Dict[str, Any]:
        with self.connection.transaction():
            self.connection.execute(
                "INSERT INTO extension_versions (name, canonical, version, source, origin, summary,"
                " packages, shared, size, installed_by, installed_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    name,
                    canonicalize_name(name),
                    version,
                    source,
                    origin,
                    summary,
                    json.dumps(packages),
                    json.dumps(shared),
                    size,
                    installed_by,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        found = self.get(name, version)
        assert found is not None
        return found

    def remove(self, name: str, version: str) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "DELETE FROM extension_versions WHERE canonical = ? AND version = ?",
                (canonicalize_name(name), version),
            )
