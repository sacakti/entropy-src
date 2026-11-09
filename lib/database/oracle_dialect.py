"""
Translate Entropy's SQL, written for SQLite, into Oracle Database 19c and later.

The application keeps one way of writing SQL; the engine in use adapts it, as
`lib/database/dialect.py` does for PostgreSQL. Text inside string literals is
never rewritten.

What differs from SQLite, and how it is bridged:

- Parameters are named (`:b0`, `:b1`, ...) in the order of SQLite's `?`, so
  rewriting `LIMIT ? OFFSET ?` into `OFFSET ... FETCH` cannot swap their values.
- Oracle stores an empty string as NULL. Text columns therefore lose NOT NULL,
  are marked with a column comment, and read back NULL as '' (see OracleConnection);
  `x = ''` becomes `x IS NULL`, also when the '' arrives as a parameter.
- TEXT becomes VARCHAR2(4000), or CLOB for columns that hold documents (bodies,
  definitions, payloads); keys and unique columns stay VARCHAR2 so they can be
  indexed and compared. A CLOB compared with `=` goes through DBMS_LOB.COMPARE.
- INSERT OR IGNORE / OR REPLACE and ON CONFLICT become MERGE.
- LIMIT/OFFSET become OFFSET ... ROWS FETCH NEXT ... ROWS ONLY (12c and later).
- IF [NOT] EXISTS is answered by ignoring the error Oracle gives (19c has no such clause).
- Column names Oracle reserves (LEVEL, SIZE, ...) are quoted; quoted names are
  upper-cased, as Oracle stores unquoted ones.

Foreign keys are left out, as for PostgreSQL: SQLite never enforces them here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Protocol, Sequence, Set, Tuple

from lib.database.dialect import (
    _INLINE_FOREIGN_KEY,
    _MASK,
    _TABLE_FOREIGN_KEY,
    DialectError,
    _Masked,
    _rewrite_calls,
)

# A parameter: its position among SQLite's `?`, kept while the SQL around it is rewritten.
_BIND = re.compile(r"\x01(\d+)\x01")
_NAME = r"(?:[\w\x00$#]+|\"[^\"]+\")"
_REF = r"(?:[\w\x00$#\"]+\.)*[\w\x00$#\"]+"

# Text written on columns whose NOT NULL Oracle cannot keep (it stores '' as NULL).
BLANK_MARK = "entropy:text-not-null"

# Words Oracle reserves that Entropy uses as column names. Quoted wherever they appear.
RESERVED_COLUMNS = ("access", "level", "number", "size", "trigger")
_RESERVED = re.compile(
    r"(?<![\w\x00$#\"])(" + "|".join(RESERVED_COLUMNS) + r")(?![\w\x00$#\"(])", re.I
)

# Columns that hold documents rather than names or states; anything else stays VARCHAR2.
_LARGE_TEXT = re.compile(
    r"^(?:body|content|contents|definition|definitions|script|data|payload|details|output|"
    r"outputs|log|logs|remarks|arguments|variables|parameters|options|result|results|"
    r"traceback|description|message|error|errors|summary|snapshot|spec|settings|inputs|"
    r"value|notes|answer|rerun_config|template|subject_template|body_template|config|"
    r"yaml|json|html|markdown|comment|comments|metadata|steps|views|state_json|"
    r"emails|tags|people)$|_(?:json|body|content|data|text|yaml|script|log|output|"
    r"definition|config|payload|template)$",
    re.I,
)
_VARCHAR = 4000
# Index keys must fit an 8 KB block (6398 bytes); keep a margin.
INDEX_BUDGET = 6000

_NOW = "SYS_EXTRACT_UTC(SYSTIMESTAMP)"
_DATETIME_FORMAT = "'YYYY-MM-DD HH24:MI:SS'"
_DATE_FORMAT = "'YYYY-MM-DD'"
_STRFTIME = {"Y": "YYYY", "m": "MM", "d": "DD", "H": "HH24", "M": "MI", "S": "SS", "f": "SS.FF3"}
_UNITS = {
    "second": ("DS", "SECOND"),
    "minute": ("DS", "MINUTE"),
    "hour": ("DS", "HOUR"),
    "day": ("DS", "DAY"),
    "month": ("YM", "MONTH"),
    "year": ("YM", "YEAR"),
}

_MASTER = (
    "(SELECT 'table' AS type, LOWER(table_name) AS name, LOWER(table_name) AS tbl_name,"
    " CAST(NULL AS VARCHAR2(1)) AS sql FROM all_tables"
    " WHERE owner = SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AND dropped = 'NO'"
    " AND table_name NOT LIKE '%$%'"
    " UNION ALL SELECT 'index', LOWER(index_name), LOWER(table_name), CAST(NULL AS VARCHAR2(1))"
    " FROM all_indexes WHERE owner = SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')"
    " AND index_type <> 'LOB' AND index_name NOT LIKE 'SYS\\_%' ESCAPE '\\'"
    " AND table_name NOT LIKE '%$%') sqlite_master"
)
_SCHEMA = "SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')"
_NOTHING = "SELECT 1 FROM DUAL WHERE 1 = 0"

# Oracle errors that answer SQLite's IF [NOT] EXISTS: the statement had nothing to do.
ALREADY_EXISTS = frozenset({955, 1408})  # name already used; columns already indexed
MISSING_TABLE = frozenset({942})
MISSING_INDEX = frozenset({1418})

_KEYWORDS = frozenset(
    [
        "select",
        "from",
        "where",
        "and",
        "or",
        "not",
        "null",
        "is",
        "in",
        "like",
        "between",
        "exists",
        "case",
        "when",
        "then",
        "else",
        "end",
        "as",
        "on",
        "join",
        "left",
        "right",
        "inner",
        "outer",
        "full",
        "cross",
        "group",
        "order",
        "by",
        "having",
        "union",
        "all",
        "distinct",
        "asc",
        "desc",
        "limit",
        "offset",
        "set",
        "values",
        "insert",
        "update",
        "delete",
        "into",
        "default",
        "true",
        "false",
        "coalesce",
        "lower",
        "upper",
        "trim",
        "substr",
        "length",
        "count",
        "sum",
        "min",
        "max",
        "avg",
        "cast",
        "nvl",
        "decode",
        "excluded",
        "fetch",
        "first",
        "next",
        "rows",
        "only",
        "with",
        "escape",
    ]
)


class Catalog(Protocol):
    """What the translator needs to know about the tables of the target schema."""

    def columns(self, table: str) -> List[str]: ...

    def conflict_key(self, table: str) -> List[str]: ...

    def unique_keys(self, table: str) -> List[List[str]]: ...

    def identity(self, table: str) -> Optional[str]: ...

    def clob_columns(self, table: str) -> Set[str]: ...

    def text_type(self, table: str, column: str) -> Optional[str]: ...


@dataclass
class OracleStatement:
    """One translated statement: Oracle SQL with named parameters, and how to run it."""

    code: str
    literals: List[str]
    # The generated key to return for the cursor's lastrowid (`RETURNING ... INTO :rid`).
    returning: Optional[str] = None
    # Errors (ORA numbers) that mean the statement had nothing to do.
    ignore: FrozenSet[int] = frozenset()
    # INSERT OR IGNORE: a duplicate on any unique key inserts nothing, as on SQLite.
    ignore_duplicates: bool = False
    # Run after the statement (column comments); already Oracle SQL without parameters.
    followups: List[str] = field(default_factory=list)
    # Tables read, and those only outer-joined, for reading NULL back as ''.
    tables: Tuple[str, ...] = ()
    outer_tables: Tuple[str, ...] = ()
    # Parameters assigned (SET a = ?), which stay values even when they are ''.
    assigned: FrozenSet[int] = frozenset()
    # CREATE INDEX: the table and plain columns, so the key can be sized to fit.
    index: Optional[Tuple[str, Tuple[str, ...]]] = None
    # A statement Oracle has no use for (VACUUM, most PRAGMAs).
    noop: bool = False

    @property
    def text(self) -> str:
        """The SQL with parameters named, for logs and for recognising the statement."""

        return self.render(None)[0]

    def render(self, values: Optional[Sequence[Any]]) -> Tuple[str, Dict[str, Any]]:
        """The SQL and its named parameters for these values."""

        code = self.code
        binds: Dict[str, Any] = {}
        if values is not None:
            empty = {
                index
                for index, value in enumerate(values)
                if isinstance(value, str) and value == "" and index not in self.assigned
            }
            if empty:
                # Oracle stores '' as NULL, so equal to '' means IS NULL.
                def compare(match: re.Match) -> str:
                    if int(match.group(2)) not in empty:
                        return str(match.group(0))
                    return " IS NULL" if match.group(1) == "=" else " IS NOT NULL"

                code = re.sub(r"\s*((?<![<>!])=|<>|!=)\s*\x01(\d+)\x01", compare, code)
            used = {int(index) for index in _BIND.findall(code)}
            binds = {f"b{index}": values[index] for index in sorted(used)}
        code = _BIND.sub(lambda m: f":b{m.group(1)}", code)
        if self.returning:
            code += f" RETURNING {_column(self.returning)} INTO :rid"
        return _MASK.sub(lambda m: self.literals[int(m.group(1))], code), binds


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _plain(masked: _Masked, token: str) -> str:
    """A table or column name as written, unquoted and lower-cased."""

    return masked.name(token.strip()).strip('"').lower()


def _column(name: str) -> str:
    """A column or table name as Oracle reads it: quoted when reserved, else as it is."""

    if name.lower() in RESERVED_COLUMNS or not re.fullmatch(r"[A-Za-z_][\w$#]*", name):
        return '"' + name.upper().replace('"', '""') + '"'
    return name


def _split_top(text: str, separator: str = ",") -> List[str]:
    """Parts of a list, split only outside parentheses."""

    parts: List[str] = []
    depth = 0
    start = 0
    for index, character in enumerate(text):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == separator and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    parts.append(text[start:].strip())
    return [part for part in parts if part]


def _closing(code: str, opening: int) -> int:
    """The index of the parenthesis that closes the one at `opening`."""

    depth = 0
    for index in range(opening, len(code)):
        if code[index] == "(":
            depth += 1
        elif code[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    raise DialectError("Unbalanced parentheses.")


def _operand_start(code: str, end: int) -> int:
    """Where the operand that ends just before `end` starts: a name, or a call or group."""

    index = end
    while index > 0 and code[index - 1].isspace():
        index -= 1
    if index > 0 and code[index - 1] == ")":
        depth = 0
        while index > 0:
            index -= 1
            if code[index] == ")":
                depth += 1
            elif code[index] == "(":
                depth -= 1
                if depth == 0:
                    break
    while index > 0 and (code[index - 1].isalnum() or code[index - 1] in '_.\x00$#"'):
        index -= 1
    return index


def _top_level(code: str, start: int = 0, end: Optional[int] = None) -> List[Tuple[int, int]]:
    """Spans of `code[start:end]` at parenthesis depth 0."""

    end = len(code) if end is None else end
    spans = []
    depth = 0
    span_start = start
    for index in range(start, end):
        character = code[index]
        if character == "(":
            if depth == 0:
                spans.append((span_start, index))
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                span_start = index + 1
    if depth == 0:
        spans.append((span_start, end))
    return spans


def _find_top(
    code: str, pattern: str, start: int = 0, end: Optional[int] = None
) -> Optional[re.Match]:
    """The first match of `pattern` at parenthesis depth 0."""

    regex = re.compile(pattern, re.I)
    for span_start, span_end in _top_level(code, start, end):
        match = regex.search(code, span_start, span_end)
        if match:
            return match
    return None


# ----------------------------------------------------------------------
# Names and parameters
# ----------------------------------------------------------------------


def _number_binds(code: str) -> str:
    counter = iter(range(1_000_000))
    return re.sub(r"\?", lambda m: f"\x01{next(counter)}\x01", code)


def _upper_quoted(masked: _Masked) -> None:
    """Quoted names are case-sensitive in Oracle, which stores unquoted ones upper-cased."""

    for index, token in enumerate(masked.values):
        if token.startswith('"') and re.fullmatch(r'"[A-Za-z_][\w$#]*"', token):
            masked.values[index] = token.upper()


def _quote_reserved(code: str) -> str:
    def quote(match: re.Match) -> str:
        # CREATE TRIGGER, DROP TRIGGER: the word as the keyword it also is.
        if re.search(
            r"\b(?:CREATE|DROP|ALTER)\s+(?:OR\s+REPLACE\s+)?$", code[: match.start()], re.I
        ):
            return str(match.group(0))
        return '"' + str(match.group(1)).upper() + '"'

    return _RESERVED.sub(quote, code)


def _rewrite_blob_literals(code: str, masked: _Masked) -> str:
    """X'00ff' is a blob literal on SQLite; Oracle reads hex with HEXTORAW."""

    def raw(match: re.Match) -> str:
        hex_digits = masked.values[int(match.group(1))][1:-1]
        return f"HEXTORAW({match.group(0)[1:]})" if hex_digits else "EMPTY_BLOB()"

    return re.sub(r"\b[xX]\x00(\d+)\x00", raw, code)


def _literal(masked: _Masked, text: str) -> str:
    """Add a string literal to the statement and return its place-holder."""

    masked.values.append(text)
    return f"\x00{len(masked.values) - 1}\x00"


# ----------------------------------------------------------------------
# Expressions
# ----------------------------------------------------------------------


def _shift(masked: _Masked, moment: str, modifiers: Sequence[str]) -> str:
    for modifier in modifiers:
        text = masked.literal(modifier)
        if text is None:
            raise DialectError("Date modifiers must be literal text on Oracle.")
        text = text.strip().lower()
        if text in ("utc", "localtime"):
            continue
        if text == "start of day":
            moment = f"CAST(TRUNC({moment}) AS TIMESTAMP)"
            continue
        if text == "start of month":
            moment = f"CAST(TRUNC({moment}, 'MM') AS TIMESTAMP)"
            continue
        if text == "start of year":
            moment = f"CAST(TRUNC({moment}, 'YYYY') AS TIMESTAMP)"
            continue
        match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s+(second|minute|hour|day|month|year)s?", text)
        if match is None:
            raise DialectError(f"Date modifier '{text}' is not supported on Oracle.")
        kind, unit = _UNITS[match.group(2)]
        moment = f"({moment} + NUMTO{kind}INTERVAL({match.group(1)}, '{unit}'))"
    return moment


def _moment(masked: _Masked, arguments: Sequence[str]) -> Optional[str]:
    """A TIMESTAMP for SQLite's time value and modifiers; None for a plain stored text."""

    if masked.literal(arguments[0]) == "now":
        return _shift(masked, _NOW, arguments[1:])
    if len(arguments) == 1:
        return None
    return _shift(masked, _parsed(masked, arguments[0]), arguments[1:])


