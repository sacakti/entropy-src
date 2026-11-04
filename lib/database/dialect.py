"""
Translate Entropy's SQL, written for SQLite, into PostgreSQL.

The application keeps one way of writing SQL; the engine in use adapts it.
Text inside string literals and quoted identifiers is never rewritten.

Foreign keys are left out on purpose. SQLite never enforces them here (Entropy
does not turn them on), so enforcing them on another engine would change what
the application does, and would reject existing rows that point at nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, List, Optional, Protocol, Sequence

_TOKENS = re.compile(
    r"'(?:[^']|'')*'" r'|"(?:[^"]|"")*"' r"|--[^\n]*" r"|/\*.*?\*/",
    re.DOTALL,
)
_MASK = re.compile(r"\x00(\d+)\x00")
_NAME = r"[\w\x00]+"

_NOW = "(now() at time zone 'utc')"
_DATETIME_FORMAT = "'YYYY-MM-DD HH24:MI:SS'"
_DATE_FORMAT = "'YYYY-MM-DD'"
_TEXT_NOW = f"to_char({_NOW}, {_DATETIME_FORMAT})"

_STRFTIME = {
    "Y": "YYYY",
    "m": "MM",
    "d": "DD",
    "H": "HH24",
    "M": "MI",
    "S": "SS",
    "f": "SS.MS",
}

_REFERENCES = (
    r"REFERENCES\s+" + _NAME + r"(?:\s*\([^)]*\))?"
    r"(?:\s+ON\s+(?:DELETE|UPDATE)\s+(?:CASCADE|SET\s+NULL|SET\s+DEFAULT|RESTRICT|NO\s+ACTION))*"
    r"(?:\s+(?:NOT\s+)?DEFERRABLE(?:\s+INITIALLY\s+\w+)?)?"
)
_TABLE_FOREIGN_KEY = re.compile(
    r",\s*(?:CONSTRAINT\s+" + _NAME + r"\s+)?FOREIGN\s+KEY\s*\([^)]*\)\s*" + _REFERENCES,
    re.IGNORECASE,
)
_INLINE_FOREIGN_KEY = re.compile(r"\s+" + _REFERENCES, re.IGNORECASE)
_TABLE_DDL = re.compile(
    r"^\s*(?:CREATE\s+(?:TEMP\s+|TEMPORARY\s+)?TABLE|ALTER\s+TABLE)\b", re.IGNORECASE
)
_INSERT = re.compile(
    r"^\s*(?P<verb>INSERT\s+OR\s+(?P<mode>IGNORE|REPLACE)\s+INTO|REPLACE\s+INTO|INSERT\s+INTO)"
    r"\s+(?P<table>" + _NAME + r")\s*(?P<columns>\([^)]*\))?",
    re.IGNORECASE,
)
_PRAGMA = re.compile(
    r"^\s*PRAGMA\s+(?P<name>\w+)\s*(?:\(\s*['\"]?(?P<argument>\w+)['\"]?\s*\))?", re.IGNORECASE
)

_MASTER = (
    "(SELECT 'table' AS type, table_name AS name, table_name AS tbl_name,"
    " CAST(NULL AS text) AS sql FROM information_schema.tables"
    " WHERE table_schema = current_schema()"
    " UNION ALL SELECT 'index', indexname, tablename, indexdef FROM pg_indexes"
    " WHERE schemaname = current_schema()) AS sqlite_master"
)

_NOTHING = "SELECT 1 WHERE false"
_BARE_CONDITION = re.compile(
    r"\b(WHERE|AND|OR|HAVING|ON)\s+([01])(?=\s*(?:$|;|\)|\b(?:AND|OR|ORDER|GROUP|LIMIT|HAVING)\b))",
    re.IGNORECASE,
)


class DialectError(ValueError):
    """SQL this translator cannot express on the target engine."""


class Catalog(Protocol):
    """What the translator needs to know about the target's tables."""

    def columns(self, table: str) -> List[str]: ...

    def conflict_key(self, table: str) -> List[str]: ...

    def identity(self, table: str) -> Optional[str]: ...


