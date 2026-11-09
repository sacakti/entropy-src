"""Add the project knowledge base."""

from lib.database.connection import DatabaseConnection
from lib.migrations.base import BaseMigration


class KnowledgeBaseMigration(BaseMigration):
    VERSION = 32
    DESCRIPTION = "Add the project knowledge base."

    def upgrade(self, connection: DatabaseConnection) -> None:
        from lib.knowledge.store import ensure_knowledge_schema

        ensure_knowledge_schema(connection)
        from lib.authorization.initializer import AuthorizationInitializer

        # The new permissions, and the built-in roles that hold them.
        AuthorizationInitializer(connection).reconcile()
