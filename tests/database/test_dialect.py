"""SQLite SQL becomes PostgreSQL; text in literals stays as it was written."""

from __future__ import annotations

import pytest

from lib.database.dialect import (
    DialectError,
    is_schema_change,
    split_statements,
    translate,
)


class Catalog:
    def __init__(self, identity=None, key=("id",), columns=("id", "a", "b")):
        self._identity, self._key, self._columns = identity, list(key), list(columns)

    def columns(self, table):
        return self._columns

    def conflict_key(self, table):
        return self._key

    def identity(self, table):
        return self._identity


def sql(text, catalog=None):
    return translate(text, catalog).text


def test_parameters_become_driver_parameters() -> None:
    assert sql("SELECT * FROM t WHERE a = ? AND b = ?") == "SELECT * FROM t WHERE a = %s AND b = %s"


def test_a_question_mark_and_percent_in_a_literal_are_only_escaped_for_the_driver() -> None:
    assert sql("SELECT 'why? 100%' FROM t WHERE a = ?") == "SELECT 'why? 100%%' FROM t WHERE a = %s"


def test_modulo_is_escaped_for_the_driver() -> None:
    assert sql("SELECT a % 2 FROM t") == "SELECT a %% 2 FROM t"


def test_keywords_in_literals_and_quoted_names_are_left_alone() -> None:
    text = sql("SELECT \"LIKE\" FROM t WHERE a = 'datetime(''now'') IFNULL( LIKE'")
    assert text == "SELECT \"LIKE\" FROM t WHERE a = 'datetime(''now'') IFNULL( LIKE'"


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        (
            "CREATE TABLE IF NOT EXISTS a AS SELECT * FROM b WHERE 0",
            "CREATE TABLE IF NOT EXISTS a AS SELECT * FROM b WHERE false",
        ),
        ("SELECT a FROM t WHERE 1 ORDER BY a", "SELECT a FROM t WHERE true ORDER BY a"),
        ("SELECT a FROM t WHERE 1 AND b = ?", "SELECT a FROM t WHERE true AND b = %s"),
        ("SELECT a FROM t WHERE b = ? AND 0", "SELECT a FROM t WHERE b = %s AND false"),
        ("SELECT a FROM t JOIN u ON 1", "SELECT a FROM t JOIN u ON true"),
        ("SELECT a FROM t WHERE (1)", "SELECT a FROM t WHERE (1)"),
    ],
)
def test_a_number_as_a_condition_becomes_a_boolean(written, expected) -> None:
    assert sql(written) == expected


def test_numbers_that_are_not_conditions_are_left_alone() -> None:
    assert sql("SELECT a FROM t WHERE 1 = 1 AND 0 = b") == "SELECT a FROM t WHERE 1 = 1 AND 0 = b"
    assert sql("UPDATE t SET a = 1 WHERE b = 0") == "UPDATE t SET a = 1 WHERE b = 0"
    assert sql("SELECT 1 FROM t WHERE a = 0 OR b = 1") == "SELECT 1 FROM t WHERE a = 0 OR b = 1"


def test_a_blob_literal_stays_a_blob() -> None:
    assert sql("UPDATE t SET a = X'' WHERE b = ?") == "UPDATE t SET a = '\\x'::bytea WHERE b = %s"
    assert sql("SELECT x'00ff'") == "SELECT '\\x00ff'::bytea"
    assert sql("SELECT max'a'") == "SELECT max'a'"


def test_a_parameter_alone_tested_for_null_gets_a_type() -> None:
    assert sql("SELECT CASE WHEN ? IS NULL THEN 1 END") == (
        "SELECT CASE WHEN CAST(%s AS text) IS NULL THEN 1 END"
    )
    assert "CAST(%s AS text) IS NOT NULL" in sql("SELECT 1 WHERE ? IS NOT NULL")


def test_is_with_a_parameter_compares_like_sqlite() -> None:
    assert (
        sql("SELECT 1 FROM t WHERE id IS NOT ?") == "SELECT 1 FROM t WHERE id IS DISTINCT FROM %s"
    )
    assert (
        sql("SELECT 1 FROM t WHERE id IS ?") == "SELECT 1 FROM t WHERE id IS NOT DISTINCT FROM %s"
    )
    assert sql("SELECT 1 FROM t WHERE id IS NOT NULL") == "SELECT 1 FROM t WHERE id IS NOT NULL"


