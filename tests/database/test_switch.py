"""Copying SQLite to another database; the target here records what it is asked to do."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("psycopg")

from lib.database.connection import DatabaseConnection  # noqa: E402
from lib.database.switch import DatabaseSwitchError, SwitchProgress, copy_database  # noqa: E402


class Target:
    def __init__(self, occupied=False, fail_on=None, miscount=False):
        self.occupied = occupied
        self.fail_on = fail_on
        self.miscount = miscount
        self.statements = []
        self.rows = {}
        self.state = []
        self.catalog = SimpleNamespace(identity=lambda table: "id" if table == "a" else None)
        self.keys = []

    def ensure_schema(self):
        self.state.append("schema")

    def fetchone(self, sql, parameters=()):
        return (1,) if self.occupied else None

    def begin(self):
        self.state.append("begin")

    def commit(self):
        self.state.append("commit")

    def rollback(self):
        self.state.append("rollback")

    def execute(self, sql, parameters=()):
        self.statements.append(sql)

    def raw_executemany(self, sql, rows):
        if self.fail_on and self.fail_on in sql:
            raise ValueError("bad value")
        table = sql.split('"')[1]
        self.rows.setdefault(table, []).extend(rows)

    def raw_rows(self, sql, parameters=None):
        table = sql.split('"')[1]
        return [(len(self.rows.get(table, [])) - (1 if self.miscount else 0),)]

    def raw_execute(self, sql, parameters=None):
        self.keys.append(parameters)


@pytest.fixture
def source(tmp_path):
    connection = DatabaseConnection(tmp_path / "entropy.db")
    connection.execute("CREATE TABLE a (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)")
    connection.execute("CREATE TABLE b (k TEXT PRIMARY KEY, data BLOB)")
    connection.execute("CREATE INDEX idx_b ON b (data)")
    connection.execute("INSERT INTO a (name) VALUES ('one'), ('two')")
    connection.execute("INSERT INTO b VALUES ('x', x'00ff')")
    connection.commit()
    yield connection
    connection.close()


def test_everything_is_copied_in_one_transaction(source) -> None:
    target = Target()
    assert copy_database(source, target) == {"a": 2, "b": 1}
    assert target.state == ["schema", "begin", "commit"]
    assert target.rows["a"] == [(1, "one"), (2, "two")]
    assert target.rows["b"] == [("x", b"\x00\xff")]


def test_tables_come_before_rows_and_indexes_after(source) -> None:
    target = Target()
    copy_database(source, target)
    assert [s.split()[1] for s in target.statements] == ["TABLE", "TABLE", "INDEX"]
    assert "sqlite_sequence" not in " ".join(target.statements)
    assert "sqlite_sequence" not in target.rows


def test_generated_keys_continue_after_the_copied_rows(source) -> None:
    target = Target()
    copy_database(source, target)
    assert target.keys == [('"a"', "id")]


def test_a_target_with_tables_is_refused_and_left_alone(source) -> None:
    target = Target(occupied=True)
    with pytest.raises(DatabaseSwitchError, match="already has tables"):
        copy_database(source, target)
    assert target.statements == []
    assert "begin" not in target.state


def test_a_failed_copy_rolls_back_and_names_the_table(source) -> None:
    target = Target(fail_on='"b"')
    with pytest.raises(DatabaseSwitchError, match="table b"):
        copy_database(source, target)
    assert target.state[-1] == "rollback"


def test_a_wrong_row_count_rolls_back(source) -> None:
    target = Target(miscount=True)
    with pytest.raises(DatabaseSwitchError, match="rows on the target"):
        copy_database(source, target)
    assert target.state[-1] == "rollback"


def test_triggers_are_refused_rather_than_silently_lost(source) -> None:
    source.execute("CREATE TRIGGER t AFTER INSERT ON a BEGIN DELETE FROM b; END")
    source.commit()
    with pytest.raises(DatabaseSwitchError, match="Triggers"):
        copy_database(source, Target())


def test_progress_follows_the_copy(source) -> None:
    progress = SwitchProgress()
    progress.begin("postgresql")
    copy_database(source, Target(), progress)
    state = progress.snapshot()
    assert state["tables_total"] == state["tables_done"] == 2
    assert state["rows_total"] == state["rows_done"] == 3
    assert state["table"] is None


def test_the_source_is_not_changed(source) -> None:
    copy_database(source, Target())
    assert source.fetchone("SELECT count(*) FROM a")[0] == 2
