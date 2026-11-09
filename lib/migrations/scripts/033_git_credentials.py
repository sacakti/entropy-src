"""Per-user Git commit identity and HTTPS credentials."""

from lib.database.connection import DatabaseConnection
from lib.migrations.base import BaseMigration


class GitCredentialsMigration(BaseMigration):
    VERSION = 33
    DESCRIPTION = "Add per-user Git identity and credentials."

    def upgrade(self, connection: DatabaseConnection) -> None:
        from lib.git_repositories.remote import ensure_git_credentials_schema

        ensure_git_credentials_schema(connection)
