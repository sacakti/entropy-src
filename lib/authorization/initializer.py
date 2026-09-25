"""
Authorization initialization.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib.database.connection import DatabaseConnection

from lib.authorization.exceptions import AuthGenericError
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

            raise AuthGenericError(
                "Bootstrap administrator must have a database identifier.",
            )

        self._seeder.seed()

        with self._connection.transaction():

            self._initialize_admin_role()
            self._initialize_admin_permissions()
            self._initialize_default_roles()
            self._assign_admin_role(
                admin_user,
            )

    def reconcile(self) -> None:
        self._seeder.seed()

        with self._connection.transaction():
            self._initialize_admin_role()
            self._initialize_admin_permissions()
            self._initialize_default_roles()

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
            (ADMIN_ROLE,),
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
            (ADMIN_ROLE,),
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

    # ------------------------------------------------------------------
    # Default roles
    # ------------------------------------------------------------------

    def _initialize_default_roles(
        self,
    ) -> None:
        """
        Initialize built-in default authorization roles.
        """

        self._initialize_global_roles()

        self._initialize_module_roles()

    def _initialize_global_roles(
        self,
    ) -> None:
        """
        Create global permission-type roles.
        """

        roles = (
            (
                "read",
                "Read access to all Entropy modules.",
            ),
            (
                "write",
                "Write access to all Entropy modules.",
            ),
            (
                "execute",
                "Execute access to all Entropy modules.",
            ),
            (
                "full",
                "Full access to all Entropy modules.",
            ),
        )

        for name, description in roles:

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
                    name,
                    description,
                ),
            )

            if name == "full":

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
                    (name,),
                )

            else:

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
                      AND permissions.permission_type = ?
                    """,
                    (
                        name,
                        name,
                    ),
                )

    def _initialize_module_roles(
        self,
    ) -> None:
        """
        Create module-scoped default roles.
        """

        rows = self._connection.fetchall(
            """
            SELECT
                modules.name AS module_name,
                permissions.permission_type AS permission_type
            FROM modules
            INNER JOIN permissions
                ON permissions.module_id = modules.id
            GROUP BY
                modules.name,
                permissions.permission_type
            ORDER BY
                modules.name,
                permissions.permission_type
            """
        )

        for row in rows:

            module = row["module_name"]
            permission_type = row["permission_type"]

            role_name = f"{module}-{permission_type}"

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
                    role_name,
                    (f"{permission_type.capitalize()} access " f"to the {module} module."),
                ),
            )

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
                INNER JOIN permissions
                    ON permissions.module_id = (
                        SELECT id
                        FROM modules
                        WHERE name = ?
                    )
                WHERE roles.name = ?
                  AND permissions.permission_type = ?
                """,
                (
                    module,
                    role_name,
                    permission_type,
                ),
            )

        #
        # Module full roles.
        #

        modules = self._connection.fetchall(
            """
            SELECT
                modules.name AS module_name
            FROM modules
            INNER JOIN permissions
                ON permissions.module_id = modules.id
            GROUP BY modules.name
            ORDER BY modules.name
            """
        )

        for row in modules:

            module = row["module_name"]
            role_name = f"{module}-full"

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
                    role_name,
                    f"Full access to the {module} module.",
                ),
            )

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
                INNER JOIN permissions
                    ON permissions.module_id = (
                        SELECT id
                        FROM modules
                        WHERE name = ?
                    )
                WHERE roles.name = ?
                """,
                (
                    module,
                    role_name,
                ),
            )
