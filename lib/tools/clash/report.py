"""
A self-contained HTML report of a database comparison, for people outside the tool.

One file with no scripts, readable on screen and in print:

- an overview: what was compared, a verdict, and counts for structure and data;
- structure: a breakdown by object type, then each difference with its DDL side by side
  (changed words marked), what exists on one side only, and the objects that match;
- data: tables whose rows differ, with the row counts and their difference, tables on one
  side only, what could not be compared and why, and the tables that match.

Row values are never in it: a comparison only reads counts and hashes.
"""

from __future__ import annotations

import difflib
from datetime import datetime, timezone
from html import escape
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

STATUS_LABELS = {
    "same": "Same",
    "different": "Different",
    "only_left": "Only left",
    "only_right": "Only right",
    "error": "Error",
    "not_compared": "Not compared",
}
# Lines of unchanged DDL shown around each change.
CONTEXT_LINES = 3
# Past this, a line pair is shown changed whole rather than word by word.
_WORD_DIFF_LIMIT = 2000

STYLE = """
:root { color-scheme: light; --text: #1f2933; --muted: #52606d; --line: #e4e7eb;
  --soft: #f5f7fa; --green: #1b7f4b; --green-soft: #e6f6ec; --red: #b42318;
  --red-soft: #fdecea; --amber: #a15c00; --amber-soft: #fff4e0; --blue: #1d5fbf;
  --blue-soft: #e8f0fc; }
* { box-sizing: border-box; }
body { margin: 0 auto; max-width: 1240px; padding: 32px 28px 48px; color: var(--text);
  font: 14px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; background: #fff; }
a { color: var(--blue); text-decoration: none; }
a:hover { text-decoration: underline; }
h1 { margin: 0 0 6px; font-size: 24px; }
h2 { margin: 40px 0 12px; padding-bottom: 6px; font-size: 18px;
  border-bottom: 2px solid var(--line); }
h3 { margin: 26px 0 10px; font-size: 15px; }
.meta { margin: 0 0 4px; color: var(--muted); }
.sides { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 18px 0; }
.side { padding: 12px 14px; border: 1px solid var(--line); border-radius: 10px; }
.side small { display: block; color: var(--muted); font-size: 11px; font-weight: 700;
  letter-spacing: .06em; text-transform: uppercase; }
.side strong { display: block; font-size: 16px; }
.side span { color: var(--muted); }
.verdict { margin: 18px 0; padding: 14px 16px; border-radius: 10px; font-size: 15px;
  font-weight: 600; }
.verdict.ok { color: var(--green); background: var(--green-soft); }
.verdict.diff { color: var(--red); background: var(--red-soft); }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px;
  margin: 10px 0 6px; }
.card { padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; }
.card b { display: block; font-size: 22px; font-variant-numeric: tabular-nums; }
.card span { color: var(--muted); font-size: 12px; }
.card.same b { color: var(--green); }
.card.different b, .card.error b { color: var(--red); }
.card.only_left b, .card.only_right b, .card.not_compared b { color: var(--amber); }
.toc { display: flex; flex-wrap: wrap; gap: 6px 18px; margin: 14px 0 0; padding: 10px 14px;
  background: var(--soft); border-radius: 10px; }
.scope { margin: 6px 0 0; padding: 0; list-style: none; color: var(--muted); }
.scope li { margin: 2px 0; }
.names { font: 12px/1.5 ui-monospace, Consolas, monospace; overflow-wrap: anywhere; }
table.grid { width: 100%; border-collapse: collapse; margin: 6px 0 12px; }
.grid th, .grid td { padding: 7px 10px; border-bottom: 1px solid var(--line); text-align: left;
  vertical-align: top; overflow-wrap: anywhere; }
.grid th { background: var(--soft); font-size: 12px; font-weight: 650; }
.grid td.number, .grid th.number { text-align: right; font-variant-numeric: tabular-nums; }
.grid td.zero { color: #9aa5b1; }
.badge { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px;
  font-weight: 650; white-space: nowrap; }
.badge.same { color: var(--green); background: var(--green-soft); }
.badge.different, .badge.error { color: var(--red); background: var(--red-soft); }
.badge.only_left, .badge.only_right, .badge.not_compared { color: var(--amber);
  background: var(--amber-soft); }
.type { display: inline-block; padding: 1px 7px; color: var(--blue); background: var(--blue-soft);
  border-radius: 6px; font-size: 11px; font-weight: 700; letter-spacing: .03em; }
.delta.up { color: var(--green); }
.delta.down { color: var(--red); }
.note { color: var(--muted); }
.object { margin: 12px 0; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
.object > summary, .object > header { display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
  padding: 9px 12px; background: var(--soft); cursor: pointer; list-style: none; }
.object > summary::-webkit-details-marker { display: none; }
.object .name { font: 600 13px ui-monospace, Consolas, monospace; }
.object .counts { margin-left: auto; color: var(--muted); font-size: 12px; }
.object .counts .plus { color: var(--green); }
.object .counts .minus { color: var(--red); }
table.diff { width: 100%; border-collapse: collapse; table-layout: fixed;
  font: 12px/1.5 ui-monospace, Consolas, monospace; }
.diff col.num { width: 46px; }
.diff th { padding: 4px 8px; color: var(--muted); background: #fff;
  font: 600 11px system-ui, sans-serif;
  text-align: left; border-bottom: 1px solid var(--line); }
.diff td { padding: 0 8px; vertical-align: top; white-space: pre-wrap; overflow-wrap: anywhere; }
.diff td.num { color: #9aa5b1; text-align: right; user-select: none;
  border-right: 1px solid var(--line); }
.diff td.del { background: var(--red-soft); }
.diff td.ins { background: var(--green-soft); }
.diff td.empty { background: repeating-linear-gradient(135deg, #fafbfc, #fafbfc 4px,
  #f2f4f7 4px, #f2f4f7 8px); }
.diff del { color: inherit; background: #f8c7c1; text-decoration: none; border-radius: 2px; }
.diff ins { color: inherit; background: #b7e4c7; text-decoration: none; border-radius: 2px; }
.diff tr.gap td { padding: 2px 8px; color: var(--muted); background: var(--soft);
  font: italic 11px system-ui, sans-serif; text-align: center; }
pre.ddl { margin: 0; padding: 10px 12px; overflow-x: auto;
  font: 12px/1.5 ui-monospace, Consolas, monospace;
  white-space: pre-wrap; }
.matches { margin: 8px 0; border: 1px solid var(--line); border-radius: 10px; }
.matches > summary { padding: 9px 12px; cursor: pointer; font-weight: 600; }
.matches > div { padding: 0 12px 10px; }
.footer { margin-top: 40px; color: var(--muted); font-size: 12px; }
.object .rows-body { padding: 4px 12px 12px; }
.object h4 { margin: 12px 0 4px; font-size: 13px; }
table.rows { font: 12px/1.45 ui-monospace, Consolas, monospace; }
.rows td.old { background: var(--red-soft); }
.rows td.new { background: var(--green-soft); }
.rows td.key { font-weight: 650; }
.rows td.null { color: #9aa5b1; font-style: italic; }
@media print {
  body { padding: 0; max-width: none; }
  .object, .matches { break-inside: avoid; }
  .toc { display: none; }
  details:not([open]) > :not(summary) { display: block; }
}
"""


