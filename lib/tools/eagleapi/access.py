"""
Who may see a collection.

A collection is a top-level item (usually a folder) and everything below
it. By default every project member sees it, as before. Its owner (the
person who created it) can restrict it: then only the owner, the people
and groups given access, and administrators see it. Access is "read"
(see and send) or "write" (also change). People given access must be
members of the project.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set

LEVELS = ("read", "write")


class EagleAccessError(ValueError):
    """A refused access change; the message is safe to show."""


def ensure_schema(connection: Any) -> None:
    if getattr(connection, "_entropy_eagleapi_access_ready", False):
        return
    with connection.transaction():
        connection.execute("""
            CREATE TABLE IF NOT EXISTS eagleapi_restricted
            (
                item_id     INTEGER PRIMARY KEY,
                project_id  INTEGER NOT NULL,
                updated_by  TEXT,
                updated_at  TEXT NOT NULL
            )
            """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS eagleapi_access
            (
                item_id      INTEGER NOT NULL,
                principal    TEXT NOT NULL CHECK (principal IN ('user', 'group')),
                principal_id INTEGER NOT NULL,
                level        TEXT NOT NULL CHECK (level IN ('read', 'write')),
                PRIMARY KEY (item_id, principal, principal_id)
            )
            """)
    connection._entropy_eagleapi_access_ready = True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Viewer:
    """The person asking: who they are and whether they see every collection."""

    def __init__(self, user_id: int, username: str, groups: Iterable[int], admin: bool) -> None:
        self.user_id = user_id
        self.username = username
        self.groups: Set[int] = set(groups)
        self.admin = admin


class EagleAccess:
    def __init__(self, connection: Any) -> None:
        ensure_schema(connection)
        self.connection = connection

    # -- reading ---------------------------------------------------------

    def restricted(self, project_id: int) -> Set[int]:
        rows = self.connection.fetchall(
            "SELECT item_id FROM eagleapi_restricted WHERE project_id = ?", (project_id,)
        )
        return {int(row["item_id"]) for row in rows}

    def entries(self, item_id: int) -> List[Dict[str, Any]]:
        rows = self.connection.fetchall(
            """
            SELECT a.principal, a.principal_id, a.level,
                   u.username, u.full_name, g.name AS group_name
            FROM eagleapi_access a
            LEFT JOIN users u ON a.principal = 'user' AND u.id = a.principal_id
            LEFT JOIN groups g ON a.principal = 'group' AND g.id = a.principal_id
            WHERE a.item_id = ?
            ORDER BY a.principal DESC, COALESCE(u.username, g.name)
            """,
            (item_id,),
        )
        return [
            {
                "kind": row["principal"],
                "name": row["username"] if row["principal"] == "user" else row["group_name"],
                "full_name": row["full_name"] if row["principal"] == "user" else None,
                "level": row["level"],
            }
            for row in rows
            if (row["username"] if row["principal"] == "user" else row["group_name"])
        ]

    def level(self, viewer: Viewer, root: Dict[str, Any], restricted: Set[int]) -> Optional[str]:
        """
        The viewer's access to a collection: "manage" (owner, administrator),
        "write", "read", or None (hidden). Open collections are "write"; the
        project role still decides what someone may do there.
        """

        if root["id"] not in restricted:
            return "write"
        if viewer.admin or (root.get("created_by") and root["created_by"] == viewer.username):
            return "manage"
        rows = self.connection.fetchall(
            "SELECT principal, principal_id, level FROM eagleapi_access WHERE item_id = ?",
            (root["id"],),
        )
        best: Optional[str] = None
        for row in rows:
            mine = (row["principal"] == "user" and int(row["principal_id"]) == viewer.user_id) or (
                row["principal"] == "group" and int(row["principal_id"]) in viewer.groups
            )
            if mine and (best is None or row["level"] == "write"):
                best = row["level"]
        return best

    # -- changes ---------------------------------------------------------

    def set(
        self,
        project_id: int,
        item_id: int,
        *,
        restricted: bool,
        entries: List[Dict[str, Any]],
        allowed_users: Set[str],
        allowed_groups: Set[str],
        updated_by: str,
    ) -> None:
        """
        Replace a collection's access. `allowed_*` are the project's members
        (people through their groups too): nobody else can be given access.
        """

        resolved = []
        for entry in entries:
            kind = entry.get("kind")
            name = str(entry.get("name") or "").strip()
            level = entry.get("level") or "read"
            if kind not in ("user", "group") or not name:
                raise EagleAccessError("Each entry needs a user or group name.")
            if level not in LEVELS:
                raise EagleAccessError("Access is 'read' or 'write'.")
            table, column = ("users", "username") if kind == "user" else ("groups", "name")
            row = self.connection.fetchone(f"SELECT id FROM {table} WHERE {column} = ?", (name,))
            if row is None:
                raise EagleAccessError(f"No {kind} named '{name}'.")
            if name not in (allowed_users if kind == "user" else allowed_groups):
                raise EagleAccessError(f"{name} is not a member of this project.")
            resolved.append((kind, int(row["id"]), level))

        with self.connection.transaction():
            self.connection.execute("DELETE FROM eagleapi_access WHERE item_id = ?", (item_id,))
            if restricted:
                self.connection.execute(
                    "INSERT OR REPLACE INTO eagleapi_restricted"
                    " (item_id, project_id, updated_by, updated_at) VALUES (?, ?, ?, ?)",
                    (item_id, project_id, updated_by, _now()),
                )
                for kind, principal_id, level in {
                    (k, p): (k, p, lv) for k, p, lv in resolved
                }.values():
                    self.connection.execute(
                        "INSERT INTO eagleapi_access (item_id, principal, principal_id, level)"
                        " VALUES (?, ?, ?, ?)",
                        (item_id, kind, principal_id, level),
                    )
            else:
                self.connection.execute(
                    "DELETE FROM eagleapi_restricted WHERE item_id = ?", (item_id,)
                )

    def forget(self, item_ids: Iterable[int]) -> None:
        """Items that were deleted, or are no longer top-level."""

        with self.connection.transaction():
            for item_id in item_ids:
                self.connection.execute("DELETE FROM eagleapi_access WHERE item_id = ?", (item_id,))
                self.connection.execute(
                    "DELETE FROM eagleapi_restricted WHERE item_id = ?", (item_id,)
                )

    def delete_project(self, project_id: int) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "DELETE FROM eagleapi_access WHERE item_id IN"
                " (SELECT item_id FROM eagleapi_restricted WHERE project_id = ?)",
                (project_id,),
            )
            self.connection.execute(
                "DELETE FROM eagleapi_restricted WHERE project_id = ?", (project_id,)
            )
