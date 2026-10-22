"""
Projects and role-based access (RBAC).

A role is a set of permissions with a scope:

- global roles (Administrator, User admin, Node admin, Plugin developer, or
  custom) are given to users and groups and apply everywhere;
- project roles (Viewer, Operator, Developer, Maintainer, or custom) are
  given to users and groups *in a project* and apply to that project's
  workflows, schedules, drafts and runs.

Nodes are global resources: shared with every project, or assigned to some.

The permission names stay the same; `AuthorizationService.has_permission`
answers per project. Older databases are converted once: legacy type roles
in use become custom roles, project-type grants become memberships of the
Default project, and direct per-user permissions become a role per user.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from lib.database.connection import DatabaseConnection

DEFAULT_PROJECT = "default"
SCOPES = ("global", "project")

# Permissions a project role may hold: what is done inside one project.
PROJECT_PERMISSIONS = frozenset(
    {
        "workflows.read",
        "workflows.write",
        "workflows.delete",
        "workflows.execute",
        "workflows.all",
        "schedules.list",
        "schedules.manage",
        "schedules.delete",
        "plugins.read",
        "plugins.execute",
        "projects.members",
    }
)

_VIEWER = ("workflows.read", "schedules.list", "plugins.read")
_OPERATOR = _VIEWER + ("workflows.execute", "plugins.execute")
_DEVELOPER = _OPERATOR + ("workflows.write", "schedules.manage")
_MAINTAINER = _DEVELOPER + ("workflows.delete", "schedules.delete", "projects.members")

# name -> (title, scope, description, permissions); None means every permission.
BUILTIN_ROLES: Dict[str, tuple] = {
    "admin": (
        "Administrator",
        "global",
        "Everything, in every project, and the administration panel.",
        None,
    ),
    "user-admin": (
        "User administrator",
        "global",
        "Manage users, groups, roles and project members.",
        (
            "users.read",
            "users.create",
            "users.modify",
            "users.delete",
            "users.enable",
            "users.disable",
            "users.roles",
            "groups.read",
            "groups.create",
            "groups.modify",
            "groups.delete",
            "groups.users",
            "groups.roles",
            "roles.read",
            "projects.read",
            "projects.manage",
        ),
    ),
    "node-admin": (
        "Node administrator",
        "global",
        "Add, set up and remove execution nodes; assign them to projects.",
        ("nodes.list", "nodes.manage", "nodes.delete", "projects.read"),
    ),
    "plugin-developer": (
        "Plugin developer",
        "global",
        "Create, install, change and remove plugins and the libraries they need.",
        ("plugins.all", "extensions.list", "extensions.install", "extensions.download"),
    ),
    "vault-user": (
        "Vault user",
        "global",
        "Use the vault: own namespaces and those shared with you.",
        (
            "vault.read",
            "vault.add",
            "vault.modify",
            "vault.delete",
            "vault.namespace.create",
            "vault.namespace.read",
            "vault.namespace.modify",
            "vault.namespace.delete",
            "vault.namespace.users",
        ),
    ),
    "viewer": ("Viewer", "project", "See the project's workflows, schedules and runs.", _VIEWER),
    "operator": ("Operator", "project", "Viewer, and run workflows and plugins.", _OPERATOR),
    "developer": (
        "Developer",
        "project",
        "Operator, and create and change workflows and schedules.",
        _DEVELOPER,
    ),
    "maintainer": (
        "Maintainer",
        "project",
        "Developer, and delete them and manage the project's members.",
        _MAINTAINER,
    ),
}

# Roles the old model generated for every module and permission type.
_LEGACY_TYPES = ("read", "write", "delete", "execute", "full")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _table_exists(connection: DatabaseConnection, table: str) -> bool:
    return (
        connection.fetchone(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        )
        is not None
    )


def _add_column(connection: DatabaseConnection, table: str, column: str, ddl: str) -> None:
    if not _table_exists(connection, table):
        return
    columns = {row["name"] for row in connection.fetchall(f"PRAGMA table_info({table})")}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


# ----------------------------------------------------------------------
# Schema
# ----------------------------------------------------------------------


def ensure_projects_schema(connection: DatabaseConnection) -> None:
    """Create the project tables and columns (idempotent)."""

    if getattr(connection, "_entropy_projects_ready", False):
        return

    with connection.transaction():
        connection.execute("""
            CREATE TABLE IF NOT EXISTS projects
            (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                key         TEXT NOT NULL UNIQUE,
                name        TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_by  TEXT,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
            """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS project_members
            (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER NOT NULL,
                user_id     INTEGER,
                group_id    INTEGER,
                role_id     INTEGER NOT NULL,
                created_at  TEXT NOT NULL,
                CHECK ((user_id IS NULL) != (group_id IS NULL))
            )
            """)
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_project_members_unique ON project_members"
            " (project_id, IFNULL(user_id, 0), IFNULL(group_id, 0), role_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_members_user ON project_members (user_id)"
        )
        connection.execute("""
            CREATE TABLE IF NOT EXISTS workflow_projects
            (
                workflow    TEXT PRIMARY KEY,
                project_id  INTEGER NOT NULL
            )
            """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS node_projects
            (
                node        TEXT NOT NULL,
                project_id  INTEGER NOT NULL,
                PRIMARY KEY (node, project_id)
            )
            """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS authorization_state
            (
                key    TEXT PRIMARY KEY,
                value  TEXT NOT NULL
            )
            """)
        _add_column(connection, "roles", "scope", "TEXT NOT NULL DEFAULT 'global'")
        _add_column(connection, "roles", "builtin", "INTEGER NOT NULL DEFAULT 0")
        _add_column(connection, "roles", "title", "TEXT")
        add_project_columns(connection)

        if connection.fetchone("SELECT 1 FROM projects WHERE key = ?", (DEFAULT_PROJECT,)) is None:
            now = _now()
            connection.execute(
                "INSERT INTO projects (key, name, description, created_by, created_at, updated_at)"
                " VALUES (?, 'Default', 'Everything created before projects existed.', NULL, ?, ?)",
                (DEFAULT_PROJECT, now, now),
            )

    connection._entropy_projects_ready = True


