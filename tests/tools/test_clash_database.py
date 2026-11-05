"""Clash database compare: generated scripts, parsing and diffs, with SQL*Plus faked."""

from __future__ import annotations

import re
import subprocess
import time
from types import SimpleNamespace
from typing import Dict, List, Tuple
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from core.web.audit import should_audit
from core.web.routes import clash, vision
from lib.tools.clash import database
from lib.tools.clash.database import (
    MAX_ROWS,
    CompareProgress,
    CompareStopped,
    DatabaseCompareError,
    Endpoint,
    compare,
    compare_rows,
    diff_rows,
    estimate_data,
    normalize_ddl,
    run_sqlplus,
)
from lib.tools.clash.jobs import CompareBusy, CompareJobs
from lib.tools.clash.report import render_report
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
        self.stats: Dict[Tuple[str, str], str] = {}
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
            lines += [
                f"{marker}R|{table}|{rows}"
                for (where, table), rows in self.stats.items()
                if where == sid
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


def test_object_types_limit_the_ddl_query() -> None:
    fake = FakeDatabases()

    compare(LEFT, RIGHT, include_data=False, object_types=["VIEW", "TRIGGER"], run=fake)

    listing = next(script for script in fake.scripts if "FROM all_objects" in script)
    assert "object_type IN ('VIEW', 'TRIGGER')" in listing


@pytest.mark.parametrize(
    "options",
    [
        {"object_types": ["TABLE'; DROP"]},
        {"object_types": []},
        # Data is table data: there would be nothing it could compare.
        {"object_types": ["VIEW"], "include_data": True},
    ],
)
def test_object_types_that_cannot_work_are_refused(options) -> None:
    with pytest.raises(DatabaseCompareError):
        compare(LEFT, RIGHT, run=FakeDatabases(), **options)


# What SQL*Plus prints for a statement Oracle will not parse: the line first, so "V|" is there.
ECHOED = (
    "SELECT 'V|' || COUNT(*) || '|' || TO_CHAR(SUM(ORA_HASH(X))) FROM \"APP1\".\"BAD\"\n"
    "                                                                     *\n"
    "ERROR at line 1:\n"
    "ORA-00942: table or view does not exist"
)


def test_an_echoed_parse_error_is_reported_on_the_table_not_raised() -> None:
    fake = FakeDatabases()
    for sid in ("SID1", "SID2"):
        fake.columns[sid].update({"BAD": {"ID": "NUMBER"}, "OK": {"ID": "NUMBER"}})
    fake.hashes.update(
        {
            ("SID1", "BAD"): ECHOED,
            ("SID2", "BAD"): "V|1|1",
            ("SID1", "OK"): "V|1|1",
            ("SID2", "OK"): "V|1|1",
        }
    )

    items = {
        item["table"]: item for item in compare(LEFT, RIGHT, include_ddl=False, run=fake)["data"]
    }

    assert items["BAD"]["status"] == "error" and "ORA-00942" in items["BAD"]["error"]
    assert items["OK"]["status"] == "same"


def test_output_that_is_not_a_hash_is_an_error_on_the_table() -> None:
    fake = FakeDatabases()
    for sid in ("SID1", "SID2"):
        fake.columns[sid]["T"] = {"ID": "NUMBER"}
    fake.hashes.update({("SID1", "T"): "something else", ("SID2", "T"): "V|1|1"})

    item = compare(LEFT, RIGHT, include_ddl=False, run=fake)["data"][0]

    assert item["status"] == "error"


def test_an_empty_table_has_no_hash_and_is_the_same() -> None:
    fake = FakeDatabases()
    for sid in ("SID1", "SID2"):
        fake.columns[sid]["T"] = {"ID": "NUMBER"}
        fake.hashes[(sid, "T")] = "V|0|"

    item = compare(LEFT, RIGHT, include_ddl=False, run=fake)["data"][0]

    assert item["status"] == "same" and item["left_rows"] == 0


def test_a_batch_that_times_out_only_costs_its_own_tables() -> None:
    fake = FakeDatabases()
    for sid in ("SID1", "SID2"):
        fake.columns[sid].update({"BIG": {"ID": "NUMBER"}, "OK": {"ID": "NUMBER"}})
        fake.hashes[(sid, "OK")] = "V|1|1"
        fake.stats[(sid, "BIG")] = str(database.HASH_BATCH_ROWS)
        fake.stats[(sid, "OK")] = "1"

    def run(endpoint, body):
        if '"BIG"' in body and "ORA_HASH" in body:
            raise DatabaseCompareError("SID1-APP1: stopped after 1800 seconds.")
        return fake(endpoint, body)

    items = {
        item["table"]: item for item in compare(LEFT, RIGHT, include_ddl=False, run=run)["data"]
    }

    assert items["BIG"]["status"] == "error" and "1800" in items["BIG"]["error"]
    assert items["OK"]["status"] == "same"


# ----------------------------------------------------------------------
# Estimates and progress
# ----------------------------------------------------------------------


def _table(rows):
    return {"columns": {"ID": "NUMBER"}, "key": [], "rows": rows}


def test_small_known_tables_need_no_consent() -> None:
    estimate = estimate_data({"A": _table(10), "B": _table(5)}, {"A": _table(20), "B": _table(5)})

    assert estimate["rows"] == 25 and not estimate["needs_consent"]
    assert estimate["largest"][0] == {"table": "A", "rows": 20}


def test_many_rows_or_unknown_sizes_need_consent() -> None:
    big = estimate_data({"A": _table(database.CONSENT_ROWS)}, {"A": _table(1)})
    unknown = estimate_data({"A": _table(None)}, {"A": _table(1)})

    assert big["needs_consent"] and big["skippable"] == ["A"] and big["large_count"] == 1
    assert unknown["needs_consent"] and unknown["unknown"] == ["A"]


def test_a_table_on_one_side_is_not_counted() -> None:
    estimate = estimate_data({"A": _table(database.CONSENT_ROWS)}, {})

    assert estimate["tables"] == 0 and not estimate["needs_consent"]


def test_large_tables_are_hashed_alone_and_progress_is_reported() -> None:
    fake = FakeDatabases()
    for sid in ("SID1", "SID2"):
        for table, rows in (("A", "5"), ("B", str(database.HASH_BATCH_ROWS)), ("C", "5")):
            fake.columns[sid][table] = {"ID": "NUMBER"}
            fake.stats[(sid, table)] = rows
            fake.hashes[(sid, table)] = "V|1|1"
    calls = []

    class Recording(CompareProgress):
        def begin(self, phase, total, rows_total=0):
            calls.append(("begin", phase, total, rows_total))

        def step(self, current):
            calls.append(("step", current))

        def advance(self, items, rows=0):
            calls.append(("advance", items, rows))

    compare(LEFT, RIGHT, include_ddl=False, run=fake, progress=Recording())

    size = database.HASH_BATCH_ROWS
    assert calls == [
        ("begin", "data", 3, size + 10),
        ("step", "A"),
        ("advance", 1, 5),
        ("step", "B"),
        ("advance", 1, size),
        ("step", "C"),
        ("advance", 1, 5),
    ]
    assert sum("ORA_HASH" in script for script in fake.scripts) == 6


def test_ddl_is_read_in_batches() -> None:
    fake = FakeDatabases()
    count = database.DDL_BATCH_OBJECTS + 1
    names = [("VIEW", f"V{number:04}") for number in range(count)]
    fake.objects = {"SID1": list(names), "SID2": list(names)}
    for sid in ("SID1", "SID2"):
        fake.ddl.update({(sid, "VIEW", name): "CREATE VIEW;" for _, name in names})

    result = compare(LEFT, RIGHT, include_data=False, run=fake)

    assert {item["status"] for item in result["ddl"]} == {"same"} and len(result["ddl"]) == count
    assert sum("GET_DDL" in script for script in fake.scripts) == 4


def test_stopping_ends_between_batches() -> None:
    class Stopper(CompareProgress):
        def step(self, current):
            raise CompareStopped("stopped")

    fake = FakeDatabases()
    fake.objects["SID1"] = [("TABLE", "T")]

    with pytest.raises(CompareStopped):
        compare(LEFT, RIGHT, include_data=False, run=fake, progress=Stopper())
    assert not any("GET_DDL" in script for script in fake.scripts)


# ----------------------------------------------------------------------
# Background jobs
# ----------------------------------------------------------------------


def _start(jobs, fake, **options):
    values = dict(
        user_id=1,
        project_id=7,
        left=LEFT,
        right=RIGHT,
        sides={"left": {}, "right": {}},
        include_ddl=False,
        run=fake,
    )
    return jobs.start(**{**values, **options})


def _big(fake) -> None:
    for sid in ("SID1", "SID2"):
        fake.columns[sid].update({"BIG": {"ID": "NUMBER"}, "SMALL": {"ID": "NUMBER"}})
        fake.stats[(sid, "BIG")] = str(database.CONSENT_ROWS)
        fake.stats[(sid, "SMALL")] = "5"
        fake.hashes[(sid, "BIG")] = "V|1|1"
        fake.hashes[(sid, "SMALL")] = "V|5|1"


def test_a_small_comparison_runs_without_asking_and_tells_the_person() -> None:
    fake = FakeDatabases()
    _tables(fake)
    for sid in ("SID1", "SID2"):
        for table in ("SAME", "DIFF", "COUNT"):
            fake.stats[(sid, table)] = "2"
    told = []

    job = _start(CompareJobs(), fake, notify=lambda *args: told.append(args))
    job.wait()

    assert job.state == "done"
    assert job.snapshot()["summary"]["data"]["different"] == 2
    assert [item[1] for item in told] == ["Database compare finished"]
    assert told[0][0] == 1 and told[0][4] == f"clash:{job.id}"
    assert "4 differences" in told[0][2]


def test_a_large_comparison_reads_no_table_until_someone_agrees() -> None:
    fake = FakeDatabases()
    _big(fake)

    job = _start(CompareJobs(), fake)
    job.wait()

    assert job.state == "waiting"
    assert job.snapshot()["estimate"]["rows"] == database.CONSENT_ROWS + 5
    assert not any("ORA_HASH" in script for script in fake.scripts)

    job.confirm(skip_large=False)
    job.wait()

    assert job.state == "done"
    assert {item["status"] for item in job.result["data"]} == {"same"}


def test_agreeing_without_the_large_tables_skips_only_them() -> None:
    fake = FakeDatabases()
    _big(fake)

    job = _start(CompareJobs(), fake)
    job.wait()
    job.confirm(skip_large=True)
    job.wait()

    items = {item["table"]: item for item in job.result["data"]}
    assert items["SMALL"]["status"] == "same"
    assert items["BIG"]["status"] == "not_compared" and "Skipped" in items["BIG"]["error"]
    assert not any('"BIG"' in script and "ORA_HASH" in script for script in fake.scripts)


def test_ddl_alone_never_asks() -> None:
    fake = FakeDatabases()
    _big(fake)

    job = _start(CompareJobs(), fake, include_ddl=True, include_data=False)
    job.wait()

    assert job.state == "done" and job.result["data"] is None


def test_stopping_a_waiting_job_ends_it_and_drops_the_credentials() -> None:
    fake = FakeDatabases()
    _big(fake)
    told = []

    job = _start(CompareJobs(), fake, notify=lambda *args: told.append(args))
    job.wait()
    job.stop()

    assert job.state == "stopped" and job._left is None and job._right is None
    assert told == []
    with pytest.raises(DatabaseCompareError):
        job.confirm(skip_large=False)


def test_an_unanswered_job_expires() -> None:
    fake = FakeDatabases()
    _big(fake)
    jobs = CompareJobs()
    job = _start(jobs, fake)
    job.wait()

    job.expire_if_unanswered(time.monotonic() + 2 * 60 * 60)

    assert job.state == "stopped" and "answered" in job.snapshot()["error"]


def test_one_comparison_at_a_time_per_person_and_project() -> None:
    fake = FakeDatabases()
    _big(fake)
    jobs = CompareJobs()

    first = _start(jobs, fake)
    first.wait()

    with pytest.raises(CompareBusy):
        _start(jobs, fake)

    other_project = _start(jobs, fake, project_id=8)
    other_project.wait()
    other_person = _start(jobs, fake, user_id=2)
    other_person.wait()
    assert jobs.current(1, 7) is first

    first.stop()
    second = _start(jobs, fake)
    second.wait()
    assert jobs.current(1, 7) is second


def test_a_connection_failure_fails_the_job_with_its_message() -> None:
    def refuse(endpoint, body):
        raise DatabaseCompareError("SID1-APP1: ORA-01017: invalid login")

    told = []
    job = _start(CompareJobs(), refuse, notify=lambda *args: told.append(args))
    job.wait()

    assert job.state == "failed" and "ORA-01017" in job.snapshot()["error"]
    assert told[0][1] == "Database compare failed" and told[0][3] == "error"


def test_an_unexpected_failure_is_logged_not_shown(caplog) -> None:
    def explode(endpoint, body):
        raise ValueError("secret detail")

    job = _start(CompareJobs(), explode)
    job.wait()

    assert job.state == "failed"
    assert "secret detail" not in job.snapshot()["error"]
    assert "secret detail" in caplog.text


def test_a_snapshot_never_holds_a_password() -> None:
    fake = FakeDatabases()
    _big(fake)

    job = _start(CompareJobs(), fake)
    job.wait()

    assert "secret1" not in str(job.snapshot()) and "secret2" not in str(job.snapshot())
    assert "secret1" not in str(job.brief())


# ----------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------


def test_the_report_escapes_everything_and_shows_differences() -> None:
    result = {
        "left": "SID1-APP1",
        "right": "SID2-APP1",
        "ddl": [
            {
                "type": "VIEW",
                "name": "<b>V",
                "status": "different",
                "left": "a<script>",
                "right": "b",
            },
            {"type": "TABLE", "name": "S", "status": "same"},
            {"type": "TABLE", "name": "L", "status": "only_left", "left": "CREATE L"},
        ],
        "data": [
            {
                "table": "T",
                "status": "not_compared",
                "error": "Skipped: about 5,000,000 rows.",
                "columns_not_compared": ["DOC"],
            },
            {"table": "D", "status": "different", "left_rows": 1000, "right_rows": 2},
        ],
    }

    report = render_report(result, name_filter="ORD%", object_types=["VIEW", "TABLE"])

    assert report.startswith("<!DOCTYPE html>")
    assert "<script" not in report and "<b>V" not in report
    assert "&lt;script&gt;" in report and "&lt;b&gt;V" in report
    assert "CREATE L" in report and "1,000" in report and "Skipped: about 5,000,000" in report
    assert "Names like ORD%" in report and "Object types: VIEW, TABLE" in report
    assert "Columns not compared: DOC" in report


def test_the_report_leaves_out_what_was_not_compared() -> None:
    report = render_report({"left": "A", "right": "B", "ddl": None, "data": []})

    assert "Structure (DDL)" not in report and "No tables matched" in report


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


def _route_request():
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(entropy_context=None)))


