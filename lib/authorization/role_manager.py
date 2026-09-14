"""
Role management.
"""

from __future__ import annotations

from lib.authorization.exceptions import AuthGenericError
from lib.database.repositories.permissions import PermissionRepository
from lib.database.repositories.role_permissions import (
    RolePermissionRepository,
)
from lib.database.repositories.roles import RoleRepository
from lib.models.authorization import Permission, Role, RolePermission

ADMIN_ROLE = "admin"


class RoleManager:
    """
    Manages authorization roles and their permissions.

    Authorization is handled by the command layer.
    This manager is responsible for role business rules.
    """

    def __init__(
        self,
        roles: RoleRepository,
        permissions: PermissionRepository,
        role_permissions: RolePermissionRepository,
    ) -> None:

        self._roles = roles

        self._permissions = permissions

        self._role_permissions = role_permissions

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(
        self,
        name: str,
        description: str | None = None,
    ) -> Role:
        """
        Create a role.
        """

        name = name.strip()

        if not name:

            raise AuthGenericError(
                "Role name cannot be empty.",
            )

        if self._roles.exists(
            name,
        ):

            raise AuthGenericError(
                f"Role '{name}' already exists.",
            )

        if description is not None:

            description = description.strip() or None

        return self._roles.create(
            Role(
                name=name,
                description=description,
            ),
        )

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get(
        self,
        name: str,
    ) -> Role:
        """
        Return a role by name.
        """

        return self._roles.get_by_name(
            name,
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(
        self,
    ) -> list[Role]:
        """
        Return all roles.
        """

        return self._roles.list()

    # ------------------------------------------------------------------
    # Modify
    # ------------------------------------------------------------------

    def modify(
        self,
        role: Role,
        name: str | None = None,
        description: str | None = None,
    ) -> Role:
        """
        Modify a role.

        The built-in administrator role is immutable.
        """

        self._protect_admin(
            role,
        )

        if name is not None:

            name = name.strip()

            if not name:

                raise AuthGenericError(
                    "Role name cannot be empty.",
                )

            if name != role.name and self._roles.exists(name):

                raise AuthGenericError(
                    f"Role '{name}' already exists.",
                )

            role.name = name

        if description is not None:

            role.description = description.strip() or None

        self._roles.update(
            role,
        )

        assert role.id is not None

        return self._roles.get(
            role.id,
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(
        self,
        role: Role,
    ) -> None:
        """
        Delete a role.

        The built-in administrator role cannot be deleted.
        """

        self._protect_admin(
            role,
        )

        assert role.id is not None

        self._roles.delete(
            role.id,
        )

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------

    def permissions(
        self,
        role: Role,
    ) -> list[Permission]:
        """
        Return permissions assigned to a role.
        """

        assert role.id is not None

        return self._role_permissions.list_permissions(
            role.id,
        )

    # ------------------------------------------------------------------
    # Grant permission
    # ------------------------------------------------------------------

    def grant_permission(
        self,
        role: Role,
        permission_name: str,
    ) -> None:
        """
        Assign a permission to a role.

        The built-in administrator role cannot be modified.
        """

        self._protect_admin(
            role,
        )

        assert role.id is not None

        permission = self._permissions.get_by_name(
            permission_name,
        )

        assert permission.id is not None

        if self._role_permissions.exists(
            role.id,
            permission.id,
        ):

            return

        self._role_permissions.create(
            RolePermission(
                role_id=role.id,
                permission_id=permission.id,
            ),
        )

    # ------------------------------------------------------------------
    # Revoke permission
    # ------------------------------------------------------------------

    def revoke_permission(
        self,
        role: Role,
        permission_name: str,
    ) -> None:
        """
        Remove a permission from a role.

        The built-in administrator role cannot be modified.
        """

        self._protect_admin(
            role,
        )

        assert role.id is not None

        permission = self._permissions.get_by_name(
            permission_name,
        )

        assert permission.id is not None

        self._role_permissions.delete_permission(
            role.id,
            permission.id,
        )

    # ------------------------------------------------------------------
    # Protection
    # ------------------------------------------------------------------

    @staticmethod
    def _protect_admin(
        role: Role,
    ) -> None:
        """
        Prevent modification of the built-in administrator role.
        """

        if role.name == ADMIN_ROLE:

            raise AuthGenericError(
                "The built-in 'admin' role cannot be modified.",
            )
