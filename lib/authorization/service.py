"""
Authorization service.
"""

from __future__ import annotations

from typing import Optional, Set

from lib.authorization.constants import ALL_SUFFIX
from lib.authorization.exceptions import AuthorizationRequiredError
from lib.database.connection import DatabaseConnection
from lib.models.authorization import PermissionType
from lib.models.session import Session


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
        project_id: Optional[int] = None,
    ) -> bool:
        """
        Return True when the user has the requested permission, directly or
        through the module's `<module>.all` permission.

        Global roles count everywhere. Project roles count in their project;
        without `project_id`, in any project (e.g. to show a "Create" button).
        """

        names = (permission, permission.split(".", 1)[0] + ALL_SUFFIX)
        return self._global_grant(user_id, names) or self._project_grant(
            user_id, names, project_id
        )

    def _global_grant(self, user_id: int, names: tuple) -> bool:
        return (
            self._connection.fetchone(
                """
            SELECT 1
            FROM permissions p

            WHERE p.name IN (?, ?)

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
                (*names, user_id, user_id, user_id),
            )
            is not None
        )

    def _project_grant(self, user_id: int, names: tuple, project_id: Optional[int]) -> bool:
        if not self._has_projects():
            return False
        project_clause = "" if project_id is None else "AND pm.project_id = ?"
        parameters = (*names, user_id, user_id) + (() if project_id is None else (project_id,))
        return (
            self._connection.fetchone(
                f"""
            SELECT 1
            FROM project_members pm
            JOIN role_permissions rp ON rp.role_id = pm.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE p.name IN (?, ?)
              AND (pm.user_id = ?
                   OR pm.group_id IN (SELECT group_id FROM user_groups WHERE user_id = ?))
              {project_clause}
            LIMIT 1
            """,
                parameters,
            )
            is not None
        )

    def _has_projects(self) -> bool:
        if getattr(self._connection, "_entropy_projects_ready", False):
            return True
        return (
            self._connection.fetchone(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'project_members'"
            )
            is not None
        )

    def projects_with(self, user_id: int, permission: str) -> Optional[Set[int]]:
        """
        Projects where the user has `permission`: None means every project
        (a global grant), otherwise the ids of the projects.
        """

        names = (permission, permission.split(".", 1)[0] + ALL_SUFFIX)
        if self._global_grant(user_id, names):
            return None
        if not self._has_projects():
            return set()
        rows = self._connection.fetchall(
            """
            SELECT DISTINCT pm.project_id
            FROM project_members pm
            JOIN role_permissions rp ON rp.role_id = pm.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE p.name IN (?, ?)
              AND (pm.user_id = ?
                   OR pm.group_id IN (SELECT group_id FROM user_groups WHERE user_id = ?))
            """,
            (*names, user_id, user_id),
        )
        return {int(row["project_id"]) for row in rows}

    def member_projects(self, user_id: int) -> Optional[Set[int]]:
        """Projects the user belongs to; None when a global role sees them all."""

        if self._global_grant(user_id, ("projects.read", "projects.all")) or self._global_grant(
            user_id, ("projects.manage", "projects.all")
        ):
            return None
        if not self._has_projects():
            return set()
        rows = self._connection.fetchall(
            "SELECT DISTINCT project_id FROM project_members WHERE user_id = ?"
            " OR group_id IN (SELECT group_id FROM user_groups WHERE user_id = ?)",
            (user_id, user_id),
        )
        return {int(row["project_id"]) for row in rows}

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

        return (
            self._connection.fetchone(
                """
            SELECT 1
            FROM permissions p
            JOIN modules m
              ON m.id = p.module_id

            WHERE m.name = ?
              AND (p.permission_type = ? OR p.name = m.name || '.all')

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
            )
            is not None
        )

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------

    def permissions(
        self,
        user_id: int,
        project_id: Optional[int] = None,
    ) -> list[str]:
        """
        Return all effective permissions for a user: global ones, plus those
        of their roles in `project_id` (or in any project when None).
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

        names = {row["name"] for row in rows}

        if self._has_projects():
            project_clause = "" if project_id is None else "AND pm.project_id = ?"
            names.update(
                row["name"]
                for row in self._connection.fetchall(
                    f"""
                    SELECT DISTINCT p.name
                    FROM project_members pm
                    JOIN role_permissions rp ON rp.role_id = pm.role_id
                    JOIN permissions p ON p.id = rp.permission_id
                    WHERE (pm.user_id = ?
                           OR pm.group_id IN (SELECT group_id FROM user_groups WHERE user_id = ?))
                      {project_clause}
                    """,
                    (user_id, user_id) + (() if project_id is None else (project_id,)),
                )
            )

        # `<module>.all` stands for every permission of its module.
        for name in [name for name in names if name.endswith(ALL_SUFFIX)]:
            module = name[: -len(ALL_SUFFIX)]
            names.update(
                row["name"]
                for row in self._connection.fetchall(
                    """
                    SELECT p.name FROM permissions p
                    JOIN modules m ON m.id = p.module_id
                    WHERE m.name = ?
                    """,
                    (module,),
                )
            )

        return sorted(names)

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
