"""The Oracle connection behaves like the SQLite one; a fake driver stands in for Oracle."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from lib.database.connection import DatabaseConnection
from lib.database.exceptions import DatabaseException
from lib.database.oracle import OracleConnection, _output_type_handler, error_code
from lib.database.switch import DatabaseSwitchError, copy_database


class OracleError(Exception):
    """Like oracledb.DatabaseError: args[0] carries the ORA number."""

    def __init__(self, code: int) -> None:
        super().__init__(SimpleNamespace(code=code, message=f"ORA-{code:05d}"))


class Var:
    def __init__(self, kind, value=None, **options):
        self.kind = kind
        self.options = options
        self.value = value

    def getvalue(self):
        return self.value


class FakeCursor:
    def __init__(self, driver):
        self.driver = driver
        self.description = None
        self.rowcount = 0
        self.rows = []
        self.arraysize = 100

    def execute(self, sql, binds=None):
        self.driver.log.append((sql, dict(binds) if isinstance(binds, dict) else binds))
        for fragment, error in list(self.driver.failing.items()):
            if fragment in sql:
                if self.driver.fail_once:
                    del self.driver.failing[fragment]
                raise error
        for fragment, (names, rows) in self.driver.results.items():
            if fragment in sql:
                self.description = [(name,) for name in names]
                self.rows = list(rows)
                self.rowcount = len(rows)
                break
        else:
            self.rowcount = 1
        if isinstance(binds, dict) and "rid" in binds:
            binds["rid"].value = [self.driver.next_id]

    def executemany(self, sql, rows):
        self.driver.log.append((sql, list(rows)))

    def setinputsizes(self, *args, **kwargs):
        self.driver.sizes.append(args or kwargs)

    def var(self, kind, **options):
        return Var(kind, **options)

    def fetchall(self):
        taken, self.rows = self.rows, []
        return taken

    def close(self):
        pass


class FakeOracle:
    """A connection; also the module, so connect() and the type names are here too."""

    DB_TYPE_CLOB = "CLOB"
    DB_TYPE_BLOB = "BLOB"
    DB_TYPE_NUMBER = "NUMBER"
    DB_TYPE_LONG = "LONG"
    DB_TYPE_LONG_RAW = "LONG_RAW"
    Error = OracleError

    def __init__(self):
        self.log = []
        self.sizes = []
        self.failing = {}
        self.fail_once = False
        self.results = {}
        self.autocommit = True
        self.healthy = True
        self.transactions = []
        self.next_id = 42
        self.version = "19.22.0.0.0"

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.transactions.append("commit")

    def rollback(self):
        self.transactions.append("rollback")

    def is_healthy(self):
        return self.healthy

    def close(self):
        self.healthy = False

    def sql(self):
        return [entry[0] for entry in self.log]


class StubCatalog:
    """users(id identity, name, note) with name and note NOT NULL text on SQLite."""

    def __init__(self):
        self.text_types = {}
        self.cleared = 0

    def columns(self, table):
        return ["id", "name", "note"]

    def unique_keys(self, table):
        return [["id"]]

    def conflict_key(self, table):
        return ["id"]

    def identity(self, table):
        return "id" if table in ("users", "a") else None

    def clob_columns(self, table):
        return set()

    def text_type(self, table, column):
        return self.text_types.get((table, column))

    def blank_columns(self, table):
        return {"name", "note"} if table == "users" else set()

    def column_types(self, table):
        return {
            "id": ("NUMBER", 22),
            "name": ("VARCHAR2", 4000),
            "note": ("VARCHAR2", 4000),
            "body": ("CLOB", 4000),
        }

    def clear(self):
        self.cleared += 1


@pytest.fixture
def database():
    connection = OracleConnection({"host": "h", "port": 1521, "database": "FREEPDB1"}, Path("x.db"))
    driver = FakeOracle()
    connection._connection = driver
    # Readers share the fake, so each test sees every statement in one log.
    connection._connect = lambda: driver
    connection._driver = lambda: driver
    connection.catalog = StubCatalog()
    return connection


def test_rows_read_like_sqlite_rows_and_blank_text_comes_back_empty(database) -> None:
    database.connection.results["FROM users"] = (
        ["ID", "NAME", "NOTE", "LABEL"],
        [(1, None, "x", None)],
    )
    row = database.fetchone("SELECT id, name, note, NULL AS label FROM users")
    assert dict(row) == {"id": 1, "name": "", "note": "x", "label": None}


def test_outer_joined_tables_keep_their_nulls(database) -> None:
    database.connection.results["FROM tasks"] = (["NAME"], [(None,)])
    row = database.fetchone("SELECT u.name FROM tasks t LEFT JOIN users u ON u.id = t.owner")
    assert row["name"] is None


def test_reads_do_not_start_a_transaction(database) -> None:
    database.execute("SELECT 1 FROM t")
    assert database.connection.autocommit is True
    assert database.connection.transactions == []


def test_a_write_holds_a_transaction_until_commit(database) -> None:
    database.execute("UPDATE t SET a = ?", (1,))
    assert database.connection.autocommit is False
    database.execute("UPDATE t SET a = ?", (2,))
    database.commit()
    assert database.connection.transactions == ["commit"]
    assert database.connection.autocommit is True
    database.execute("DELETE FROM t")
    database.rollback()
    assert database.connection.transactions == ["commit", "rollback"]


def test_merge_is_a_write(database) -> None:
    database.execute(
        "INSERT OR REPLACE INTO users (id, name, note) VALUES (?, ?, ?)", (1, "a", "b")
    )
    assert database.connection.autocommit is False
    assert database.connection.sql()[-1].startswith("MERGE INTO users")


def test_parameters_are_named_and_converted(database) -> None:
    long_text = "é" * 3000
    database.execute(
        "UPDATE t SET a = ?, b = ?, c = ? WHERE d = ?", (True, long_text, b"\0" * 3000, 5)
    )
    sql, binds = database.connection.log[-1]
    assert sql == "UPDATE t SET a = :b0, b = :b1, c = :b2 WHERE d = :b3"
    assert binds == {"b0": 1, "b1": long_text, "b2": b"\0" * 3000, "b3": 5}
    assert database.connection.sizes[-1] == {"b1": "CLOB", "b2": "BLOB"}


def test_lastrowid_comes_from_returning(database) -> None:
    cursor = database.execute("INSERT INTO users (name) VALUES (?)", ("a",))
    assert (
        database.connection.sql()[-1]
        == "INSERT INTO users (name) VALUES (:b0) RETURNING id INTO :rid"
    )
    assert cursor.lastrowid == 42


def test_if_not_exists_is_answered_by_ignoring_the_error(database) -> None:
    database.connection.failing["CREATE TABLE t"] = OracleError(955)
    database.execute("CREATE TABLE IF NOT EXISTS t (a TEXT NOT NULL)")
    # The table was there already: its comments are not written again.
    assert not any(sql.startswith("COMMENT") for sql in database.connection.sql())
    database.connection.failing.clear()
    database.execute("CREATE TABLE IF NOT EXISTS u (a TEXT NOT NULL)")
    assert database.connection.sql()[-1] == "COMMENT ON COLUMN u.a IS 'entropy:text-not-null'"


def test_other_errors_are_raised(database) -> None:
    database.connection.failing["CREATE TABLE t"] = OracleError(1031)
    with pytest.raises(OracleError):
        database.execute("CREATE TABLE IF NOT EXISTS t (a TEXT)")


def test_insert_or_ignore_ignores_a_duplicate(database) -> None:
    database.connection.failing["INSERT INTO log"] = OracleError(1)
    database.catalog.unique_keys = lambda table: []
    cursor = database.execute("INSERT OR IGNORE INTO log (message) VALUES (?)", ("x",))
    assert cursor.rowcount == 0
    with pytest.raises(OracleError):
        database.execute("INSERT INTO log (message) VALUES (?)", ("x",))


def test_generated_keys_continue_after_rows_given_their_own(database) -> None:
    database.connection.failing["INSERT INTO users"] = OracleError(1)
    database.connection.fail_once = True
    cursor = database.execute("INSERT INTO users (name) VALUES (?)", ("a",))
    statements = database.connection.sql()
    assert statements[-2] == (
        "ALTER TABLE users MODIFY id GENERATED BY DEFAULT ON NULL AS IDENTITY (START WITH LIMIT"
        " VALUE)"
    )
    assert statements[-1].startswith("INSERT INTO users")
    assert cursor.lastrowid == 42


def test_an_index_too_wide_for_a_block_shortens_its_text_columns(database) -> None:
    database.execute("CREATE INDEX i ON users (name, note)")
    assert database.connection.sql()[-3:] == [
        "ALTER TABLE users MODIFY (name VARCHAR2(3000))",
        "ALTER TABLE users MODIFY (note VARCHAR2(3000))",
        "CREATE INDEX i ON users (name, note)",
    ]


def test_an_index_on_long_text_is_refused_clearly(database) -> None:
    with pytest.raises(DatabaseException, match="CLOB"):
        database.execute("CREATE INDEX i ON users (name, body)")


def test_a_lost_connection_is_replaced_for_reads(database) -> None:
    database.connection.failing["FROM t"] = OracleError(3113)
    database.connection.fail_once = True
    database.connection.healthy = False

    fresh = FakeOracle()
    fresh.results["FROM t"] = (["A"], [(1,)])
    database._connect = lambda: fresh
    assert database.fetchone("SELECT a FROM t")["a"] == 1


def test_numbers_clob_and_blob_are_read_as_python_values() -> None:
    handler = _output_type_handler(FakeOracle)
    cursor = FakeCursor(FakeOracle())
    number = handler(cursor, SimpleNamespace(type_code="NUMBER"))
    assert number.kind is Decimal
    assert number.options["outconverter"](Decimal("3")) == 3
    assert number.options["outconverter"](Decimal("2.5")) == 2.5
    assert handler(cursor, SimpleNamespace(type_code="CLOB")).kind == "LONG"
    assert handler(cursor, SimpleNamespace(type_code="BLOB")).kind == "LONG_RAW"
    assert handler(cursor, SimpleNamespace(type_code="VARCHAR")) is None


def test_error_codes() -> None:
    assert error_code(OracleError(955)) == 955
    assert error_code(Exception("ORA-00942: table or view does not exist")) == 942
    assert error_code(Exception("other")) is None


def test_the_schema_name_is_checked() -> None:
    with pytest.raises(DatabaseException):
        OracleConnection({"host": "h", "database": "d", "schema": "bad name"}, Path("x.db"))


def test_a_missing_driver_is_explained(monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name == "oracledb":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)
    connection = OracleConnection({"host": "h", "database": "d"}, Path("x.db"))
    with pytest.raises(DatabaseException, match="oracledb"):
        connection.open()


# ----------------------------------------------------------------------
# The copy from SQLite
# ----------------------------------------------------------------------


@pytest.fixture
def source(tmp_path):
    connection = DatabaseConnection(tmp_path / "entropy.db")
    connection.execute("CREATE TABLE a (id INTEGER PRIMARY KEY AUTOINCREMENT, note TEXT NOT NULL)")
    connection.execute("INSERT INTO a (note) VALUES ('short'), (?)", ("x" * 5000,))
    connection.commit()
    yield connection
    connection.close()


def test_the_copy_measures_text_inserts_and_continues_keys(database, source) -> None:
    driver = database.connection
    driver.results["sqlite_master"] = ([], [])
    driver.results["SELECT count(*) FROM a"] = (["COUNT"], [(2,)])
    copy_database(source, database)

    # The SQLite values were too long for VARCHAR2: the column is a CLOB.
    assert database.catalog.text_types == {("a", "note"): "CLOB"}
    statements = driver.sql()
    assert (
        "CREATE TABLE a (id NUMBER(19) GENERATED BY DEFAULT ON NULL AS IDENTITY PRIMARY KEY, note"
        " CLOB)" in statements
    )
    assert "COMMENT ON COLUMN a.note IS 'entropy:text-not-null'" in statements
    insert = next(entry for entry in driver.log if entry[0].startswith("INSERT INTO a (id, note)"))
    assert insert[1] == [(1, "short"), (2, "x" * 5000)]
    assert statements[-1] == (
        "ALTER TABLE a MODIFY id GENERATED BY DEFAULT ON NULL AS IDENTITY (START WITH LIMIT VALUE)"
    )
    assert driver.transactions == ["commit"]


def test_a_failed_copy_drops_the_tables_it_created(database, source) -> None:
    driver = database.connection
    driver.results["sqlite_master"] = ([], [])
    driver.results["SELECT count(*) FROM a"] = (["COUNT"], [(1,)])  # one row short
    with pytest.raises(DatabaseSwitchError, match="expected 2"):
        copy_database(source, database)
    assert driver.sql()[-1] == "DROP TABLE a PURGE"
    assert driver.transactions == ["rollback"]