@dataclass(frozen=True)
class Statement:
    """One translated statement."""

    text: str
    # The statement returns this generated key, for the cursor's lastrowid.
    returning: Optional[str] = None


class _Masked:
    """SQL whose literals and quoted names are hidden while it is rewritten."""

    def __init__(self, sql: str) -> None:
        self.values: List[str] = []

        def hide(match: re.Match) -> str:
            token = match.group(0)
            if token.startswith(("--", "/*")):
                return " "
            self.values.append(token)
            return f"\x00{len(self.values) - 1}\x00"

        self.code = _TOKENS.sub(hide, sql)

    def literal(self, text: str) -> Optional[str]:
        """The value of a string literal argument; None for anything else."""

        match = _MASK.fullmatch(text.strip())
        if match is None:
            return None
        token = self.values[int(match.group(1))]
        return token[1:-1].replace("''", "'") if token.startswith("'") else None

    def name(self, text: str) -> str:
        """An identifier without its quotes."""

        match = _MASK.fullmatch(text.strip())
        if match is None:
            return text.strip().lower()
        return self.values[int(match.group(1))].strip('"').replace('""', '"')

    def restore(self, code: str) -> str:
        """Put the literals back, ready for the driver's %s parameters."""

        code = code.replace("%", "%%").replace("?", "%s")
        return _MASK.sub(lambda m: self.values[int(m.group(1))].replace("%", "%%"), code)


def _rewrite_calls(code: str, name: str, build: Callable[[List[str]], str]) -> str:
    """Replace every call of a function, with its arguments split at the top level."""

    pattern = re.compile(r"\b" + name + r"\s*\(", re.IGNORECASE)
    position = 0
    while True:
        match = pattern.search(code, position)
        if match is None:
            return code
        depth = 1
        index = match.end()
        arguments: List[str] = []
        start = index
        while index < len(code) and depth:
            character = code[index]
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
            elif character == "," and depth == 1:
                arguments.append(code[start:index].strip())
                start = index + 1
            index += 1
        if depth:
            raise DialectError(f"Unbalanced parentheses in a call of {name}().")
        arguments.append(code[start : index - 1].strip())
        replacement = build(arguments)
        code = code[: match.start()] + replacement + code[index:]
        position = match.start()


def _moment(masked: _Masked, arguments: Sequence[str]) -> str:
    """A UTC timestamp from SQLite's time value and modifiers."""

    if masked.literal(arguments[0]) == "now":
        moment = _NOW
    else:
        moment = f"(({arguments[0]})::timestamptz at time zone 'utc')"
    for modifier in arguments[1:]:
        moment += f" + ({modifier})::interval"
    return moment


def _strftime_format(fmt: str) -> str:
    """A to_char format for a strftime format."""

    parts: List[str] = []
    index = 0
    while index < len(fmt):
        character = fmt[index]
        if character == "%" and index + 1 < len(fmt):
            code = fmt[index + 1]
            if code not in _STRFTIME:
                raise DialectError(f"strftime format %{code} is not supported.")
            parts.append(_STRFTIME[code])
            index += 2
            continue
        literal = character
        index += 1
        while index < len(fmt) and fmt[index] != "%":
            literal += fmt[index]
            index += 1
        parts.append('"' + literal + '"')
    return "'" + "".join(parts) + "'"


def _rewrite_blob_literals(code: str, masked: _Masked) -> str:
    """X'00ff' is a blob on SQLite and a bit string on PostgreSQL."""

    def bytea(match: re.Match) -> str:
        index = int(match.group(1))
        masked.values[index] = "'\\x" + masked.values[index][1:-1] + "'"
        return f"\x00{index}\x00::bytea"

    return re.sub(r"\b[xX]\x00(\d+)\x00", bytea, code)


