"""
User role management.
"""

from __future__ import annotations

from lib.database.repositories.roles import RoleRepository
from lib.database.repositories.user_roles import UserRoleRepository
from lib.models.authorization import Role, UserRole
from lib.models.users import User


class UserRoleManager:
    """
    Manages user-to-role assignments.

    Authorization is handled by the command layer.
    """

    def __init__(
        self,
        roles: RoleRepository,
        user_roles: UserRoleRepository,
    ) -> None:

        self._roles = roles

        self._user_roles = user_roles

    # ------------------------------------------------------------------
    # Roles
    # ------------------------------------------------------------------

    def roles(
        self,
        user: User,
    ) -> list[Role]:
        """
        Return roles assigned to a user.
        """

        assert user.id is not None

        return self._user_roles.list_roles(
            user.id,
        )

    # ------------------------------------------------------------------
    # Add Role
    # ------------------------------------------------------------------

    def add_role(
        self,
        user: User,
        role_name: str,
    ) -> None:
        """
        Assign a role to a user.

        Adding an existing role is idempotent.
        """

        assert user.id is not None

        role = self._roles.get_by_name(
            role_name,
        )

        assert role.id is not None

        if self._user_roles.exists(
            user.id,
            role.id,
        ):

            return

        self._user_roles.create(
            UserRole(
                user_id=user.id,
                role_id=role.id,
            ),
        )

    # ------------------------------------------------------------------
    # Remove Role
    # ------------------------------------------------------------------

    def revoke_role(
        self,
        user: User,
        role_name: str,
    ) -> None:
        """
        Remove a role from a user.

        Removing a missing assignment is harmless.
        """

        assert user.id is not None

        role = self._roles.get_by_name(
            role_name,
        )

        assert role.id is not None

        self._user_roles.delete_role(
            user.id,
            role.id,
        )
