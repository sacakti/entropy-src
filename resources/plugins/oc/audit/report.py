"""
The audit report: one self-contained HTML file (no scripts, no external files).
"""

from __future__ import annotations

import difflib
import json
from collections import Counter
from html import escape
from typing import Any, Dict, List

LONG_VALUE = 120

STYLE = """
:root{--ink:#1f2328;--muted:#656d76;--line:#d0d7de;--soft:#f6f8fa;--add:#1a7f37;--del:#cf222e;
--mod:#9a6700}
*{box-sizing:border-box}
body{margin:0;font:14px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;color:var(--ink);
background:#fff}
main{max-width:1180px;margin:0 auto;padding:28px 24px 60px}
h1{margin:0 0 4px;font-size:24px}
.meta{color:var(--muted);margin:0 0 20px}
.meta code{color:var(--ink)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;
margin:0 0 20px}
.tile{border:1px solid var(--line);border-radius:10px;padding:12px 14px;background:var(--soft)}
.tile b{display:block;font-size:24px}
.tile span{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.tile.added b{color:var(--add)}
.tile.removed b{color:var(--del)}
.tile.modified b{color:var(--mod)}
.kinds{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 20px}
.chip{border:1px solid var(--line);border-radius:999px;padding:2px 10px;font-size:12px;
background:#fff}
nav.toc{border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:0 0 24px}
nav.toc ol{margin:6px 0 0;padding-left:20px;columns:2}
nav.toc a{color:inherit}
section.resource{border:1px solid var(--line);border-radius:12px;margin:0 0 18px;overflow:hidden;
break-inside:avoid}
section.resource>header{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:10px 14px;
background:var(--soft);border-bottom:1px solid var(--line)}
section.resource>header h2{margin:0;font-size:16px}
section.resource>header code{color:var(--muted);font-size:12px}
.status{border-radius:999px;padding:1px 9px;font-size:12px;font-weight:600;color:#fff}
.status.added{background:var(--add)}
.status.removed{background:var(--del)}
.status.modified{background:var(--mod)}
.body{padding:10px 14px 14px}
h3{margin:12px 0 6px;font-size:13px;text-transform:uppercase;letter-spacing:.04em;
color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;vertical-align:top;padding:6px 8px;border-bottom:1px solid var(--line)}
th{background:var(--soft);font-weight:600}
td.path{font-family:ui-monospace,Menlo,monospace;word-break:break-all;width:32%}
td.change{white-space:nowrap;font-weight:600}
td.change.added{color:var(--add)}
td.change.removed{color:var(--del)}
td.change.changed{color:var(--mod)}
pre{margin:0;white-space:pre-wrap;word-break:break-word;font:12px/1.45 ui-monospace,Menlo,monospace}
pre.diff span{display:block}
pre.diff .add{background:#dafbe1}
pre.diff .del{background:#ffebe9}
pre.diff .hunk{color:var(--muted)}
.before{color:var(--del)}
.after{color:var(--add)}
.muted{color:var(--muted)}
ul.facts{margin:0;padding-left:18px}
.empty{border:1px dashed var(--line);border-radius:12px;padding:30px;text-align:center;
color:var(--muted)}
@media print{main{padding:0}
section.resource{break-inside:avoid}
"""


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2, ensure_ascii=False, default=str)
    return str(value)


def _value(value: Any) -> str:
    if value is None:
        return '<span class="muted">—</span>'
    return f"<pre>{escape(_text(value))}</pre>"


def _line_diff(before: Any, after: Any) -> str:
    lines = difflib.unified_diff(
        _text(before).splitlines(), _text(after).splitlines(), "before", "after", lineterm="", n=2
    )
    rows = []
    for line in list(lines)[2:]:
        kind = (
            "add"
            if line.startswith("+")
            else "del" if line.startswith("-") else "hunk" if line.startswith("@@") else ""
        )
        rows.append(f'<span class="{kind}">{escape(line) or "&nbsp;"}</span>')
    return f'<pre class="diff">{"".join(rows)}</pre>'


def _is_long(value: Any) -> bool:
    text = _text(value)
    return "\n" in text or len(text) > LONG_VALUE


def _before_after(item: Dict[str, Any]) -> str:
    """Two cells, or one wide line diff for long changed values."""

    if item["change"] == "changed" and (_is_long(item["before"]) or _is_long(item["after"])):
        return f'<td colspan="2">{_line_diff(item["before"], item["after"])}</td>'
    return (
        f'<td class="before">{_value(item["before"])}</td>'
        f'<td class="after">{_value(item["after"])}</td>'
    )


