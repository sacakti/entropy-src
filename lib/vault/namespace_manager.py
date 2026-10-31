"""
Vault namespace management.
"""

from __future__ import annotations

from lib.database.repositories.vault_namespaces import (
    VaultNamespaceRepository,
)
from lib.models.authorization import VaultNamespace
from lib.vault.exceptions import (
    VaultError,
    VaultNamespaceExistsError,
    VaultNamespaceNameError,
)


class VaultNamespaceManager:
    """
    Manages a project's Vault namespaces.

    Namespace names are unique within a project. Who may use a namespace is
    decided by project roles (see lib.vault.access), not here.
    """

    def __init__(
        self,
        namespaces: VaultNamespaceRepository,
    ) -> None:

        self._namespaces = namespaces

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(
        self,
        name: str,
        project_id: int,
        owner_user_id: int | None = None,
    ) -> VaultNamespace:
        """
        Create a Vault namespace in a project.
        """

        name = name.strip()

        if not name:

            raise VaultNamespaceNameError()

        if self._namespaces.exists(
            name,
            project_id,
        ):

            raise VaultNamespaceExistsError(name)

        namespace = VaultNamespace(
            name=name,
            project_id=project_id,
            owner_user_id=owner_user_id,
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
        project_id: int,
    ) -> VaultNamespace:
        """
        Return a project's namespace by name.
        """

        return self._namespaces.get_by_name(
            name,
            project_id,
        )

    def get_by_id(
        self,
        namespace_id: int,
    ) -> VaultNamespace:
        """
        Return a namespace by identifier.
        """

        return self._namespaces.get(
            namespace_id,
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(
        self,
        project_id: int | None = None,
    ) -> list[VaultNamespace]:
        """
        Return a project's namespaces (all namespaces without a project).
        """

        return self._namespaces.list(
            project_id,
        )

    # ------------------------------------------------------------------
    # Modify
    # ------------------------------------------------------------------

    def modify(
        self,
        namespace: VaultNamespace,
        name: str | None = None,
    ) -> VaultNamespace:
        """
        Rename a namespace within its project.
        """

        if name is not None:

            name = name.strip()

            if not name:

                raise VaultError(
                    "Vault namespace name cannot be empty.",
                )

            if name != namespace.name and self._namespaces.exists(
                name,
                namespace.project_id,
            ):

                raise VaultNamespaceExistsError(name)

            namespace.name = name

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
        Delete a Vault namespace and its entries.
        """

        assert namespace.id is not None

        self._namespaces.delete(
            namespace.id,
        )
