"""Add release tags, artifact links, global environments and housekeeping."""

from lib.database.connection import DatabaseConnection
from lib.migrations.base import BaseMigration


class ReleaseManagerEnhancementsMigration(BaseMigration):
    VERSION = 22
    DESCRIPTION = "Add release environments, artifact links and archive support."

    def upgrade(self, connection: DatabaseConnection) -> None:
        from lib.releases.store import ensure_releases_schema

        ensure_releases_schema(connection)
