"""The PostgreSQL connection behaves like the SQLite one; no server is involved here."""

from __future__ import annotations

import contextlib
import threading
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

psycopg = pytest.importorskip("psycopg")

from lib.database.exceptions import DatabaseException  # noqa: E402
from lib.database.postgres import (  # noqa: E402
    PostgresConnection,
    Row,
    _register_adapters,
    number_from_numeric,
)


class FakeCursor:
    def __init__(self, driver):
        self.driver = driver
        self.description = None
        self.rowcount = -1
        self.rows = []

    def execute(self, sql, parameters=None):
        self.driver.log.append(sql)
        if sql in self.driver.failing:
            raise self.driver.failing[sql]
        result = self.driver.results.get(sql)
        if result is not None:
            names, self.rows = result
            self.description = [SimpleNamespace(name=name) for name in names]
            self.rowcount = len(self.rows)
        else:
            self.rowcount = 1
        return self

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchmany(self, size=1):
        taken, self.rows = self.rows[:size], self.rows[size:]
        return taken

    def fetchall(self):
        taken, self.rows = self.rows, []
        return taken

    def close(self):
        pass


class FakeDriver:
    closed = False

    def __init__(self):
        self.log = []
        self.failing = {}
        self.results = {}

    def cursor(self):
        return FakeCursor(self)

    def execute(self, sql):
        return self.cursor().execute(sql)

    def close(self):
        self.closed = True

    @contextlib.contextmanager
    def pipeline(self):
        self.pipelines = getattr(self, "pipelines", 0) + 1
        yield


class StubCatalog:
    def __init__(self, identity=None):
        self._identity = identity

    def identity(self, table):
        return self._identity

    def conflict_key(self, table):
        return ["id"]

    def columns(self, table):
        return ["id", "a"]

    def clear(self):
        self.cleared = True


@pytest.fixture
def database():
    connection = PostgresConnection({"host": "h", "port": 5432, "database": "d"}, Path("x.db"))
    driver = FakeDriver()
    connection._connection = driver
    # Pool readers share the fake, so each test sees every statement in one log.
    connection._connect = lambda: driver
    connection.catalog = StubCatalog()
    return connection


def test_row_reads_like_sqlite_row() -> None:
    row = Row(["id", "name"], [1, "a"])
    assert row["id"] == 1
    assert row["NAME"] == "a"
    assert row[1] == "a"
    assert dict(row) == {"id": 1, "name": "a"}
    assert list(row) == [1, "a"]
    assert row.keys() == ["id", "name"]
    assert len(row) == 2
    with pytest.raises(IndexError):
        row["missing"]


def test_reads_do_not_start_a_transaction(database) -> None:
    database.execute("SELECT 1")
    assert database.connection.log == ["SELECT 1"]


def test_a_write_starts_a_transaction_until_commit(database) -> None:
    database.execute("UPDATE t SET a = ?", (1,))
    database.execute("UPDATE t SET a = ?", (2,))
    database.commit()
    assert [s for s in database.connection.log if s in ("BEGIN", "COMMIT")] == ["BEGIN", "COMMIT"]


def test_commit_and_rollback_without_a_transaction_do_nothing(database) -> None:
    database.commit()
    database.rollback()
    assert database.connection.log == []


def test_transaction_rolls_back_on_failure(database) -> None:
    with pytest.raises(ValueError), database.transaction():
        database.execute("UPDATE t SET a = 1")
        raise ValueError
    assert database.connection.log[-1] == "ROLLBACK"
    database.execute("UPDATE t SET a = 1")
    assert database.connection.log[-4] == "BEGIN"


def test_a_failed_statement_leaves_the_transaction_usable(database) -> None:
    failing = "UPDATE t SET bad = 1"
    database.connection.failing[failing] = ValueError("no")
    database.begin()
    with pytest.raises(ValueError):
        database.execute(failing)
    assert database.connection.log[-3:] == [
        failing,
        "ROLLBACK TO SAVEPOINT entropy_statement",
        "RELEASE SAVEPOINT entropy_statement",
    ]
    database.execute("UPDATE t SET a = 1")
    database.commit()
    assert database.connection.log[-1] == "COMMIT"


