"""Add project-scoped artifact inventory."""

from lib.database.connection import DatabaseConnection
from lib.migrations.base import BaseMigration


class ArtifactsMigration(BaseMigration):
    VERSION = 16
    DESCRIPTION = "Add project release artifacts."

    def upgrade(self, connection: DatabaseConnection) -> None:
        from lib.artifacts.store import ensure_artifacts_schema
        from lib.authorization.initializer import AuthorizationInitializer

        ensure_artifacts_schema(connection)
        AuthorizationInitializer(connection).reconcile()
