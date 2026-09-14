"""
Authorization constants.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionDefinition:
    """
    Built-in permission definition.
    """

    module: str
    name: str
    permission_type: str
    description: str


@dataclass(frozen=True)
class ModuleDefinition:
    """
    Built-in authorization module definition.
    """

    name: str
    description: str


MODULES = (
    ModuleDefinition(
        name="vault",
        description="Entropy Vault operations.",
    ),
    ModuleDefinition(
        name="users",
        description="User account management.",
    ),
    ModuleDefinition(
        name="workflows",
        description="Workflow management and execution.",
    ),
    ModuleDefinition(
        name="plugins",
        description="Plugin management.",
    ),
    ModuleDefinition(
        name="extensions",
        description="Extension management.",
    ),
    ModuleDefinition(
        name="generate",
        description="Artifact generation operations.",
    ),
    ModuleDefinition(
        name="migrate",
        description="Database migration operations.",
    ),
    ModuleDefinition(
        name="upgrade",
        description="Entropy application upgrade operations.",
    ),
    ModuleDefinition(
        name="auth",
        description="Authentication and session operations.",
    ),
    ModuleDefinition(
        name="roles",
        description="Authorization role management.",
    ),
    ModuleDefinition(
        name="groups",
        description="User group management.",
    ),
)


PERMISSIONS = (
    PermissionDefinition(
        "vault",
        "vault.add",
        "write",
        "Add a Vault entry.",
    ),
    PermissionDefinition(
        "vault",
        "vault.read",
        "read",
        "Read Vault entries.",
    ),
    PermissionDefinition(
        "vault",
        "vault.modify",
        "write",
        "Modify a Vault entry.",
    ),
    PermissionDefinition(
        "vault",
        "vault.delete",
        "write",
        "Delete a Vault entry.",
    ),
    PermissionDefinition(
        "vault",
        "vault.namespace.create",
        "write",
        "Create Vault namespaces.",
    ),
    PermissionDefinition(
        "vault",
        "vault.namespace.read",
        "read",
        "Read Vault namespaces.",
    ),
    PermissionDefinition(
        "vault",
        "vault.namespace.modify",
        "write",
        "Modify Vault namespaces.",
    ),
    PermissionDefinition(
        "vault",
        "vault.namespace.delete",
        "write",
        "Delete Vault namespaces.",
    ),
    PermissionDefinition(
        "vault",
        "vault.namespace.users",
        "write",
        "Manage users assigned to Vault namespaces.",
    ),
    PermissionDefinition(
        "users",
        "users.create",
        "write",
        "Create users.",
    ),
    PermissionDefinition(
        "users",
        "users.read",
        "read",
        "Read user information.",
    ),
    PermissionDefinition(
        "users",
        "users.modify",
        "write",
        "Modify users.",
    ),
    PermissionDefinition(
        "users",
        "users.delete",
        "write",
        "Delete users.",
    ),
    PermissionDefinition(
        "users",
        "users.enable",
        "write",
        "Enable users.",
    ),
    PermissionDefinition(
        "users",
        "users.disable",
        "write",
        "Disable users.",
    ),
    PermissionDefinition(
        "users",
        "users.roles",
        "write",
        "Manage roles assigned to users.",
    ),
    PermissionDefinition(
        "workflows",
        "workflows.add",
        "write",
        "Create workflows.",
    ),
    PermissionDefinition(
        "workflows",
        "workflows.list",
        "read",
        "List workflows.",
    ),
    PermissionDefinition(
        "workflows",
        "workflows.edit",
        "write",
        "Edit workflows.",
    ),
    PermissionDefinition(
        "workflows",
        "workflows.run",
        "execute",
        "Run workflows.",
    ),
    PermissionDefinition(
        "workflows",
        "workflows.start",
        "execute",
        "Start workflows.",
    ),
    PermissionDefinition(
        "plugins",
        "plugins.install",
        "write",
        "Install plugins.",
    ),
    PermissionDefinition(
        "plugins",
        "plugins.uninstall",
        "write",
        "Uninstall plugins.",
    ),
    PermissionDefinition(
        "plugins",
        "plugins.list",
        "read",
        "List plugins.",
    ),
    PermissionDefinition(
        "plugins",
        "plugins.upgrade",
        "write",
        "Upgrade plugins.",
    ),
    PermissionDefinition(
        "plugins",
        "plugins.run",
        "execute",
        "Execute plugins.",
    ),
    PermissionDefinition(
        "extensions",
        "extensions.download",
        "write",
        "Download extensions.",
    ),
    PermissionDefinition(
        "extensions",
        "extensions.install",
        "write",
        "Install extensions.",
    ),
    PermissionDefinition(
        "extensions",
        "extensions.list",
        "read",
        "List extensions.",
    ),
    PermissionDefinition(
        "generate",
        "generate.plugin",
        "execute",
        "Generate plugins.",
    ),
    PermissionDefinition(
        "migrate",
        "migrate.database",
        "execute",
        "Run database migrations.",
    ),
    PermissionDefinition(
        "upgrade",
        "upgrade.entropy",
        "execute",
        "Upgrade Entropy.",
    ),
    PermissionDefinition(
        "auth",
        "auth.login",
        "execute",
        "Authenticate a user.",
    ),
    PermissionDefinition(
        "auth",
        "auth.logout",
        "execute",
        "Terminate the current session.",
    ),
    PermissionDefinition(
        "auth",
        "auth.status",
        "read",
        "Read authentication status.",
    ),
    PermissionDefinition(
        "roles",
        "roles.create",
        "write",
        "Create authorization roles.",
    ),
    PermissionDefinition(
        "roles",
        "roles.read",
        "read",
        "Read authorization roles.",
    ),
    PermissionDefinition(
        "roles",
        "roles.modify",
        "write",
        "Modify authorization roles.",
    ),
    PermissionDefinition(
        "roles",
        "roles.delete",
        "write",
        "Delete authorization roles.",
    ),
    PermissionDefinition(
        "roles",
        "roles.permissions",
        "write",
        "Manage role permissions.",
    ),
    PermissionDefinition(
        "groups",
        "groups.create",
        "write",
        "Create user groups.",
    ),
    PermissionDefinition(
        "groups",
        "groups.read",
        "read",
        "Read user groups.",
    ),
    PermissionDefinition(
        "groups",
        "groups.modify",
        "write",
        "Modify user groups.",
    ),
    PermissionDefinition(
        "groups",
        "groups.delete",
        "write",
        "Delete user groups.",
    ),
    PermissionDefinition(
        "groups",
        "groups.users",
        "write",
        "Manage users assigned to groups.",
    ),
    PermissionDefinition(
        "groups",
        "groups.roles",
        "write",
        "Manage roles assigned to groups.",
    ),
)


ADMIN_ROLE = "admin"

DEFAULT_ROLES = (
    "read",
    "write",
    "execute",
    "full",
)