def test_a_statement_in_a_transaction_costs_one_round_trip(database) -> None:
    database.begin()
    database.execute("UPDATE t SET a = 1")
    assert database.connection.pipelines == 1
    assert database.connection.log[-3:] == [
        "SAVEPOINT entropy_statement",
        "UPDATE t SET a = 1",
        "RELEASE SAVEPOINT entropy_statement",
    ]


def test_lastrowid_comes_from_the_generated_key(database) -> None:
    database.catalog = StubCatalog(identity="id")
    sql = 'INSERT INTO t (a) VALUES (%s) RETURNING "id"'
    database.connection.results[sql] = (["id"], [Row(["id"], [7])])
    cursor = database.execute("INSERT INTO t (a) VALUES (?)", (1,))
    assert cursor.lastrowid == 7
    assert cursor.fetchone() is None


def test_statements_without_rows_read_as_empty(database) -> None:
    cursor = database.execute("UPDATE t SET a = 1")
    assert cursor.fetchone() is None
    assert cursor.fetchall() == []
    assert cursor.fetchmany(5) == []
    assert list(cursor) == []
    assert cursor.description is None


def test_a_schema_change_forgets_what_is_known_about_tables(database) -> None:
    database.execute("ALTER TABLE t ADD COLUMN a TEXT")
    assert database.catalog.cleared


def test_fetch_helpers_go_through_translation(database) -> None:
    database.connection.results["SELECT a FROM t WHERE b = %s"] = (["a"], [Row(["a"], [1])])
    assert database.fetchone("SELECT a FROM t WHERE b = ?", (2,))["a"] == 1


def test_executescript_commits_first_and_runs_each_statement(database) -> None:
    database.execute("UPDATE t SET a = 1")
    database.executescript("CREATE TABLE a (x TEXT); CREATE TABLE b (y TEXT);")
    log = database.connection.log
    assert log.index("COMMIT") < log.index("CREATE TABLE a (x TEXT)")
    assert "CREATE TABLE b (y TEXT)" in log


def test_a_dropped_idle_connection_is_reopened_once(database, monkeypatch) -> None:
    lost = database.connection
    lost.failing["UPDATE t SET a = 1"] = psycopg.OperationalError("gone")
    lost.closed = True
    fresh = FakeDriver()

    def reconnect():
        database._connection = fresh

    monkeypatch.setattr(database, "open", reconnect)
    database.connection.failing = {}
    lost.failing["SELECT 1"] = psycopg.OperationalError("gone")
    database._connect = lambda: fresh
    database.execute("SELECT 1")
    assert fresh.log == ["SELECT 1"]


def test_a_dropped_connection_inside_a_transaction_is_not_retried(database) -> None:
    driver = database.connection
    database.begin()
    driver.failing["UPDATE t SET a = 1"] = psycopg.OperationalError("gone")
    with pytest.raises(psycopg.OperationalError):
        database.execute("UPDATE t SET a = 1")


def _separate_readers(database):
    readers = []

    def connect():
        readers.append(FakeDriver())
        return readers[-1]

    database._connect = connect
    return readers


def test_reads_outside_a_transaction_use_the_pool(database) -> None:
    readers = _separate_readers(database)
    database.execute("SELECT 1")
    assert database.connection.log == []
    assert readers[0].log == ["SELECT 1"]


def test_a_read_after_a_write_sees_that_write_on_the_same_connection(database) -> None:
    readers = _separate_readers(database)
    database.execute("UPDATE t SET a = 1")
    database.execute("SELECT a FROM t")
    assert "SELECT a FROM t" in database.connection.log
    assert readers == []


def test_another_threads_read_does_not_wait_for_a_transaction(database) -> None:
    readers = _separate_readers(database)
    done = []

    def read():
        done.append(database.execute("SELECT 2"))

    with database.transaction():
        database.execute("UPDATE t SET a = 1")
        thread = threading.Thread(target=read)
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive(), "the read waited for the transaction"
    assert readers[0].log == ["SELECT 2"]
    assert "SELECT 2" not in database.connection.log


@pytest.mark.parametrize("read", ["fetchone", "fetchall", "execute"])
def test_no_way_of_reading_waits_for_another_threads_transaction(database, read) -> None:
    _separate_readers(database)
    thread = threading.Thread(target=lambda: getattr(database, read)("SELECT 2"))
    with database.transaction():
        database.execute("UPDATE t SET a = 1")
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive(), f"{read} waited for the transaction"


