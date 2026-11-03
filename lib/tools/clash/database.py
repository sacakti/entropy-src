"""
Compare one schema in two Oracle databases, through SQL*Plus.

DDL comes from DBMS_METADATA, normalized so a schema name, a tablespace or a
system-generated constraint name is not reported as a difference. Data is compared with
a row count and a hash per table, so no row leaves the database until someone opens a
table; `compare_rows` then reads up to MAX_ROWS rows from each side.

Everything sent to SQL*Plus is generated here and only reads. The password goes through
stdin, never the command line. Names and passwords are checked first, because a script
is plain text.
"""

from __future__ import annotations

import csv
import io
import os
import re
import secrets
import shutil
import subprocess  # nosec B404 - runs sqlplus with an argument list
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from core.exceptions import EntropyException

Runner = Callable[["Endpoint", str], str]

# GET_DDL's name for each object type compared.
OBJECT_TYPES = {
    "TABLE": "TABLE",
    "VIEW": "VIEW",
    "MATERIALIZED VIEW": "MATERIALIZED_VIEW",
    "SEQUENCE": "SEQUENCE",
    "INDEX": "INDEX",
    "TRIGGER": "TRIGGER",
    "SYNONYM": "SYNONYM",
    "PROCEDURE": "PROCEDURE",
    "FUNCTION": "FUNCTION",
    "PACKAGE": "PACKAGE_SPEC",
    "PACKAGE BODY": "PACKAGE_BODY",
    "TYPE": "TYPE_SPEC",
    "TYPE BODY": "TYPE_BODY",
}

# ORA_HASH and a plain SELECT handle these; LOBs, LONG and object types are reported.
COMPARABLE_TYPES = (
    "VARCHAR2",
    "NVARCHAR2",
    "CHAR",
    "NCHAR",
    "NUMBER",
    "FLOAT",
    "BINARY_FLOAT",
    "BINARY_DOUBLE",
    "DATE",
    "RAW",
    "TIMESTAMP",
    "INTERVAL",
)

# Each column adds up to 11 characters to a VARCHAR2 expression limited to 4000.
MAX_HASHED_COLUMNS = 360
MAX_ROWS = 5000
MAX_REPORTED_ROWS = 500
TIMEOUT_SECONDS = 1800

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]{0,127}$")
_HOST = re.compile(r"^[A-Za-z0-9._:\[\]-]{1,255}$")
_SID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_FILTER = re.compile(r"^[A-Za-z0-9_$#%]{1,128}$")
_ERROR_START = re.compile(r"^(ERROR( at line \d+)?:|ORA-\d+:|SP2-\d+:)")
_ERROR_LINE = re.compile(r"^(ORA-\d+:|SP2-\d+:).*$", re.MULTILINE)
_SYSTEM_NAME = re.compile(r'"SYS_(C|IL|LOB|NC|FK)[0-9A-Z$_]*"')
_SEQUENCE_START = re.compile(r"\s+START WITH \d+")


class DatabaseCompareError(EntropyException):
    """The comparison could not run; the message is safe to show."""


@dataclass(frozen=True)
class Endpoint:
    """One side of the comparison."""

    host: str
    port: int
    sid: str
    username: str
    password: str
    schema: str

    def __post_init__(self) -> None:
        if not _HOST.match(self.host):
            raise DatabaseCompareError(f"'{self.host}' is not a valid host.")
        if not 0 < int(self.port) < 65536:
            raise DatabaseCompareError(f"'{self.port}' is not a valid port.")
        if not _SID.match(self.sid):
            raise DatabaseCompareError(f"'{self.sid}' is not a valid SID.")
        if not _NAME.match(self.username):
            raise DatabaseCompareError("The vault entry has an invalid username.")
        if not _NAME.match(self.schema):
            raise DatabaseCompareError(f"'{self.schema}' is not a valid schema name.")
        # The password sits between double quotes in a script line.
        if not self.password or any(item in self.password for item in ('"', "\n", "\r")):
            raise DatabaseCompareError(
                "The vault entry's password is empty or has a quote or line break.",
            )

    @property
    def owner(self) -> str:
        return self.schema.upper()

    @property
    def label(self) -> str:
        return f"{self.sid}-{self.owner}"


