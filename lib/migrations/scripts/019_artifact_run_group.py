"""Store run identifiers for grouping generated artifacts."""

from lib.database.connection import DatabaseConnection
from lib.migrations.base import BaseMigration


class ArtifactRunGroupMigration(BaseMigration):
    VERSION = 19
    DESCRIPTION = "Group generated artifacts by execution."

    def upgrade(self, connection: DatabaseConnection) -> None:
        from lib.artifacts.store import ensure_artifacts_schema

        ensure_artifacts_schema(connection)