def test_like_ignores_case_as_in_sqlite() -> None:
    assert sql("SELECT 1 FROM t WHERE a LIKE ?") == "SELECT 1 FROM t WHERE a ILIKE %s"
    assert sql("SELECT 1 FROM t WHERE a NOT LIKE ?") == "SELECT 1 FROM t WHERE a NOT ILIKE %s"


def test_now_keeps_sqlites_text_format() -> None:
    text = sql("UPDATE t SET a = datetime('now')")
    assert text == ("UPDATE t SET a = to_char((now() at time zone 'utc'), 'YYYY-MM-DD HH24:MI:SS')")


def test_datetime_with_a_parameter_modifier() -> None:
    text = sql("DELETE FROM t WHERE a < datetime('now', ?)")
    assert "(now() at time zone 'utc') + (%s)::interval" in text


def test_date_of_a_column_and_parameter() -> None:
    text = sql("SELECT 1 FROM t WHERE date(t.due_date) <= date(?)")
    assert "((t.due_date)::timestamptz at time zone 'utc')" in text
    assert "((%s)::timestamptz at time zone 'utc')" in text
    assert "date(" not in text.replace("due_date", "")


def test_strftime_formats() -> None:
    text = sql("SELECT strftime('%Y-%m-%dT%H:%M:%SZ', 'now')")
    assert '\'YYYY"-"MM"-"DD"T"HH24":"MI":"SS"Z"\'' in text
    assert "SS.MS" in sql("SELECT strftime('%H:%M:%f', 'now')")


def test_an_unknown_strftime_format_is_refused() -> None:
    with pytest.raises(DialectError):
        sql("SELECT strftime('%W', 'now')")


def test_julianday_with_a_nested_call() -> None:
    text = sql("SELECT julianday(COALESCE(j.finished_at, CURRENT_TIMESTAMP)) FROM j")
    assert text.startswith("SELECT (extract(epoch from (COALESCE(j.finished_at, to_char(")


def test_functions() -> None:
    assert sql("SELECT IFNULL(a, ?) FROM t") == "SELECT COALESCE(a, %s) FROM t"
    assert (
        sql("SELECT group_concat(g.name, ', ') FROM g")
        == "SELECT string_agg((g.name)::text, ', ') FROM g"
    )
    assert "','" in sql("SELECT group_concat(a) FROM g")


def test_nocase_ordering_and_comparison() -> None:
    assert sql("SELECT a FROM t ORDER BY a COLLATE NOCASE") == "SELECT a FROM t ORDER BY lower(a)"
    assert (
        sql("SELECT 1 FROM t WHERE (name = ? COLLATE NOCASE OR CAST(id AS TEXT) = ?)")
        == "SELECT 1 FROM t WHERE (lower(name) = lower(%s) OR CAST(id AS TEXT) = %s)"
    )


def test_create_table_types_and_keys() -> None:
    text = sql(
        "CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY AUTOINCREMENT, n INT DEFAULT 0,"
        " r REAL, b BLOB, name TEXT COLLATE NOCASE, at TEXT DEFAULT (datetime('now')))"
    )
    assert "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY" in text
    assert "n BIGINT DEFAULT 0" in text
    assert "r DOUBLE PRECISION" in text
    assert "b BYTEA" in text
    assert "name TEXT," in text
    assert "DEFAULT (to_char(" in text


def test_foreign_keys_are_left_out_as_sqlite_never_enforces_them() -> None:
    text = sql(
        "CREATE TABLE t (id INTEGER PRIMARY KEY,"
        " a INTEGER NOT NULL REFERENCES u(id) ON DELETE CASCADE,"
        ' b INTEGER REFERENCES "v",'
        " c INTEGER, FOREIGN KEY (c) REFERENCES w(id) ON DELETE SET NULL ON UPDATE CASCADE,"
        " CONSTRAINT k FOREIGN KEY (a) REFERENCES u(id))"
    )
    assert "REFERENCES" not in text
    assert "FOREIGN" not in text
    assert "a BIGINT NOT NULL," in text
    assert text.rstrip().endswith("c BIGINT)")


