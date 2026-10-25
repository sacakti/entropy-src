"""Add searchable tags to project artifacts."""

from lib.database.connection import DatabaseConnection
from lib.migrations.base import BaseMigration


class ArtifactTagsMigration(BaseMigration):
    VERSION = 17
    DESCRIPTION = "Add tags to project artifacts."

    def upgrade(self, connection: DatabaseConnection) -> None:
        columns = {row["name"] for row in connection.fetchall("PRAGMA table_info(artifacts)")}
        if "tags" not in columns:
            connection.execute("ALTER TABLE artifacts ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'")
