"""
An Oracle Database (19c and later) connection with the interface of DatabaseConnection.

It shares PostgresConnection's structure: one connection for writes, serialized by
a reentrant lock, a transaction from the first write to commit or rollback, a small
pool of connections for reads, and what is known about the schema kept in memory.
What differs is Oracle's:

- SQL is translated by `oracle_dialect`, with named parameters;
- a failed statement is undone by Oracle itself, so the transaction stays usable
  without savepoints; DDL, however, commits whatever transaction is open;
- Oracle stores '' as NULL: text columns that were NOT NULL on SQLite carry a
  comment, and read NULL back as '', as Entropy expects;
- column names arrive upper-cased and are given back lower-cased; numbers arrive as
  int or float; CLOB and BLOB arrive as str and bytes.

The driver (python-oracledb, thin mode: no Oracle client needed) is imported only here.
"""

from __future__ import annotations

import decimal
import re
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from lib.database import oracle_dialect
from lib.database.exceptions import DatabaseException
from lib.database.oracle_dialect import BLANK_MARK, INDEX_BUDGET, OracleStatement
from lib.database.postgres import PostgresConnection, Row, number_from_numeric

_SCHEMA_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]*$")
_SCHEMA = "SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')"
# Strings longer than this (bytes) are sent as CLOB, bytes longer than this as BLOB.
_LONG_TEXT = 4000
_LONG_BYTES = 2000
_DUPLICATE = 1  # ORA-00001: unique constraint violated
_NUMBER_BYTES = 22


def error_code(error: BaseException) -> Optional[int]:
    """The ORA number of a driver error, or None."""

    first = error.args[0] if error.args else None
    code = getattr(first, "code", None)
    if isinstance(code, int):
        return code
    match = re.search(r"ORA-(\d{5})", str(error))
    return int(match.group(1)) if match else None


class _Result:
    """The rows of one statement, already read: the connection is free for the next."""

    def __init__(
        self,
        names: Optional[Sequence[str]],
        rows: List[Any],
        rowcount: int = -1,
        lastrowid: Optional[int] = None,
    ) -> None:
        self._names = list(names) if names is not None else None
        self._rows = rows
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    @property
    def description(self) -> Any:
        if self._names is None:
            return None
        return [(name, None, None, None, None, None, None) for name in self._names]

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

    def __iter__(self) -> _Result:
        return self

    def __next__(self) -> Any:
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row


