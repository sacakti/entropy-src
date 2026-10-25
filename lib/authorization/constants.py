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
    ModuleDefinition(
        name="nodes",
        description="Execution node management.",
    ),
    ModuleDefinition(
        name="schedules",
        description="Scheduled workflow and plugin runs.",
    ),
    ModuleDefinition(
        name="projects",
        description="Projects: who may do what with whose workflows, schedules and nodes.",
    ),
    ModuleDefinition(
        name="tasks",
        description="Project task tracking, collaboration and reminders.",
    ),
    ModuleDefinition(
        name="releases",
        description="Release tracking, task coordination and environment promotion.",
    ),
    ModuleDefinition(
        name="artifacts",
        description="Project release packages and deployment artifacts.",
    ),
    ModuleDefinition(
        name="system",
        description="Entropy settings: e-mail, sign-in, data retention.",
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
        "delete",
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
        "delete",
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
        "delete",
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
        "workflows.read",
        "read",
        "View workflows, their definitions, history and runs.",
    ),
    PermissionDefinition(
        "workflows",
        "workflows.write",
        "write",
        "Create, import and modify workflows; restore earlier versions.",
    ),
    PermissionDefinition(
        "workflows",
        "workflows.delete",
        "delete",
        "Delete workflows.",
    ),
    PermissionDefinition(
        "workflows",
        "workflows.execute",
        "execute",
        "Run and stop workflows.",
    ),
    PermissionDefinition(
        "workflows",
        "workflows.all",
        "full",
        "Every workflows permission (read, write, delete, execute).",
    ),
    PermissionDefinition(
        "plugins",
        "plugins.read",
        "read",
        "View plugins, their source files and history.",
    ),
    PermissionDefinition(
        "plugins",
        "plugins.write",
        "write",
        "Create, import, install, modify and upgrade plugins; restore earlier versions.",
    ),
    PermissionDefinition(
        "plugins",
        "plugins.delete",
        "delete",
        "Uninstall plugins and delete drafts.",
    ),
    PermissionDefinition(
        "plugins",
        "plugins.execute",
        "execute",
        "Run plugins directly (test runs).",
    ),
    PermissionDefinition(
        "plugins",
        "plugins.all",
        "full",
        "Every plugins permission (read, write, delete, execute).",
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
        "delete",
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
        "delete",
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
    PermissionDefinition(
        "auth",
        "auth.switch",
        "execute",
        "Switch to an authenticated user session.",
    ),
    PermissionDefinition(
        "auth",
        "auth.list",
        "read",
        "List authenticated user sessions.",
    ),
    PermissionDefinition(
        "nodes",
        "nodes.list",
        "read",
        "List execution nodes and their metrics.",
    ),
    PermissionDefinition(
        "nodes",
        "nodes.manage",
        "write",
        "Add, set up, enable and modify execution nodes.",
    ),
    PermissionDefinition(
        "nodes",
        "nodes.delete",
        "delete",
        "Remove execution nodes (and uninstall their agents).",
    ),
    PermissionDefinition(
        "schedules",
        "schedules.list",
        "read",
        "List schedules and their runs.",
    ),
    PermissionDefinition(
        "schedules",
        "schedules.manage",
        "write",
        "Create, modify, pause and trigger schedules.",
    ),
    PermissionDefinition(
        "schedules",
        "schedules.delete",
        "delete",
        "Delete schedules.",
    ),
    PermissionDefinition(
        "projects",
        "projects.read",
        "read",
        "See every project and its members.",
    ),
    PermissionDefinition(
        "projects",
        "projects.manage",
        "write",
        "Create, change and delete projects; manage any project's members and nodes.",
    ),
    PermissionDefinition(
        "projects",
        "projects.members",
        "write",
        "Manage the members of a project (in a project role: that project).",
    ),
    PermissionDefinition("tasks", "tasks.read", "read", "View tasks in a project."),
    PermissionDefinition("tasks", "tasks.create", "write", "Create tasks in a project."),
    PermissionDefinition("tasks", "tasks.manage", "write", "Update and assign project tasks."),
    PermissionDefinition("tasks", "tasks.comment", "write", "Comment on project tasks."),
    PermissionDefinition("tasks", "tasks.follow", "write", "Follow project tasks."),
    PermissionDefinition("releases", "releases.read", "read", "View project releases and promotions."),
    PermissionDefinition("releases", "releases.create", "write", "Create project releases."),
    PermissionDefinition("releases", "releases.manage", "write", "Update releases and link tasks."),
    PermissionDefinition("releases", "releases.promote", "execute", "Promote completed releases using workflows."),
    PermissionDefinition("artifacts", "artifacts.read", "read", "View release artifacts in a project."),
    PermissionDefinition("artifacts", "artifacts.write", "write", "Upload and register release artifacts in a project."),
    PermissionDefinition(
        "system",
        "system.settings",
        "write",
        "Change Entropy settings: e-mail (SMTP), sign-in (LDAP, SSO), data retention.",
    ),
)


# Permissions replaced by newer ones. Grants of an old permission (to roles
# or users) move to its replacements when the catalogue is reconciled.
# Editing a workflow used to include deleting it, so that grant keeps both.
PERMISSION_RENAMES = {
    "workflows.list": ("workflows.read",),
    "workflows.add": ("workflows.write",),
    "workflows.edit": ("workflows.write", "workflows.delete"),
    "workflows.run": ("workflows.execute",),
    "workflows.start": ("workflows.execute",),
    "plugins.list": ("plugins.read",),
    "plugins.install": ("plugins.write",),
    "plugins.upgrade": ("plugins.write",),
    "plugins.uninstall": ("plugins.delete",),
    "plugins.run": ("plugins.execute",),
}

# New permissions split out of one that remains: whoever held the existing
# permission when the new one first appears keeps what they could do.
PERMISSION_SPLITS = {
    "nodes.delete": "nodes.manage",
    "schedules.delete": "schedules.manage",
}

# `<module>.all` grants every permission of its module.
ALL_SUFFIX = ".all"


ADMIN_ROLE = "admin"

DEFAULT_ROLES = (
    "read",
    "write",
    "delete",
    "execute",
    "full",
)