# ----------------------------------------------------------------------
# Small parts
# ----------------------------------------------------------------------


def _badge(status: str) -> str:
    return (
        f'<span class="badge {escape(status)}">{escape(STATUS_LABELS.get(status, status))}</span>'
    )


def _number(value: Optional[int]) -> str:
    return "—" if value is None else f"{value:,}"


def _count(items: Sequence[Dict[str, Any]], status: str) -> int:
    return sum(1 for item in items if item["status"] == status)


def _cards(items: Sequence[Dict[str, Any]], noun: str) -> str:
    cards = [f'<div class="card"><b>{len(items):,}</b><span>{escape(noun)}</span></div>']
    for status, label in STATUS_LABELS.items():
        count = _count(items, status)
        if count:
            cards.append(
                f'<div class="card {status}"><b>{count:,}</b><span>{escape(label)}</span></div>'
            )
    return f'<div class="cards">{"".join(cards)}</div>'


def _anchor(*parts: str) -> str:
    return "-".join("".join(char if char.isalnum() else "_" for char in part) for part in parts)


# ----------------------------------------------------------------------
# Side-by-side DDL
# ----------------------------------------------------------------------


def _words(text: str) -> List[str]:
    """Words, spaces and punctuation as separate pieces, to mark what changed in a line."""

    pieces: List[str] = []
    current = ""
    for char in text:
        kind = char.isalnum() or char in "_$#"
        if current and (kind != (current[-1].isalnum() or current[-1] in "_$#") or not kind):
            pieces.append(current)
            current = ""
        current += char
    if current:
        pieces.append(current)
    return pieces