def _record(user_id: int = 1):
    return ("token", Mock(), SimpleNamespace(id=user_id, username="someone"))


@pytest.fixture
def routed(monkeypatch):
    """The compare routes with one project and comparisons that wait for an answer."""

    fake = FakeDatabases()
    _big(fake)
    jobs = CompareJobs()
    original = jobs.start

    def start(**options):
        job = original(**{**options, "run": fake})
        job.wait()
        return job

    monkeypatch.setattr(jobs, "start", start)
    monkeypatch.setattr(clash, "JOBS", jobs)
    monkeypatch.setattr(clash, "_project_id", lambda request, user: 7)
    monkeypatch.setattr(
        clash,
        "_endpoint",
        lambda request, user, project_id, side: LEFT if side.sid == "SID1" else RIGHT,
    )
    return jobs


def _payload(**changes):
    values = dict(left=_side(), right=_side(sid="SID2"))
    return clash.CompareRequest(**{**values, **changes})


def test_starting_answers_with_the_job_and_no_credentials(routed) -> None:
    snapshot = clash.start_compare(_payload(ddl=False), _route_request(), _record())

    assert snapshot["state"] == "waiting" and snapshot["estimate"]["needs_consent"]
    assert snapshot["sides"]["right"]["sid"] == "SID2"
    assert "skippable" not in snapshot["estimate"]
    assert "password" not in str(snapshot) and "secret" not in str(snapshot)