# ----------------------------------------------------------------------
# SQL*Plus
# ----------------------------------------------------------------------


def sqlplus_path() -> str:
    """ORACLE_HOME's sqlplus, else the one on PATH."""

    home = os.environ.get("ORACLE_HOME")
    candidate = Path(home) / "bin" / "sqlplus" if home else None
    found = str(candidate) if candidate and candidate.is_file() else shutil.which("sqlplus")
    if not found:
        raise DatabaseCompareError(
            "SQL*Plus was not found on the Entropy server: install it, or set ORACLE_HOME.",
        )
    return found


def run_sqlplus(endpoint: Endpoint, body: str) -> str:
    """Run a generated script and return its output; a failure raises."""

    script = "\n".join(
        [
            "WHENEVER OSERROR EXIT FAILURE",
            "WHENEVER SQLERROR EXIT FAILURE",
            "SET ECHO OFF TERMOUT ON FEEDBACK OFF VERIFY OFF DEFINE OFF SERVEROUTPUT OFF",
            f'CONNECT {endpoint.username}/"{endpoint.password}"'
            f"@//{endpoint.host}:{endpoint.port}/{endpoint.sid}",
            "SET HEADING OFF PAGESIZE 0 TAB OFF TRIMOUT ON TRIMSPOOL ON",
            "SET LINESIZE 32767 LONG 2000000000 LONGCHUNKSIZE 32767 WRAP ON",
            body,
            "EXIT",
            "",
        ]
    )

    # UTF-8 from both databases, so the same text compares equal.
    environment = {**os.environ, "NLS_LANG": "AMERICAN_AMERICA.AL32UTF8"}

    try:
        result = subprocess.run(  # nosec B603 - an argument list, nothing from the user
            [sqlplus_path(), "-S", "-L", "/nolog"],
            input=script,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
            env=environment,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise DatabaseCompareError(
            f"{endpoint.label}: stopped after {TIMEOUT_SECONDS} seconds. Compare fewer objects.",
        ) from None
    except OSError as exc:
        raise DatabaseCompareError(f"Unable to start SQL*Plus: {exc.strerror}.") from None

    if result.returncode != 0:
        output = (result.stdout + result.stderr).replace(endpoint.password, "***")
        found = _ERROR_LINE.search(output)
        detail = found.group(0) if found else output.strip()[-300:]
        raise DatabaseCompareError(f"{endpoint.label}: {detail}")

    return result.stdout


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _sections(output: str, marker: str) -> Iterable[Tuple[str, str]]:
    """The (title, text) pairs of output split by lines starting with `marker`."""

    title: Optional[str] = None
    lines: List[str] = []

    for line in output.splitlines():
        if line.startswith(marker):
            if title is not None:
                yield title, "\n".join(lines)
            title, lines = line[len(marker) :].strip(), []
        elif title is not None:
            lines.append(line)

    if title is not None:
        yield title, "\n".join(lines)


def _section_error(text: str) -> Optional[str]:
    """The error of a section that failed, which starts with the error."""

    stripped = text.strip()
    if not _ERROR_START.match(stripped):
        return None
    found = _ERROR_LINE.search(stripped)
    return found.group(0) if found else stripped.splitlines()[0]


def _on_both(left: Endpoint, right: Endpoint, task: Callable[[Endpoint], Any]) -> Tuple[Any, Any]:
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(task, left), pool.submit(task, right)
        return first.result(), second.result()


# ----------------------------------------------------------------------
# DDL
# ----------------------------------------------------------------------


def normalize_ddl(text: str, owner: str, object_type: str = "") -> str:
    """Remove what differs between environments without being a schema difference."""

    text = text.replace(f'"{owner}".', "")
    text = _SYSTEM_NAME.sub('"SYS_GENERATED"', text)
    if object_type == "SEQUENCE":
        # The next value depends on use, not on the definition.
        text = _SEQUENCE_START.sub("", text)
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines).strip()