def add_project_columns(connection: DatabaseConnection) -> None:
    """Project columns on resource tables (call again once those tables exist)."""

    _add_column(connection, "schedules", "project_id", "INTEGER")
    _add_column(connection, "run_metadata", "project_id", "INTEGER")
    _add_column(connection, "workflow_drafts", "project_id", "INTEGER")
    # 'shared': every project may run on the node; 'assigned': see node_projects.
    _add_column(connection, "nodes", "scope", "TEXT NOT NULL DEFAULT 'shared'")


def default_project_id(connection: DatabaseConnection) -> int:
    ensure_projects_schema(connection)
    return int(
        connection.fetchone("SELECT id FROM projects WHERE key = ?", (DEFAULT_PROJECT,))["id"]
    )


# ----------------------------------------------------------------------
# Built-in roles and the one-time conversion
# ----------------------------------------------------------------------


def role_scope(permissions: Iterable[str]) -> str:
    """'project' when every permission can be held in a project, else 'global'."""

    names = set(permissions)
    return "project" if names and names <= PROJECT_PERMISSIONS else "global"


def _permission_ids(connection: DatabaseConnection, names: Optional[Sequence[str]]) -> Set[int]:
    if names is None:
        return {row["id"] for row in connection.fetchall("SELECT id FROM permissions")}
    if not names:
        return set()
    marks = ", ".join("?" for _ in names)
    return {
        row["id"]
        for row in connection.fetchall(
            f"SELECT id FROM permissions WHERE name IN ({marks})", tuple(names)
        )
    }


