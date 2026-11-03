"""Clash database compare: generated scripts, parsing and diffs, with SQL*Plus faked."""

from __future__ import annotations

import re
import subprocess
from types import SimpleNamespace
from typing import Dict, List, Tuple
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from core.web.audit import should_audit
from core.web.routes import clash
from lib.tools.clash import database
from lib.tools.clash.database import (
    MAX_ROWS,
    DatabaseCompareError,
    Endpoint,
    compare,
    compare_rows,
    diff_rows,
    normalize_ddl,
    run_sqlplus,
)
from lib.vault.exceptions import VaultError

LEFT = Endpoint("db1", 1521, "SID1", "reader", "secret1", "app1")
RIGHT = Endpoint("db2", 1521, "SID2", "reader", "secret2", "app1")


class FakeDatabases:
    """Answers the generated scripts the way SQL*Plus prints them, and records them."""

    def __init__(self) -> None:
        self.objects: Dict[str, List[Tuple[str, str]]] = {"SID1": [], "SID2": []}
        self.ddl: Dict[Tuple[str, str, str], str] = {}
        self.columns: Dict[str, Dict[str, Dict[str, str]]] = {"SID1": {}, "SID2": {}}
        self.keys: Dict[str, Dict[str, List[str]]] = {"SID1": {}, "SID2": {}}
        self.hashes: Dict[Tuple[str, str], str] = {}
        self.rows: Dict[Tuple[str, str], str] = {}
        self.scripts: List[str] = []

    def __call__(self, endpoint: Endpoint, body: str) -> str:
        self.scripts.append(body)
        sid = endpoint.sid

        if "FROM all_objects" in body:
            marker = re.search(r"SELECT '(#\w+#)'", body).group(1)
            return "".join(f"{marker}{kind}|{name}\n" for kind, name in self.objects[sid])

        if "FROM all_tables" in body:
            marker = re.search(r"SELECT '(#\w+#)'", body).group(1)
            lines = [
                f"{marker}C|{table}|{column}|{kind}"
                for table, columns in self.columns[sid].items()
                for column, kind in columns.items()
            ]
            lines += [
                f"{marker}K|{table}|{column}"
                for table, key in self.keys[sid].items()
                for column in key
            ]
            return "\n".join(lines) + "\n"

        output: List[str] = []

        if "MARKUP CSV" in body:
            table = re.search(r'FROM "APP1"\."(\w+)"', body).group(1)
            return self.rows.get((sid, table), "")

        for line in body.splitlines():
            found = re.match(r"PROMPT (#\w+#)(.*)", line)
            if found:
                output.append(found.group(1) + found.group(2))
                title = found.group(2)
                if "GET_DDL" in body:
                    kind, _, name = title.partition("|")
                    output.append(self.ddl.get((sid, kind, name), "ORA-31603: object not found"))
                else:
                    output.append(self.hashes.get((sid, title), "ORA-00942: no such table"))

        return "\n".join(output) + "\n"


@pytest.mark.parametrize(
    "changes",
    [
        {"host": "db1;drop"},
        {"port": 70000},
        {"sid": "a b"},
        {"username": 'x"/y'},
        {"schema": "a.b"},
        {"password": 'has"quote'},
        {"password": "two\nlines"},
        {"password": ""},
    ],
)
def test_values_that_would_change_the_script_are_refused(changes) -> None:
    values = dict(host="db", port=1521, sid="S", username="u", password="p", schema="APP1")
    with pytest.raises(DatabaseCompareError):
        Endpoint(**{**values, **changes})


def test_normalize_removes_what_only_differs_by_environment() -> None:
    one = 'CREATE TABLE "APP1"."T"  \n ( CONSTRAINT "SYS_C0012" PRIMARY KEY ("ID"));\n\n'
    other = 'CREATE TABLE "APP2"."T"\n ( CONSTRAINT "SYS_C9931" PRIMARY KEY ("ID"));'

    assert normalize_ddl(one, "APP1") == normalize_ddl(other, "APP2")
    assert normalize_ddl('CONSTRAINT "PK_T"', "APP1") == 'CONSTRAINT "PK_T"'


