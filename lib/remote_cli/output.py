"""Plain-text tables and JSON output."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from typing import Any, Iterable, List, Sequence


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


def table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> None:
    """Columns padded to their widest cell, like kubectl/oc."""

    cells: List[List[str]] = [[str(header).upper() for header in headers]]
    for row in rows:
        cells.append(["-" if value is None or value == "" else str(value) for value in row])
    if len(cells) == 1:
        print("No resources found.")
        return
    widths = [max(len(row[index]) for row in cells) for index in range(len(headers))]
    for row in cells:
        print("   ".join(value.ljust(widths[index]) for index, value in enumerate(row)).rstrip())