def _parsed(masked: _Masked, value: str) -> str:
    """Stored ISO text (UTC, with or without 'T' and fractions) as a TIMESTAMP."""

    t = _literal(masked, "'T'")
    space = _literal(masked, "' '")
    return f"TO_TIMESTAMP(SUBSTR(REPLACE({value}, {t}, {space}), 1, 19), {_DATETIME_FORMAT})"


def _iso_text(masked: _Masked, value: str, length: int) -> str:
    """Stored ISO text cut to a date or date and time, as SQLite's date() and datetime() give."""

    t = _literal(masked, "'T'")
    space = _literal(masked, "' '")
    return f"SUBSTR(REPLACE({value}, {t}, {space}), 1, {length})"


def _strftime_format(fmt: str) -> str:
    parts: List[str] = []
    index = 0
    while index < len(fmt):
        character = fmt[index]
        if character == "%" and index + 1 < len(fmt):
            code = fmt[index + 1]
            if code not in _STRFTIME:
                raise DialectError(f"strftime format %{code} is not supported on Oracle.")
            parts.append(_STRFTIME[code])
            index += 2
            continue
        text = character
        index += 1
        while index < len(fmt) and fmt[index] != "%":
            text += fmt[index]
            index += 1
        parts.append('"' + text + '"')
    return "'" + "".join(parts) + "'"


