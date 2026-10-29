"""Plain-text tables, JSON and YAML: the output modes of the command contract."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from typing import Any, Callable, Iterable, List, Optional, Sequence, Tuple

# (header, value of an item, shown only in wide/detailed)
Column = Tuple[str, Callable[[Any], Any], bool]


def emit_json(data: Any) -> None:
    json.dump(data, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


def when(value: Any) -> str:
    """ISO timestamps as local 'YYYY-MM-DD HH:MM'."""

    if not value:
        return "-"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone()
    return parsed.strftime("%Y-%m-%d %H:%M")


def _cell(value: Any) -> str:
    return "-" if value is None or value == "" else str(value)


def plain_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    """Columns padded to their widest cell, like kubectl/oc."""

    cells: List[List[str]] = [[str(header).upper() for header in headers]]
    cells.extend([_cell(value) for value in row] for row in rows)
    if len(cells) == 1:
        return "No resources found."
    widths = [max(len(row[index]) for row in cells) for index in range(len(headers))]
    return "\n".join(
        "   ".join(value.ljust(widths[index]) for index, value in enumerate(row)).rstrip()
        for row in cells
    )


def boxed_table(title: str, headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    """A titled table with borders: the detailed mode."""

    cells: List[List[str]] = [[str(header) for header in headers]]
    cells.extend([_cell(value) for value in row] for row in rows)
    if len(cells) == 1:
        return f"{title}\nNo resources found."
    widths = [max(len(row[index]) for row in cells) for index in range(len(headers))]

    def line(left: str, middle: str, right: str) -> str:
        return left + middle.join("─" * (width + 2) for width in widths) + right

    def row(values: Sequence[str]) -> str:
        return "│" + "│".join(f" {v.ljust(widths[i])} " for i, v in enumerate(values)) + "│"

    lines = [f"{title} ({len(cells) - 1})", line("┌", "┬", "┐"), row(cells[0])]
    lines.append(line("├", "┼", "┤"))
    lines.extend(row(values) for values in cells[1:])
    lines.append(line("└", "┴", "┘"))
    return "\n".join(lines)


def table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> None:
    print(plain_table(headers, rows))


_PLAIN = re.compile(r"^[A-Za-z0-9_./@+-][A-Za-z0-9_ ./@:+-]*$")
_RESERVED = {"true", "false", "yes", "no", "null", "on", "off", "~"}


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if _PLAIN.match(text) and text.lower() not in _RESERVED and not text.endswith(" "):
        try:
            float(text)
        except ValueError:
            return text
    return json.dumps(text, ensure_ascii=False)


def to_yaml(data: Any, indent: int = 0) -> str:
    """Block-style YAML for JSON-like data (the standard library has no YAML)."""

    pad = "  " * indent
    if isinstance(data, dict):
        if not data:
            return pad + "{}"
        lines = []
        for key, value in data.items():
            name = _yaml_scalar(str(key))
            if isinstance(value, (dict, list)) and value:
                lines.append(f"{pad}{name}:")
                lines.append(to_yaml(value, indent + 1))
            else:
                lines.append(f"{pad}{name}: {to_yaml(value).strip()}")
        return "\n".join(lines)
    if isinstance(data, list):
        if not data:
            return pad + "[]"
        lines = []
        for value in data:
            if isinstance(value, (dict, list)) and value:
                nested = to_yaml(value, indent + 1).splitlines()
                lines.append(f"{pad}- {nested[0].strip()}")
                lines.extend(nested[1:])
            else:
                lines.append(f"{pad}- {to_yaml(value).strip()}")
        return "\n".join(lines)
    return pad + _yaml_scalar(data)


def render(
    mode: str,
    items: Sequence[Any],
    columns: Sequence[Column],
    *,
    title: str,
    kind: str,
    name: Optional[Callable[[Any], Any]] = None,
    data: Any = None,
) -> str:
    """
    Items in an output mode. `data` is what json/yaml print (default the
    items); `name` gives the `kind/name` of an item (default column one).
    """

    if mode == "json":
        return json.dumps(items if data is None else data, indent=2, default=str)
    if mode == "yaml":
        return to_yaml(json.loads(json.dumps(items if data is None else data, default=str)))
    if mode == "name":
        named = name or columns[0][1]
        return "\n".join(f"{kind}/{named(item)}" for item in items)
    shown = [column for column in columns if mode != "table" or not column[2]]
    headers = [column[0] for column in shown]
    rows = [[column[1](item) for column in shown] for item in items]
    if mode == "detailed":
        return boxed_table(title, [header.title() for header in headers], rows)
    return plain_table(headers, rows)