def _rewrite_functions(code: str, masked: _Masked) -> str:
    code = _rewrite_calls(
        code,
        "datetime",
        lambda args: f"to_char({_moment(masked, args)}, {_DATETIME_FORMAT})",
    )
    code = _rewrite_calls(
        code,
        "date",
        lambda args: f"to_char({_moment(masked, args)}, {_DATE_FORMAT})",
    )

    def strftime(args: List[str]) -> str:
        fmt = masked.literal(args[0])
        if fmt is None:
            raise DialectError("strftime needs a literal format.")
        return f"to_char({_moment(masked, args[1:])}, {_strftime_format(fmt)})"

    code = _rewrite_calls(code, "strftime", strftime)

    def julianday(args: List[str]) -> str:
        if masked.literal(args[0]) == "now":
            return "(extract(epoch from now()) / 86400.0 + 2440587.5)"
        return f"(extract(epoch from ({args[0]})::timestamptz) / 86400.0 + 2440587.5)"

    code = _rewrite_calls(code, "julianday", julianday)
    code = _rewrite_calls(
        code,
        "group_concat",
        lambda args: f"string_agg(({args[0]})::text, {args[1] if len(args) > 1 else repr(',')})",
    )
    code = re.sub(r"\bIFNULL\s*\(", "COALESCE(", code, flags=re.IGNORECASE)
    code = re.sub(r"\bCURRENT_TIMESTAMP\b", _TEXT_NOW, code, flags=re.IGNORECASE)
    return re.sub(
        r"\bCURRENT_DATE\b", f"to_char({_NOW}, {_DATE_FORMAT})", code, flags=re.IGNORECASE
    )


def _rewrite_table_ddl(code: str) -> str:
    code = _TABLE_FOREIGN_KEY.sub("", code)
    code = _INLINE_FOREIGN_KEY.sub("", code)
    code = re.sub(r"\s+COLLATE\s+\w+", "", code, flags=re.IGNORECASE)
    code = re.sub(
        r"\bINTEGER\s+PRIMARY\s+KEY(?:\s+AUTOINCREMENT)?\b",
        "BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY",
        code,
        flags=re.IGNORECASE,
    )
    code = re.sub(r"\b(?:INTEGER|INT)\b", "BIGINT", code, flags=re.IGNORECASE)
    code = re.sub(r"\bBLOB\b", "BYTEA", code, flags=re.IGNORECASE)
    return re.sub(r"\bREAL\b", "DOUBLE PRECISION", code, flags=re.IGNORECASE)