def test_a_sequence_start_value_is_not_a_difference() -> None:
    one = 'CREATE SEQUENCE "S" MINVALUE 1 START WITH 100 CACHE 20'
    other = 'CREATE SEQUENCE "S" MINVALUE 1 START WITH 900 CACHE 20'

    assert normalize_ddl(one, "A", "SEQUENCE") == normalize_ddl(other, "A", "SEQUENCE")
    assert normalize_ddl(one, "A", "VIEW") != normalize_ddl(other, "A", "VIEW")


def test_ddl_statuses() -> None:
    fake = FakeDatabases()
    fake.objects["SID1"] = [("TABLE", "A"), ("VIEW", "B"), ("TABLE", "L"), ("TABLE", "E")]
    fake.objects["SID2"] = [("TABLE", "A"), ("VIEW", "B"), ("TABLE", "R"), ("TABLE", "E")]
    fake.ddl.update(
        {
            ("SID1", "TABLE", "A"): 'CREATE TABLE "APP1"."A" (X NUMBER);',
            ("SID2", "TABLE", "A"): 'CREATE TABLE "APP1"."A" (X NUMBER);',
            ("SID1", "VIEW", "B"): "CREATE VIEW B AS SELECT 1 FROM dual;",
            ("SID2", "VIEW", "B"): "CREATE VIEW B AS SELECT 2 FROM dual;",
            ("SID1", "TABLE", "L"): "CREATE TABLE L;",
            ("SID2", "TABLE", "R"): "CREATE TABLE R;",
            ("SID1", "TABLE", "E"): "ERROR:\nORA-31603: object not found",
            ("SID2", "TABLE", "E"): "CREATE TABLE E;",
        }
    )

    result = compare(LEFT, RIGHT, include_data=False, run=fake)

    items = {item["name"]: item for item in result["ddl"]}
    assert {name: item["status"] for name, item in items.items()} == {
        "A": "same",
        "B": "different",
        "L": "only_left",
        "R": "only_right",
        "E": "error",
    }
    assert "SELECT 1" in items["B"]["left"] and "SELECT 2" in items["B"]["right"]
    assert "ORA-31603" in items["E"]["error"]
    # Text of an identical object is not sent to the browser.
    assert "left" not in items["A"]
    assert result["data"] is None and result["left"] == "SID1-APP1"


def _tables(fake: FakeDatabases) -> None:
    columns = {"ID": "NUMBER", "NAME": "VARCHAR2", "DOC": "CLOB"}
    for sid in ("SID1", "SID2"):
        for table in ("SAME", "DIFF", "COUNT"):
            fake.columns[sid][table] = dict(columns)
            fake.keys[sid][table] = ["ID"]
    fake.columns["SID1"]["L"] = {"ID": "NUMBER"}
    fake.columns["SID2"]["R"] = {"ID": "NUMBER"}
    fake.hashes.update(
        {
            ("SID1", "SAME"): "V|2|100",
            ("SID2", "SAME"): "V|2|100",
            ("SID1", "DIFF"): "V|2|100",
            ("SID2", "DIFF"): "V|2|999",
            ("SID1", "COUNT"): "V|2|100",
            ("SID2", "COUNT"): "V|3|100",
        }
    )


def test_data_is_compared_by_count_and_hash_without_reading_rows() -> None:
    fake = FakeDatabases()
    _tables(fake)

    items = {
        item["table"]: item for item in compare(LEFT, RIGHT, include_ddl=False, run=fake)["data"]
    }

    assert {name: item["status"] for name, item in items.items()} == {
        "COUNT": "different",
        "DIFF": "different",
        "L": "only_left",
        "R": "only_right",
        "SAME": "same",
    }
    assert items["DIFF"]["left_rows"] == 2 and items["COUNT"]["right_rows"] == 3
    assert items["SAME"]["columns_not_compared"] == ["DOC"]
    assert not any("SELECT *" in script for script in fake.scripts)
    hashing = next(script for script in fake.scripts if "ORA_HASH" in script)
    # Read only, and the LOB column stays out of the hash.
    assert "SET TRANSACTION READ ONLY;" in hashing
    assert '"DOC"' not in hashing


