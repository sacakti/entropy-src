"""
Vault namespace management.
"""

from __future__ import annotations

from lib.database.repositories.users import UserRepository
from lib.database.repositories.vault_namespace_access import (
    VaultNamespaceAccessRepository,
)
from lib.database.repositories.vault_namespaces import (
    VaultNamespaceRepository,
)
from lib.models.authorization import (
    VaultAccess,
    VaultNamespace,
    VaultNamespaceAccess,
)
from lib.models.users import User
from lib.vault.exceptions import (
    VaultError,
    VaultNamespaceExistsError,
    VaultNamespaceNameError,
)


class VaultNamespaceManager:
    """
    Manages Vault namespaces and namespace access.

    Authorization decisions are handled by the command/service layer.
    This manager handles namespace business rules.
    """

    def __init__(
        self,
        namespaces: VaultNamespaceRepository,
        access: VaultNamespaceAccessRepository,
        users: UserRepository,
    ) -> None:

        self._namespaces = namespaces

        self._access = access

        self._users = users

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(
        self,
        name: str,
        owner_user_id: int,
        visibility,
    ) -> VaultNamespace:
        """
        Create a Vault namespace.
        """

        name = name.strip()

        if not name:

            raise VaultNamespaceNameError()

        if self._namespaces.exists(
            name,
        ):

            raise VaultNamespaceExistsError(name)

        namespace = VaultNamespace(
            name=name,
            owner_user_id=owner_user_id,
            visibility=visibility,
        )

        return self._namespaces.create(
            namespace,
        )

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get(
        self,
        name: str,
    ) -> VaultNamespace:
        """
        Return a namespace by name.
        """

        return self._namespaces.get_by_name(
            name,
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(
        self,
    ) -> list[VaultNamespace]:
        """
        Return all namespaces.
        """

        return self._namespaces.list()

    # ------------------------------------------------------------------
    # Modify
    # ------------------------------------------------------------------

    def modify(
        self,
        namespace: VaultNamespace,
        name: str | None = None,
        visibility=None,
    ) -> VaultNamespace:
        """
        Modify a namespace.
        """

        if name is not None:

            name = name.strip()

            if not name:

                raise VaultError(
                    "Vault namespace name cannot be empty.",
                )

            if name != namespace.name and self._namespaces.exists(name):

                raise VaultNamespaceExistsError(name)

            namespace.name = name

        if visibility is not None:

            namespace.visibility = visibility

        self._namespaces.update(
            namespace,
        )

        assert namespace.id is not None

        return self._namespaces.get(
            namespace.id,
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(
        self,
        namespace: VaultNamespace,
    ) -> None:
        """
        Delete a Vault namespace.
        """

        assert namespace.id is not None

        self._namespaces.delete(
            namespace.id,
        )

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    def grant_access(
        self,
        namespace: VaultNamespace,
        username: str,
        access: VaultAccess,
    ) -> None:
        """
        Grant or update a user's namespace access.
        """

        assert namespace.id is not None

        user = self._users.get_by_username(
            username,
        )

        assert user.id is not None

        if self._access.exists(
            namespace.id,
            user.id,
        ):

            self._access.update_access(
                namespace.id,
                user.id,
                access,
            )

            return

        self._access.create(
            VaultNamespaceAccess(
                namespace_id=namespace.id,
                user_id=user.id,
                access=access,
            ),
        )

    def revoke_access(
        self,
        namespace: VaultNamespace,
        username: str,
    ) -> None:
        """
        Revoke a user's namespace access.
        """

        assert namespace.id is not None

        user = self._users.get_by_username(
            username,
        )

        assert user.id is not None

        self._access.delete_by_user(
            namespace.id,
            user.id,
        )

    def access(
        self,
        namespace: VaultNamespace,
        user: User,
    ) -> VaultAccess | None:
        """
        Return a user's access level for a namespace.
        """

        assert namespace.id is not None
        assert user.id is not None

        return self._access.get_access(
            namespace.id,
            user.id,
        )

    def users(
        self,
        namespace: VaultNamespace,
    ) -> list[User]:
        """
        Return users with explicit access to a namespace.
        """

        assert namespace.id is not None

        assignments = self._access.list_by_namespace(
            namespace.id,
        )

        return [
            self._users.get(
                assignment.user_id,
            )
            for assignment in assignments
        ]

    def access_assignments(
        self,
        namespace: VaultNamespace,
    ) -> list[VaultNamespaceAccess]:
        """
        Return all access assignments for a namespace.
        """

        assert namespace.id is not None

        return self._access.list_by_namespace(
            namespace.id,
        )

    def access_by_user_id(
        self,
        namespace: VaultNamespace,
        user_id: int,
    ) -> VaultAccess | None:
        """
        Return a user's effective access level for a namespace.

        Namespace owners implicitly have administrator access.
        """

        assert namespace.id is not None

        if namespace.owner_user_id == user_id:

            return VaultAccess.ADMIN

        return self._access.get_access(
            namespace.id,
            user_id,
        )