def list_objects(
    endpoint: Endpoint, name_filter: Optional[str], run: Runner
) -> List[Tuple[str, str]]:
    marker = f"#{secrets.token_hex(8)}#"
    types = ", ".join(_literal(item) for item in OBJECT_TYPES)
    pattern = f" AND object_name LIKE {_literal(name_filter.upper())}" if name_filter else ""
    output = run(
        endpoint,
        f"SELECT {_literal(marker)} || object_type || '|' || object_name FROM all_objects"
        f" WHERE owner = {_literal(endpoint.owner)} AND object_type IN ({types})"
        f" AND generated = 'N' AND temporary = 'N' AND object_name NOT LIKE 'BIN$%'{pattern}"
        " ORDER BY object_type, object_name;",
    )
    objects = []
    for line in output.splitlines():
        if line.startswith(marker):
            object_type, _, name = line[len(marker) :].strip().partition("|")
            objects.append((object_type, name))
    return objects


def read_ddl(
    endpoint: Endpoint, objects: Sequence[Tuple[str, str]], run: Runner
) -> Dict[Tuple[str, str], Dict[str, str]]:
    """Each object's DDL, or the error of reading it: one object does not stop the rest."""

    if not objects:
        return {}

    marker = f"#{secrets.token_hex(8)}#"
    settings = "\n".join(
        "  DBMS_METADATA.SET_TRANSFORM_PARAM("
        f"DBMS_METADATA.SESSION_TRANSFORM, '{name}', {value});"
        for name, value in (
            ("SEGMENT_ATTRIBUTES", "FALSE"),
            ("STORAGE", "FALSE"),
            ("TABLESPACE", "FALSE"),
            ("PRETTY", "TRUE"),
            ("SQLTERMINATOR", "TRUE"),
        )
    )
    statements = ["BEGIN", settings, "END;", "/", "WHENEVER SQLERROR CONTINUE"]

    for object_type, name in objects:
        statements.append(f"PROMPT {marker}{object_type}|{name}")
        statements.append(
            f"SELECT DBMS_METADATA.GET_DDL({_literal(OBJECT_TYPES[object_type])},"
            f" {_literal(name)}, {_literal(endpoint.owner)}) FROM dual;"
        )

    result: Dict[Tuple[str, str], Dict[str, str]] = {}

    for title, text in _sections(run(endpoint, "\n".join(statements)), marker):
        object_type, _, name = title.partition("|")
        error = _section_error(text)
        result[(object_type, name)] = (
            {"error": error} if error else {"ddl": normalize_ddl(text, endpoint.owner, object_type)}
        )

    return result


def compare_ddl(
    left: Endpoint, right: Endpoint, name_filter: Optional[str], run: Runner
) -> List[Dict[str, Any]]:
    left_objects, right_objects = _on_both(
        left, right, lambda side: list_objects(side, name_filter, run)
    )
    left_ddl, right_ddl = _on_both(
        left,
        right,
        lambda side: read_ddl(side, left_objects if side is left else right_objects, run),
    )

    items: List[Dict[str, Any]] = []

    for key in sorted(set(left_objects) | set(right_objects)):
        one, other = left_ddl.get(key), right_ddl.get(key)
        item: Dict[str, Any] = {"type": key[0], "name": key[1]}

        if one is None or other is None:
            present = one or other or {}
            item["status"] = "only_left" if one else "only_right"
            item["left" if one else "right"] = present.get("ddl", "")
            if present.get("error"):
                item["error"] = present["error"]
        elif one.get("error") or other.get("error"):
            item["status"] = "error"
            item["error"] = one.get("error") or other.get("error")
        elif one["ddl"] == other["ddl"]:
            item["status"] = "same"
        else:
            item.update(status="different", left=one["ddl"], right=other["ddl"])

        items.append(item)

    return items


# ----------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------


def _is_comparable(data_type: str) -> bool:
    return data_type.upper().startswith(COMPARABLE_TYPES)