def test_columns_on_one_side_are_reported_and_shared_ones_compared() -> None:
    fake = FakeDatabases()
    fake.columns["SID1"]["T"] = {"ID": "NUMBER", "OLD": "DATE"}
    fake.columns["SID2"]["T"] = {"ID": "NUMBER", "NEW": "DATE"}
    fake.hashes.update({("SID1", "T"): "V|1|5", ("SID2", "T"): "V|1|5"})

    item = compare(LEFT, RIGHT, include_ddl=False, run=fake)["data"][0]

    assert item["status"] == "same"
    assert item["columns_only_left"] == ["OLD"] and item["columns_only_right"] == ["NEW"]


def test_a_table_only_with_lobs_is_not_compared() -> None:
    fake = FakeDatabases()
    for sid in ("SID1", "SID2"):
        fake.columns[sid]["T"] = {"DOC": "BLOB"}

    item = compare(LEFT, RIGHT, include_ddl=False, run=fake)["data"][0]

    assert item["status"] == "not_compared"


def test_a_table_that_cannot_be_read_does_not_stop_the_others() -> None:
    fake = FakeDatabases()
    for sid in ("SID1", "SID2"):
        fake.columns[sid].update({"BAD": {"ID": "NUMBER"}, "OK": {"ID": "NUMBER"}})
    fake.hashes.update(
        {
            ("SID1", "OK"): "V|1|1",
            ("SID2", "OK"): "V|1|1",
            ("SID1", "BAD"): "ERROR at line 1:\nORA-01031: insufficient privileges",
            ("SID2", "BAD"): "V|1|1",
        }
    )

    items = {
        item["table"]: item for item in compare(LEFT, RIGHT, include_ddl=False, run=fake)["data"]
    }

    assert items["OK"]["status"] == "same"
    assert items["BAD"]["status"] == "error" and "ORA-01031" in items["BAD"]["error"]


def test_an_invalid_name_filter_is_refused() -> None:
    with pytest.raises(DatabaseCompareError):
        compare(LEFT, RIGHT, name_filter="A' OR '1'='1", run=FakeDatabases())


def test_name_filter_reaches_the_queries_in_upper_case() -> None:
    fake = FakeDatabases()

    compare(LEFT, RIGHT, name_filter="ord%", run=fake)

    assert any("object_name LIKE 'ORD%'" in script for script in fake.scripts)
    assert any("t.table_name LIKE 'ORD%'" in script for script in fake.scripts)


# ----------------------------------------------------------------------
# Rows
# ----------------------------------------------------------------------


COLUMNS = ["ID", "NAME"]


def test_rows_by_key() -> None:
    result = diff_rows(
        COLUMNS,
        ["ID"],
        [["1", "a"], ["2", "b"], ["3", "c"]],
        [["1", "a"], ["2", "B"], ["4", "d"]],
    )

    assert result["same"] == 1
    assert result["only_left"] == [["3", "c"]] and result["only_right"] == [["4", "d"]]
    assert result["changed"] == [
        {"key": ["2"], "left": ["2", "b"], "right": ["2", "B"], "columns": ["NAME"]}
    ]
    assert not result["truncated"]


def test_rows_without_a_key_count_duplicates() -> None:
    result = diff_rows(
        COLUMNS,
        [],
        [["1", "a"], ["1", "a"], ["2", "b"]],
        [["1", "a"], ["2", "x"]],
    )

    assert result["same"] == 1 and result["changed"] == []
    assert sorted(result["only_left"]) == [["1", "a"], ["2", "b"]]
    assert result["only_right"] == [["2", "x"]]