def seed_builtin_roles(connection: DatabaseConnection) -> None:
    """Create the built-in roles and keep their permissions exactly as defined."""

    now = _now()
    for name, (title, scope, description, permissions) in BUILTIN_ROLES.items():
        connection.execute(
            "INSERT OR IGNORE INTO roles (name, description, created_at, updated_at)"
            " VALUES (?, ?, ?, ?)",
            (name, description, now, now),
        )
        connection.execute(
            "UPDATE roles SET title = ?, scope = ?, builtin = 1, description = ? WHERE name = ?",
            (title, scope, description, name),
        )
        role_id = connection.fetchone("SELECT id FROM roles WHERE name = ?", (name,))["id"]
        wanted = _permission_ids(connection, permissions)
        current = {
            row["permission_id"]
            for row in connection.fetchall(
                "SELECT permission_id FROM role_permissions WHERE role_id = ?", (role_id,)
            )
        }
        for permission_id in wanted - current:
            connection.execute(
                "INSERT OR IGNORE INTO role_permissions (role_id, permission_id, created_at)"
                " VALUES (?, ?, ?)",
                (role_id, permission_id, now),
            )
        for permission_id in current - wanted:
            connection.execute(
                "DELETE FROM role_permissions WHERE role_id = ? AND permission_id = ?",
                (role_id, permission_id),
            )


def _legacy_role_names(connection: DatabaseConnection) -> Set[str]:
    modules = [row["name"] for row in connection.fetchall("SELECT name FROM modules")]
    names = set(_LEGACY_TYPES)
    for module in modules:
        names.update(f"{module}-{kind}" for kind in _LEGACY_TYPES)
    return names


def _role_permission_names(connection: DatabaseConnection, role_id: int) -> List[str]:
    return [
        row["name"]
        for row in connection.fetchall(
            "SELECT p.name FROM permissions p JOIN role_permissions rp"
            " ON rp.permission_id = p.id WHERE rp.role_id = ?",
            (role_id,),
        )
    ]


def _unique_role_name(connection: DatabaseConnection, base: str) -> str:
    base = re.sub(r"[^a-z0-9-]+", "-", base.lower()).strip("-")[:60] or "role"
    name, number = base, 2
    while connection.fetchone("SELECT 1 FROM roles WHERE name = ?", (name,)):
        name, number = f"{base}-{number}", number + 1
    return name