def _marked(old: str, new: str) -> Tuple[str, str]:
    """Both lines escaped, with the words that differ in <del> and <ins>."""

    if len(old) + len(new) > _WORD_DIFF_LIMIT:
        return escape(old), escape(new)
    left, right = _words(old), _words(new)
    matcher = difflib.SequenceMatcher(None, left, right, autojunk=False)
    one: List[str] = []
    other: List[str] = []
    for tag, a, b, c, d in matcher.get_opcodes():
        before, after = escape("".join(left[a:b])), escape("".join(right[c:d]))
        if tag == "equal":
            one.append(before)
            other.append(after)
            continue
        if before:
            one.append(f"<del>{before}</del>")
        if after:
            other.append(f"<ins>{after}</ins>")
    return "".join(one), "".join(other)


def _row(
    left_number: Optional[int],
    left_html: Optional[str],
    right_number: Optional[int],
    right_html: Optional[str],
    kind: str,
) -> str:
    def cell(number: Optional[int], html: Optional[str], changed: str) -> str:
        if html is None:
            return '<td class="num"></td><td class="empty"></td>'
        css = f' class="{changed}"' if kind != "equal" else ""
        return f'<td class="num">{number}</td><td{css}>{html or " "}</td>'

    return f"<tr>{cell(left_number, left_html, 'del')}{cell(right_number, right_html, 'ins')}</tr>"