def test_a_second_start_is_a_conflict(routed) -> None:
    clash.start_compare(_payload(ddl=False), _route_request(), _record())

    with pytest.raises(HTTPException) as caught:
        clash.start_compare(_payload(ddl=False), _route_request(), _record())

    assert caught.value.status_code == 409


@pytest.mark.parametrize(
    "changes", [{"ddl": False, "data": False}, {"name_filter": "a'b"}, {"object_types": ["NOPE"]}]
)
def test_bad_options_are_refused_before_starting(routed, changes) -> None:
    with pytest.raises(HTTPException) as caught:
        clash.start_compare(_payload(**changes), _route_request(), _record())

    assert caught.value.status_code == 422
    assert routed.current(1, 7) is None


def test_someone_elses_comparison_does_not_exist(routed) -> None:
    job = clash.start_compare(_payload(ddl=False), _route_request(), _record())

    for call in (
        lambda: clash.compare_status(job["id"], _route_request(), _record(2)),
        lambda: clash.stop_compare(job["id"], _route_request(), _record(2)),
        lambda: clash.compare_report(job["id"], _route_request(), _record(2)),
    ):
        with pytest.raises(HTTPException) as caught:
            call()
        assert caught.value.status_code == 404

    assert routed.current(1, 7).state == "waiting"


