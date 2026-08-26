"""
Create Entropy authorization tables.
"""

from __future__ import annotations

from lib.database.connection import DatabaseConnection
from lib.database.objects.group_roles import GroupRolesTable
from lib.database.objects.groups import GroupsTable
from lib.database.objects.modules import ModulesTable
from lib.database.objects.permissions import PermissionsTable
from lib.database.objects.role_permissions import RolePermissionsTable
from lib.database.objects.roles import RolesTable
from lib.database.objects.user_groups import UserGroupsTable
from lib.database.objects.user_privileges import UserPrivilegesTable
from lib.database.objects.user_roles import UserRolesTable
from lib.database.objects.vault_namespace_access import (
    VaultNamespaceAccessTable,
)
from lib.database.objects.vault_namespaces import (
    VaultNamespacesTable,
)
from lib.migrations.base import BaseMigration


class AuthorizationMigration(BaseMigration):
    """
    Create Entropy authorization tables.
    """

    VERSION = 3

    DESCRIPTION = "Create Entropy authorization tables."

    def upgrade(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """
        Create authorization tables.
        """

        GroupsTable().create(
            connection,
        )

        RolesTable().create(
            connection,
        )

        ModulesTable().create(
            connection,
        )

        PermissionsTable().create(
            connection,
        )

        UserGroupsTable().create(
            connection,
        )

        UserRolesTable().create(
            connection,
        )

        GroupRolesTable().create(
            connection,
        )

        RolePermissionsTable().create(
            connection,
        )

        UserPrivilegesTable().create(
            connection,
        )

        VaultNamespacesTable().create(
            connection,
        )

        VaultNamespaceAccessTable().create(
            connection,
        )