def _rewrite_functions(code: str, masked: _Masked) -> str:
    def datetime(arguments: List[str]) -> str:
        moment = _moment(masked, arguments)
        if moment is None:
            return _iso_text(masked, arguments[0], 19)
        return f"TO_CHAR({moment}, {_DATETIME_FORMAT})"

    def date(arguments: List[str]) -> str:
        moment = _moment(masked, arguments)
        if moment is None:
            return _iso_text(masked, arguments[0], 10)
        return f"TO_CHAR({moment}, {_DATE_FORMAT})"

    def strftime(arguments: List[str]) -> str:
        fmt = masked.literal(arguments[0])
        if fmt is None:
            raise DialectError("strftime needs a literal format.")
        moment = _moment(masked, arguments[1:]) or _parsed(masked, arguments[1])
        return f"TO_CHAR({moment}, {_strftime_format(fmt)})"

    def julianday(arguments: List[str]) -> str:
        moment = _moment(masked, arguments) or _parsed(masked, arguments[0])
        epoch = _literal(masked, "'1970-01-01'")
        return f"(CAST({moment} AS DATE) - TO_DATE({epoch}, {_DATE_FORMAT}) + 2440587.5)"

    def group_concat(arguments: List[str]) -> str:
        separator = arguments[1] if len(arguments) > 1 else _literal(masked, "','")
        return f"LISTAGG({arguments[0]}, {separator}) WITHIN GROUP (ORDER BY NULL)"

    def extreme(name: str) -> Callable[[List[str]], str]:
        def build(arguments: List[str]) -> str:
            if len(arguments) > 1:
                return f"{'GREATEST' if name == 'max' else 'LEAST'}({', '.join(arguments)})"
            return f"\x02{name}\x02({arguments[0]})"

        return build

    code = _rewrite_calls(code, "datetime", datetime)
    code = _rewrite_calls(code, "date", date)
    code = _rewrite_calls(code, "strftime", strftime)
    code = _rewrite_calls(code, "julianday", julianday)
    code = _rewrite_calls(code, "group_concat", group_concat)
    # Two or more arguments: SQLite's scalar max/min. One: the aggregate, kept as it is.
    code = _rewrite_calls(code, "max", extreme("max"))
    code = _rewrite_calls(code, "min", extreme("min"))
    code = re.sub(r"\x02(max|min)\x02", lambda m: m.group(1).upper(), code)
    code = re.sub(r"\bIFNULL\s*\(", "COALESCE(", code, flags=re.I)
    code = re.sub(
        r"\bCURRENT_TIMESTAMP\b", f"TO_CHAR({_NOW}, {_DATETIME_FORMAT})", code, flags=re.I
    )
    code = re.sub(r"\bCURRENT_DATE\b", f"TO_CHAR({_NOW}, {_DATE_FORMAT})", code, flags=re.I)
    code = re.sub(r"\bAS\s+TEXT\s*\)", f"AS VARCHAR2({_VARCHAR}))", code, flags=re.I)
    code = re.sub(r"\bAS\s+(?:INTEGER|INT|BIGINT)\s*\)", "AS NUMBER(19))", code, flags=re.I)
    code = re.sub(r"\bAS\s+(?:REAL|FLOAT|DOUBLE)\s*\)", "AS BINARY_DOUBLE)", code, flags=re.I)
    return re.sub(r"\bAS\s+NUMERIC\s*\)", "AS NUMBER)", code, flags=re.I)


