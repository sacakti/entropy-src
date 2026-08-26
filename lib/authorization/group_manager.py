"""
Group management.
"""

from __future__ import annotations

from lib.database.repositories.group_roles import GroupRoleRepository
from lib.database.repositories.groups import GroupRepository
from lib.database.repositories.roles import RoleRepository
from lib.database.repositories.user_groups import UserGroupRepository
from lib.database.repositories.users import UserRepository
from lib.models.authorization import Group
from lib.models.authorization import GroupRole
from lib.models.authorization import Role
from lib.models.authorization import UserGroup
from lib.models.users import User


class GroupManager:
    """
    Manages authorization groups.

    Groups provide a way to associate users with reusable roles.

    Authorization is handled by the command layer.
    This manager is responsible for group business rules.
    """

    def __init__(
        self,
        groups: GroupRepository,
        users: UserRepository,
        roles: RoleRepository,
        user_groups: UserGroupRepository,
        group_roles: GroupRoleRepository,
    ) -> None:

        self._groups = groups

        self._users = users

        self._roles = roles

        self._user_groups = user_groups

        self._group_roles = group_roles

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(
        self,
        name: str,
        description: str | None = None,
    ) -> Group:
        """
        Create a group.
        """

        name = name.strip()

        if not name:

            raise ValueError(
                "Group name cannot be empty.",
            )

        if self._groups.exists(
            name,
        ):

            raise ValueError(
                f"Group '{name}' already exists.",
            )

        if description is not None:

            description = description.strip() or None

        return self._groups.create(
            Group(
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
    ) -> Group:
        """
        Return a group by name.
        """

        return self._groups.get_by_name(
            name,
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(
        self,
    ) -> list[Group]:
        """
        Return all groups.
        """

        return self._groups.list()

    # ------------------------------------------------------------------
    # Modify
    # ------------------------------------------------------------------

    def modify(
        self,
        group: Group,
        name: str | None = None,
        description: str | None = None,
    ) -> Group:
        """
        Modify a group.
        """

        if name is not None:

            name = name.strip()

            if not name:

                raise ValueError(
                    "Group name cannot be empty.",
                )

            if (
                name != group.name
                and self._groups.exists(name)
            ):

                raise ValueError(
                    f"Group '{name}' already exists.",
                )

            group.name = name

        if description is not None:

            group.description = description.strip() or None

        self._groups.update(
            group,
        )

        assert group.id is not None

        return self._groups.get(
            group.id,
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(
        self,
        group: Group,
    ) -> None:
        """
        Delete a group.
        """

        assert group.id is not None

        self._groups.delete(
            group.id,
        )

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def users(
        self,
        group: Group,
    ) -> list[User]:
        """
        Return users assigned to a group.
        """

        assert group.id is not None

        return self._user_groups.list_users(
            group.id,
        )

    # ------------------------------------------------------------------
    # Add User
    # ------------------------------------------------------------------

    def add_user(
        self,
        group: Group,
        username: str,
    ) -> None:
        """
        Add a user to a group.

        Adding an existing membership is idempotent.
        """

        assert group.id is not None

        user = self._users.get_by_username(
            username,
        )

        assert user.id is not None

        if self._user_groups.exists(
            user.id,
            group.id,
        ):
            return

        self._user_groups.create(
            UserGroup(
                user_id=user.id,
                group_id=group.id,
            ),
        )

    # ------------------------------------------------------------------
    # Remove User
    # ------------------------------------------------------------------

    def remove_user(
        self,
        group: Group,
        username: str,
    ) -> None:
        """
        Remove a user from a group.

        Removing a missing membership is harmless.
        """

        assert group.id is not None

        user = self._users.get_by_username(
            username,
        )

        assert user.id is not None

        self._user_groups.delete_group(
            user.id,
            group.id,
        )

    # ------------------------------------------------------------------
    # Roles
    # ------------------------------------------------------------------

    def roles(
        self,
        group: Group,
    ) -> list[Role]:
        """
        Return roles assigned to a group.
        """

        assert group.id is not None

        return self._group_roles.list_roles(
            group.id,
        )

    # ------------------------------------------------------------------
    # Add Role
    # ------------------------------------------------------------------

    def grant_role(
        self,
        group: Group,
        role_name: str,
    ) -> None:
        """
        Grant a role to a group.

        Granting an existing role is idempotent.
        """

        assert group.id is not None

        role = self._roles.get_by_name(
            role_name,
        )

        assert role.id is not None

        if self._group_roles.exists(
            group.id,
            role.id,
        ):

            return

        self._group_roles.create(
            GroupRole(
                group_id=group.id,
                role_id=role.id,
            ),
        )

    # ------------------------------------------------------------------
    # Remove Role
    # ------------------------------------------------------------------

    def revoke_role(
        self,
        group: Group,
        role_name: str,
    ) -> None:
        """
        Revoke a role from a group.

        Revoking a missing membership is harmless.
        """

        assert group.id is not None

        role = self._roles.get_by_name(
            role_name,
        )

        assert role.id is not None

        self._group_roles.delete_by_role(
            group.id,
            role.id,
        )