def convert_legacy(connection: DatabaseConnection) -> None:
    """One-time move from the type-role model to scoped roles and projects."""

    if connection.fetchone("SELECT 1 FROM authorization_state WHERE key = 'rbac_v1'"):
        return

    now = _now()
    default_id = default_project_id(connection)
    legacy = _legacy_role_names(connection)
    builtin = set(BUILTIN_ROLES)

    for role in connection.fetchall("SELECT id, name FROM roles"):
        if role["name"] in builtin:
            continue
        used = connection.fetchone(
            "SELECT 1 FROM user_roles WHERE role_id = ? UNION SELECT 1 FROM group_roles"
            " WHERE role_id = ?",
            (role["id"], role["id"]),
        )
        if role["name"] in legacy and not used:
            # Generated roles nobody holds are just clutter now.
            connection.execute("DELETE FROM role_permissions WHERE role_id = ?", (role["id"],))
            connection.execute("DELETE FROM roles WHERE id = ?", (role["id"],))
            continue
        scope = role_scope(_role_permission_names(connection, role["id"]))
        connection.execute(
            "UPDATE roles SET scope = ?, builtin = 0, title = COALESCE(title, name)"
            " WHERE id = ?",
            (scope, role["id"]),
        )
        if scope == "project":
            # Everything lived in what is now the Default project.
            connection.execute(
                "INSERT OR IGNORE INTO project_members (project_id, user_id, role_id, created_at)"
                " SELECT ?, user_id, role_id, ? FROM user_roles WHERE role_id = ?",
                (default_id, now, role["id"]),
            )
            connection.execute(
                "INSERT OR IGNORE INTO project_members (project_id, group_id, role_id, created_at)"
                " SELECT ?, group_id, role_id, ? FROM group_roles WHERE role_id = ?",
                (default_id, now, role["id"]),
            )
            connection.execute("DELETE FROM user_roles WHERE role_id = ?", (role["id"],))
            connection.execute("DELETE FROM group_roles WHERE role_id = ?", (role["id"],))

    # Permissions granted straight to users become a role of their own.
    if _table_exists(connection, "user_privileges"):
        users = connection.fetchall(
            "SELECT DISTINCT up.user_id, u.username FROM user_privileges up"
            " JOIN users u ON u.id = up.user_id"
        )
        for user in users:
            names = [
                row["name"]
                for row in connection.fetchall(
                    "SELECT p.name FROM permissions p JOIN user_privileges up"
                    " ON up.permission_id = p.id WHERE up.user_id = ?",
                    (user["user_id"],),
                )
            ]
            groups = {
                "project": [name for name in names if name in PROJECT_PERMISSIONS],
                "global": [name for name in names if name not in PROJECT_PERMISSIONS],
            }
            for scope, members in groups.items():
                if not members:
                    continue
                role_name = _unique_role_name(connection, f"{user['username']}-{scope}")
                connection.execute(
                    "INSERT INTO roles (name, title, description, scope, builtin, created_at,"
                    " updated_at) VALUES (?, ?, ?, ?, 0, ?, ?)",
                    (
                        role_name,
                        f"{user['username']} ({scope})",
                        f"Given directly to {user['username']} before roles had scopes.",
                        scope,
                        now,
                        now,
                    ),
                )
                role_id = connection.fetchone("SELECT id FROM roles WHERE name = ?", (role_name,))[
                    "id"
                ]
                for permission_id in _permission_ids(connection, members):
                    connection.execute(
                        "INSERT INTO role_permissions (role_id, permission_id, created_at)"
                        " VALUES (?, ?, ?)",
                        (role_id, permission_id, now),
                    )
                if scope == "project":
                    connection.execute(
                        "INSERT OR IGNORE INTO project_members (project_id, user_id, role_id,"
                        " created_at) VALUES (?, ?, ?, ?)",
                        (default_id, user["user_id"], role_id, now),
                    )
                else:
                    connection.execute(
                        "INSERT OR IGNORE INTO user_roles (user_id, role_id, created_at)"
                        " VALUES (?, ?, ?)",
                        (user["user_id"], role_id, now),
                    )
        connection.execute("DELETE FROM user_privileges")

    connection.execute("INSERT INTO authorization_state (key, value) VALUES ('rbac_v1', ?)", (now,))


# ----------------------------------------------------------------------
# Projects and their resources
# ----------------------------------------------------------------------