class OracleCatalog:
    """What the translator and the connection need to know about tables; kept until DDL."""

    def __init__(self, connection: OracleConnection) -> None:
        self._connection = connection
        self._columns: Dict[str, List[Tuple[str, str, int, Optional[str]]]] = {}
        self._identity: Dict[str, Optional[str]] = {}
        self._keys: Dict[str, List[List[str]]] = {}
        # Chosen before a table is created (the copy measures SQLite's longest values).
        self.text_types: Dict[Tuple[str, str], str] = {}

    def clear(self) -> None:
        self._columns.clear()
        self._identity.clear()
        self._keys.clear()

    def _load(self, table: str) -> List[Tuple[str, str, int, Optional[str]]]:
        if table not in self._columns:
            rows = self._connection.raw_rows(
                "SELECT LOWER(c.column_name), c.data_type, c.data_length, m.comments"
                " FROM all_tab_columns c LEFT JOIN all_col_comments m ON m.owner = c.owner"
                " AND m.table_name = c.table_name AND m.column_name = c.column_name"
                f" WHERE c.owner = {_SCHEMA} AND c.table_name = UPPER(:1) ORDER BY c.column_id",
                (table,),
            )
            self._columns[table] = [(row[0], row[1], int(row[2] or 0), row[3]) for row in rows]
        return self._columns[table]

    def columns(self, table: str) -> List[str]:
        return [column[0] for column in self._load(table)]

    def clob_columns(self, table: str) -> Set[str]:
        return {column[0] for column in self._load(table) if column[1] == "CLOB"}

    def blank_columns(self, table: str) -> Set[str]:
        """Text columns that were NOT NULL on SQLite: NULL here is '' there."""

        return {column[0] for column in self._load(table) if column[3] == BLANK_MARK}

    def column_types(self, table: str) -> Dict[str, Tuple[str, int]]:
        return {column[0]: (column[1], column[2]) for column in self._load(table)}

    def identity(self, table: str) -> Optional[str]:
        if table not in self._identity:
            rows = self._connection.raw_rows(
                "SELECT LOWER(column_name) FROM all_tab_identity_cols"
                f" WHERE owner = {_SCHEMA} AND table_name = UPPER(:1)",
                (table,),
            )
            self._identity[table] = rows[0][0] if rows else None
        return self._identity[table]

    def unique_keys(self, table: str) -> List[List[str]]:
        """The primary key, then the unique indexes on plain columns."""

        if table not in self._keys:
            rows = self._connection.raw_rows(
                "SELECT i.index_name, LOWER(c.column_name),"
                " CASE WHEN k.constraint_type = 'P' THEN 0 ELSE 1 END"
                " FROM all_indexes i JOIN all_ind_columns c"
                " ON c.index_owner = i.owner AND c.index_name = i.index_name"
                " LEFT JOIN all_constraints k ON k.owner = i.owner AND k.index_name = i.index_name"
                " AND k.constraint_type = 'P'"
                f" WHERE i.table_owner = {_SCHEMA} AND i.table_name = UPPER(:1)"
                " AND i.uniqueness = 'UNIQUE' AND i.index_type = 'NORMAL'"
                " ORDER BY 3, i.index_name, c.column_position",
                (table,),
            )
            keys: Dict[str, List[str]] = {}
            for name, column, _ in rows:
                keys.setdefault(name, []).append(column)
            self._keys[table] = list(keys.values())
        return self._keys[table]

    def conflict_key(self, table: str) -> List[str]:
        keys = self.unique_keys(table)
        return keys[0] if keys else []

    def text_type(self, table: str, column: str) -> Optional[str]:
        return self.text_types.get((table.lower(), column.lower()))