def read_tables(
    endpoint: Endpoint, name_filter: Optional[str], run: Runner
) -> Dict[str, Dict[str, Any]]:
    """Each table's columns ({name: type}) and primary key columns, in order."""

    marker = f"#{secrets.token_hex(8)}#"
    owner = _literal(endpoint.owner)
    pattern = f" AND t.table_name LIKE {_literal(name_filter.upper())}" if name_filter else ""
    output = run(
        endpoint,
        f"""SELECT {_literal(marker)} || 'C|' || t.table_name || '|' || c.column_name || '|'
       || c.data_type
FROM all_tables t JOIN all_tab_columns c ON c.owner = t.owner AND c.table_name = t.table_name
WHERE t.owner = {owner} AND t.temporary = 'N' AND t.secondary = 'N' AND t.nested = 'NO'
  AND t.dropped = 'NO'{pattern}
ORDER BY t.table_name, c.column_id;
SELECT {_literal(marker)} || 'K|' || k.table_name || '|' || k.column_name
FROM all_constraints p JOIN all_cons_columns k
  ON k.owner = p.owner AND k.constraint_name = p.constraint_name
WHERE p.owner = {owner} AND p.constraint_type = 'P'
ORDER BY k.table_name, k.position;""",
    )

    tables: Dict[str, Dict[str, Any]] = {}

    for line in output.splitlines():
        if not line.startswith(marker):
            continue
        fields = line[len(marker) :].strip().split("|")
        if fields[0] == "C" and len(fields) == 4:
            table = tables.setdefault(fields[1], {"columns": {}, "key": []})
            table["columns"][fields[2]] = fields[3]
        elif fields[0] == "K" and len(fields) == 3 and fields[1] in tables:
            tables[fields[1]]["key"].append(fields[2])

    return tables


def _read_only_session() -> List[str]:
    """Same formats and sort order on both sides; a consistent, read-only snapshot."""

    return [
        "ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD\"T\"HH24:MI:SS';",
        "ALTER SESSION SET NLS_TIMESTAMP_FORMAT = 'YYYY-MM-DD\"T\"HH24:MI:SS.FF9';",
        "ALTER SESSION SET NLS_TIMESTAMP_TZ_FORMAT = 'YYYY-MM-DD\"T\"HH24:MI:SS.FF9 TZH:TZM';",
        "ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';",
        "ALTER SESSION SET NLS_SORT = BINARY;",
        "ALTER SESSION SET NLS_COMP = BINARY;",
        "SET TRANSACTION READ ONLY;",
    ]


def read_hashes(
    endpoint: Endpoint, columns: Dict[str, List[str]], run: Runner
) -> Dict[str, Dict[str, Any]]:
    """Each table's row count and a hash of its rows that ignores their order."""

    if not columns:
        return {}

    marker = f"#{secrets.token_hex(8)}#"
    statements = _read_only_session() + ["WHENEVER SQLERROR CONTINUE"]

    for table, names in columns.items():
        row_hash = " || ',' || ".join(f"TO_CHAR(ORA_HASH({_identifier(name)}))" for name in names)
        statements.append(f"PROMPT {marker}{table}")
        statements.append(
            f"SELECT 'V|' || COUNT(*) || '|' || TO_CHAR(SUM(ORA_HASH({row_hash})))"
            f" FROM {_identifier(endpoint.owner)}.{_identifier(table)};"
        )

    result: Dict[str, Dict[str, Any]] = {}

    for table, text in _sections(run(endpoint, "\n".join(statements)), marker):
        error = _section_error(text)
        if error:
            result[table] = {"error": error}
            continue
        _, _, values = text.strip().partition("V|")
        count, _, digest = values.partition("|")
        result[table] = {"rows": int(count), "hash": digest.strip()}

    return result


