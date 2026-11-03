"""
Project scoped schedule names: the same name may exist in several projects.

schedules is rebuilt to be unique on (project_id, name) instead of name.
Schedules from before projects (no project_id) move to the Default project.
Ids are kept, so schedule_runs still point at their schedules.
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


def _name_is_globally_unique(connection: DatabaseConnection) -> bool:
    """Whether schedules still has a unique index on name alone."""

    for index in connection.fetchall("PRAGMA index_list(schedules)"):
        if not index["unique"]:
            continue
        columns = connection.fetchall(f"PRAGMA index_info({index['name']})")
        if [column["name"] for column in columns] == ["name"]:
            return True
    return False


class ProjectScopedSchedulesMigration(BaseMigration):
    VERSION = 27
    DESCRIPTION = "Make schedule names unique per project."

    def upgrade(self, connection: DatabaseConnection) -> None:
        from lib.authorization.projects import default_project_id

        if not _table_exists(connection, "schedules"):
            return
        # New installs are created with the per-project constraint.
        if not _name_is_globally_unique(connection):
            return

        default_id = default_project_id(connection)
        owner = "project_id" if "project_id" in _columns(connection, "schedules") else "NULL"

        connection.execute("""
            CREATE TABLE schedules_scoped
            (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id       INTEGER NOT NULL,
                name             TEXT NOT NULL,
                description      TEXT NOT NULL DEFAULT '',
                kind             TEXT NOT NULL
                    CHECK (kind IN ('workflow', 'plugin')),
                target           TEXT NOT NULL,
                cron             TEXT NOT NULL,
                timezone         TEXT NOT NULL DEFAULT 'UTC',
                node             TEXT NOT NULL DEFAULT 'local',
                parameters       TEXT NOT NULL DEFAULT '{}',
                enabled          INTEGER NOT NULL DEFAULT 1,
                user_id          INTEGER NOT NULL,
                username         TEXT NOT NULL,
                created_at       TEXT NOT NULL,
                updated_at       TEXT NOT NULL,
                next_run_at      TEXT,
                last_run_at      TEXT,
                UNIQUE (project_id, name)
            )
            """)
        connection.execute(
            f"""
            INSERT INTO schedules_scoped
            (id, project_id, name, description, kind, target, cron, timezone, node, parameters,
             enabled, user_id, username, created_at, updated_at, next_run_at, last_run_at)
            SELECT id, IFNULL({owner}, ?), name, description, kind, target, cron, timezone, node,
                   parameters, enabled, user_id, username, created_at, updated_at, next_run_at,
                   last_run_at
            FROM schedules
            """,
            (default_id,),
        )
        connection.execute("DROP TABLE schedules")
        connection.execute("ALTER TABLE schedules_scoped RENAME TO schedules")