def test_reads_really_run_at_the_same_time(database) -> None:
    """Each read waits until another is also inside the server: only true if they overlap."""

    both_inside = threading.Barrier(2, timeout=5)

    class Waiting(FakeDriver):
        def cursor(self):
            cursor = super().cursor()
            execute = cursor.execute

            def meeting(sql, parameters=None):
                both_inside.wait()
                return execute(sql, parameters)

            cursor.execute = meeting
            return cursor

    database._connect = Waiting
    failures = []

    def read():
        try:
            database.fetchone("SELECT 1")
        except threading.BrokenBarrierError as error:
            failures.append(error)

    threads = [threading.Thread(target=read) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert failures == []


def test_the_pool_is_limited_and_reuses_readers(database) -> None:
    readers = _separate_readers(database)
    for _ in range(10):
        database.execute("SELECT 1")
    assert len(readers) == 1
    assert len(readers[0].log) == 10


def test_a_reader_rows_can_be_read_after_it_was_given_back(database) -> None:
    driver = database.connection
    driver.results["SELECT a FROM t"] = (["a"], [Row(["a"], [1]), Row(["a"], [2])])
    cursor = database.execute("SELECT a FROM t")
    assert [row["a"] for row in cursor] == [1, 2]


def test_a_lost_reader_is_replaced_once(database) -> None:
    readers = _separate_readers(database)
    database.execute("SELECT 1")
    readers[0].closed = True
    readers[0].failing["SELECT 1"] = psycopg.OperationalError("gone")
    broken = readers[0]
    database.execute("SELECT 1")
    assert readers[-1] is not broken
    assert readers[-1].log == ["SELECT 1"]


def test_closing_closes_the_readers(database) -> None:
    readers = _separate_readers(database)
    database.execute("SELECT 1")
    database.close()
    assert readers[0].closed


def test_create_if_not_exists_is_sent_once(database) -> None:
    sql = "CREATE TABLE IF NOT EXISTS a (x TEXT)"
    database.execute(sql)
    database.execute(sql)
    assert database.connection.log.count(sql) == 1


def test_schema_lookups_are_remembered_only_when_found(database) -> None:
    driver = database.connection
    readers = _separate_readers(database)
    query = "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?"
    assert database.execute(query, ("a",)).fetchone() is None
    assert database.execute(query, ("a",)).fetchone() is None
    assert len(readers[0].log) == 2
    text = readers[0].log[0]
    readers[0].results[text] = (["x"], [Row(["x"], [1])])
    assert database.execute(query, ("a",)).fetchone()[0] == 1
    assert database.execute(query, ("a",)).fetchone()[0] == 1
    assert len(readers[0].log) == 3
    assert driver.log == []


def test_a_real_schema_change_forgets_what_was_known(database) -> None:
    sql = "CREATE TABLE IF NOT EXISTS a (x TEXT)"
    database.execute(sql)
    database.execute("DROP TABLE a")
    database.execute(sql)
    assert database.connection.log.count(sql) == 2


def test_a_rollback_forgets_what_the_transaction_created(database) -> None:
    sql = "CREATE TABLE IF NOT EXISTS a (x TEXT)"
    database.begin()
    database.execute(sql)
    database.rollback()
    database.execute(sql)
    assert database.connection.log.count(sql) == 2


def test_a_bad_schema_name_is_refused() -> None:
    with pytest.raises(DatabaseException):
        PostgresConnection({"schema": 'x"; DROP'}, Path("x"))


def test_numeric_results_become_plain_numbers() -> None:
    assert number_from_numeric(Decimal("3")) == 3
    assert isinstance(number_from_numeric(Decimal("3")), int)
    assert number_from_numeric(Decimal("1.5")) == 1.5


def test_numbers_and_flags_are_sent_untyped() -> None:
    from psycopg.adapt import AdaptersMap, PyFormat, Transformer

    adapters = AdaptersMap(psycopg.adapters)
    _register_adapters(adapters)
    transformer = Transformer(SimpleNamespace(adapters=adapters, connection=None))
    values = (5, 1.5, True, False)
    dumped = transformer.dump_sequence(values, [PyFormat.TEXT] * len(values))
    assert [bytes(value) for value in dumped] == [b"5", b"1.5", b"1", b"0"]
    assert list(transformer.types) == [0, 0, 0, 0]
