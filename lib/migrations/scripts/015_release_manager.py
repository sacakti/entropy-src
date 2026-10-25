"""Add project release management and promotion batches."""

from lib.database.connection import DatabaseConnection
from lib.migrations.base import BaseMigration


class ReleaseManagerMigration(BaseMigration):
    VERSION = 15
    DESCRIPTION = "Add project releases and workflow promotions."

    def upgrade(self, connection: DatabaseConnection) -> None:
        from lib.releases.store import ensure_releases_schema
        from lib.authorization.initializer import AuthorizationInitializer

        ensure_releases_schema(connection)
        AuthorizationInitializer(connection).reconcile()
