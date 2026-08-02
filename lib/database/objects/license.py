"""
License table.
"""

from lib.database.connection import DatabaseConnection

from lib.database.base import DatabaseObject


class LicensesTable(DatabaseObject):

    NAME = "licenses"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS licenses
            (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                license_key     TEXT UNIQUE,
                edition         TEXT,
                customer        TEXT,
                email           TEXT,
                issued_at       TEXT,
                expires_at      TEXT,
                activated_at    TEXT,
                status          TEXT,
                signature       TEXT
            )
            """
        )
