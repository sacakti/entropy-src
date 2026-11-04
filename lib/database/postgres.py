"""
A PostgreSQL connection with the interface of DatabaseConnection.

The rest of Entropy keeps working with one connection object whichever engine
is in use, so this class behaves the way the SQLite connection does:

- one connection shared across threads, serialized by a reentrant lock;
- a transaction starts at the first write and ends with commit or rollback;
- rows can be read by name and by position;
- a failed statement does not end the transaction it ran in;
- values are compared loosely, so a number can be matched against a text column.

Two things differ, because the server is across a network, not a file away. Reads
outside a transaction use a small pool, so a slow page does not hold up the others;
writes stay one transaction at a time. And checks that the schema is as expected,
which the application repeats constantly, are answered from memory once known.

The driver is imported only here, so SQLite installations never need it.
"""

from __future__ import annotations

import queue
import re
import threading
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from lib.database.connection import DatabaseConnection
from lib.database.dialect import Statement, is_schema_change, split_statements, translate
from lib.database.exceptions import DatabaseException

_WRITES = ("INSERT", "UPDATE", "DELETE", "REPLACE")
_SCHEMA_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_READERS = 4
_ENSURE = re.compile(r"\s*CREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX)\s+IF\s+NOT\s+EXISTS\b", re.I)
_SCHEMA_QUERY = re.compile(r"\s*PRAGMA\s+table_info\b|.*\bsqlite_(?:master|schema)\b", re.I | re.S)


class Row:
    """A result row, read like sqlite3.Row: by position or by column name."""

    __slots__ = ("_names", "_values")

    def __init__(self, names: Sequence[str], values: Sequence[Any]) -> None:
        self._names = names
        self._values = tuple(values)

    def keys(self) -> List[str]:
        return list(self._names)

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            wanted = key.lower()
            for index, name in enumerate(self._names):
                if name.lower() == wanted:
                    return self._values[index]
            raise IndexError(f"No item with that key: {key}")
        return self._values[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Row):
            return self._names == other._names and self._values == other._values
        return NotImplemented

    def __hash__(self) -> int:
        return hash((tuple(self._names), self._values))

    def __repr__(self) -> str:
        return f"Row({dict(zip(self._names, self._values))!r})"


def _row_factory(cursor: Any) -> Any:
    names = [column.name for column in cursor.description or ()]

    def make(values: Sequence[Any]) -> Row:
        return Row(names, values)

    return make


def number_from_numeric(value: Decimal) -> Any:
    """SUM and AVG give NUMERIC here; Entropy expects int or float, as from SQLite."""

    return int(value) if value == value.to_integral_value() else float(value)


def _register_adapters(adapters: Any) -> None:
    """Send numbers untyped, so the server matches them to any column, as SQLite does."""

    from psycopg.adapt import Dumper, Loader

    class UntypedNumber(Dumper):
        oid = 0

        def dump(self, obj: Any) -> bytes:
            return str(obj).encode("ascii")

    class UntypedFlag(Dumper):
        oid = 0

        def dump(self, obj: Any) -> bytes:
            return b"1" if obj else b"0"

    class PlainNumber(Loader):
        def load(self, data: Any) -> Any:
            return number_from_numeric(Decimal(bytes(data).decode("ascii")))

    adapters.register_dumper(int, UntypedNumber)
    adapters.register_dumper(float, UntypedNumber)
    adapters.register_dumper(bool, UntypedFlag)
    adapters.register_loader("numeric", PlainNumber)


class _Cursor:
    """The result of one statement; thread-safe, and tolerant of statements without rows."""

    def __init__(self, cursor: Any, lock: Any, statement: Statement) -> None:
        self._cursor = cursor
        self._lock = lock
        self.lastrowid: Optional[int] = None
        self.rowcount: int = cursor.rowcount
        if statement.returning and cursor.description is not None:
            # The generated key answers lastrowid; an INSERT itself has no rows to read.
            rows = cursor.fetchall()
            if rows:
                self.lastrowid = rows[-1][0]
            self._has_rows = False
        else:
            self._has_rows = cursor.description is not None

    @property
    def description(self) -> Any:
        return self._cursor.description if self._has_rows else None

    def fetchone(self) -> Any:
        with self._lock:
            return self._cursor.fetchone() if self._has_rows else None

    def fetchmany(self, size: Optional[int] = None) -> List[Any]:
        with self._lock:
            if not self._has_rows:
                return []
            rows = self._cursor.fetchmany(size) if size is not None else self._cursor.fetchmany()
            return list(rows)

    def fetchall(self) -> List[Any]:
        with self._lock:
            return list(self._cursor.fetchall()) if self._has_rows else []

    def close(self) -> None:
        with self._lock:
            self._cursor.close()

    def __iter__(self) -> _Cursor:
        return self

    def __next__(self) -> Any:
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row


