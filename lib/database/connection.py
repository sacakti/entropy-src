
"""
Database connection.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Iterator, Optional


class _LockedCursor:
    """Serialize cursor operations against the shared SQLite connection."""

    def __init__(self, cursor: sqlite3.Cursor, lock: RLock) -> None:
        self._cursor = cursor
        self._lock = lock

    def fetchone(self):
        with self._lock:
            return self._cursor.fetchone()

    def fetchmany(self, size: Optional[int] = None):
        with self._lock:
            if size is None:
                return self._cursor.fetchmany()
            return self._cursor.fetchmany(size)

    def fetchall(self):
        with self._lock:
            return self._cursor.fetchall()

    def close(self) -> None:
        with self._lock:
            self._cursor.close()

    def __iter__(self):
        return self

    def __next__(self):
        with self._lock:
            return next(self._cursor)

    @property
    def description(self):
        return self._cursor.description

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    @property
    def arraysize(self) -> int:
        return self._cursor.arraysize


class DatabaseConnection:
    """
    SQLite database connection shared across application threads.

    Operations are serialized using a reentrant lock. Transactions hold
    the lock for their complete duration so another thread cannot execute
    statements inside the active transaction.
    """

    def __init__(self, database: Path) -> None:
        self._database = database
        self._connection: Optional[sqlite3.Connection] = None
        self._lock = RLock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open the database connection if it is not already open."""

        with self._lock:
            if self._connection is not None:
                return

            self._connection = sqlite3.connect(
                self._database,
                check_same_thread=False,
            )
            self._connection.row_factory = sqlite3.Row

    def close(self) -> None:
        """Close the database connection."""

        with self._lock:
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
    ) -> _LockedCursor:
        """Execute SQL and return a synchronized cursor."""

        with self._lock:
            cursor = self.connection.execute(sql, parameters)
            return _LockedCursor(cursor, self._lock)

    def executescript(self, script: str) -> _LockedCursor:
        """Execute multiple SQL statements."""

        with self._lock:
            cursor = self.connection.executescript(script)
            return _LockedCursor(cursor, self._lock)

    # ------------------------------------------------------------------
    # Transaction
    # ------------------------------------------------------------------

    @contextmanager
    def transaction(self) -> Iterator[DatabaseConnection]:
        """Commit on success and roll back on failure."""

        with self._lock:
            try:
                yield self
                self.commit()
            except Exception:
                self.rollback()
                raise

    def commit(self) -> None:
        """Commit the active transaction."""

        with self._lock:
            self.connection.commit()

    def rollback(self) -> None:
        """Roll back the active transaction."""

        with self._lock:
            self.connection.rollback()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def connection(self) -> sqlite3.Connection:
        """Return the underlying active SQLite connection."""

        with self._lock:
            if self._connection is None:
                self.open()

            assert self._connection is not None
            return self._connection

    @property
    def database(self) -> Path:
        """Return the database file path."""

        return self._database

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def fetchone(self, sql: str, parameters: tuple = ()):
        """Execute a query and return one row."""

        with self._lock:
            cursor = self.execute(sql, parameters)
            try:
                return cursor.fetchone()
            finally:
                cursor.close()

    def fetchall(self, sql: str, parameters: tuple = ()):
        """Execute a query and return all rows."""

        with self._lock:
            cursor = self.execute(sql, parameters)
            try:
                return cursor.fetchall()
            finally:
                cursor.close()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def table_exists(self, table: str) -> bool:
        """Return True if a table exists."""

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
