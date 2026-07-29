"""
SQLite connection.
"""

import sqlite3
from pathlib import Path
from sqlite3 import Connection
from typing import Optional


class DatabaseConnection:

    def __init__(
        self,
        database: Path,
    ):
        self._database = database
        self._connection: Optional[Connection] = None

    @property
    def connection(self) -> Connection:

        if self._connection is None:

            self._connection = sqlite3.connect(self._database)

            self._connection.row_factory = sqlite3.Row

        assert self._connection is not None
        return self._connection

    def close(self) -> None:

        if self._connection:

            self._connection.close()
            self._connection = None
