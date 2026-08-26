"""
Authorization initialization.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib.database.connection import DatabaseConnection

from lib.authorization.seeder import AuthorizationSeeder
from lib.models.users import User

from .constants import (
    ADMIN_ROLE,
)


class AuthorizationInitializer:
    """
    Initializes built-in Entropy authorization data.

    The initializer is idempotent. Existing authorization records
    are preserved while missing built-in records are created.
    """

    def __init__(
        self,
        connection: DatabaseConnection,
    ) -> None:

        self._connection = connection
        self._seeder = AuthorizationSeeder(
            connection,
        )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def initialize(
        self,
        admin_user: User,
    ) -> None:
        """
        Initialize the built-in authorization model and assign
        the administrator role to the bootstrap administrator.
        """

        if admin_user.id is None:

            raise ValueError(
                "Bootstrap administrator must have a database identifier.",
            )

        self._seeder.seed()

        with self._connection.transaction():

            self._initialize_admin_role()
            self._initialize_admin_permissions()
            self._assign_admin_role(
                admin_user,
            )

    # ------------------------------------------------------------------
    # Admin role
    # ------------------------------------------------------------------

    def _initialize_admin_role(
        self,
    ) -> None:

        self._connection.execute(
            """
            INSERT OR IGNORE INTO roles
            (
                name,
                description,
                created_at,
                updated_at
            )
            VALUES
            (
                ?,
                ?,
                datetime('now'),
                datetime('now')
            )
            """,
            (
                ADMIN_ROLE,
                "Full Entropy administrator.",
            ),
        )

    # ------------------------------------------------------------------
    # Admin permissions
    # ------------------------------------------------------------------

    def _initialize_admin_permissions(
        self,
    ) -> None:

        self._connection.execute(
            """
            INSERT OR IGNORE INTO role_permissions
            (
                role_id,
                permission_id,
                created_at
            )
            SELECT
                roles.id,
                permissions.id,
                datetime('now')
            FROM roles
            CROSS JOIN permissions
            WHERE roles.name = ?
            """,
            (
                ADMIN_ROLE,
            ),
        )

    def _assign_admin_role(
        self,
        admin_user: User,
    ) -> None:
        """
        Assign the administrator role to the bootstrap administrator.
        """

        row = self._connection.fetchone(
            """
            SELECT id
            FROM roles
            WHERE name = ?
            """,
            (
                ADMIN_ROLE,
            ),
        )

        if row is None:

            raise RuntimeError(
                "Administrator role was not initialized.",
            )

        self._connection.execute(
            """
            INSERT OR IGNORE INTO user_roles
            (
                user_id,
                role_id,
                created_at
            )
            VALUES
            (
                ?,
                ?,
                datetime('now')
            )
            """,
            (
                admin_user.id,
                int(row["id"]),
            ),
        )