def _rewrite_expressions(code: str) -> str:
    # SQLite takes a number as a condition; PostgreSQL only a boolean.
    code = _BARE_CONDITION.sub(
        lambda m: f"{m.group(1)} {'false' if m.group(2) == '0' else 'true'}",
        code,
    )
    # A parameter alone gives the server no type to read it as.
    code = re.sub(r"\?\s+IS\s+(NOT\s+)?NULL\b", r"CAST(? AS text) IS \1NULL", code, flags=re.I)
    # SQLite's IS compares with anything; PostgreSQL's only with NULL, TRUE and FALSE.
    code = re.sub(r"\bIS\s+NOT\s+\?", "IS DISTINCT FROM ?", code, flags=re.I)
    code = re.sub(r"\bIS\s+\?", "IS NOT DISTINCT FROM ?", code, flags=re.I)
    # SQLite's LIKE ignores case; PostgreSQL's does not.
    code = re.sub(r"\bLIKE\b", "ILIKE", code, flags=re.IGNORECASE)
    code = re.sub(
        r"([\w.\x00]+)\s*=\s*\?\s+COLLATE\s+NOCASE\b",
        r"lower(\1) = lower(?)",
        code,
        flags=re.IGNORECASE,
    )
    code = re.sub(
        r"([\w.\x00]+)\s+COLLATE\s+NOCASE\b",
        r"lower(\1)",
        code,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\bsqlite_(?:master|schema)\b", _MASTER, code, flags=re.IGNORECASE)


def _quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _rewrite_insert(
    code: str,
    masked: _Masked,
    catalog: Optional[Catalog],
) -> tuple[str, Optional[str]]:
    """INSERT OR IGNORE / REPLACE, and the generated key SQLite gives as lastrowid."""

    match = _INSERT.match(code)
    if match is None:
        return code, None

    verb = match.group("verb").upper()
    replacing = verb.startswith("REPLACE") or (match.group("mode") or "").upper() == "REPLACE"
    ignoring = (match.group("mode") or "").upper() == "IGNORE"
    table = masked.name(match.group("table"))

    code = code[: match.start("verb")] + "INSERT INTO" + code[match.end("verb") :]
    code = code.rstrip().rstrip(";").rstrip()
    upper = code.upper()

    if "ON CONFLICT" not in upper:
        if ignoring:
            code += " ON CONFLICT DO NOTHING"
        elif replacing:
            code += _replace_clause(table, match.group("columns"), masked, catalog)

    returning = None
    if catalog is not None and "RETURNING" not in upper:
        returning = catalog.identity(table)
        if returning:
            code += f" RETURNING {_quoted(returning)}"
    return code, returning


def _replace_clause(
    table: str,
    columns: Optional[str],
    masked: _Masked,
    catalog: Optional[Catalog],
) -> str:
    if catalog is None:
        raise DialectError(f"Replacing rows of {table} needs the table's catalog.")
    key = catalog.conflict_key(table)
    if not key:
        return ""
    if columns:
        names = [masked.name(item) for item in columns.strip()[1:-1].split(",")]
    else:
        names = catalog.columns(table)
    updates = [name for name in names if name not in key]
    target = ", ".join(_quoted(name) for name in key)
    if not updates:
        return f" ON CONFLICT ({target}) DO NOTHING"
    assignments = ", ".join(f"{_quoted(name)} = EXCLUDED.{_quoted(name)}" for name in updates)
    return f" ON CONFLICT ({target}) DO UPDATE SET {assignments}"


def _pragma(sql: str) -> Optional[str]:
    match = _PRAGMA.match(sql)
    if match is None:
        return None
    name = match.group("name").lower()
    if name == "table_info" and match.group("argument"):
        table = match.group("argument").lower()
        return (
            "SELECT c.ordinal_position - 1 AS cid, c.column_name AS name, c.data_type AS type,"
            " CASE WHEN c.is_nullable = 'NO' THEN 1 ELSE 0 END AS \"notnull\","
            " c.column_default AS dflt_value,"
            " CASE WHEN EXISTS (SELECT 1 FROM pg_index i JOIN pg_attribute a"
            " ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)"
            f" WHERE i.indisprimary AND i.indrelid = to_regclass('{table}')"
            " AND a.attname = c.column_name) THEN 1 ELSE 0 END AS pk"
            " FROM information_schema.columns c"
            f" WHERE c.table_schema = current_schema() AND c.table_name = '{table}'"
            " ORDER BY c.ordinal_position"
        )
    if name == "foreign_keys":
        return "SELECT 0 AS foreign_keys"
    return _NOTHING


def translate(sql: str, catalog: Optional[Catalog] = None) -> Statement:
    """One SQLite statement as PostgreSQL, with %s parameters."""

    pragma = _pragma(sql)
    if pragma is not None:
        return Statement(pragma)

    masked = _Masked(sql)
    code = _rewrite_blob_literals(masked.code, masked)
    if _TABLE_DDL.match(code):
        code = _rewrite_table_ddl(code)
    code = _rewrite_functions(code, masked)
    code = _rewrite_expressions(code)
    code, returning = _rewrite_insert(code, masked, catalog)
    return Statement(masked.restore(code), returning)


def split_statements(script: str) -> List[str]:
    """The statements of a script, split where no literal or comment hides the semicolon."""

    masked = _Masked(script)
    statements = []
    for part in masked.code.split(";"):
        if part.strip():
            statements.append(_MASK.sub(lambda m: masked.values[int(m.group(1))], part).strip())
    return statements


def is_schema_change(sql: str) -> bool:
    """True when a statement changes tables, so what is known about them is out of date."""

    return re.match(r"\s*(?:CREATE|ALTER|DROP)\b", sql, re.IGNORECASE) is not None
