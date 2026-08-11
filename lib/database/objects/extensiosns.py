"""
Extension registry table.
"""

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class ExtensionsTable(DatabaseObject):
    """
    Stores extensions registered with Entropy.
    """

    NAME = "extensions"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS extensions
            (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,

                name            TEXT NOT NULL UNIQUE,

                version         TEXT NOT NULL,

                wheel           TEXT NOT NULL,

                installer       TEXT NOT NULL,

                installed_at    TEXT NOT NULL,

                python_tag      TEXT NOT NULL,

                platform_tag    TEXT NOT NULL,

                dist_info       TEXT NOT NULL DEFAULT '',

                entry_points    TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
