"""
Database connection.
"""

from __future__ import annotations

from contextlib import contextmanager
import sqlite3
from pathlib import Path
from sqlite3 import Cursor, Row
from typing import Iterator


class DatabaseConnection:
    """
    SQLite database connection.

    This class owns the underlying SQLite connection and exposes
    common database operations used throughout the framework.
    """

    def __init__(
        self,
        database: Path,
    ) -> None:

        self._database = database

        self._connection: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """
        Open the database connection.
        """

        if self._connection is not None:
            return

        self._connection = sqlite3.connect(
            self._database,
        )

        self._connection.row_factory = Row

    def close(self) -> None:
        """
        Close the database connection.
        """

        if self._connection is None:
            return

        self._connection.close()

        self._connection = None

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        sql: str,
        parameters: tuple = (),
    ) -> Cursor:
        """
        Execute a SQL statement.
        """

        return self.connection.execute(
            sql,
            parameters,
        )

    def executescript(
        self,
        script: str,
    ) -> Cursor:
        """
        Execute multiple SQL statements.
        """

        return self.connection.executescript(
            script,
        )

    # ------------------------------------------------------------------
    # Transaction
    # ------------------------------------------------------------------

    @contextmanager
    def transaction(
        self,
    ) -> Iterator["DatabaseConnection"]:
        """
        Execute operations inside a transaction.

        Commits on success and rolls back on failure.
        """

        try:

            yield self

            self.commit()

        except Exception:

            self.rollback()

            raise

    def commit(self) -> None:
        """
        Commit the active transaction.
        """

        self.connection.commit()

    def rollback(self) -> None:
        """
        Roll back the active transaction.
        """

        self.connection.rollback()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def connection(self) -> sqlite3.Connection:
        """
        Return the active SQLite connection.

        The connection is opened lazily on first access.
        """

        if self._connection is None:

            self.open()

        assert self._connection is not None

        return self._connection

    @property
    def database(self) -> Path:
        """
        Database file.
        """

        return self._database

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def fetchone(
        self,
        sql: str,
        parameters: tuple = (),
    ):
        """
        Execute a query and return a single row.
        """

        cursor = self.execute(
            sql,
            parameters,
        )

        return cursor.fetchone()


    def fetchall(
        self,
        sql: str,
        parameters: tuple = (),
    ):
        """
        Execute a query and return all rows.
        """

        cursor = self.execute(
            sql,
            parameters,
        )

        return cursor.fetchall()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def table_exists(
        self,
        table: str,
    ) -> bool:
        """
        Return True if a table exists.
        """

        return (
            self.fetchone(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table'
                AND name = ?
                """,
                (table,),
            )
            is not None
        )
