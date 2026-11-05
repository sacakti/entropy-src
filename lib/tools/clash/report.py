"""
A self-contained HTML report of a database comparison, for people outside the tool.

One file with no scripts: a summary, then each object's and table's result, with the DDL
differences readable in place. Row values are never in it: a comparison only reads counts
and hashes.
"""

from __future__ import annotations

import difflib
from datetime import datetime, timezone
from html import escape
from typing import Any, Dict, Iterable, List, Optional, Sequence

STATUS_LABELS = {
    "same": "Same",
    "different": "Different",
    "only_left": "Only left",
    "only_right": "Only right",
    "error": "Error",
    "not_compared": "Not compared",
}

STYLE = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0 auto; max-width: 1100px; padding: 32px 24px; color: #1f2933;
  font: 14px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; background: #fff; }
h1 { margin: 0 0 4px; font-size: 22px; }
h2 { margin: 32px 0 10px; font-size: 16px; }
.meta { margin: 0 0 4px; color: #52606d; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; padding: 0; list-style: none; }
.chips li { padding: 4px 10px; border: 1px solid #cbd2d9; border-radius: 6px; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 6px 10px; border-bottom: 1px solid #e4e7eb; text-align: left;
  vertical-align: top; overflow-wrap: anywhere; }
th { background: #f5f7fa; font-weight: 600; }
td.number { text-align: right; font-variant-numeric: tabular-nums; }
.status { font-weight: 600; }
.status.same { color: #1b7f4b; }
.status.different, .status.error { color: #b42318; }
.status.only_left, .status.only_right, .status.not_compared { color: #a15c00; }
.note { color: #52606d; }
details { margin: 8px 0; border: 1px solid #e4e7eb; border-radius: 6px; }
summary { padding: 8px 10px; cursor: pointer; font-weight: 600; }
pre { margin: 0; padding: 10px; overflow-x: auto; border-top: 1px solid #e4e7eb;
  font: 12px/1.45 ui-monospace, Consolas, monospace; }
pre span { display: block; white-space: pre; }
.added { background: #e6f6ec; }
.removed { background: #fdecea; }
.hunk { color: #52606d; }
@media print { details { break-inside: avoid; } }
"""


def _counts(items: Sequence[Dict[str, Any]], noun: str) -> str:
    chips = [f"<li><strong>{len(items):,}</strong> {escape(noun)}</li>"]
    for status, label in STATUS_LABELS.items():
        count = sum(1 for item in items if item["status"] == status)
        if count:
            chips.append(f"<li><strong>{count:,}</strong> {escape(label.lower())}</li>")
    return f'<ul class="chips">{"".join(chips)}</ul>'


def _status(item: Dict[str, Any]) -> str:
    status = item["status"]
    label = escape(STATUS_LABELS.get(status, status))
    text = f'<span class="status {escape(status)}">{label}</span>'
    if item.get("error"):
        text += f" {escape(str(item['error']))}"
    return text


def _diff_lines(left: str, right: str, left_label: str, right_label: str) -> Iterable[str]:
    lines = difflib.unified_diff(
        left.splitlines(),
        right.splitlines(),
        fromfile=left_label,
        tofile=right_label,
        lineterm="",
    )
    for line in lines:
        if line.startswith(("+++", "---", "@@")):
            kind = "hunk"
        elif line.startswith("+"):
            kind = "added"
        elif line.startswith("-"):
            kind = "removed"
        else:
            kind = ""
        yield f'<span class="{kind}">{escape(line)}</span>'


def _ddl_detail(item: Dict[str, Any], left_label: str, right_label: str) -> str:
    status = item["status"]
    if status == "different":
        body = "".join(
            _diff_lines(item.get("left", ""), item.get("right", ""), left_label, right_label)
        )
    elif status in ("only_left", "only_right"):
        source = item.get("left" if status == "only_left" else "right", "")
        body = "".join(f"<span>{escape(line)}</span>" for line in source.splitlines())
    else:
        return ""

    if not body:
        return ""

    title = f"{item['type']} {item['name']} ({STATUS_LABELS[status].lower()})"
    return f"<details><summary>{escape(title)}</summary><pre>{body}</pre></details>"


def _ddl_section(items: Sequence[Dict[str, Any]], left: str, right: str) -> str:
    rows = "".join(
        f"<tr><td>{escape(item['type'])}</td><td>{escape(item['name'])}</td>"
        f"<td>{_status(item)}</td></tr>"
        for item in items
    )
    details = "".join(_ddl_detail(item, left, right) for item in items)
    parts = [
        "<h2>Structure (DDL)</h2>",
        _counts(items, "objects"),
        (
            f"<table><thead><tr><th>Type</th><th>Name</th><th>Result</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
            if items
            else '<p class="note">No objects matched.</p>'
        ),
    ]
    if details:
        parts.append(f"<h2>Structure differences</h2>{details}")
    return "".join(parts)


def _number(value: Optional[int]) -> str:
    return "—" if value is None else f"{value:,}"


def _data_notes(item: Dict[str, Any]) -> str:
    notes: List[str] = []
    for key, label in (
        ("columns_only_left", "Columns only left"),
        ("columns_only_right", "Columns only right"),
        ("columns_not_compared", "Columns not compared"),
    ):
        if item.get(key):
            notes.append(f"{label}: {', '.join(item[key])}")
    return "".join(f'<div class="note">{escape(note)}</div>' for note in notes)


def _data_section(items: Sequence[Dict[str, Any]], left: str, right: str) -> str:
    rows = "".join(
        f"<tr><td>{escape(item['table'])}</td>"
        f'<td class="number">{_number(item.get("left_rows"))}</td>'
        f'<td class="number">{_number(item.get("right_rows"))}</td>'
        f"<td>{_status(item)}{_data_notes(item)}</td></tr>"
        for item in items
    )
    return "".join(
        [
            "<h2>Data</h2>",
            _counts(items, "tables"),
            '<p class="note">Compared by row count and a hash of each table\'s rows; '
            "no row values are in this report.</p>",
            (
                f"<table><thead><tr><th>Table</th><th>{escape(left)} rows</th>"
                f"<th>{escape(right)} rows</th><th>Result</th></tr></thead>"
                f"<tbody>{rows}</tbody></table>"
                if items
                else '<p class="note">No tables matched.</p>'
            ),
        ]
    )


def render_report(
    result: Dict[str, Any],
    *,
    name_filter: Optional[str] = None,
    object_types: Optional[Sequence[str]] = None,
    generated_at: Optional[datetime] = None,
) -> str:
    """The comparison as one HTML document."""

    left, right = str(result["left"]), str(result["right"])
    when = (generated_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M UTC")
    title = f"Database compare: {left} and {right}"

    filters = [f"Generated {when}"]
    if name_filter:
        filters.append(f"Names like {name_filter}")
    if object_types:
        filters.append(f"Object types: {', '.join(object_types)}")

    sections = []
    if result.get("ddl") is not None:
        sections.append(_ddl_section(result["ddl"], left, right))
    if result.get("data") is not None:
        sections.append(_data_section(result["data"], left, right))

    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        f"<title>{escape(title)}</title><style>{STYLE}</style></head><body>"
        f"<h1>{escape(title)}</h1>"
        + "".join(f'<p class="meta">{escape(line)}</p>' for line in filters)
        + "".join(sections)
        + "</body></html>"
    )
