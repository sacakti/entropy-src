"""Add messages administrators send to everyone through Vision."""

from lib.database.connection import DatabaseConnection
from lib.migrations.base import BaseMigration


class VisionBroadcastsMigration(BaseMigration):
    VERSION = 28
    DESCRIPTION = "Add Vision broadcasts."

    def upgrade(self, connection: DatabaseConnection) -> None:
        from lib.vision.broadcasts import ensure_broadcasts_schema

        ensure_broadcasts_schema(connection)