def test_add_column_types() -> None:
    assert (
        sql("ALTER TABLE t ADD COLUMN n INTEGER NOT NULL DEFAULT 0")
        == "ALTER TABLE t ADD COLUMN n BIGINT NOT NULL DEFAULT 0"
    )


def test_expression_index() -> None:
    assert (
        sql("CREATE UNIQUE INDEX i ON m (project_id, IFNULL(user_id, 0))")
        == "CREATE UNIQUE INDEX i ON m (project_id, COALESCE(user_id, 0))"
    )


def test_insert_or_ignore() -> None:
    assert (
        sql("INSERT OR IGNORE INTO t (a) VALUES (?);")
        == "INSERT INTO t (a) VALUES (%s) ON CONFLICT DO NOTHING"
    )


@pytest.mark.parametrize("verb", ["INSERT OR REPLACE", "REPLACE"])
def test_insert_or_replace_updates_on_the_key(verb) -> None:
    assert sql(f"{verb} INTO t (id, a) VALUES (?, ?)", Catalog()) == (
        'INSERT INTO t (id, a) VALUES (%s, %s) ON CONFLICT ("id") DO UPDATE SET "a" = EXCLUDED."a"'
    )


def test_replace_without_listed_columns_uses_the_tables_columns() -> None:
    assert '"b" = EXCLUDED."b"' in sql("REPLACE INTO t VALUES (?, ?, ?)", Catalog())


def test_replace_of_only_key_columns_does_nothing_on_conflict() -> None:
    assert sql("REPLACE INTO t (id) VALUES (?)", Catalog()).endswith(
        'ON CONFLICT ("id") DO NOTHING'
    )


def test_replace_needs_the_catalog() -> None:
    with pytest.raises(DialectError):
        sql("REPLACE INTO t (id) VALUES (?)")


def test_an_existing_on_conflict_is_kept() -> None:
    text = sql(
        "INSERT INTO t (id, a) VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET a = excluded.a",
        Catalog(),
    )
    assert text.count("ON CONFLICT") == 1


def test_insert_returns_the_generated_key_for_lastrowid() -> None:
    statement = translate("INSERT INTO t (a) VALUES (?)", Catalog(identity="id"))
    assert statement.returning == "id"
    assert statement.text.endswith('RETURNING "id"')


def test_insert_into_a_table_without_a_generated_key_returns_nothing() -> None:
    statement = translate("INSERT INTO t (a) VALUES (?)", Catalog())
    assert statement.returning is None
    assert "RETURNING" not in statement.text


def test_update_is_not_treated_as_insert() -> None:
    assert translate("UPDATE t SET a = ?", Catalog(identity="id")).returning is None


def test_table_info() -> None:
    text = sql("PRAGMA table_info(Artifacts)")
    assert "c.column_name AS name" in text
    assert 'AS "notnull"' in text  # a reserved word on PostgreSQL
    assert "c.table_name = 'artifacts'" in text
    assert "table_name = 'quoted'" in sql('PRAGMA table_info("quoted")')


def test_foreign_keys_pragma_reports_off() -> None:
    assert sql("PRAGMA foreign_keys") == "SELECT 0 AS foreign_keys"


def test_other_pragmas_do_nothing() -> None:
    assert sql("PRAGMA integrity_check") == "SELECT 1 WHERE false"
    assert sql("PRAGMA journal_mode = WAL") == "SELECT 1 WHERE false"


def test_sqlite_master_reads_the_servers_catalog() -> None:
    text = sql("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?")
    assert "information_schema.tables" in text
    assert "AS sqlite_master WHERE type = 'table' AND name = %s" in text


def test_split_statements_keeps_semicolons_in_literals() -> None:
    assert split_statements("INSERT INTO t VALUES ('a;b'); -- no;\n; SELECT 1;") == [
        "INSERT INTO t VALUES ('a;b')",
        "SELECT 1",
    ]


def test_schema_changes_are_recognised() -> None:
    assert is_schema_change("  create table t (a)")
    assert not is_schema_change("SELECT 'create'")