def side_by_side(left: str, right: str, left_label: str, right_label: str) -> Tuple[str, int, int]:
    """
    Two DDL texts as a table, left and right, with unchanged stretches shortened.
    Returns the table and how many lines were added and removed.
    """

    one, other = left.splitlines(), right.splitlines()
    matcher = difflib.SequenceMatcher(None, one, other, autojunk=False)
    rows: List[str] = []
    added = removed = 0
    groups = list(matcher.get_grouped_opcodes(CONTEXT_LINES))
    previous_end = 0
    for group in groups:
        first = group[0][1]
        if first > previous_end:
            skipped = first - previous_end
            rows.append(f'<tr class="gap"><td colspan="4">{skipped:,} unchanged lines</td></tr>')
        for tag, a, b, c, d in group:
            if tag == "equal":
                for offset in range(b - a):
                    text = escape(one[a + offset])
                    rows.append(_row(a + offset + 1, text, c + offset + 1, text, "equal"))
                continue
            removed += b - a
            added += d - c
            for offset in range(max(b - a, d - c)):
                old = one[a + offset] if a + offset < b else None
                new = other[c + offset] if c + offset < d else None
                old_html: Optional[str]
                new_html: Optional[str]
                if old is not None and new is not None:
                    old_html, new_html = _marked(old, new)
                else:
                    old_html = escape(old) if old is not None else None
                    new_html = escape(new) if new is not None else None
                rows.append(
                    _row(
                        a + offset + 1 if old is not None else None,
                        old_html,
                        c + offset + 1 if new is not None else None,
                        new_html,
                        "change",
                    )
                )
        previous_end = group[-1][2]
    if groups and previous_end < len(one):
        rows.append(
            f'<tr class="gap"><td colspan="4">{len(one) - previous_end:,} unchanged lines</td></tr>'
        )
    table = (
        '<table class="diff"><colgroup><col class="num"><col><col class="num"><col></colgroup>'
        f"<thead><tr><th></th><th>{escape(left_label)}</th><th></th><th>{escape(right_label)}</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )
    return table, added, removed


# ----------------------------------------------------------------------
# Structure
# ----------------------------------------------------------------------


def _type_breakdown(items: Sequence[Dict[str, Any]]) -> str:
    types: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        types.setdefault(item["type"], []).append(item)
    statuses = [status for status in STATUS_LABELS if _count(items, status)]
    head = "".join(
        f'<th class="number">{escape(STATUS_LABELS[status])}</th>' for status in statuses
    )
    rows = []
    for name in sorted(types):
        group = types[name]
        cells = []
        for status in statuses:
            count = _count(group, status)
            cells.append(f'<td class="number{"" if count else " zero"}">{count:,}</td>')
        rows.append(
            f'<tr><td><span class="type">{escape(name)}</span></td>{"".join(cells)}'
            f'<td class="number">{len(group):,}</td></tr>'
        )
    return (
        f'<table class="grid"><thead><tr><th>Object type</th>{head}<th class="number">Total</th>'
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def _ddl_object(item: Dict[str, Any], left: str, right: str) -> str:
    status = item["status"]
    header = (
        f'<span class="type">{escape(item["type"])}</span>'
        f'<span class="name">{escape(item["name"])}</span>{_badge(status)}'
    )
    anchor = _anchor("ddl", item["type"], item["name"])
    if status == "different":
        table, added, removed = side_by_side(
            item.get("left", ""), item.get("right", ""), left, right
        )
        counts = (
            f'<span class="counts"><span class="minus">−{removed}</span> '
            f'<span class="plus">+{added}</span> lines</span>'
        )
        return (
            f'<details class="object" id="{anchor}" open><summary>{header}{counts}</summary>'
            f"{table}</details>"
        )
    if status in ("only_left", "only_right"):
        here, there = (left, right) if status == "only_left" else (right, left)
        source = item.get("left" if status == "only_left" else "right", "")
        note = f'<span class="counts">In {escape(here)}, missing in {escape(there)}</span>'
        body = f'<pre class="ddl">{escape(source)}</pre>' if source else ""
        return (
            f'<details class="object" id="{anchor}" open><summary>{header}{note}</summary>'
            f"{body}</details>"
        )
    error = f'<span class="counts">{escape(str(item.get("error") or ""))}</span>'
    return f'<div class="object" id="{anchor}"><header>{header}{error}</header></div>'


def _name_list(items: Sequence[Dict[str, Any]], key: str, label: str) -> str:
    if not items:
        return ""
    groups: Dict[str, List[str]] = {}
    for item in items:
        groups.setdefault(item.get("type", ""), []).append(str(item[key]))
    lines = "".join(
        f'<p>{f"<span class=type>{escape(kind)}</span> " if kind else ""}'
        f'<span class="names">{escape(", ".join(sorted(names)))}</span></p>'
        for kind, names in sorted(groups.items())
    )
    return (
        f'<details class="matches"><summary>{escape(label)} ({len(items):,})</summary>'
        f"<div>{lines}</div></details>"
    )


def _ddl_section(items: Sequence[Dict[str, Any]], left: str, right: str) -> str:
    parts = ['<h2 id="structure">Structure (DDL)</h2>']
    if not items:
        parts.append('<p class="note">No objects matched.</p>')
        return "".join(parts)
    parts.append(_cards(items, "objects"))
    parts.append(_type_breakdown(items))

    shown = [
        ("different", "Different", "The definition differs; changed words are marked."),
        ("only_left", f"Only in {left}", f"These objects are missing in {right}."),
        ("only_right", f"Only in {right}", f"These objects are missing in {left}."),
        ("error", "Not read", "These objects could not be read on one side."),
    ]
    for status, title, note in shown:
        group = [item for item in items if item["status"] == status]
        if not group:
            continue
        parts.append(
            f'<h3 id="ddl-{status}">{escape(title)} ({len(group):,})</h3>'
            f'<p class="note">{escape(note)}</p>'
        )
        parts.extend(_ddl_object(item, left, right) for item in group)

    parts.append(
        _name_list(
            [item for item in items if item["status"] == "same"], "name", "Objects that match"
        )
    )
    return "".join(parts)


# ----------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------


def _delta(item: Dict[str, Any]) -> str:
    one, other = item.get("left_rows"), item.get("right_rows")
    if one is None or other is None:
        return '<td class="number">—</td>'
    change = other - one
    if change == 0:
        return '<td class="number zero">0</td>'
    css = "up" if change > 0 else "down"
    sign = "+" if change > 0 else "−"
    return f'<td class="number"><span class="delta {css}">{sign}{abs(change):,}</span></td>'


def _data_notes(item: Dict[str, Any]) -> str:
    notes: List[str] = []
    for key, label in (
        ("columns_only_left", "Columns only left"),
        ("columns_only_right", "Columns only right"),
        ("columns_not_compared", "Columns not compared"),
    ):
        if item.get(key):
            notes.append(f'<div class="note">{escape(f"{label}: " + ", ".join(item[key]))}</div>')
    if item.get("error"):
        notes.insert(0, f'<div class="note">{escape(str(item["error"]))}</div>')
    return "".join(notes)


def _data_table(items: Sequence[Dict[str, Any]], left: str, right: str) -> str:
    rows = "".join(
        f'<tr><td><span class="name">{escape(item["table"])}</span></td>'
        f'<td class="number">{_number(item.get("left_rows"))}</td>'
        f'<td class="number">{_number(item.get("right_rows"))}</td>'
        f"{_delta(item)}<td>{_badge(item['status'])}{_data_notes(item)}</td></tr>"
        for item in items
    )
    return (
        f'<table class="grid"><thead><tr><th>Table</th><th class="number">{escape(left)} rows</th>'
        f'<th class="number">{escape(right)} rows</th><th class="number">Difference</th>'
        f"<th>Result</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def _data_section(items: Sequence[Dict[str, Any]], left: str, right: str) -> str:
    parts = ['<h2 id="data">Data</h2>']
    if not items:
        parts.append('<p class="note">No tables matched.</p>')
        return "".join(parts)
    parts.append(_cards(items, "tables"))
    left_total = sum(item.get("left_rows") or 0 for item in items)
    right_total = sum(item.get("right_rows") or 0 for item in items)
    parts.append(
        f'<p class="note">Rows counted: {left_total:,} in {escape(left)}, '
        f"{right_total:,} in {escape(right)}. Tables are compared by row count and a hash of "
        "their rows; for the tables whose rows differ, the rows themselves are compared and "
        "the differing ones are listed below, with their values.</p>"
    )
    shown = [
        (
            "different",
            "Rows differ",
            "Same columns, different rows: which rows, and which values, follow the table.",
        ),
        ("only_left", f"Only in {left}", f"These tables are missing in {right}."),
        ("only_right", f"Only in {right}", f"These tables are missing in {left}."),
        ("not_compared", "Not compared", "Skipped, or no column could be compared."),
        ("error", "Not read", "These tables could not be read."),
    ]
    for status, title, note in shown:
        group = [item for item in items if item["status"] == status]
        if not group:
            continue
        if status == "different":
            # The largest differences first.
            group.sort(
                key=lambda item: -abs((item.get("right_rows") or 0) - (item.get("left_rows") or 0))
            )
        parts.append(
            f'<h3 id="data-{status}">{escape(title)} ({len(group):,})</h3>'
            f'<p class="note">{escape(note)}</p>{_data_table(group, left, right)}'
        )
        if status == "different":
            parts.extend(_row_details(item, left, right) for item in group)
    same = [item for item in items if item["status"] == "same"]
    if same:
        parts.append(
            f'<details class="matches"><summary>Tables that match ({len(same):,})</summary><div>'
            f"{_data_table(same, left, right)}</div></details>"
        )
    return "".join(parts)


def _cell(value: str, css: str = "") -> str:
    if value == "":
        return f'<td class="null {css}">null</td>'
    return f'<td class="{css}">{escape(value)}</td>' if css else f"<td>{escape(value)}</td>"


def _rows_grid(columns: Sequence[str], rows: Sequence[Sequence[str]], key: Sequence[str]) -> str:
    head = "".join(f"<th>{escape(name)}</th>" for name in columns)
    body = "".join(
        "<tr>"
        + "".join(_cell(value, "key" if name in key else "") for name, value in zip(columns, row))
        + "</tr>"
        for row in rows
    )
    return f'<table class="grid rows"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def _changed_grid(
    changed: Sequence[Dict[str, Any]],
    key: Sequence[str],
    columns: Sequence[str],
    left: str,
    right: str,
) -> str:
    """One line per changed value: the row's key, the column, and both values."""

    head = "".join(f"<th>{escape(name)}</th>" for name in key)
    lines: List[str] = []
    for change in changed:
        values = dict(zip(columns, zip(change["left"], change["right"])))
        for index, column in enumerate(change["columns"]):
            keys = (
                "".join(_cell(value, "key") for value in change["key"])
                if index == 0
                else f'<td colspan="{len(key)}"></td>'
            )
            one, other = values.get(column, ("", ""))
            lines.append(
                f"<tr>{keys}<td>{escape(column)}</td>{_cell(one, 'old')}{_cell(other, 'new')}</tr>"
            )
    return (
        f'<table class="grid rows"><thead><tr>{head}<th>Column</th><th>{escape(left)}</th>'
        f"<th>{escape(right)}</th></tr></thead><tbody>{''.join(lines)}</tbody></table>"
    )


def _listed(shown: int, total: int, what: str) -> str:
    if shown >= total:
        return ""
    return f'<p class="note">The first {shown:,} of {total:,} {escape(what)} are listed.</p>'


def _row_details(item: Dict[str, Any], left: str, right: str) -> str:
    """Which rows of a table differ, with their values."""

    name = escape(item["table"])
    rows = item.get("rows")
    if not rows:
        reason = item.get("rows_error") or "The rows were not read."
        return (
            f'<div class="object" id="{_anchor("rows", item["table"])}"><header>'
            f'<span class="name">{name}</span><span class="note">{escape(reason)}</span>'
            "</header></div>"
        )
    columns, key = rows["columns"], rows["key"]
    counts = (
        f'{rows["changed_count"]:,} changed · {rows["only_left_count"]:,} only in {escape(left)}'
        f' · {rows["only_right_count"]:,} only in {escape(right)} · {rows["same"]:,} the same'
    )
    matched = escape(", ".join(key)) if key else "whole rows (no primary key)"
    body: List[str] = [f'<p class="note">Matched by {matched}.</p>']
    if rows.get("truncated"):
        body.append(
            f'<p class="note">A side has more than {rows["limit"]:,} rows: only the first '
            f'{rows["limit"]:,} (in key order) were compared.</p>'
        )
    if rows["changed"]:
        body.append(f"<h4>Changed rows ({rows['changed_count']:,})</h4>")
        body.append(_changed_grid(rows["changed"], key, columns, left, right))
        body.append(_listed(len(rows["changed"]), rows["changed_count"], "changed rows"))
    for side, label in (("only_left", left), ("only_right", right)):
        if rows[side]:
            total = rows[f"{side}_count"]
            body.append(f"<h4>Only in {escape(label)} ({total:,})</h4>")
            body.append(_rows_grid(columns, rows[side], key))
            body.append(_listed(len(rows[side]), total, "rows"))
    if not (rows["changed"] or rows["only_left"] or rows["only_right"]):
        body.append(
            '<p class="note">No differing row among those read: the difference is past the rows'
            " compared.</p>"
        )
    return (
        f'<details class="object" id="{_anchor("rows", item["table"])}" open><summary>'
        f'<span class="name">{name}</span><span class="counts">{counts}</span></summary>'
        f'<div class="rows-body">{"".join(body)}</div></details>'
    )


# ----------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------


def _side(label: str, title: str, side: Optional[Dict[str, Any]]) -> str:
    detail = ""
    if side:
        detail = (
            f"<span>{escape(str(side.get('host', '')))}:{escape(str(side.get('port', '')))}"
            f" / {escape(str(side.get('sid', '')))} · schema "
            f"{escape(str(side.get('schema_name', '')))}</span>"
        )
    return (
        f'<div class="side"><small>{escape(title)}</small><strong>{escape(label)}</strong>'
        f"{detail}</div>"
    )


def _verdict(result: Dict[str, Any]) -> str:
    differences = 0
    for key in ("ddl", "data"):
        differences += sum(1 for item in result.get(key) or [] if item["status"] != "same")
    if differences == 0:
        return '<p class="verdict ok">Everything compared matches.</p>'
    noun = "difference" if differences == 1 else "differences"
    return f'<p class="verdict diff">{differences:,} {noun} found.</p>'


def _toc(result: Dict[str, Any]) -> str:
    links: List[str] = []
    for key, prefix, label in (("ddl", "ddl", "Structure"), ("data", "data", "Data")):
        items = result.get(key)
        if items is None:
            continue
        links.append(f'<a href="#{"structure" if key == "ddl" else "data"}"><b>{label}</b></a>')
        for status in ("different", "only_left", "only_right", "not_compared", "error"):
            count = _count(items, status)
            if count:
                links.append(
                    f'<a href="#{prefix}-{status}">{escape(STATUS_LABELS[status])} ({count:,})</a>'
                )
    return f'<nav class="toc">{"".join(links)}</nav>' if links else ""


def render_report(
    result: Dict[str, Any],
    *,
    name_filter: Optional[str] = None,
    object_types: Optional[Sequence[str]] = None,
    tables: Iterable[str] = (),
    tables_vault: Optional[Dict[str, Any]] = None,
    sides: Optional[Dict[str, Dict[str, Any]]] = None,
    generated_at: Optional[datetime] = None,
) -> str:
    """The comparison as one HTML document."""

    left, right = str(result["left"]), str(result["right"])
    when = (generated_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M UTC")
    title = f"Database compare: {left} and {right}"
    named = list(tables)

    scope: List[str] = []
    if named:
        source = (
            f" (with the list in Vault {tables_vault.get('namespace')}/{tables_vault.get('key')})"
            if tables_vault
            else ""
        )
        scope.append(
            f'Tables{escape(source)}: <span class="names">{escape(", ".join(named))}</span>'
            " and, for structure, their indexes and triggers"
        )
    if name_filter:
        scope.append(f"Names like {escape(name_filter)}")
    if named and name_filter:
        scope.append("An object named in the list or like the pattern is compared.")
    if object_types:
        scope.append(f"Object types: {escape(', '.join(object_types))}")
    if not named and not name_filter:
        scope.append("The whole schema")

    sections = []
    if result.get("ddl") is not None:
        sections.append(_ddl_section(result["ddl"], left, right))
    if result.get("data") is not None:
        sections.append(_data_section(result["data"], left, right))

    overview: List[str] = [_verdict(result)]
    if result.get("ddl"):
        overview.append(f"<h3>Structure</h3>{_cards(result['ddl'], 'objects')}")
    if result.get("data"):
        overview.append(f"<h3>Data</h3>{_cards(result['data'], 'tables')}")

    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)}</title><style>{STYLE}</style></head><body>"
        f"<h1>{escape(title)}</h1>"
        f'<p class="meta">Generated {escape(when)}</p>'
        f'<div class="sides">{_side(left, "Left", (sides or {}).get("left"))}'
        f'{_side(right, "Right", (sides or {}).get("right"))}</div>'
        f'<ul class="scope">{"".join(f"<li>{line}</li>" for line in scope)}</ul>'
        + "".join(overview)
        + _toc(result)
        + "".join(sections)
        + '<p class="footer">Made by Entropy. DDL is compared after leaving out schema names, '
        "tablespaces and system-generated names; data by row count and hash, then row by row "
        "for the tables whose rows differ. This report holds row values: share it as you would "
        "the data.</p>" + "</body></html>"
    )