def _reads(sql: str) -> bool:
    """A statement that only reads: it needs no transaction and can use the pool."""

    return re.match(r"\s*(?:SELECT|PRAGMA)\b", sql, re.I) is not None


class _Remembered:
    """Rows already known, read like the result of a statement."""

    lastrowid = None
    rowcount = -1

    def __init__(self, rows: Sequence[Any] = ()) -> None:
        self._rows = list(rows)
        self.description = None

    def fetchone(self) -> Any:
        return self._rows.pop(0) if self._rows else None

    def fetchmany(self, size: Optional[int] = None) -> List[Any]:
        count = 1 if size is None else size
        taken, self._rows = self._rows[:count], self._rows[count:]
        return taken

    def fetchall(self) -> List[Any]:
        taken, self._rows = self._rows, []
        return taken

    def close(self) -> None:
        self._rows = []

    def __iter__(self) -> _Remembered:
        return self

    def __next__(self) -> Any:
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row


class _Catalog:
    """What the translator needs to know about tables; remembered until the schema changes."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection
        self._columns: Dict[str, List[str]] = {}
        self._identity: Dict[str, Optional[str]] = {}
        self._keys: Dict[str, List[str]] = {}

    def clear(self) -> None:
        self._columns.clear()
        self._identity.clear()
        self._keys.clear()

    def _load(self, table: str) -> None:
        rows = self._connection.raw_rows(
            "SELECT column_name, is_identity FROM information_schema.columns"
            " WHERE table_schema = current_schema() AND table_name = %s"
            " ORDER BY ordinal_position",
            (table,),
        )
        self._columns[table] = [row[0] for row in rows]
        self._identity[table] = next((row[0] for row in rows if row[1] == "YES"), None)

    def columns(self, table: str) -> List[str]:
        if table not in self._columns:
            self._load(table)
        return self._columns[table]

    def identity(self, table: str) -> Optional[str]:
        if table not in self._identity:
            self._load(table)
        return self._identity[table]

    def conflict_key(self, table: str) -> List[str]:
        """The primary key, or else the first unique index on plain columns."""

        if table not in self._keys:
            rows = self._connection.raw_rows(
                "SELECT i.indexrelid, a.attname FROM pg_index i"
                " JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)"
                " WHERE i.indrelid = to_regclass(%s) AND i.indisunique AND i.indexprs IS NULL"
                " ORDER BY i.indisprimary DESC, i.indexrelid, a.attnum",
                (table,),
            )
            first = rows[0][0] if rows else None
            self._keys[table] = [row[1] for row in rows if row[0] == first]
        return self._keys[table]


class PostgresConnection(DatabaseConnection):
    """A PostgreSQL database behind the interface of DatabaseConnection."""

    def __init__(self, settings: Dict[str, Any], database: Path) -> None:
        super().__init__(database)
        schema = str(settings.get("schema") or "")
        if schema and not _SCHEMA_NAME.match(schema):
            raise DatabaseException("The schema name has letters, digits and underscores only.")
        self._settings = settings
        self._schema = schema
        self._active = False
        self._owner: Optional[int] = None
        self.catalog = _Catalog(self)
        self._readers: queue.LifoQueue = queue.LifoQueue()
        self._reader_count = 0
        self._reader_lock = threading.Lock()
        self._generation = 0
        self._ensured: set = set()
        self._known_rows: Dict[Any, List[Any]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _driver(self) -> Any:
        try:
            import psycopg
        except ImportError:
            raise DatabaseException(
                "The PostgreSQL driver (psycopg) is not installed, so Entropy cannot reach its "
                "database."
            ) from None
        return psycopg

    def _connect(self) -> Any:
        psycopg = self._driver()
        options = "-c timezone=UTC"
        if self._schema:
            options += f" -c search_path={self._schema}"
        connection = psycopg.connect(
            host=self._settings["host"],
            port=int(self._settings["port"]),
            dbname=self._settings["database"],
            user=self._settings.get("username") or None,
            password=self._settings.get("password") or None,
            sslmode="require" if self._settings.get("ssl") else "prefer",
            connect_timeout=10,
            options=options,
            # Statements start a transaction only when they write, as with SQLite.
            autocommit=True,
            prepare_threshold=None,
            row_factory=_row_factory,
        )
        _register_adapters(connection.adapters)
        return connection

    def open(self) -> None:
        """Connect, unless already connected."""

        with self._lock:
            if self._connection is not None:
                return
            self._connection = self._connect()
            self._active = False
            self._owner = None

    def close(self) -> None:
        """Close every connection; an unfinished transaction is abandoned."""

        with self._lock:
            self._close_readers()
            if self._connection is None:
                return
            self._connection.close()
            self._connection = None
            self._active = False
            self._owner = None
            self.catalog.clear()
            self._forget_schema()

    def _close_readers(self) -> None:
        with self._reader_lock:
            # A reader still in use is closed when it is given back.
            self._generation += 1
            while True:
                try:
                    self._readers.get_nowait().close()
                except queue.Empty:
                    break
                self._reader_count -= 1

    def _forget_schema(self) -> None:
        self._ensured.clear()
        self._known_rows.clear()

    def ensure_schema(self) -> None:
        """Create the configured schema if it is not there yet."""

        if self._schema:
            self.raw_execute(f'CREATE SCHEMA IF NOT EXISTS "{self._schema}"')

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(self, sql: str, parameters: Iterable[Any] = ()) -> Any:
        """Translate and execute one statement."""

        values = tuple(parameters)
        if _ENSURE.match(sql) and sql in self._ensured:
            return _Remembered()
        key = (sql, values) if _SCHEMA_QUERY.match(sql) else None
        if key is not None and key in self._known_rows:
            return _Remembered(self._known_rows[key])

        statement = None
        if not self._in_own_transaction():
            statement = translate(sql) if _reads(sql) else None
        if statement is not None:
            cursor = self._read(statement, values)
        else:
            with self._lock:
                _ = self.connection  # connect first: translating may read the catalog
                statement = translate(sql, self.catalog)
                cursor = self._run(sql, statement, values)

        if _ENSURE.match(sql):
            self._ensured.add(sql)
        elif key is not None:
            # Only what exists: a table that is missing may be created by another process.
            rows = cursor.fetchall()
            if rows:
                self._known_rows[key] = rows
            return _Remembered(rows)
        return cursor

    def fetchone(self, sql: str, parameters: Iterable[Any] = ()) -> Any:
        """One row. Unlike SQLite's connection this takes no lock: reads run side by side."""

        cursor = self.execute(sql, parameters)
        try:
            return cursor.fetchone()
        finally:
            cursor.close()

    def fetchall(self, sql: str, parameters: Iterable[Any] = ()) -> Any:
        """All rows. Unlike SQLite's connection this takes no lock: reads run side by side."""

        cursor = self.execute(sql, parameters)
        try:
            return cursor.fetchall()
        finally:
            cursor.close()

    def _in_own_transaction(self) -> bool:
        return self._active and self._owner == threading.get_ident()

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def _borrow(self) -> tuple[Any, int]:
        with self._reader_lock:
            generation = self._generation
            try:
                return self._readers.get_nowait(), generation
            except queue.Empty:
                create = self._reader_count < _READERS
                if create:
                    self._reader_count += 1
        if not create:
            return self._readers.get(), generation
        try:
            return self._connect(), generation
        except Exception:
            with self._reader_lock:
                self._reader_count -= 1
            raise

    def _give_back(self, reader: Any, generation: int) -> None:
        with self._reader_lock:
            if generation == self._generation and not reader.closed:
                self._readers.put(reader)
                return
            self._reader_count -= 1
        reader.close()

    def _read(self, statement: Statement, parameters: tuple) -> _Cursor:
        """A read outside any transaction, beside whatever else is running."""

        reader, generation = self._borrow()
        try:
            try:
                cursor = reader.cursor().execute(statement.text, parameters)
            except Exception as error:
                if not self._lost(error, reader):
                    raise
                # The server restarted or dropped an idle connection: start over.
                reader.close()
                self._give_back(reader, generation)
                reader, generation = self._borrow()
                cursor = reader.cursor().execute(statement.text, parameters)
            # The rows are already here: the result needs no connection, nor any lock.
            return _Cursor(cursor, threading.RLock(), statement)
        finally:
            self._give_back(reader, generation)

    def executescript(self, script: str) -> _Cursor:  # type: ignore[override]
        """Execute several statements. Like SQLite, this commits what is pending first."""

        with self._lock:
            self.commit()
            result: Optional[_Cursor] = None
            for sql in split_statements(script):
                result = self.execute(sql)
            if result is None:
                result = self.execute("SELECT 1 WHERE false")
            return result

    def _run(self, sql: str, statement: Statement, parameters: tuple) -> _Cursor:
        word = statement.text.lstrip().split(None, 1)[0].upper() if statement.text.strip() else ""

        if word == "BEGIN":
            self.begin()
            return self._cursor(self.connection.cursor(), statement)
        if word in ("COMMIT", "END"):
            self.commit()
            return self._cursor(self.connection.cursor(), statement)
        if word == "ROLLBACK" and " TO " not in statement.text.upper():
            self.rollback()
            return self._cursor(self.connection.cursor(), statement)

        if word in _WRITES:
            self.begin()

        try:
            cursor = self._guarded(statement.text, parameters)
        except Exception as error:
            if not self._active and self._lost(error, self._connection):
                # The server restarted or dropped an idle connection: nothing was in progress.
                self.close()
                self.open()
                cursor = self._guarded(statement.text, parameters)
            else:
                raise

        if is_schema_change(sql):
            self.catalog.clear()
            # Creating what may be missing changes nothing that is already known.
            if not _ENSURE.match(sql):
                self._forget_schema()
        return self._cursor(cursor, statement)

    def _guarded(self, text: str, parameters: tuple) -> Any:
        """Run a statement so that its failure leaves the open transaction usable."""

        connection = self.connection
        if not self._active:
            return connection.cursor().execute(text, parameters)

        # One round trip for all three: the server may be far away.
        try:
            with connection.pipeline():
                connection.execute("SAVEPOINT entropy_statement")
                cursor = connection.cursor().execute(text, parameters)
                connection.execute("RELEASE SAVEPOINT entropy_statement")
        except Exception:
            connection.execute("ROLLBACK TO SAVEPOINT entropy_statement")
            connection.execute("RELEASE SAVEPOINT entropy_statement")
            raise
        return cursor

    def _lost(self, error: Exception, connection: Any) -> bool:
        operational = getattr(self._driver(), "OperationalError", ())
        return isinstance(error, operational) and (connection is None or bool(connection.closed))

    def _cursor(self, cursor: Any, statement: Statement) -> _Cursor:
        return _Cursor(cursor, self._lock, statement)

    # ------------------------------------------------------------------
    # Transaction
    # ------------------------------------------------------------------

    def begin(self) -> None:
        """Start a transaction, unless one is open."""

        with self._lock:
            if not self._active:
                self.connection.execute("BEGIN")
                self._active = True
                self._owner = threading.get_ident()

    def commit(self) -> None:
        """Commit the active transaction, if any."""

        with self._lock:
            if self._active:
                self.connection.execute("COMMIT")
                self._active = False
                self._owner = None

    def rollback(self) -> None:
        """Roll back the active transaction, if any."""

        with self._lock:
            if self._active:
                self.connection.execute("ROLLBACK")
                self._active = False
                self._owner = None
                # What this transaction created is gone again.
                self.catalog.clear()
                self._forget_schema()

    # ------------------------------------------------------------------
    # Untranslated access
    # ------------------------------------------------------------------

    def raw_execute(self, sql: str, parameters: Optional[tuple] = None) -> Any:
        """A statement already written for PostgreSQL."""

        with self._lock:
            return self.connection.cursor().execute(sql, parameters)

    def raw_rows(self, sql: str, parameters: Optional[tuple] = None) -> List[Any]:
        """The rows of a query already written for PostgreSQL."""

        with self._lock:
            return list(self.connection.cursor().execute(sql, parameters).fetchall())

    def raw_executemany(self, sql: str, rows: Sequence[Sequence[Any]]) -> None:
        """Many rows through one statement already written for PostgreSQL."""

        with self._lock:
            self.connection.cursor().executemany(sql, rows)

    @property
    def connection(self) -> Any:
        """The driver's connection, connected if it was not."""

        with self._lock:
            if self._connection is None:
                self.open()
            return self._connection

    def server_version(self) -> str:
        """The server's version, as a check that the connection works."""

        rows = self.raw_rows("SHOW server_version")
        return str(rows[0][0]) if rows else ""
