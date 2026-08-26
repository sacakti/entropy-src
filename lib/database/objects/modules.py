"""
Authorization modules database table.
"""

from __future__ import annotations

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class ModulesTable(DatabaseObject):
    """
    Stores Entropy authorization modules.
    """

    NAME = "modules"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """
        Create the modules table.
        """

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS modules
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                name TEXT NOT NULL UNIQUE,

                description TEXT
            )
            """
        )