def project_payload(row: Any) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "key": row["key"],
        "name": row["name"],
        "description": row["description"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


class Projects:
    """Projects, their members and which workflows, schedules and nodes they own."""

    KEY = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")

    def __init__(self, connection: DatabaseConnection) -> None:
        ensure_projects_schema(connection)
        self.connection = connection

    # -- projects -------------------------------------------------------

    def list(self, ids: Optional[Set[int]] = None) -> List[Dict[str, Any]]:
        rows = self.connection.fetchall(
            "SELECT * FROM projects ORDER BY key = 'default' DESC, name"
        )
        return [project_payload(row) for row in rows if ids is None or row["id"] in ids]

    def get(self, key_or_id: Any) -> Optional[Dict[str, Any]]:
        column = "id" if isinstance(key_or_id, int) else "key"
        row = self.connection.fetchone(f"SELECT * FROM projects WHERE {column} = ?", (key_or_id,))
        return project_payload(row) if row else None

    def create(self, key: str, name: str, description: str, user: str) -> Dict[str, Any]:
        key = key.strip().lower()
        if not self.KEY.match(key):
            raise ValueError(
                "A project key is 1-40 lowercase letters, digits or dashes, starting with a"
                " letter or digit."
            )
        if self.get(key):
            raise ValueError(f"Project '{key}' already exists.")
        now = _now()
        with self.connection.transaction():
            self.connection.execute(
                "INSERT INTO projects (key, name, description, created_by, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (key, name.strip() or key, description.strip(), user, now, now),
            )
        created = self.get(key)
        assert created is not None
        return created

    def update(self, key: str, name: str, description: str) -> Dict[str, Any]:
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE projects SET name = ?, description = ?, updated_at = ? WHERE key = ?",
                (name.strip() or key, description.strip(), _now(), key),
            )
        updated = self.get(key)
        if updated is None:
            raise LookupError(f"Project '{key}' not found.")
        return updated

    def usage(self, project_id: int) -> Dict[str, int]:
        default_id = default_project_id(self.connection)
        workflows = self.connection.fetchone(
            "SELECT COUNT(*) AS n FROM workflow_projects WHERE project_id = ?", (project_id,)
        )["n"]
        if project_id == default_id and _table_exists(self.connection, "workflow_registry"):
            # Workflows registered without a project (before projects, or by the CLI).
            workflows += self.connection.fetchone(
                "SELECT COUNT(*) AS n FROM workflow_registry WHERE name NOT IN"
                " (SELECT workflow FROM workflow_projects)"
            )["n"]
        schedules = (
            self.connection.fetchone(
                "SELECT COUNT(*) AS n FROM schedules WHERE IFNULL(project_id, ?) = ?",
                (default_id, project_id),
            )["n"]
            if _table_exists(self.connection, "schedules")
            else 0
        )
        members = self.connection.fetchone(
            "SELECT COUNT(*) AS n FROM project_members WHERE project_id = ?", (project_id,)
        )["n"]
        return {"workflows": workflows, "schedules": schedules, "members": members}

    def delete(self, key: str) -> None:
        project = self.get(key)
        if project is None:
            raise LookupError(f"Project '{key}' not found.")
        if key == DEFAULT_PROJECT:
            raise ValueError("The Default project cannot be deleted.")
        usage = self.usage(project["id"])
        if usage["workflows"] or usage["schedules"]:
            raise ValueError(
                f"Project '{key}' still has {usage['workflows']} workflow(s) and"
                f" {usage['schedules']} schedule(s); move or delete them first."
            )
        with self.connection.transaction():
            self.connection.execute(
                "DELETE FROM project_members WHERE project_id = ?", (project["id"],)
            )
            self.connection.execute(
                "DELETE FROM node_projects WHERE project_id = ?", (project["id"],)
            )
            self.connection.execute("DELETE FROM projects WHERE id = ?", (project["id"],))

    # -- members --------------------------------------------------------

    def members(self, project_id: int) -> List[Dict[str, Any]]:
        rows = self.connection.fetchall(
            """
            SELECT pm.id, pm.user_id, pm.group_id, r.name AS role, COALESCE(r.title, r.name) AS
                   role_title, u.username, u.full_name, g.name AS group_name
            FROM project_members pm
            JOIN roles r ON r.id = pm.role_id
            LEFT JOIN users u ON u.id = pm.user_id
            LEFT JOIN groups g ON g.id = pm.group_id
            WHERE pm.project_id = ?
            ORDER BY pm.group_id IS NOT NULL, COALESCE(u.username, g.name), r.name
            """,
            (project_id,),
        )
        return [
            {
                "id": row["id"],
                "kind": "group" if row["group_id"] else "user",
                "name": row["group_name"] if row["group_id"] else row["username"],
                "full_name": row["full_name"],
                "role": row["role"],
                "role_title": row["role_title"],
            }
            for row in rows
        ]

    def set_members(self, project_id: int, members: Sequence[Dict[str, str]]) -> None:
        """Replace the members: [{kind: user|group, name, role}]."""

        resolved = []
        for member in members:
            role = self.connection.fetchone(
                "SELECT id, scope FROM roles WHERE name = ?", (member["role"],)
            )
            if role is None:
                raise ValueError(f"No role named '{member['role']}'.")
            if role["scope"] != "project":
                raise ValueError(f"'{member['role']}' is a global role, not a project role.")
            if member["kind"] == "group":
                principal = self.connection.fetchone(
                    "SELECT id FROM groups WHERE name = ?", (member["name"],)
                )
            else:
                principal = self.connection.fetchone(
                    "SELECT id FROM users WHERE username = ?", (member["name"],)
                )
            if principal is None:
                raise ValueError(f"No {member['kind']} named '{member['name']}'.")
            resolved.append((member["kind"], principal["id"], role["id"]))

        now = _now()
        with self.connection.transaction():
            self.connection.execute(
                "DELETE FROM project_members WHERE project_id = ?", (project_id,)
            )
            for kind, principal_id, role_id in dict.fromkeys(resolved):
                column = "group_id" if kind == "group" else "user_id"
                self.connection.execute(
                    f"INSERT OR IGNORE INTO project_members (project_id, {column}, role_id,"
                    " created_at) VALUES (?, ?, ?, ?)",
                    (project_id, principal_id, role_id, now),
                )

    def memberships(self, user_id: int) -> List[Dict[str, Any]]:
        """The user's projects and roles there (directly or through groups)."""

        rows = self.connection.fetchall(
            """
            SELECT p.key, p.name, r.name AS role, COALESCE(r.title, r.name) AS role_title,
                   g.name AS via_group
            FROM project_members pm
            JOIN projects p ON p.id = pm.project_id
            JOIN roles r ON r.id = pm.role_id
            LEFT JOIN groups g ON g.id = pm.group_id
            WHERE pm.user_id = ?
               OR pm.group_id IN (SELECT group_id FROM user_groups WHERE user_id = ?)
            ORDER BY p.name, r.name
            """,
            (user_id, user_id),
        )
        return [dict(row) for row in rows]

    # -- resources ------------------------------------------------------

    def workflow_project(self, workflow: str) -> int:
        row = self.connection.fetchone(
            "SELECT project_id FROM workflow_projects WHERE workflow = ?", (workflow,)
        )
        return int(row["project_id"]) if row else default_project_id(self.connection)

    def set_workflow_project(self, workflow: str, project_id: int) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "INSERT INTO workflow_projects (workflow, project_id) VALUES (?, ?)"
                " ON CONFLICT (workflow) DO UPDATE SET project_id = excluded.project_id",
                (workflow, project_id),
            )

    def forget_workflow(self, workflow: str) -> None:
        with self.connection.transaction():
            self.connection.execute("DELETE FROM workflow_projects WHERE workflow = ?", (workflow,))

    def workflow_projects(self) -> Dict[str, int]:
        return {
            row["workflow"]: int(row["project_id"])
            for row in self.connection.fetchall(
                "SELECT workflow, project_id FROM workflow_projects"
            )
        }

    def node_access(self, node: str) -> Dict[str, Any]:
        row = self.connection.fetchone("SELECT scope FROM nodes WHERE name = ?", (node,))
        scope = row["scope"] if row and row["scope"] else "shared"
        projects = [
            int(item["project_id"])
            for item in self.connection.fetchall(
                "SELECT project_id FROM node_projects WHERE node = ?", (node,)
            )
        ]
        return {"scope": scope, "projects": projects}

    def node_available(self, node: str, project_id: int) -> bool:
        access = self.node_access(node)
        return access["scope"] != "assigned" or project_id in access["projects"]

    def set_node_access(self, node: str, scope: str, project_ids: Sequence[int]) -> None:
        if scope not in ("shared", "assigned"):
            raise ValueError("A node is 'shared' with every project or 'assigned' to some.")
        with self.connection.transaction():
            self.connection.execute("UPDATE nodes SET scope = ? WHERE name = ?", (scope, node))
            self.connection.execute("DELETE FROM node_projects WHERE node = ?", (node,))
            for project_id in dict.fromkeys(project_ids):
                self.connection.execute(
                    "INSERT INTO node_projects (node, project_id) VALUES (?, ?)",
                    (node, project_id),
                )