def compare_data(
    left: Endpoint, right: Endpoint, name_filter: Optional[str], run: Runner
) -> List[Dict[str, Any]]:
    left_tables, right_tables = _on_both(
        left, right, lambda side: read_tables(side, name_filter, run)
    )

    items: Dict[str, Dict[str, Any]] = {}
    hashed: Dict[str, List[str]] = {}

    for name in sorted(set(left_tables) | set(right_tables)):
        if name not in right_tables or name not in left_tables:
            items[name] = {
                "table": name,
                "status": "only_left" if name in left_tables else "only_right",
            }
            continue

        one, other = left_tables[name]["columns"], right_tables[name]["columns"]
        shared = [
            column
            for column in one
            if column in other and _is_comparable(one[column]) and _is_comparable(other[column])
        ]
        items[name] = {
            "table": name,
            "key": (
                left_tables[name]["key"]
                if left_tables[name]["key"] == right_tables[name]["key"]
                else []
            ),
            "columns_only_left": [column for column in one if column not in other],
            "columns_only_right": [column for column in other if column not in one],
            "columns_not_compared": [
                column for column in one if column in other and column not in shared
            ],
        }

        if not shared:
            items[name].update(status="not_compared", error="No column can be compared.")
        elif len(shared) > MAX_HASHED_COLUMNS:
            items[name].update(
                status="not_compared",
                error=f"More than {MAX_HASHED_COLUMNS} columns can not be hashed.",
            )
        else:
            hashed[name] = shared

    left_hashes, right_hashes = _on_both(left, right, lambda side: read_hashes(side, hashed, run))

    for name in hashed:
        one, other = left_hashes.get(name, {}), right_hashes.get(name, {})
        item = items[name]
        item["left_rows"], item["right_rows"] = one.get("rows"), other.get("rows")

        if one.get("error") or other.get("error"):
            item.update(status="error", error=one.get("error") or other.get("error"))
        elif "rows" not in one or "rows" not in other:
            item.update(status="error", error="The table could not be read.")
        elif one["rows"] == other["rows"] and one["hash"] == other["hash"]:
            item["status"] = "same"
        else:
            item["status"] = "different"

    return list(items.values())


# ----------------------------------------------------------------------
# Rows of one table
# ----------------------------------------------------------------------


def read_rows(
    endpoint: Endpoint,
    table: str,
    columns: Sequence[str],
    order: Sequence[str],
    run: Runner,
) -> List[List[str]]:
    """Up to MAX_ROWS + 1 rows, in binary order: one extra shows that more exist."""

    select = ", ".join(_identifier(name) for name in columns)
    sort = ", ".join(_identifier(name) for name in order)
    output = run(
        endpoint,
        "\n".join(
            _read_only_session()
            + [
                "SET MARKUP CSV ON DELIMITER , QUOTE ON",
                f"SELECT * FROM (SELECT {select} FROM"
                f" {_identifier(endpoint.owner)}.{_identifier(table)} ORDER BY {sort})"
                f" WHERE ROWNUM <= {MAX_ROWS + 1};",
            ]
        ),
    )
    return [row for row in csv.reader(io.StringIO(output)) if len(row) == len(columns)]


def _last_shared(rows: Sequence[Tuple[str, ...]], others: Iterable[Tuple[str, ...]]) -> int:
    shared = set(others)
    return max((index for index, row in enumerate(rows) if row in shared), default=-1)


