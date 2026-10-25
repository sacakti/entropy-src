"""Support importing local and remote Git repositories."""

from lib.database.connection import DatabaseConnection
from lib.migrations.base import BaseMigration


class GitRepositorySourcesMigration(BaseMigration):
    VERSION = 21
    DESCRIPTION = "Add local path and remote sources to Git repositories."

    def upgrade(self, connection: DatabaseConnection) -> None:
        from lib.git_repositories.store import ensure_git_repositories_schema

        ensure_git_repositories_schema(connection)
