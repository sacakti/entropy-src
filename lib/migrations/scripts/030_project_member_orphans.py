"""
Remove project memberships of users and groups that no longer exist.

Deleting a user or group used to leave these rows behind (foreign keys are not enforced).
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


class ProjectMemberOrphansMigration(BaseMigration):
    VERSION = 30
    DESCRIPTION = "Remove project memberships of deleted users and groups."

    def upgrade(self, connection: DatabaseConnection) -> None:
        if not all(
            _table_exists(connection, name) for name in ("project_members", "users", "groups")
        ):
            return

        connection.execute(
            "DELETE FROM project_members"
            " WHERE (user_id IS NOT NULL AND user_id NOT IN (SELECT id FROM users))"
            " OR (group_id IS NOT NULL AND group_id NOT IN (SELECT id FROM groups))"
        )