def _data_table(entry: Dict[str, Any]) -> str:
    rows = []
    for item in entry["data"]:
        if item["hidden"]:
            cells = '<td colspan="2" class="muted">Value hidden (Secret)</td>'
        else:
            cells = _before_after(item)
        rows.append(
            f'<tr><td class="path">{escape(item["key"])}</td>'
            f'<td class="change {item["change"]}">{item["change"]}</td>{cells}</tr>'
        )
    label = "Secret keys" if entry["kind"] == "Secret" else "Data keys"
    return (
        f"<h3>{label} ({len(entry['data'])})</h3><table><thead><tr><th>Key</th><th>Change</th>"
        f"<th>Before</th><th>After</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def _field_table(entry: Dict[str, Any]) -> str:
    rows = "".join(
        f'<tr><td class="path">{escape(item["path"])}</td>'
        f'<td class="change {item["change"]}">{item["change"]}</td>{_before_after(item)}</tr>'
        for item in entry["fields"]
    )
    return (
        f"<h3>Fields ({len(entry['fields'])})</h3><table><thead><tr><th>Field</th><th>Change</th>"
        f"<th>Before</th><th>After</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def _resource(index: int, entry: Dict[str, Any]) -> str:
    parts = [
        f'<section class="resource" id="r{index}"><header><span class="status {entry["status"]}">'
        f'{entry["status"]}</span><h2>{escape(entry["kind"])} / {escape(entry["name"])}</h2>'
        f'<code>{escape(entry["file"])}</code></header><div class="body">'
    ]
    if entry["status"] != "modified" and entry["summary"]:
        facts = "".join(f"<li>{escape(fact)}</li>" for fact in entry["summary"])
        parts.append(f'<ul class="facts">{facts}</ul>')
    if entry["data"] and entry["status"] == "modified":
        parts.append(_data_table(entry))
    if entry["fields"]:
        parts.append(_field_table(entry))
    parts.append("</div></section>")
    return "".join(parts)


def build_report(meta: Dict[str, Any], entries: List[Dict[str, Any]]) -> str:
    """The report page; `meta` holds title, repository, generated, base, commit and notes."""

    statuses = Counter(entry["status"] for entry in entries)
    kinds = Counter(entry["kind"] for entry in entries)
    field_count = sum(len(entry["fields"]) + len(entry["data"]) for entry in entries)
    tiles = [
        ("Resources changed", len(entries), ""),
        ("Modified", statuses["modified"], "modified"),
        ("Added", statuses["added"], "added"),
        ("Removed", statuses["removed"], "removed"),
        ("Field and key changes", field_count, ""),
    ]
    tile_html = "".join(
        f'<div class="tile {cls}"><b>{count}</b><span>{label}</span></div>'
        for label, count, cls in tiles
    )
    kind_html = "".join(
        f'<span class="chip">{escape(kind)}: {count}</span>'
        for kind, count in sorted(kinds.items())
    )
    toc = "".join(
        f'<li><a href="#r{index}">{escape(entry["kind"])} / {escape(entry["name"])}</a> '
        f'<span class="muted">({entry["status"]})</span></li>'
        for index, entry in enumerate(entries)
    )
    meta_lines = [
        f"Repository <code>{escape(meta['repository'])}</code>",
        f"generated {escape(meta['generated'])}",
        f"compared with <code>{escape(meta['base'])}</code>",
    ]
    if meta.get("commit"):
        meta_lines.append(f"committed as <code>{escape(meta['commit'])}</code>")
    notes = "".join(f'<p class="meta">{escape(note)}</p>' for note in meta.get("notes", []))
    body = (
        (
            f'<nav class="toc"><strong>Contents</strong><ol>{toc}</ol></nav>'
            if len(entries) > 1
            else ""
        )
        + "".join(_resource(index, entry) for index, entry in enumerate(entries))
        if entries
        else '<div class="empty"><strong>No changes.</strong><br>'
        "The OpenShift resources match the previous audit.</div>"
    )
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(meta['title'])} — {escape(meta['generated'])}</title>"
        f"<style>{STYLE}</style></head><body><main><h1>{escape(meta['title'])}</h1>"
        f"<p class=\"meta\">{' · '.join(meta_lines)}</p>{notes}"
        f'<div class="tiles">{tile_html}</div>'
        + (f'<div class="kinds">{kind_html}</div>' if kinds else "")
        + f"{body}</main></body></html>"
    )
