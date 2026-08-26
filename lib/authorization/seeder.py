"""
Authorization seeder.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .constants import (
    MODULES,
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

            self._seed_modules()
            self._seed_permissions()

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
