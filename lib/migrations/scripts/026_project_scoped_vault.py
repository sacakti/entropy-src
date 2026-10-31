"""
Project scoped Vault: namespaces belong to a project and access comes only
from project roles.

- vault_namespaces gets project_id (from the vault_namespace_projects map,
  else the Default project) and is unique on (project_id, name). The
  visibility column goes; owner_user_id stays as "created by" and no longer
  blocks deleting that user.
- Per-user namespace grants (vault_namespace_access) are dropped, and so is
  the global "Vault user" role. Vault permissions are removed from every other
  global role and from direct user grants: the Administrator role keeps
  everything, everyone else gets Vault access from a project role.

Entries keep their namespace ids, so no secret is re-encrypted or moved.
"""

from lib.database.connection import DatabaseConnection
from lib.migrations.base import BaseMigration


def _table_exists(connection: DatabaseConnection, table: str) -> bool:
    return (
        connection.fetchone(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        )
        is not None
    )


def _columns(connection: DatabaseConnection, table: str) -> set:
    return {row["name"] for row in connection.fetchall(f"PRAGMA table_info({table})")}


class ProjectScopedVaultMigration(BaseMigration):
    VERSION = 26
    DESCRIPTION = "Make Vault namespaces project scoped; Vault access from project roles only."

    def upgrade(self, connection: DatabaseConnection) -> None:
        if _table_exists(connection, "vault_namespaces") and "project_id" not in _columns(
            connection, "vault_namespaces"
        ):
            self._rebuild_namespaces(connection)

        if _table_exists(connection, "vault_namespace_access"):
            connection.execute("DROP TABLE vault_namespace_access")

        if _table_exists(connection, "vault_namespace_projects"):
            connection.execute("DROP TABLE vault_namespace_projects")

        if _table_exists(connection, "roles"):
            self._remove_global_vault_access(connection)

    # ------------------------------------------------------------------
    # Namespaces
    # ------------------------------------------------------------------

    @staticmethod
    def _rebuild_namespaces(connection: DatabaseConnection) -> None:
        from lib.authorization.projects import default_project_id

        # Dropping the old table must not cascade to vault_entries. Entropy
        # never enables foreign keys, and the pragma cannot change inside the
        # migration's transaction, so refuse rather than lose secrets.
        if connection.fetchone("PRAGMA foreign_keys")[0]:
            raise RuntimeError(
                "Foreign keys are enabled; the Vault namespace table cannot be rebuilt safely."
            )

        default_id = default_project_id(connection)
        owners = (
            "(SELECT p.project_id FROM vault_namespace_projects p WHERE p.namespace_id = n.id)"
            if _table_exists(connection, "vault_namespace_projects")
            else "NULL"
        )

        connection.execute(
            """
            CREATE TABLE vault_namespaces_scoped
            (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id    INTEGER NOT NULL,
                name          TEXT NOT NULL,
                owner_user_id INTEGER
                    REFERENCES users (id) ON DELETE SET NULL,
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL,
                UNIQUE (project_id, name)
            )
            """
        )
        connection.execute(
            f"""
            INSERT INTO vault_namespaces_scoped
            (id, project_id, name, owner_user_id, created_at, updated_at)
            SELECT n.id, IFNULL({owners}, ?), n.name, n.owner_user_id,
                   n.created_at, n.updated_at
            FROM vault_namespaces n
            """,
            (default_id,),
        )
        connection.execute("DROP TABLE vault_namespaces")
        connection.execute("ALTER TABLE vault_namespaces_scoped RENAME TO vault_namespaces")

    # ------------------------------------------------------------------
    # Roles and grants
    # ------------------------------------------------------------------

    @staticmethod
    def _remove_global_vault_access(connection: DatabaseConnection) -> None:
        role = connection.fetchone("SELECT id FROM roles WHERE name = 'vault-user'")

        if role is not None:
            for table in ("user_roles", "group_roles", "role_permissions"):
                if _table_exists(connection, table):
                    connection.execute(f"DELETE FROM {table} WHERE role_id = ?", (role["id"],))
            if _table_exists(connection, "project_members"):
                connection.execute("DELETE FROM project_members WHERE role_id = ?", (role["id"],))
            connection.execute("DELETE FROM roles WHERE id = ?", (role["id"],))

        if not _table_exists(connection, "permissions"):
            return

        vault = "(SELECT id FROM permissions WHERE name LIKE 'vault.%')"

        if _table_exists(connection, "user_privileges"):
            connection.execute(f"DELETE FROM user_privileges WHERE permission_id IN {vault}")

        if _table_exists(connection, "role_permissions"):
            # Global roles only (project roles keep their Vault permissions);
            # the Administrator role is given every permission at startup.
            scope = (
                "AND role_id IN (SELECT id FROM roles WHERE IFNULL(scope, 'global') = 'global'"
                " AND name <> 'admin')"
                if "scope" in _columns(connection, "roles")
                else "AND role_id IN (SELECT id FROM roles WHERE name <> 'admin')"
            )
            connection.execute(
                f"DELETE FROM role_permissions WHERE permission_id IN {vault} {scope}"
            )
