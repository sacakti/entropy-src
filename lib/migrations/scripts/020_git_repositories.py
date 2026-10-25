"""Create Entropy-managed Git repository metadata."""

from lib.database.connection import DatabaseConnection
from lib.migrations.base import BaseMigration


class GitRepositoriesMigration(BaseMigration):
    VERSION = 20
    DESCRIPTION = "Add user and project scoped Git repositories."

    def upgrade(self, connection: DatabaseConnection) -> None:
        from lib.git_repositories.store import ensure_git_repositories_schema

        ensure_git_repositories_schema(connection)