def _set_spans(code: str) -> List[Tuple[int, int]]:
    """Where assignments are (UPDATE ... SET a = 1, b = 2), which are not comparisons."""

    spans = []
    for match in re.finditer(r"\bSET\b", code, re.I):
        stop = _find_top(code, r"\bWHERE\b|\bWHEN\b", match.end())
        spans.append((match.end(), stop.start() if stop else len(code)))
    return spans


def _inside(position: int, spans: Sequence[Tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in spans)


def _rewrite_empty_text(code: str, masked: _Masked) -> str:
    """Comparisons with '' become IS [NOT] NULL: Oracle stores '' as NULL."""

    empty = {index for index, token in enumerate(masked.values) if token == "''"}
    if not empty:
        return code
    spans = _set_spans(code)

    def compare(match: re.Match) -> str:
        if int(match.group(2)) not in empty or _inside(match.start(), spans):
            return str(match.group(0))
        return " IS NULL" if match.group(1) == "=" else " IS NOT NULL"

    return re.sub(r"\s*((?<![<>!])=|<>|!=)\s*\x00(\d+)\x00", compare, code)


def _rewrite_null_safe(code: str) -> str:
    """SQLite's `a IS ?` compares with anything; DECODE matches NULL with NULL too."""

    while True:
        match = re.search(r"\bIS\s+(NOT\s+)?(\x01\d+\x01)", code, re.I)
        if match is None:
            return code
        start = _operand_start(code, match.start())
        operand = code[start : match.start()].strip()
        wanted = "0" if match.group(1) else "1"
        code = (
            code[:start]
            + f"DECODE({operand}, {match.group(2)}, 1, 0) = {wanted}"
            + code[match.end() :]
        )


def _rewrite_limits(code: str) -> str:
    """LIMIT n [OFFSET m], and LIMIT m, n: Oracle's row limiting clause (12c and later)."""

    pattern = re.compile(
        r"\bLIMIT\s+(?P<a>[^\s,()]+)(?:\s*,\s*(?P<b>[^\s,()]+)|\s+OFFSET\s+(?P<offset>[^\s,()]+))?",
        re.I,
    )

    def build(match: re.Match) -> str:
        if match.group("b"):
            offset, limit = match.group("a"), match.group("b")
        else:
            offset, limit = match.group("offset"), match.group("a")
        fetch = "" if limit.strip() == "-1" else f"FETCH NEXT {limit} ROWS ONLY"
        if offset:
            return f"OFFSET {offset} ROWS {fetch}".rstrip()
        return fetch.replace("NEXT", "FIRST")

    return pattern.sub(build, code)


def _rewrite_from_dual(code: str) -> str:
    """Oracle's SELECT always reads from something: DUAL when SQLite reads from nothing."""

    position = 0
    while True:
        match = re.compile(r"\bSELECT\b", re.I).search(code, position)
        if match is None:
            return code
        # The extent of this SELECT: to the closing parenthesis of its group, or the end.
        depth = 0
        end = len(code)
        for index in range(match.end(), len(code)):
            if code[index] == "(":
                depth += 1
            elif code[index] == ")":
                if depth == 0:
                    end = index
                    break
                depth -= 1
        own = _find_top(
            code, r"\bFROM\b|\bUNION\b|\bINTERSECT\b|\bMINUS\b|\bEXCEPT\b", match.end(), end
        )
        if own is None or own.group(0).upper() != "FROM":
            stop = own.start() if own else end
            clause = _find_top(code, r"\b(?:WHERE|GROUP|ORDER|FETCH|OFFSET)\b", match.end(), stop)
            insert_at = clause.start() if clause else stop
            code = code[:insert_at].rstrip() + " FROM DUAL " + code[insert_at:]
        position = match.end()


def _rewrite_aliases(code: str) -> str:
    """Oracle names a table or subquery in FROM without AS."""

    code = re.sub(
        r"(\b(?:FROM|JOIN)\s+" + _NAME + r")\s+AS\s+(?=" + _NAME + r")", r"\1 ", code, flags=re.I
    )
    position = 0
    while True:
        match = re.compile(r"\b(?:FROM|JOIN)\s*\(", re.I).search(code, position)
        if match is None:
            return code
        close = _closing(code, match.end() - 1)
        alias = re.match(r"\s+AS\s+(?=" + _NAME + r")", code[close + 1 :], re.I)
        if alias:
            code = code[: close + 1] + " " + code[close + 1 + alias.end() :]
        position = match.end()


def _rewrite_expressions(code: str, masked: _Masked) -> str:
    code = _rewrite_functions(code, masked)
    # SQLite takes a number as a condition; Oracle only a comparison.
    code = re.sub(
        r"\b(WHERE|AND|OR|HAVING|ON|WHEN)\s+([01])(?=\s*(?:$|;|\)|\b(?:AND|OR|ORDER|GROUP|LIMIT|HAVING|THEN)\b))",
        lambda m: f"{m.group(1)} 1 = {'0' if m.group(2) == '0' else '1'}",
        code,
        flags=re.I,
    )
    code = re.sub(r"\bTRUE\b", "1", code, flags=re.I)
    code = re.sub(r"\bFALSE\b", "0", code, flags=re.I)
    code = _rewrite_null_safe(code)
    code = _rewrite_empty_text(code, masked)
    code = re.sub(
        r"(" + _REF + r")\s*=\s*(\x01\d+\x01)\s+COLLATE\s+NOCASE\b",
        r"LOWER(\1) = LOWER(\2)",
        code,
        flags=re.I,
    )
    code = re.sub(r"(" + _REF + r")\s+COLLATE\s+NOCASE\b", r"LOWER(\1)", code, flags=re.I)
    code = re.sub(r"\s+COLLATE\s+\w+", "", code, flags=re.I)
    code = re.sub(r"\bsqlite_(?:master|schema)\b", _MASTER, code, flags=re.I)
    code = _rewrite_limits(code)
    code = _rewrite_aliases(code)
    return _rewrite_from_dual(code)


def _tables(code: str, masked: _Masked) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """The tables a statement names, and those it only outer-joins."""

    tables = []
    outer = []
    for match in re.finditer(
        r"\b(LEFT\s+(?:OUTER\s+)?JOIN|RIGHT\s+(?:OUTER\s+)?JOIN|FULL\s+(?:OUTER\s+)?JOIN|JOIN|FROM|UPDATE|INTO)\s+("
        + _NAME
        + r")",
        code,
        re.I,
    ):
        name = _plain(masked, match.group(2)).lower()
        if name in ("dual", "select") or name.startswith("("):
            continue
        tables.append(name)
        if not match.group(1).upper().startswith("JOIN") and match.group(1).upper() not in (
            "FROM",
            "UPDATE",
            "INTO",
        ):
            outer.append(name)
    return tuple(dict.fromkeys(tables)), tuple(dict.fromkeys(outer))


def _rewrite_clob_compare(code: str, tables: Sequence[str], catalog: Optional[Catalog]) -> str:
    """A CLOB cannot be compared with `=`; DBMS_LOB.COMPARE can."""

    if catalog is None or not tables:
        return code
    clobs: Set[str] = set()
    for table in tables:
        try:
            clobs |= {name.lower() for name in catalog.clob_columns(table)}
        except Exception:  # noqa: BLE001 - a table that does not exist yet has no CLOBs
            continue
    if not clobs:
        return code
    spans = _set_spans(code)

    def compare(match: re.Match) -> str:
        name = match.group(2).strip('"').lower()
        if name not in clobs or _inside(match.start(), spans):
            return str(match.group(0))
        operator = "=" if match.group(3) == "=" else "<>"
        return f"DBMS_LOB.COMPARE({match.group(1)}, TO_CLOB({match.group(4)})) {operator} 0"

    return re.sub(
        r"((?:[\w\x00$#\"]+\.)?([\w$#\"]+))\s*((?<![<>!])=|<>|!=)\s*(\x01\d+\x01|\x00\d+\x00)",
        compare,
        code,
    )


# ----------------------------------------------------------------------
# Tables and indexes
# ----------------------------------------------------------------------

_CONSTRAINT = re.compile(
    r"\s*(?:"
    r"(?P<pk>PRIMARY\s+KEY(?:\s+(?:ASC|DESC))?(?:\s+AUTOINCREMENT)?)"
    r"|(?P<notnull>NOT\s+NULL)"
    r"|(?P<null>NULL)"
    r"|(?P<unique>UNIQUE)"
    r"|(?P<default>DEFAULT\s+)"
    r"|(?P<check>CHECK\s*\()"
    r"|(?P<collate>COLLATE\s+\w+)"
    r"|(?P<named>CONSTRAINT\s+" + _NAME + r")"
    r"|(?P<on_conflict>ON\s+CONFLICT\s+\w+)"
    r")",
    re.I,
)


def _default_value(rest: str) -> Tuple[str, str]:
    """The expression after DEFAULT, and what follows it."""

    rest = rest.lstrip()
    if rest.startswith("("):
        close = _closing(rest, 0)
        return rest[: close + 1], rest[close + 1 :]
    match = re.match(r"[-+]?\d+(?:\.\d+)?|\x00\d+\x00|\w+", rest)
    if match is None:
        raise DialectError(f"Cannot read the default value in '{rest[:40]}'.")
    value = match.group(0)
    if value.upper() == "TRUE":
        value = "1"
    elif value.upper() == "FALSE":
        value = "0"
    return value, rest[match.end() :]


def _text_type(table: str, column: str, size: Optional[int], catalog: Optional[Catalog]) -> str:
    if catalog is not None:
        override = catalog.text_type(table, column)
        if override:
            return override
    if size is not None:
        return f"VARCHAR2({size})"
    if _LARGE_TEXT.search(column):
        return "CLOB"
    return f"VARCHAR2({_VARCHAR})"


def _key_size(count: int) -> int:
    return min(_VARCHAR, max(100, INDEX_BUDGET // max(count, 1)))


def _column_definition(
    table: str,
    part: str,
    masked: _Masked,
    keyed: Dict[str, int],
    catalog: Optional[Catalog],
) -> Tuple[str, Optional[str]]:
    """One column for Oracle, and its name when it is text that must not be NULL."""

    match = re.match(r"\s*(" + _NAME + r")", part)
    if match is None:
        raise DialectError(f"Cannot read the column definition '{part[:60]}'.")
    raw_name = match.group(1)
    name = _plain(masked, raw_name)
    rest = part[match.end() :]
    type_match = re.match(r"\s*([A-Za-z_]\w*)(\s*\([^)]*\))?", rest)
    declared = ""
    if type_match and not _CONSTRAINT.match(rest):
        declared = type_match.group(1).upper()
        rest = rest[type_match.end() :]

    default = None
    not_null = primary = unique = False
    checks: List[str] = []
    named = ""
    while rest.strip():
        clause = _CONSTRAINT.match(rest)
        if clause is None:
            raise DialectError(f"Cannot read '{rest.strip()[:40]}' in column {name}.")
        rest = rest[clause.end() :]
        if clause.group("pk"):
            primary = True
        elif clause.group("notnull"):
            not_null = True
        elif clause.group("unique"):
            unique = True
        elif clause.group("default"):
            default, rest = _default_value(rest)
        elif clause.group("check"):
            # CHECK( was read with its parenthesis: take everything up to the one closing it.
            close = _closing("(" + rest, 0)
            checks.append("CHECK (" + rest[: close - 1] + ")")
            rest = rest[close:]
        elif clause.group("named"):
            named = clause.group("named") + " "

    column = _column(name)
    if raw_name.startswith("\x00"):
        column = masked.values[int(_MASK.fullmatch(raw_name).group(1))]  # type: ignore[union-attr]

    if primary and declared in ("INTEGER", "INT", "BIGINT", ""):
        # SQLite's rowid key: new rows get the next number unless one is given.
        return f"{column} NUMBER(19) GENERATED BY DEFAULT ON NULL AS IDENTITY PRIMARY KEY", None

    blank: Optional[str] = None
    if declared in ("INTEGER", "INT", "BIGINT", "SMALLINT", "TINYINT", "BOOLEAN", "BOOL"):
        oracle_type = "NUMBER(19)"
    elif declared in ("REAL", "FLOAT", "DOUBLE"):
        oracle_type = "BINARY_DOUBLE"
    elif declared in ("NUMERIC", "DECIMAL"):
        oracle_type = "NUMBER"
    elif declared == "BLOB":
        oracle_type = "BLOB"
    else:
        size = None
        if name.lower() in keyed:
            size = _key_size(keyed[name.lower()])
        elif primary or unique:
            size = _key_size(1)
        oracle_type = _text_type(table, name.lower(), size, catalog)
        if not_null:
            # Oracle would refuse ''. The comment keeps that it was NOT NULL, to read NULL as ''.
            not_null = False
            blank = name

    pieces = [column, oracle_type]
    if default is not None:
        pieces.append(f"DEFAULT {default}")
    if not_null:
        pieces.append("NOT NULL")
    if primary:
        pieces.append(named + "PRIMARY KEY")
    elif unique:
        pieces.append(named + "UNIQUE")
    pieces.extend(checks)
    return " ".join(pieces), blank


def _keyed_columns(parts: Sequence[str], masked: _Masked) -> Dict[str, int]:
    """Columns in a table-level PRIMARY KEY or UNIQUE, with how many share that key."""

    keyed: Dict[str, int] = {}
    for part in parts:
        match = re.match(
            r"\s*(?:CONSTRAINT\s+" + _NAME + r"\s+)?(?:PRIMARY\s+KEY|UNIQUE)\s*\((.*)\)",
            part,
            re.I | re.S,
        )
        if match:
            names = [_plain(masked, item.split()[0]) for item in _split_top(match.group(1))]
            for name in names:
                keyed[name.lower()] = max(keyed.get(name.lower(), 0), len(names))
    return keyed


def _comment(table: str, column: str) -> str:
    return f"COMMENT ON COLUMN {_column(table)}.{_column(column)} IS '{BLANK_MARK}'"


def _create_table(
    code: str, masked: _Masked, catalog: Optional[Catalog]
) -> Tuple[str, List[str], FrozenSet[int]]:
    match = re.match(
        r"\s*CREATE\s+(?:TEMP\s+|TEMPORARY\s+)?TABLE\s+(?P<ifnot>IF\s+NOT\s+EXISTS\s+)?(?P<name>"
        + _NAME
        + r")\s*",
        code,
        re.I,
    )
    if match is None:
        raise DialectError("Cannot read the CREATE TABLE statement.")
    ignore = ALREADY_EXISTS if match.group("ifnot") else frozenset()
    table = _plain(masked, match.group("name"))
    written = match.group("name")
    head = f"CREATE TABLE {written if written.startswith(chr(0)) else _column(table)}"
    rest = code[match.end() :]
    if re.match(r"AS\b", rest, re.I):
        return f"{head} {rest}", [], ignore
    if not rest.startswith("("):
        raise DialectError(f"Cannot read the columns of table {table}.")
    close = _closing(rest, 0)
    body = rest[1:close]
    body = _TABLE_FOREIGN_KEY.sub("", "," + body)[1:]
    body = _INLINE_FOREIGN_KEY.sub("", body)
    parts = _split_top(body)
    keyed = _keyed_columns(parts, masked)
    columns: List[str] = []
    blanks: List[str] = []
    for part in parts:
        if re.match(
            r"\s*(?:CONSTRAINT\s+" + _NAME + r"\s+)?(?:PRIMARY\s+KEY|UNIQUE|CHECK|FOREIGN\s+KEY)\b",
            part,
            re.I,
        ):
            columns.append(_quote_constraint(part, masked))
            continue
        definition, blank = _column_definition(table, part, masked, keyed, catalog)
        columns.append(definition)
        if blank:
            blanks.append(blank)
    # Table options SQLite knows (WITHOUT ROWID, STRICT) mean nothing here.
    return f"{head} ({', '.join(columns)})", [_comment(table, name) for name in blanks], ignore


def _quote_constraint(part: str, masked: _Masked) -> str:
    match = re.match(
        r"(\s*(?:CONSTRAINT\s+" + _NAME + r"\s+)?(?:PRIMARY\s+KEY|UNIQUE)\s*)\((.*)\)\s*$",
        part,
        re.I | re.S,
    )
    if match is None:
        return part
    names = [_column(_plain(masked, item.split()[0])) for item in _split_top(match.group(2))]
    return f"{match.group(1).strip()} ({', '.join(names)})"


def _alter_table(code: str, masked: _Masked, catalog: Optional[Catalog]) -> Tuple[str, List[str]]:
    match = re.match(
        r"\s*ALTER\s+TABLE\s+(" + _NAME + r")\s+ADD\s+(?:COLUMN\s+)?(.*)$", code, re.I | re.S
    )
    if match is None:
        return code, []
    table = _plain(masked, match.group(1))
    definition, blank = _column_definition(table, match.group(2), masked, {}, catalog)
    followups = [_comment(table, blank)] if blank else []
    return f"ALTER TABLE {match.group(1)} ADD ({definition})", followups


def _create_index(
    code: str, masked: _Masked
) -> Tuple[str, FrozenSet[int], Optional[Tuple[str, Tuple[str, ...]]]]:
    match = re.match(
        r"\s*CREATE\s+(?P<unique>UNIQUE\s+)?INDEX\s+(?P<ifnot>IF\s+NOT\s+EXISTS\s+)?(?P<name>"
        + _NAME
        + r")\s+ON\s+(?P<table>"
        + _NAME
        + r")\s*\(",
        code,
        re.I,
    )
    if match is None:
        raise DialectError("Cannot read the CREATE INDEX statement.")
    ignore = ALREADY_EXISTS if match.group("ifnot") else frozenset()
    close = _closing(code, match.end() - 1)
    items = _split_top(code[match.end() : close])
    condition = re.match(r"\s*WHERE\s+(.*)$", code[close + 1 :], re.I | re.S)
    table = _plain(masked, match.group("table"))
    plain: List[str] = []
    columns: List[str] = []
    for item in items:
        item = re.sub(r"\s+(?:ASC|DESC)\s*$", "", item, flags=re.I)
        nocase = re.search(r"\s+COLLATE\s+NOCASE\s*$", item, re.I)
        item = re.sub(r"\s+COLLATE\s+\w+\s*$", "", item, flags=re.I)
        if re.fullmatch(_NAME, item.strip()):
            plain.append(_plain(masked, item.strip()))
            item = (
                _column(_plain(masked, item.strip()))
                if not item.strip().startswith("\x00")
                else item.strip()
            )
        if nocase:
            item = f"LOWER({item})"
        if condition:
            # No partial indexes in Oracle: rows outside the condition get a NULL key,
            # and a key that is all NULL is not indexed, so it cannot clash either.
            item = f"CASE WHEN {condition.group(1).strip()} THEN {item} END"
        columns.append(item)
    unique = "UNIQUE " if match.group("unique") else ""
    name, on = match.group("name"), match.group("table")
    text = f"CREATE {unique}INDEX {name} ON {on} ({', '.join(columns)})"
    return text, ignore, (table, tuple(plain))


# ----------------------------------------------------------------------
# INSERT OR IGNORE / OR REPLACE / ON CONFLICT
# ----------------------------------------------------------------------

_INSERT = re.compile(
    r"^\s*(?P<verb>INSERT\s+OR\s+(?P<mode>IGNORE|REPLACE)\s+INTO|REPLACE\s+INTO|INSERT\s+INTO)"
    r"\s+(?P<table>" + _NAME + r")\s*",
    re.I,
)


def _qualify(expression: str, table: str, columns: Set[str]) -> str:
    """Bare column names in an ON CONFLICT update are the row already there."""

    def name(match: re.Match) -> str:
        word = str(match.group(0))
        if word.lower() in columns and word.lower() not in _KEYWORDS:
            return f"{table}.{_column(word)}"
        return word

    return re.sub(r"(?<![\w.\x00$#\"\x01])[A-Za-z_][\w$#]*(?![\w$#\x00]|\s*\()", name, expression)


def _select_as(select: str, names: Sequence[str]) -> str:
    """A SELECT whose results are named like the columns they fill."""

    match = re.match(r"\s*SELECT\s+(DISTINCT\s+)?", select, re.I)
    if match is None:
        raise DialectError("Cannot read the SELECT of an INSERT.")
    end = _find_top(select, r"\bFROM\b", match.end())
    stop = end.start() if end else len(select)
    items = _split_top(select[match.end() : stop])
    if len(items) != len(names):
        raise DialectError("The INSERT names a different number of columns than it selects.")
    renamed = []
    for item, name in zip(items, names):
        alias = re.search(r"[\w\x00)\x01]\s+(?:AS\s+)?([A-Za-z_][\w$#]*)\s*$", item, re.I)
        if alias and alias.group(1).lower() not in _KEYWORDS:
            item = item[: alias.start(1)].rstrip()
            item = re.sub(r"\s+AS$", "", item, flags=re.I)
        renamed.append(f"{item} AS {_column(name)}")
    return select[: match.end()] + ", ".join(renamed) + " " + select[stop:]


def _rewrite_insert(
    code: str,
    masked: _Masked,
    catalog: Optional[Catalog],
) -> Tuple[str, Optional[str], bool, FrozenSet[int]]:
    """Returns the statement, the generated key to return, whether duplicates are ignored,
    and the parameters that are assigned values."""

    match = _INSERT.match(code)
    if match is None:
        return code, None, False, frozenset()
    verb = match.group("verb").upper()
    mode = (match.group("mode") or "").upper()
    replacing = verb.startswith("REPLACE") or mode == "REPLACE"
    ignoring = mode == "IGNORE"
    table_token = match.group("table")
    table = _plain(masked, table_token)
    rest = code[match.end() :].rstrip().rstrip(";")

    names: Optional[List[str]] = None
    if rest.startswith("("):
        close = _closing(rest, 0)
        names = [_plain(masked, item) for item in _split_top(rest[1:close])]
        rest = rest[close + 1 :].lstrip()

    conflict = _find_top(rest, r"\bON\s+CONFLICT\b")
    conflict_text = rest[conflict.start() :] if conflict else ""
    source = rest[: conflict.start()].strip() if conflict else rest.strip()
    column_list = f" ({', '.join(_column(n) for n in names)})" if names else ""

    plain = f"INSERT INTO {table_token}{column_list} {source}"
    if not (replacing or ignoring or conflict):
        returning = None
        if catalog is not None and re.match(r"VALUES\b", source, re.I):
            returning = catalog.identity(table)
        return plain, returning, False, frozenset()

    if catalog is None:
        raise DialectError(f"Merging rows into {table} needs the table's catalog.")
    if names is None:
        names = catalog.columns(table)

    update: Optional[str] = None
    condition = ""
    key: List[str] = []
    if conflict:
        target = re.match(
            r"ON\s+CONFLICT\s*(?:\((.*?)\))?\s*DO\s+(NOTHING|UPDATE\s+SET\s+(.*))$",
            conflict_text,
            re.I | re.S,
        )
        if target is None:
            raise DialectError("Cannot read the ON CONFLICT clause.")
        key = [_plain(masked, item) for item in _split_top(target.group(1) or "")]
        if target.group(3):
            update = target.group(3)
            where = _find_top(update, r"\bWHERE\b")
            if where:
                condition = update[where.end() :].strip()
                update = update[: where.start()].strip()
    filled = {name.lower() for name in names}
    if not key:
        key = next(
            (k for k in catalog.unique_keys(table) if k and {c.lower() for c in k} <= filled), []
        )
    if not key:
        # No unique key among the columns given: nothing can be matched, so a plain INSERT,
        # whose duplicates (on a key it does not fill) are ignored when SQLite would.
        returning = catalog.identity(table) if re.match(r"VALUES\b", source, re.I) else None
        return plain, returning, ignoring, frozenset()

    if re.match(r"VALUES\b", source, re.I):
        values = source[source.index("(") : _closing(source, source.index("(")) + 1]
        items = _split_top(values[1:-1])
        if len(items) != len(names):
            raise DialectError(
                f"The INSERT into {table} gives {len(items)} values for {len(names)} columns."
            )
        selected = (
            "SELECT "
            + ", ".join(f"{item} AS {_column(name)}" for item, name in zip(items, names))
            + " FROM DUAL"
        )
    else:
        selected = _select_as(source, names)

    target_name = table_token
    columns = {name.lower() for name in catalog.columns(table)} | {name.lower() for name in names}
    on = " AND ".join(f"{target_name}.{_column(name)} = excluded.{_column(name)}" for name in key)
    lowered_key = {name.lower() for name in key}
    assigned: Set[int] = set()
    sets: List[str] = []
    if update is not None:
        for assignment in _split_top(update):
            left, _, right = assignment.partition("=")
            column = _plain(masked, left.strip().split(".")[-1])
            if column.lower() in lowered_key:
                continue  # Oracle cannot update the columns it matched on; they are equal anyway.
            assigned |= {int(index) for index in _BIND.findall(right)}
            sets.append(f"{_column(column)} = {_qualify(right.strip(), target_name, columns)}")
    elif replacing:
        sets = [
            f"{_column(name)} = excluded.{_column(name)}"
            for name in names
            if name.lower() not in lowered_key
        ]

    merge = f"MERGE INTO {target_name} USING ({selected}) excluded ON ({on})"
    if sets:
        merge += " WHEN MATCHED THEN UPDATE SET " + ", ".join(sets)
        if condition:
            merge += " WHERE " + _qualify(condition, target_name, columns)
    merge += (
        f" WHEN NOT MATCHED THEN INSERT ({', '.join(_column(n) for n in names)})"
        f" VALUES ({', '.join('excluded.' + _column(n) for n in names)})"
    )
    return merge, None, ignoring, frozenset(assigned)


# ----------------------------------------------------------------------
# PRAGMA
# ----------------------------------------------------------------------

_PRAGMA = re.compile(
    r"^\s*PRAGMA\s+(?P<name>\w+)\s*(?:\(\s*['\"]?(?P<argument>[\w$#]+)['\"]?\s*\))?", re.I
)


def _pragma(sql: str) -> Optional[OracleStatement]:
    match = _PRAGMA.match(sql)
    if match is None:
        return None
    name = match.group("name").lower()
    argument = (match.group("argument") or "").upper().replace("'", "")
    if name == "table_info" and argument:
        return OracleStatement(
            "SELECT c.column_id - 1 AS cid, LOWER(c.column_name) AS name, c.data_type AS type,"
            " CASE WHEN c.nullable = 'N' OR m.comments = '"
            + BLANK_MARK
            + '\' THEN 1 ELSE 0 END AS "notnull",'
            " CAST(NULL AS VARCHAR2(1)) AS dflt_value,"
            " CASE WHEN EXISTS (SELECT 1 FROM all_constraints k JOIN all_cons_columns kc"
            " ON kc.owner = k.owner AND kc.constraint_name = k.constraint_name"
            f" WHERE k.owner = c.owner AND k.table_name = c.table_name AND k.constraint_type = 'P'"
            " AND kc.column_name = c.column_name) THEN 1 ELSE 0 END AS pk"
            " FROM all_tab_columns c LEFT JOIN all_col_comments m ON m.owner = c.owner"
            " AND m.table_name = c.table_name AND m.column_name = c.column_name"
            f" WHERE c.owner = {_SCHEMA} AND c.table_name = '{argument}' ORDER BY c.column_id",
            [],
        )
    if name == "index_list" and argument:
        return OracleStatement(
            "SELECT ROWNUM - 1 AS seq, LOWER(index_name) AS name,"
            " CASE WHEN uniqueness = 'UNIQUE' THEN 1 ELSE 0 END AS \"unique\","
            " 'c' AS origin, 0 AS partial FROM all_indexes"
            f" WHERE table_owner = {_SCHEMA} AND table_name = '{argument}' AND index_type <> 'LOB'",
            [],
        )
    if name == "index_info" and argument:
        return OracleStatement(
            "SELECT column_position - 1 AS seqno, -1 AS cid, LOWER(column_name) AS name"
            f" FROM all_ind_columns WHERE index_owner = {_SCHEMA} AND index_name = '{argument}'"
            " ORDER BY column_position",
            [],
        )
    if name == "foreign_keys":
        return OracleStatement("SELECT 0 AS foreign_keys FROM DUAL", [])
    return OracleStatement(_NOTHING, [], noop=True)


# ----------------------------------------------------------------------
# Entry points
# ----------------------------------------------------------------------


def translate(sql: str, catalog: Optional[Catalog] = None) -> OracleStatement:
    """One SQLite statement as Oracle SQL, with named parameters."""

    pragma = _pragma(sql)
    if pragma is not None:
        return pragma
    if re.match(r"\s*(?:VACUUM|ANALYZE|REINDEX)\b", sql, re.I):
        return OracleStatement(_NOTHING, [], noop=True)

    masked = _Masked(sql)
    _upper_quoted(masked)
    code = _number_binds(masked.code).strip().rstrip(";").strip()
    code = _rewrite_blob_literals(code, masked)
    code = _quote_reserved(code)
    followups: List[str] = []
    ignore: FrozenSet[int] = frozenset()
    index = None

    if re.match(r"\s*CREATE\s+(?:TEMP\s+|TEMPORARY\s+)?TABLE\b", code, re.I):
        code, followups, ignore = _create_table(code, masked, catalog)
    elif re.match(r"\s*CREATE\s+(?:UNIQUE\s+)?INDEX\b", code, re.I):
        code, ignore, index = _create_index(code, masked)
    elif re.match(r"\s*ALTER\s+TABLE\b", code, re.I):
        code, followups = _alter_table(code, masked, catalog)
    elif re.match(r"\s*DROP\s+TABLE\b", code, re.I):
        exists = re.match(r"\s*DROP\s+TABLE\s+IF\s+EXISTS\s+", code, re.I)
        if exists:
            ignore = MISSING_TABLE
            code = "DROP TABLE " + code[exists.end() :]
        code += " PURGE"
    elif re.match(r"\s*DROP\s+INDEX\b", code, re.I):
        exists = re.match(r"\s*DROP\s+INDEX\s+IF\s+EXISTS\s+", code, re.I)
        if exists:
            ignore = MISSING_INDEX
            code = "DROP INDEX " + code[exists.end() :]

    code = _rewrite_expressions(code, masked)
    tables, outer = _tables(code, masked)
    code = _rewrite_clob_compare(code, tables, catalog)
    code, returning, ignore_duplicates, assigned = _rewrite_insert(code, masked, catalog)
    if re.match(r"\s*UPDATE\b", code, re.I):
        assigned = assigned | _assigned_in_set(code)
    return OracleStatement(
        code.strip(),
        masked.values,
        returning=returning,
        ignore=ignore,
        ignore_duplicates=ignore_duplicates,
        followups=[_MASK.sub(lambda m: masked.values[int(m.group(1))], item) for item in followups],
        tables=tables,
        outer_tables=outer,
        assigned=assigned,
        index=index,
    )


def _assigned_in_set(code: str) -> FrozenSet[int]:
    """Parameters given as new values (UPDATE t SET a = ?), not compared with."""

    assigned: Set[int] = set()
    for start, end in _set_spans(code):
        for span_start, span_end in _top_level(code, start, end):
            for match in re.finditer(r"=\s*\x01(\d+)\x01", code[span_start:span_end]):
                assigned.add(int(match.group(1)))
    return frozenset(assigned)


def split_statements(script: str) -> List[str]:
    """The statements of a script (shared with the PostgreSQL translator)."""

    from lib.database.dialect import split_statements as split

    return split(script)
