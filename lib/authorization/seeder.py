"""
Authorization seeder.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .constants import (
    MODULES,
    PERMISSION_RENAMES,
    PERMISSION_SPLITS,
    PERMISSIONS,
)

if TYPE_CHECKING:
    from lib.database.connection import DatabaseConnection


class AuthorizationSeeder:
    """
    Seeds built-in authorization modules and permissions.

    Idempotent and safe to execute during application startup.
    """

    def __init__(
        self,
        connection: DatabaseConnection,
    ) -> None:

        self._connection = connection

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def seed(
        self,
    ) -> None:

        with self._connection.transaction():

            existing = {
                row["name"] for row in self._connection.fetchall("SELECT name FROM permissions")
            }

            self._seed_modules()
            self._seed_permissions()
            self._apply_renames()
            self._apply_splits(existing)

    # ------------------------------------------------------------------
    # Modules
    # ------------------------------------------------------------------

    def _seed_modules(
        self,
    ) -> None:

        for module in MODULES:

            self._connection.execute(
                """
                INSERT OR IGNORE INTO modules
                (
                    name,
                    description
                )
                VALUES
                (
                    ?,
                    ?
                )
                """,
                (
                    module.name,
                    module.description,
                ),
            )

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------

    def _seed_permissions(
        self,
    ) -> None:

        for permission in PERMISSIONS:

            self._connection.execute(
                """
                INSERT OR IGNORE INTO permissions
                (
                    module_id,
                    name,
                    description,
                    permission_type
                )
                SELECT
                    id,
                    ?,
                    ?,
                    ?
                FROM modules
                WHERE name = ?
                """,
                (
                    permission.name,
                    permission.description,
                    permission.permission_type,
                    permission.module,
                ),
            )

            # Built-in permissions may change type or wording between releases.
            self._connection.execute(
                """
                UPDATE permissions
                SET permission_type = ?, description = ?
                WHERE name = ?
                  AND (permission_type != ? OR description != ?)
                """,
                (
                    permission.permission_type,
                    permission.description,
                    permission.name,
                    permission.permission_type,
                    permission.description,
                ),
            )

    # ------------------------------------------------------------------
    # Renamed and split permissions
    # ------------------------------------------------------------------

    def _permission_id(self, name: str):
        row = self._connection.fetchone("SELECT id FROM permissions WHERE name = ?", (name,))
        return row["id"] if row is not None else None

    def _copy_grants(self, source_id: int, target_id: int) -> None:
        """Give `target` to every role and user holding `source`."""

        self._connection.execute(
            """
            INSERT OR IGNORE INTO role_permissions (role_id, permission_id, created_at)
            SELECT role_id, ?, datetime('now')
            FROM role_permissions
            WHERE permission_id = ?
            """,
            (target_id, source_id),
        )
        self._connection.execute(
            """
            INSERT OR IGNORE INTO user_privileges (user_id, permission_id, created_at)
            SELECT user_id, ?, datetime('now')
            FROM user_privileges
            WHERE permission_id = ?
            """,
            (target_id, source_id),
        )

    def _apply_renames(self) -> None:
        """Move grants of replaced permissions to their replacements, then drop them."""

        for old, replacements in PERMISSION_RENAMES.items():
            old_id = self._permission_id(old)
            if old_id is None:
                continue

            for name in replacements:
                new_id = self._permission_id(name)
                if new_id is not None:
                    self._copy_grants(old_id, new_id)

            self._connection.execute(
                "DELETE FROM role_permissions WHERE permission_id = ?", (old_id,)
            )
            self._connection.execute(
                "DELETE FROM user_privileges WHERE permission_id = ?", (old_id,)
            )
            self._connection.execute("DELETE FROM permissions WHERE id = ?", (old_id,))

    def _apply_splits(self, existing: set) -> None:
        """A new permission split out of another starts with that one's grants."""

        for name, source in PERMISSION_SPLITS.items():
            if name in existing:
                continue  # granted or revoked deliberately since
            source_id = self._permission_id(source)
            new_id = self._permission_id(name)
            if source_id is not None and new_id is not None:
                self._copy_grants(source_id, new_id)
