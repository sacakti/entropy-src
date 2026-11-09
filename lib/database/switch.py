"""
Switch Entropy from SQLite to another database: copy everything once, then
run on the new one after a restart.

The copy is one transaction, so a failure leaves the target empty and Entropy
still on SQLite. The SQLite file is left in place, untouched. (Oracle commits
CREATE TABLE as it runs; there the tables a failed copy created are dropped again.)
"""

from __future__ import annotations

from threading import Lock
from typing import Any, Dict, List, Optional

from lib.database.connection import DatabaseConnection
from lib.database.exceptions import DatabaseException
from lib.database.postgres import PostgresConnection

BATCH_SIZE = 500


# What Entropy is doing while it is unavailable for changes, or about to restart.
ACTIVE_STATES = ("copying", "restarting", "restart_required")


class DatabaseSwitchError(DatabaseException):
    """The database could not be switched; Entropy stays on the one it runs on."""


class SwitchProgress:
    """How far a switch has come, for Settings and Vision. Holds no connection details."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._values = self._idle()

    @staticmethod
    def _idle() -> Dict[str, Any]:
        return {
            "state": "idle",
            "engine": None,
            "table": None,
            "tables_done": 0,
            "tables_total": 0,
            "rows_done": 0,
            "rows_total": 0,
            "error": None,
        }

    def begin(self, engine: str) -> bool:
        """Start a switch; False when one is already under way."""

        with self._lock:
            if self._values["state"] in ACTIVE_STATES:
                return False
            self._values = {**self._idle(), "state": "copying", "engine": engine}
            return True

    def update(self, **changes: Any) -> None:
        with self._lock:
            self._values.update(changes)

    def add_rows(self, count: int) -> None:
        with self._lock:
            self._values["rows_done"] += count

    def table_done(self) -> None:
        with self._lock:
            self._values["tables_done"] += 1

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._values)

    def reset(self) -> None:
        with self._lock:
            self._values = self._idle()


# One server, one switch.
PROGRESS = SwitchProgress()


def _quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _objects(source: DatabaseConnection, kind: str) -> List[Any]:
    return [
        row
        for row in source.fetchall(
            "SELECT name, sql FROM sqlite_master WHERE type = ? ORDER BY name", (kind,)
        )
        # SQLite's own tables and the indexes it makes for UNIQUE have no definition to copy.
        if row["sql"] and not str(row["name"]).startswith("sqlite_")
    ]


def _copy_rows(
    source: DatabaseConnection,
    target: PostgresConnection,
    table: str,
    progress: Optional[SwitchProgress] = None,
) -> int:
    columns = [row["name"] for row in source.fetchall(f"PRAGMA table_info({_quoted(table)})")]
    insert_rows = getattr(target, "insert_rows", None)
    names = ", ".join(_quoted(column) for column in columns)
    insert = f"INSERT INTO {_quoted(table)} ({names}) VALUES ({', '.join('%s' for _ in columns)})"
    cursor = source.execute(f"SELECT {names} FROM {_quoted(table)}")
    copied = 0
    try:
        while True:
            rows = cursor.fetchmany(BATCH_SIZE)
            if not rows:
                return copied
            if insert_rows is not None:
                insert_rows(table, columns, [tuple(row) for row in rows])
            else:
                target.raw_executemany(insert, [tuple(row) for row in rows])
            copied += len(rows)
            if progress is not None:
                progress.add_rows(len(rows))
    finally:
        cursor.close()


def _continue_keys(target: PostgresConnection, table: str) -> None:
    """New rows must get keys after the copied ones."""

    continue_keys = getattr(target, "continue_keys", None)
    if continue_keys is not None:
        continue_keys(table)
        return
    identity = target.catalog.identity(table)
    if identity is None:
        return
    target.raw_execute(
        f"SELECT setval(pg_get_serial_sequence(%s, %s), m) FROM"
        f" (SELECT max({_quoted(identity)}) AS m FROM {_quoted(table)}) AS keys"
        f" WHERE m IS NOT NULL",
        (_quoted(table), identity),
    )


def copy_database(
    source: DatabaseConnection,
    target: PostgresConnection,
    progress: Optional[SwitchProgress] = None,
) -> Dict[str, int]:
    """
    Copy every table and index to an empty target, checking each table's row
    count. Returns the number of rows per table.
    """

    unsupported = _objects(source, "trigger") + _objects(source, "view")
    if unsupported:
        names = ", ".join(row["name"] for row in unsupported)
        raise DatabaseSwitchError(f"Triggers and views cannot be copied yet: {names}.")

    try:
        target.ensure_schema()
        occupied = target.fetchone("SELECT 1 FROM sqlite_master WHERE type = 'table'") is not None
    except DatabaseException:
        raise
    except Exception as error:
        raise DatabaseSwitchError(f"Cannot use the target database: {error}") from error
    if occupied:
        raise DatabaseSwitchError(
            "The target already has tables. Give Entropy an empty database or schema: "
            "nothing was copied or changed."
        )

    tables = _objects(source, "table")
    counts: Dict[str, int] = {}
    if progress is not None:
        total = sum(
            source.fetchone(f"SELECT count(*) FROM {_quoted(table['name'])}")[0] for table in tables
        )
        progress.update(tables_total=len(tables), rows_total=total)
    plan_table = getattr(target, "plan_table", None)
    created: List[str] = []
    target.begin()
    try:
        for table in tables:
            if plan_table is not None:
                plan_table(source, table["name"])
            target.execute(table["sql"])
            created.append(table["name"])
        for table in tables:
            name = table["name"]
            if progress is not None:
                progress.update(table=name)
            try:
                counts[name] = _copy_rows(source, target, name, progress)
            except Exception as error:
                raise DatabaseSwitchError(f"Copying table {name} failed: {error}") from error
            if progress is not None:
                progress.table_done()
        if progress is not None:
            progress.update(table=None)
        for index in _objects(source, "index"):
            try:
                target.execute(index["sql"])
            except Exception as error:
                raise DatabaseSwitchError(
                    f"Creating index {index['name']} failed: {error}"
                ) from error
        count_rows = getattr(target, "count_rows", None)
        for name, count in counts.items():
            if count_rows is not None:
                copied = count_rows(name)
            else:
                copied = target.raw_rows(f"SELECT count(*) FROM {_quoted(name)}")[0][0]
            if copied != count:
                raise DatabaseSwitchError(
                    f"Table {name} has {copied} rows on the target, expected {count}."
                )
            _continue_keys(target, name)
        target.commit()
    except Exception as error:
        target.rollback()
        discard = getattr(target, "discard", None)
        if discard is not None:
            discard(created)
        if isinstance(error, DatabaseException):
            raise
        raise DatabaseSwitchError(f"The copy failed: {error}") from error
    return counts