def test_a_cut_off_side_does_not_report_unread_rows_as_missing() -> None:
    # Left has rows beyond the limit; right has keys that sort after what left returned.
    left = [[str(number), "a"] for number in range(MAX_ROWS + 1)]
    right = [[str(number), "a"] for number in range(MAX_ROWS - 1)] + [[str(MAX_ROWS + 50), "a"]]

    result = diff_rows(COLUMNS, ["ID"], left, right)

    assert result["truncated"]
    assert result["only_right"] == [] and result["only_left"] == []
    assert result["same"] == MAX_ROWS - 1


def test_reported_rows_are_capped_but_counted() -> None:
    left = [[str(number), "a"] for number in range(database.MAX_REPORTED_ROWS + 5)]

    result = diff_rows(COLUMNS, ["ID"], left, [])

    assert result["only_left_count"] == database.MAX_REPORTED_ROWS + 5
    assert len(result["only_left"]) == database.MAX_REPORTED_ROWS


def test_compare_rows_reads_shared_comparable_columns_in_key_order() -> None:
    fake = FakeDatabases()
    for sid in ("SID1", "SID2"):
        fake.columns[sid]["T_1"] = {"ID": "NUMBER", "NOTE": "VARCHAR2", "DOC": "CLOB"}
        fake.keys[sid]["T_1"] = ["ID"]
    fake.rows[("SID1", "T_1")] = '"1","two\nlines"\n"2","b"\n'
    fake.rows[("SID2", "T_1")] = '"1","two\nlines"\n"2","B, c"\n'

    result = compare_rows(LEFT, RIGHT, "t_1", run=fake)

    assert result["table"] == "T_1" and result["columns"] == ["ID", "NOTE"]
    assert result["same"] == 1
    assert result["changed"][0]["right"] == ["2", "B, c"]
    script = next(script for script in fake.scripts if "MARKUP CSV" in script)
    assert 'ORDER BY "ID"' in script and "SET TRANSACTION READ ONLY;" in script
    assert f"ROWNUM <= {MAX_ROWS + 1}" in script


@pytest.mark.parametrize("table", ["MISSING", "a b", "x;drop"])
def test_compare_rows_refuses_unknown_or_invalid_tables(table: str) -> None:
    with pytest.raises(DatabaseCompareError):
        compare_rows(LEFT, RIGHT, table, run=FakeDatabases())


def test_every_generated_script_only_reads() -> None:
    fake = FakeDatabases()
    fake.objects["SID1"] = [("TABLE", "T")]
    _tables(fake)
    compare(LEFT, RIGHT, run=fake)
    compare_rows(LEFT, RIGHT, "DIFF", run=fake)

    forbidden = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|TRUNCATE|CREATE|GRANT)\b", re.I)
    for script in fake.scripts:
        assert not forbidden.search(script), script


# ----------------------------------------------------------------------
# SQL*Plus
# ----------------------------------------------------------------------


def _completed(code: int, stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], code, stdout=stdout, stderr="")


def test_password_goes_through_stdin_never_the_command_line(monkeypatch) -> None:
    calls = {}

    def fake_run(command, **options):
        calls.update(command=command, **options)
        return _completed(0, "done")

    monkeypatch.setattr(database.shutil, "which", lambda name: "/bin/sqlplus")
    monkeypatch.delenv("ORACLE_HOME", raising=False)
    monkeypatch.setattr(database.subprocess, "run", fake_run)

    assert run_sqlplus(LEFT, "SELECT 1 FROM dual;") == "done"

    assert "secret1" not in " ".join(calls["command"])
    assert calls["command"][-1] == "/nolog"
    assert 'CONNECT reader/"secret1"@//db1:1521/SID1' in calls["input"]
    assert calls["input"].index("WHENEVER SQLERROR EXIT") < calls["input"].index("CONNECT")