class OracleConnection(PostgresConnection):
    """An Oracle schema behind the interface of DatabaseConnection."""

    def __init__(self, settings: Dict[str, Any], database: Path) -> None:
        schema = str(settings.get("schema") or "")
        if schema and not _SCHEMA_NAME.match(schema):
            raise DatabaseException("The Oracle schema name has letters, digits, _, $ and # only.")
        super().__init__({**settings, "schema": ""}, database)
        self._schema = schema.upper()
        self._settings = settings
        self.catalog = OracleCatalog(self)  # type: ignore[assignment]
        self._translations: Dict[str, OracleStatement] = {}
        self._translations_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _driver(self) -> Any:
        try:
            import oracledb
        except ImportError:
            raise DatabaseException(
                "The Oracle driver (oracledb) is not installed, so Entropy cannot reach its "
                "database."
            ) from None
        return oracledb

    def _connect(self) -> Any:
        oracledb = self._driver()
        settings = self._settings
        connection = oracledb.connect(
            user=settings.get("username") or None,
            password=settings.get("password") or None,
            host=settings["host"],
            port=int(settings.get("port") or 1521),
            service_name=settings["database"],
            protocol="tcps" if settings.get("ssl") else "tcp",
            tcp_connect_timeout=10,
        )
        # Statements outside a transaction commit as they run, as with SQLite.
        connection.autocommit = True
        connection.outputtypehandler = _output_type_handler(oracledb)
        cursor = connection.cursor()
        try:
            cursor.execute("ALTER SESSION SET TIME_ZONE = 'UTC'")
            cursor.execute("ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,'")
            if self._schema:
                cursor.execute(f"ALTER SESSION SET CURRENT_SCHEMA = {self._schema}")
        finally:
            cursor.close()
        return connection

    def ensure_schema(self) -> None:
        """The schema is an Oracle user, which an administrator creates; check it is reachable."""

        if self._schema:
            rows = self.raw_rows("SELECT 1 FROM all_users WHERE username = :1", (self._schema,))
            if not rows:
                raise DatabaseException(f"The Oracle schema {self._schema} does not exist.")

    def _forget_schema(self) -> None:
        super()._forget_schema()
        with self._translations_lock:
            self._translations.clear()

    # ------------------------------------------------------------------
    # Engine specifics
    # ------------------------------------------------------------------

    def _translate(self, sql: str, catalog: Any) -> OracleStatement:
        """Translations need the catalog (MERGE keys, CLOBs), and are kept until DDL."""

        with self._translations_lock:
            known = self._translations.get(sql)
        if known is not None:
            return known
        statement = oracle_dialect.translate(sql, self.catalog)  # type: ignore[arg-type]
        if not re.match(r"\s*(?:CREATE|ALTER|DROP)\b", sql, re.I):
            with self._translations_lock:
                self._translations[sql] = statement
        return statement

    def _guarded(self, statement: Any, parameters: tuple) -> Any:
        # Oracle undoes a failed statement by itself; the transaction stays usable.
        return self._execute_on(self.connection, statement, parameters)

    def _wrap(self, cursor: Any, lock: Any, statement: Any) -> Any:
        return cursor

    def _is_closed(self, connection: Any) -> bool:
        try:
            return not connection.is_healthy()
        except Exception:  # noqa: BLE001 - a connection that cannot say is not usable
            return True

    def _lost(self, error: Exception, connection: Any) -> bool:
        driver_error = getattr(self._driver(), "Error", ())
        return isinstance(error, driver_error) and (
            connection is None or self._is_closed(connection)
        )

    def _execute_on(
        self, connection: Any, statement: OracleStatement, parameters: tuple
    ) -> _Result:
        """Run one translated statement and read its rows at once."""

        if statement.noop:
            return _Result(["result"], [])
        if statement.index is not None:
            self._fit_index(*statement.index)
        sql, binds = statement.render(parameters)
        cursor = connection.cursor()
        try:
            sizes = self._prepare_binds(binds)
            if sizes:
                cursor.setinputsizes(**sizes)
            returned = None
            if statement.returning:
                returned = cursor.var(int)
                binds["rid"] = returned
            try:
                cursor.execute(sql, binds)
            except Exception as error:
                code = error_code(error)
                if code in statement.ignore:
                    return _Result(None, [], rowcount=0)
                if code == _DUPLICATE and statement.ignore_duplicates:
                    return _Result(None, [], rowcount=0)
                if code == _DUPLICATE and self._behind_copied_keys(statement):
                    cursor.execute(sql, binds)
                else:
                    raise
            names = None
            rows: List[Any] = []
            if cursor.description is not None:
                names = [_name(column[0]) for column in cursor.description]
                blank = self._blank_names(statement, names)
                rows = [_row(names, values, blank) for values in cursor.fetchall()]
            lastrowid = None
            if returned is not None:
                value = returned.getvalue()
                if isinstance(value, list):
                    value = value[0] if value else None
                lastrowid = int(value) if value is not None else None
            result = _Result(names, rows, rowcount=cursor.rowcount, lastrowid=lastrowid)
        finally:
            cursor.close()
        for followup in statement.followups:
            self.raw_execute(followup)
        return result

    def _prepare_binds(self, binds: Dict[str, Any]) -> Dict[str, Any]:
        """Values as Oracle takes them: flags as numbers, long text as CLOB, long bytes as BLOB."""

        oracledb = self._driver()
        sizes: Dict[str, Any] = {}
        for name, value in binds.items():
            if isinstance(value, bool):
                binds[name] = int(value)
            elif (
                isinstance(value, str)
                and len(value) > _LONG_TEXT // 4
                and len(value.encode("utf-8")) > _LONG_TEXT
            ):
                sizes[name] = oracledb.DB_TYPE_CLOB
            elif isinstance(value, (bytes, bytearray, memoryview)) and len(value) > _LONG_BYTES:
                sizes[name] = oracledb.DB_TYPE_BLOB
                binds[name] = bytes(value)
        return sizes

    def _blank_names(self, statement: OracleStatement, names: Sequence[str]) -> Set[str]:
        """Result columns whose NULL is SQLite's '' (not those of outer-joined tables)."""

        blank: Set[str] = set()
        for table in statement.tables:
            if table in statement.outer_tables or table in ("dual", "sqlite_master"):
                continue
            try:
                blank |= self.catalog.blank_columns(table)  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001 - views and system tables have no marks
                continue
        return blank & set(names)

    def _behind_copied_keys(self, statement: OracleStatement) -> bool:
        """
        A duplicate key on an INSERT that let the key be generated means rows were added
        with keys of their own (a copy, a migration rebuilding a table): continue after them.
        """

        match = re.match(r"\s*INSERT\s+INTO\s+([\w$#\"]+)\s*(\(([^)]*)\))?", statement.code, re.I)
        if match is None:
            return False
        table = match.group(1).strip('"').lower()
        identity = self.catalog.identity(table)
        if identity is None:
            return False
        named = [item.strip().strip('"').lower() for item in (match.group(3) or "").split(",")]
        if identity in named:
            return False
        self.continue_keys(table)
        return True

    def _fit_index(self, table: str, columns: Sequence[str]) -> None:
        """Shorten VARCHAR2 columns so an index key fits an 8 KB block, as Oracle requires."""

        if not columns:
            return
        types = self.catalog.column_types(table)  # type: ignore[attr-defined]
        text = [c for c in columns if types.get(c, ("", 0))[0] in ("VARCHAR2", "NVARCHAR2")]
        if not text:
            return
        if any(types.get(c, ("", 0))[0] == "CLOB" for c in columns):
            raise DatabaseException(
                f"Cannot index {table}({', '.join(columns)}): a column holds long text (CLOB)."
            )
        fixed = (len(columns) - len(text)) * _NUMBER_BYTES
        if fixed + sum(types[c][1] for c in text) <= INDEX_BUDGET:
            return
        each = max(100, (INDEX_BUDGET - fixed) // len(text))
        for column in text:
            if types[column][1] > each:
                try:
                    self.raw_execute(
                        f"ALTER TABLE {oracle_dialect._column(table)}"
                        f" MODIFY ({oracle_dialect._column(column)} VARCHAR2({each}))"
                    )
                except Exception as error:
                    raise DatabaseException(
                        f"Cannot index {table}({', '.join(columns)}): {column} holds values longer"
                        f" than the {each} bytes an index key leaves for it ({error})."
                    ) from None
        self.catalog.clear()

    # ------------------------------------------------------------------
    # Transaction
    # ------------------------------------------------------------------

    def begin(self) -> None:
        with self._lock:
            if not self._active:
                self.connection.autocommit = False
                self._active = True
                self._owner = threading.get_ident()

    def commit(self) -> None:
        with self._lock:
            if self._active:
                self.connection.commit()
                self.connection.autocommit = True
                self._active = False
                self._owner = None

    def rollback(self) -> None:
        with self._lock:
            if self._active:
                self.connection.rollback()
                self.connection.autocommit = True
                self._active = False
                self._owner = None
                self.catalog.clear()
                self._forget_schema()

    # ------------------------------------------------------------------
    # Untranslated access
    # ------------------------------------------------------------------

    def raw_execute(self, sql: str, parameters: Optional[Sequence[Any]] = None) -> Any:
        """A statement already written for Oracle."""

        with self._lock:
            cursor = self.connection.cursor()
            try:
                cursor.execute(sql, list(parameters or ()))
                return cursor.rowcount
            finally:
                cursor.close()

    def raw_rows(self, sql: str, parameters: Optional[Sequence[Any]] = None) -> List[Any]:
        """The rows of a query already written for Oracle."""

        with self._lock:
            cursor = self.connection.cursor()
            try:
                cursor.execute(sql, list(parameters or ()))
                return list(cursor.fetchall())
            finally:
                cursor.close()

    def raw_executemany(self, sql: str, rows: Sequence[Sequence[Any]]) -> None:
        with self._lock:
            cursor = self.connection.cursor()
            try:
                cursor.executemany(sql, list(rows))
            finally:
                cursor.close()

    def server_version(self) -> str:
        return str(getattr(self.connection, "version", "") or "")

    # ------------------------------------------------------------------
    # The copy from SQLite (lib/database/switch.py)
    # ------------------------------------------------------------------

    def plan_table(self, source: Any, table: str) -> None:
        """Text columns whose SQLite values are too long for VARCHAR2 become CLOB."""

        for column in source.fetchall(f"PRAGMA table_info({_sqlite_quoted(table)})"):
            declared = str(column["type"] or "").upper()
            if (
                declared
                and "CHAR" not in declared
                and "TEXT" not in declared
                and "CLOB" not in declared
            ):
                continue
            longest = source.fetchone(
                f"SELECT max(length(CAST({_sqlite_quoted(column['name'])} AS BLOB)))"
                f" FROM {_sqlite_quoted(table)}"
            )[0]
            if longest and int(longest) > _LONG_TEXT:
                self.catalog.text_types[(table.lower(), str(column["name"]).lower())] = "CLOB"  # type: ignore[attr-defined]

    def insert_rows(
        self, table: str, columns: Sequence[str], rows: Sequence[Sequence[Any]]
    ) -> None:
        """Copied rows, as they are (long text as CLOB, flags as numbers)."""

        oracledb = self._driver()
        types = self.catalog.column_types(table)  # type: ignore[attr-defined]
        names = ", ".join(oracle_dialect._column(column) for column in columns)
        places = ", ".join(f":{index + 1}" for index in range(len(columns)))
        sizes = []
        for column in columns:
            kind = types.get(column.lower(), ("", 0))[0]
            sizes.append(
                oracledb.DB_TYPE_CLOB
                if kind == "CLOB"
                else oracledb.DB_TYPE_BLOB if kind == "BLOB" else None
            )
        prepared = [tuple(int(v) if isinstance(v, bool) else v for v in row) for row in rows]
        with self._lock:
            cursor = self.connection.cursor()
            try:
                if any(sizes):
                    cursor.setinputsizes(*sizes)
                cursor.executemany(
                    f"INSERT INTO {oracle_dialect._column(table)} ({names}) VALUES ({places})",
                    prepared,
                )
            finally:
                cursor.close()

    def count_rows(self, table: str) -> int:
        rows = self.raw_rows(f"SELECT count(*) FROM {oracle_dialect._column(table)}")
        return int(rows[0][0]) if rows else 0

    def continue_keys(self, table: str) -> None:
        """New rows get keys after the copied ones."""

        identity = self.catalog.identity(table)
        if identity is None:
            return
        self.raw_execute(
            f"ALTER TABLE {oracle_dialect._column(table)} MODIFY {oracle_dialect._column(identity)}"
            " GENERATED BY DEFAULT ON NULL AS IDENTITY (START WITH LIMIT VALUE)"
        )

    def discard(self, tables: Iterable[str]) -> None:
        """Drop what a failed copy created: Oracle commits CREATE TABLE as it runs."""

        for table in tables:
            try:
                self.raw_execute(f"DROP TABLE {oracle_dialect._column(table)} PURGE")
            except Exception:  # noqa: BLE001 - a table the copy never got to create
                continue
        self.catalog.clear()
        self._forget_schema()


def _name(raw: str) -> str:
    """Oracle gives unquoted names upper-cased; Entropy reads them lower-case, as SQLite gives."""

    return raw.lower() if raw == raw.upper() else raw


def _row(names: Sequence[str], values: Sequence[Any], blank: Set[str]) -> Row:
    if blank:
        values = [
            "" if value is None and name in blank else value for name, value in zip(names, values)
        ]
    return Row(names, values)


def _sqlite_quoted(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _output_type_handler(oracledb: Any) -> Any:
    """Numbers as int or float (as SQLite gives them), CLOB as str and BLOB as bytes."""

    def handler(cursor: Any, metadata: Any) -> Any:
        kind = getattr(metadata, "type_code", None)
        if kind is oracledb.DB_TYPE_NUMBER:
            return cursor.var(
                decimal.Decimal, arraysize=cursor.arraysize, outconverter=number_from_numeric
            )
        if kind is oracledb.DB_TYPE_CLOB:
            return cursor.var(oracledb.DB_TYPE_LONG, arraysize=cursor.arraysize)
        if kind is oracledb.DB_TYPE_BLOB:
            return cursor.var(oracledb.DB_TYPE_LONG_RAW, arraysize=cursor.arraysize)
        return None

    return handler