def diff_rows(
    columns: Sequence[str],
    key: Sequence[str],
    left: Sequence[Sequence[str]],
    right: Sequence[Sequence[str]],
) -> Dict[str, Any]:
    """
    Rows only on one side, and (with a key) rows whose values differ.

    If a side has more than MAX_ROWS rows, the rest of it is unknown, so a row of the
    other side after the last key both share can not be called missing: it is not reported.
    """

    truncated = len(left) > MAX_ROWS or len(right) > MAX_ROWS
    left_rows = [tuple(row) for row in left[:MAX_ROWS]]
    right_rows = [tuple(row) for row in right[:MAX_ROWS]]

    positions = [columns.index(name) for name in key] if key else []

    def key_of(row: Tuple[str, ...]) -> Tuple[str, ...]:
        return tuple(row[index] for index in positions) if positions else row

    left_keys = [key_of(row) for row in left_rows]
    right_keys = [key_of(row) for row in right_rows]

    left_limit = len(left_keys) if not truncated else _last_shared(left_keys, right_keys) + 1
    right_limit = len(right_keys) if not truncated else _last_shared(right_keys, left_keys) + 1

    only_left: List[Tuple[str, ...]] = []
    only_right: List[Tuple[str, ...]] = []
    changed: List[Dict[str, Any]] = []
    same = 0

    if positions:
        left_by_key = dict(zip(left_keys, left_rows))
        right_by_key = dict(zip(right_keys, right_rows))

        for row_key, row in zip(left_keys[:left_limit], left_rows[:left_limit]):
            other = right_by_key.get(row_key)
            if other is None:
                only_left.append(row)
            elif other == row:
                same += 1
            else:
                changed.append(
                    {
                        "key": list(row_key),
                        "left": list(row),
                        "right": list(other),
                        "columns": [
                            name for name, one, two in zip(columns, row, other) if one != two
                        ],
                    }
                )

        only_right = [
            row
            for row_key, row in zip(right_keys[:right_limit], right_rows[:right_limit])
            if row_key not in left_by_key
        ]
    else:
        # No key: rows are matched whole, and duplicates count.
        left_count = Counter(left_rows[:left_limit])
        right_count = Counter(right_rows[:right_limit])
        only_left = list((left_count - right_count).elements())
        only_right = list((right_count - left_count).elements())
        same = sum((left_count & right_count).values())

    return {
        "columns": list(columns),
        "key": list(key),
        "same": same,
        "only_left_count": len(only_left),
        "only_right_count": len(only_right),
        "changed_count": len(changed),
        "only_left": [list(row) for row in only_left[:MAX_REPORTED_ROWS]],
        "only_right": [list(row) for row in only_right[:MAX_REPORTED_ROWS]],
        "changed": changed[:MAX_REPORTED_ROWS],
        "truncated": truncated,
        "limit": MAX_ROWS,
    }


def compare_rows(
    left: Endpoint, right: Endpoint, table: str, run: Runner = run_sqlplus
) -> Dict[str, Any]:
    """The differing rows of one table, up to MAX_ROWS rows from each side."""

    if not _NAME.match(table):
        raise DatabaseCompareError(f"'{table}' is not a valid table name.")

    left_tables, right_tables = _on_both(left, right, lambda side: read_tables(side, table, run))

    if table.upper() not in left_tables or table.upper() not in right_tables:
        raise DatabaseCompareError(f"Table '{table}' is not in both schemas.")

    table = table.upper()
    one, other = left_tables[table], right_tables[table]
    columns = [
        column
        for column, data_type in one["columns"].items()
        if column in other["columns"]
        and _is_comparable(data_type)
        and _is_comparable(other["columns"][column])
    ]

    if not columns:
        raise DatabaseCompareError(f"Table '{table}' has no column that can be compared.")

    key = one["key"] if one["key"] == other["key"] and set(one["key"]) <= set(columns) else []
    order = key or columns

    left_rows, right_rows = _on_both(
        left, right, lambda side: read_rows(side, table, columns, order, run)
    )

    return {"table": table, **diff_rows(columns, key, left_rows, right_rows)}


# ----------------------------------------------------------------------
# Comparison
# ----------------------------------------------------------------------


def compare(
    left: Endpoint,
    right: Endpoint,
    *,
    include_ddl: bool = True,
    include_data: bool = True,
    name_filter: Optional[str] = None,
    run: Runner = run_sqlplus,
) -> Dict[str, Any]:
    """Compare the two schemas' DDL and table data."""

    if name_filter and not _FILTER.match(name_filter):
        raise DatabaseCompareError(
            "The name filter can use letters, digits, '_', '$', '#' and '%'.",
        )

    return {
        "left": left.label,
        "right": right.label,
        "ddl": compare_ddl(left, right, name_filter, run) if include_ddl else None,
        "data": compare_data(left, right, name_filter, run) if include_data else None,
    }
