"""
Against a real PostgreSQL server; skipped unless one is given:

    ENTROPY_TEST_POSTGRES_URL=postgresql://user:password@host:5432/database

Each test uses its own schema and removes it afterwards.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

psycopg = pytest.importorskip("psycopg")

from lib.database.connection import DatabaseConnection  # noqa: E402
from lib.database.postgres import PostgresConnection  # noqa: E402
from lib.database.switch import DatabaseSwitchError, copy_database  # noqa: E402

URL = os.environ.get("ENTROPY_TEST_POSTGRES_URL", "")

pytestmark = pytest.mark.skipif(not URL, reason="ENTROPY_TEST_POSTGRES_URL is not set")


def settings(schema: str) -> dict:
    url = urlsplit(URL)
    return {
        "host": url.hostname,
        "port": url.port or 5432,
        "database": url.path.lstrip("/"),
        "schema": schema,
        "username": unquote(url.username or ""),
        "password": unquote(url.password or ""),
        "ssl": False,
    }


@pytest.fixture
def target():
    schema = f"entropy_test_{uuid.uuid4().hex[:12]}"
    connection = PostgresConnection(settings(schema), Path("unused.db"))
    connection.ensure_schema()
    yield connection
    connection.rollback()
    connection.raw_execute(f'DROP SCHEMA "{schema}" CASCADE')
    connection.close()


TABLE = (
    "CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT COLLATE NOCASE,"
    " count INTEGER NOT NULL DEFAULT 0, ratio REAL, data BLOB,"
    " owner INTEGER REFERENCES nobody(id) ON DELETE CASCADE,"
    " created_at TEXT NOT NULL DEFAULT (datetime('now')))"
)


def test_a_table_can_be_created_written_and_read(target) -> None:
    target.execute(TABLE)
    cursor = target.execute(
        "INSERT INTO items (name, count, ratio, data, owner) VALUES (?, ?, ?, ?, ?)",
        ("One", True, 1.5, b"\x00\xff", 999),
    )
    assert cursor.lastrowid == 1
    target.commit()
    row = target.fetchone("SELECT * FROM items WHERE name LIKE ?", ("on%",))
    assert row["count"] == 1
    assert row["ratio"] == 1.5
    assert bytes(row["data"]) == b"\x00\xff"
    assert row["owner"] == 999  # not enforced, as on SQLite
    assert len(row["created_at"]) == 19


def test_numbers_match_text_columns_as_on_sqlite(target) -> None:
    target.execute(TABLE)
    target.execute("INSERT INTO items (name) VALUES (?)", (5,))
    target.commit()
    assert target.fetchone("SELECT name FROM items WHERE name = ?", (5,))["name"] == "5"
    assert target.fetchone("SELECT count(*) AS n FROM items WHERE id = ?", ("1",))["n"] == 1


def test_a_failed_statement_does_not_end_the_transaction(target) -> None:
    target.execute(TABLE)
    target.execute("INSERT INTO items (name) VALUES (?)", ("kept",))
    with pytest.raises(psycopg.errors.UndefinedTable):
        target.execute("INSERT INTO missing (a) VALUES (?)", (1,))
    target.commit()
    assert target.fetchone("SELECT count(*) AS n FROM items")["n"] == 1


def test_rollback_undoes_writes(target) -> None:
    target.execute(TABLE)
    with pytest.raises(ValueError), target.transaction():
        target.execute("INSERT INTO items (name) VALUES (?)", ("gone",))
        raise ValueError
    assert target.fetchone("SELECT count(*) AS n FROM items")["n"] == 0


def test_insert_or_ignore_and_replace(target) -> None:
    target.execute("CREATE TABLE s (key TEXT PRIMARY KEY, value TEXT)")
    target.execute("INSERT OR IGNORE INTO s (key, value) VALUES (?, ?)", ("a", "1"))
    target.execute("INSERT OR IGNORE INTO s (key, value) VALUES (?, ?)", ("a", "2"))
    assert target.fetchone("SELECT value FROM s")["value"] == "1"
    target.execute("INSERT OR REPLACE INTO s (key, value) VALUES (?, ?)", ("a", "3"))
    target.commit()
    assert target.fetchone("SELECT value FROM s")["value"] == "3"


def test_table_helpers(target) -> None:
    target.execute(TABLE)
    assert target.table_exists("items")
    assert not target.table_exists("missing")
    columns = {row["name"]: row for row in target.fetchall("PRAGMA table_info(items)")}
    assert columns["id"]["pk"] == 1
    assert columns["count"]["notnull"] == 1
    assert target.fetchone("PRAGMA foreign_keys")[0] == 0


def test_sums_and_dates(target) -> None:
    target.execute(TABLE)
    target.execute("INSERT INTO items (count) VALUES (?), (?)", (2, 3))
    target.commit()
    assert target.fetchone("SELECT SUM(count) AS n FROM items")["n"] == 5
    assert isinstance(target.fetchone("SELECT julianday('now') AS d")["d"], float)
    assert (
        target.fetchone(
            "SELECT count(*) AS n FROM items WHERE created_at > datetime('now', ?)", ("-1 day",)
        )["n"]
        == 2
    )
    assert "," in target.fetchone("SELECT group_concat(id) AS g FROM items")["g"]


def _sqlite(tmp_path) -> DatabaseConnection:
    source = DatabaseConnection(tmp_path / "entropy.db")
    source.execute(TABLE)
    source.execute("CREATE UNIQUE INDEX idx_items ON items (name, IFNULL(owner, 0))")
    source.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    source.execute(
        "INSERT INTO items (name, data, owner) VALUES ('a', x'00ff', 404), ('b', NULL, 1)"
    )
    source.execute("INSERT INTO settings VALUES ('k', '100% ok?')")
    source.commit()
    return source


def test_copy_then_new_keys_continue(tmp_path, target) -> None:
    source = _sqlite(tmp_path)
    assert copy_database(source, target) == {"items": 2, "settings": 1}
    assert target.fetchone("SELECT value FROM settings WHERE key = 'k'")["value"] == "100% ok?"
    assert bytes(target.fetchone("SELECT data FROM items WHERE name = 'a'")["data"]) == b"\x00\xff"
    assert target.execute("INSERT INTO items (name) VALUES ('c')").lastrowid == 3
    target.commit()
    source.close()


def test_copy_refuses_a_used_target_and_a_failure_leaves_it_empty(tmp_path, target) -> None:
    source = _sqlite(tmp_path)
    source.execute("CREATE TABLE broken (n INTEGER)")
    source.execute("INSERT INTO broken VALUES ('not a number')")
    source.commit()
    with pytest.raises(DatabaseSwitchError, match="broken"):
        copy_database(source, target)
    assert target.fetchone("SELECT 1 FROM sqlite_master WHERE type = 'table'") is None

    source.execute("DROP TABLE broken")
    source.commit()
    copy_database(source, target)
    with pytest.raises(DatabaseSwitchError, match="already has tables"):
        copy_database(source, target)
    source.close()
