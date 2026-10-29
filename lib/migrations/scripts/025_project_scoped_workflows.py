"""
Project scoped workflow names: the same name may exist in several projects.

workflow_registry gets project_id (from the legacy workflow_projects map,
else the Default project) and is unique on (project_id, name). Run alerts
and kept definition versions of workflows are re-keyed to
"<project_id>/<name>" (see lib.authorization.projects.workflow_key).
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


class ProjectScopedWorkflowsMigration(BaseMigration):
    VERSION = 25
    DESCRIPTION = "Make workflow names unique per project."

    def upgrade(self, connection: DatabaseConnection) -> None:
        from lib.authorization.projects import default_project_id

        if not _table_exists(connection, "workflow_registry"):
            return
        if "project_id" in _columns(connection, "workflow_registry"):
            return

        default_id = default_project_id(connection)
        owners = (
            "(SELECT wp.project_id FROM workflow_projects wp WHERE wp.workflow = r.name)"
            if _table_exists(connection, "workflow_projects")
            else "NULL"
        )

        connection.execute(
            """
            CREATE TABLE workflow_registry_scoped
            (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id      INTEGER NOT NULL,
                name            TEXT NOT NULL,
                version         TEXT NOT NULL,
                description     TEXT,
                definition      TEXT NOT NULL,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL,
                UNIQUE (project_id, name)
            )
            """
        )
        connection.execute(
            f"""
            INSERT INTO workflow_registry_scoped
            (id, project_id, name, version, description, definition, created_at, updated_at)
            SELECT r.id, IFNULL({owners}, ?), r.name, r.version, r.description,
                   r.definition, r.created_at, r.updated_at
            FROM workflow_registry r
            """,
            (default_id,),
        )
        connection.execute("DROP TABLE workflow_registry")
        connection.execute("ALTER TABLE workflow_registry_scoped RENAME TO workflow_registry")

        # Shared tables keyed by the bare name now use "<project_id>/<name>".
        scoped = (
            "(SELECT CAST(r.project_id AS TEXT) || '/' || r.name FROM workflow_registry r"
            " WHERE r.name = {column})"
        )
        if _table_exists(connection, "run_alerts"):
            connection.execute(
                "UPDATE run_alerts SET target = IFNULL("
                + scoped.format(column="run_alerts.target")
                + ", CAST(? AS TEXT) || '/' || target) WHERE kind = 'workflow'",
                (default_id,),
            )
        if _table_exists(connection, "definition_history"):
            connection.execute(
                "UPDATE definition_history SET name = IFNULL("
                + scoped.format(column="definition_history.name")
                + ", CAST(? AS TEXT) || '/' || name) WHERE kind = 'workflow'",
                (default_id,),
            )