def test_confirm_result_and_report(routed) -> None:
    job = clash.start_compare(_payload(ddl=False), _route_request(), _record())

    with pytest.raises(HTTPException) as caught:
        clash.compare_result(job["id"], _route_request(), _record())
    assert caught.value.status_code == 409

    clash.confirm_compare(
        job["id"], clash.ConfirmRequest(skip_large=True), _route_request(), _record()
    )
    routed.current(1, 7).wait()

    assert clash.compare_status(job["id"], _route_request(), _record())["state"] == "done"
    assert clash.compare_result(job["id"], _route_request(), _record())["left"] == "SID1-APP1"

    report = clash.compare_report(job["id"], _route_request(), _record())
    assert report.media_type.startswith("text/html")
    assert 'filename="database-compare-SID1-APP1-SID2-APP1.html"' in (
        report.headers["content-disposition"]
    )
    assert b"Skipped" in report.body


def test_vision_shows_only_this_persons_comparison_under_way(monkeypatch) -> None:
    fake = FakeDatabases()
    _big(fake)
    jobs = CompareJobs()
    monkeypatch.setattr(vision, "CLASH_JOBS", jobs)
    project = {"id": 7}
    me = SimpleNamespace(id=1)

    assert vision._clash_compare(project, me) is None

    job = _start(jobs, fake)
    job.wait()

    shown = vision._clash_compare(project, me)
    assert shown["id"] == job.id and shown["state"] == "waiting"
    assert "sides" not in shown and "estimate" not in shown
    assert vision._clash_compare(project, SimpleNamespace(id=2)) is None
    assert vision._clash_compare({"id": 8}, me) is None
    assert vision._clash_compare(None, me) is None

    job.stop()
    assert vision._clash_compare(project, me) is None


def test_the_current_comparison_can_be_picked_up_again(routed) -> None:
    assert clash.current_compare(_route_request(), _record()) == {"job": None}

    job = clash.start_compare(_payload(ddl=False), _route_request(), _record())

    assert clash.current_compare(_route_request(), _record())["job"]["id"] == job["id"]


def test_routes_are_audited_and_discovered() -> None:
    assert should_audit("POST", "/api/clash/database/compare")
    paths = {route.path for route in clash.router.routes}
    assert paths == {
        "/api/clash/database/compare",
        "/api/clash/database/compare/current",
        "/api/clash/database/compare/{job_id}",
        "/api/clash/database/compare/{job_id}/confirm",
        "/api/clash/database/compare/{job_id}/stop",
        "/api/clash/database/compare/{job_id}/result",
        "/api/clash/database/compare/{job_id}/report",
        "/api/clash/database/rows",
    }