def test_a_failure_reports_the_oracle_error_without_the_password(monkeypatch) -> None:
    monkeypatch.setattr(database.shutil, "which", lambda name: "/bin/sqlplus")
    monkeypatch.delenv("ORACLE_HOME", raising=False)
    monkeypatch.setattr(
        database.subprocess,
        "run",
        lambda command, **options: _completed(1, "secret1 failed\nORA-01017: invalid login\n"),
    )

    with pytest.raises(DatabaseCompareError) as caught:
        run_sqlplus(LEFT, "SELECT 1 FROM dual;")

    assert str(caught.value) == "SID1-APP1: ORA-01017: invalid login"


def test_no_sqlplus_says_so(monkeypatch) -> None:
    monkeypatch.setattr(database.shutil, "which", lambda name: None)
    monkeypatch.delenv("ORACLE_HOME", raising=False)

    with pytest.raises(DatabaseCompareError, match="SQL\\*Plus was not found"):
        run_sqlplus(LEFT, "SELECT 1 FROM dual;")


# ----------------------------------------------------------------------
# Route: credentials from the project's Vault
# ----------------------------------------------------------------------


class _Namespaces:
    def get(self, name: str, project_id: int):
        if name != "db" or project_id != 7:
            raise VaultError("not in this project")
        return SimpleNamespace(id=1)


class _Values:
    def __init__(self, value) -> None:
        self.value = value

    def get(self, namespace_id: int, key: str):
        if key != "app1":
            raise VaultError("no such key")
        return self.value


def _side(**changes):
    values = dict(host="db1", port=1521, sid="SID1", schema_name="APP1", namespace="db", key="app1")
    return clash.SideRequest(**{**values, **changes})


@pytest.fixture
def vault(monkeypatch):
    """Vault routes' helpers, with the value to return and the permissions checked."""

    state = SimpleNamespace(value='{"username": "reader", "password": "pw"}', checked=[])

    def require(request, user, permission, project_id):
        state.checked.append((permission, project_id))

    monkeypatch.setattr("core.web.routes.vault._require", require)
    monkeypatch.setattr(
        "core.web.routes.vault._vault_components",
        lambda request: (_Values(state.value), _Namespaces()),
    )
    return state


def test_credentials_need_vault_read_in_the_project(vault) -> None:
    endpoint = clash._endpoint(Mock(), Mock(), 7, _side())

    assert vault.checked == [("vault.read", 7)]
    assert (endpoint.username, endpoint.password, endpoint.owner) == ("reader", "pw", "APP1")


def test_no_vault_read_stops_before_any_value_is_read(monkeypatch, vault) -> None:
    def refuse(request, user, permission, project_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    monkeypatch.setattr("core.web.routes.vault._require", refuse)
    monkeypatch.setattr(
        "core.web.routes.vault._vault_components",
        lambda request: pytest.fail("the vault was read without permission"),
    )

    with pytest.raises(HTTPException) as caught:
        clash._endpoint(Mock(), Mock(), 7, _side())

    assert caught.value.status_code == 403


@pytest.mark.parametrize("project,side", [(8, {}), (7, {"namespace": "other"}), (7, {"key": "no"})])
def test_a_reference_outside_the_project_is_not_found(vault, project, side) -> None:
    with pytest.raises(HTTPException) as caught:
        clash._endpoint(Mock(), Mock(), project, _side(**side))

    assert caught.value.status_code == 404


@pytest.mark.parametrize(
    "value", ["not json", "[1]", '{"username": "u"}', '{"username": "u", "password": 1}']
)
def test_a_badly_formed_value_is_refused_without_showing_it(vault, value) -> None:
    vault.value = value

    with pytest.raises(HTTPException) as caught:
        clash._endpoint(Mock(), Mock(), 7, _side())

    assert caught.value.status_code == 422
    assert value not in caught.value.detail


def test_an_object_value_is_accepted(vault) -> None:
    vault.value = {"username": "reader", "password": "pw"}

    assert clash._endpoint(Mock(), Mock(), 7, _side()).username == "reader"


def test_routes_are_audited_and_discovered() -> None:
    assert should_audit("POST", "/api/clash/database/compare")
    paths = {route.path for route in clash.router.routes}
    assert paths == {"/api/clash/database/compare", "/api/clash/database/rows"}
