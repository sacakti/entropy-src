"""
SQLite connection.
"""

import sqlite3
from pathlib import Path


class DatabaseConnection:

    def __init__(
        self,
        database: Path,
    ):
        self._database = database
        self._connection = None

    @property
    def connection(self):

        if self._connection is None:

            self._connection = sqlite3.connect(
                self._database
            )

            self._connection.row_factory = sqlite3.Row

        return self._connection

    def close(self):

        if self._connection:

            self._connection.close()
            self._connection = None
