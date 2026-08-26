"""
Authorization service.
"""

from __future__ import annotations

from lib.authorization.exceptions import AuthorizationRequiredError
from lib.database.connection import DatabaseConnection
from lib.models.authorization import PermissionType
from lib.auth.session import Session

class AuthorizationService:
    """
    Resolves effective permissions for authenticated users.

    Permissions can be granted through:
        user -> role -> permission
        user -> group -> role -> permission
        user -> privilege -> permission

    The administrator role is treated normally through the database
    authorization model; there is no hard-coded user bypass here.
    """

    def __init__(
        self,
        connection: DatabaseConnection,
    ) -> None:

        self._connection = connection

    # ------------------------------------------------------------------
    # Permission
    # ------------------------------------------------------------------

    def has_permission(
        self,
        user_id: int,
        permission: str,
    ) -> bool:
        """
        Return True when the user has the requested permission.
        """

        return self._connection.fetchone(
            """
            SELECT 1
            FROM permissions p

            WHERE p.name = ?

            AND
            (
                EXISTS
                (
                    SELECT 1
                    FROM user_privileges up
                    WHERE up.user_id = ?
                      AND up.permission_id = p.id
                )

                OR

                EXISTS
                (
                    SELECT 1
                    FROM user_roles ur
                    JOIN role_permissions rp
                      ON rp.role_id = ur.role_id
                    WHERE ur.user_id = ?
                      AND rp.permission_id = p.id
                )

                OR

                EXISTS
                (
                    SELECT 1
                    FROM user_groups ug
                    JOIN group_roles gr
                      ON gr.group_id = ug.group_id
                    JOIN role_permissions rp
                      ON rp.role_id = gr.role_id
                    WHERE ug.user_id = ?
                      AND rp.permission_id = p.id
                )
            )

            LIMIT 1
            """,
            (
                permission,
                user_id,
                user_id,
                user_id,
            ),
        ) is not None

    # ------------------------------------------------------------------
    # Permission type
    # ------------------------------------------------------------------

    def has_permission_type(
        self,
        user_id: int,
        module: str,
        permission_type: PermissionType,
    ) -> bool:
        """
        Return True when the user has at least one permission of the
        requested type within a module.
        """

        return self._connection.fetchone(
            """
            SELECT 1
            FROM permissions p
            JOIN modules m
              ON m.id = p.module_id

            WHERE m.name = ?
              AND p.permission_type = ?

            AND
            (
                EXISTS
                (
                    SELECT 1
                    FROM user_privileges up
                    WHERE up.user_id = ?
                      AND up.permission_id = p.id
                )

                OR

                EXISTS
                (
                    SELECT 1
                    FROM user_roles ur
                    JOIN role_permissions rp
                      ON rp.role_id = ur.role_id
                    WHERE ur.user_id = ?
                      AND rp.permission_id = p.id
                )

                OR

                EXISTS
                (
                    SELECT 1
                    FROM user_groups ug
                    JOIN group_roles gr
                      ON gr.group_id = ug.group_id
                    JOIN role_permissions rp
                      ON rp.role_id = gr.role_id
                    WHERE ug.user_id = ?
                      AND rp.permission_id = p.id
                )
            )

            LIMIT 1
            """,
            (
                module,
                permission_type.value,
                user_id,
                user_id,
                user_id,
            ),
        ) is not None

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------

    def permissions(
        self,
        user_id: int,
    ) -> list[str]:
        """
        Return all effective permissions for a user.
        """

        rows = self._connection.fetchall(
            """
            SELECT DISTINCT p.name
            FROM permissions p

            WHERE
                EXISTS
                (
                    SELECT 1
                    FROM user_privileges up
                    WHERE up.user_id = ?
                      AND up.permission_id = p.id
                )

                OR

                EXISTS
                (
                    SELECT 1
                    FROM user_roles ur
                    JOIN role_permissions rp
                      ON rp.role_id = ur.role_id
                    WHERE ur.user_id = ?
                      AND rp.permission_id = p.id
                )

                OR

                EXISTS
                (
                    SELECT 1
                    FROM user_groups ug
                    JOIN group_roles gr
                      ON gr.group_id = ug.group_id
                    JOIN role_permissions rp
                      ON rp.role_id = gr.role_id
                    WHERE ug.user_id = ?
                      AND rp.permission_id = p.id
                )

            ORDER BY p.name
            """,
            (
                user_id,
                user_id,
                user_id,
            ),
        )

        return [
            row["name"]
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Require
    # ------------------------------------------------------------------

    def require(
        self,
        session: Session,
        permission: str,
    ) -> None:
        """
        Require a specific permission.

        Raises
        ------
        AuthorizationRequiredError
            If the user does not have the requested permission.
        """

        if not self.has_permission(
            session.user_id,
            permission,
        ):

            raise AuthorizationRequiredError(
                permission,
            )

    def require_type(
        self,
        session: Session,
        module: str,
        permission_type: PermissionType,
    ) -> None:
        """
        Require a permission type within a module.
        """

        if not self.has_permission_type(
            session.user_id,
            module,
            permission_type,
        ):

            raise AuthorizationRequiredError(
                f"{module}:{permission_type.value}",
            )
