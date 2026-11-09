"""
A knowledge base entry as a file to share: HTML, PDF or Word (.docx).

All three show the same thing: what was done (the title), its version, where, when, who
took part, tags and reference, then how it was done with its images in place. HTML and PDF
use the task report's renderers (lib/tasks/report.py and report_pdf.py), so a description
reads the same everywhere; Word is written by lib/knowledge/docx.py. Nothing is fetched:
images come from the entry's own attachments.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from lib.pdf.document import CONTENT_W, MARGIN, add_page_numbers, write_pdf
from lib.tasks.report import _description
from lib.tasks.report_pdf import _COLORS, _Report

FORMATS = ("html", "pdf", "docx")


def when_text(entry: Dict[str, Any]) -> str:
    try:
        day = date.fromisoformat(entry["happened_on"]).strftime("%a %d %b %Y")
    except (KeyError, ValueError):
        day = str(entry.get("happened_on") or "")
    return f"{day}, {entry['happened_time']}" if entry.get("happened_time") else day


def fields(entry: Dict[str, Any], members: Dict[str, str]) -> List[Tuple[str, str]]:
    """The entry's facts in reading order, people by their full names."""

    people = ", ".join(members.get(name.lower(), name) for name in entry.get("people") or [])
    rows = [
        ("Version", f"{entry.get('version') or 1}"),
        ("Where", entry.get("location") or "—"),
        ("When", when_text(entry)),
        ("Who", people or "—"),
    ]
    if entry.get("tags"):
        rows.append(("Tags", ", ".join(entry["tags"])))
    if entry.get("reference"):
        rows.append(("Reference", entry["reference"]))
    author = members.get(str(entry.get("updated_by") or "").lower(), entry.get("updated_by") or "")
    rows.append(("Last saved", f"{entry.get('updated_at') or ''} UTC by {author}".strip()))
    return rows


def file_name(entry: Dict[str, Any], extension: str) -> str:
    stem = "".join(char if char.isalnum() or char in "-_" else "-" for char in entry["title"])
    stem = "-".join(part for part in stem.split("-") if part)[:80] or "entry"
    return f"{stem}-v{entry.get('version') or 1}.{extension}"


# ----------------------------------------------------------------------
# HTML
# ----------------------------------------------------------------------

_STYLE = """
:root{--ink:#1d2433;--muted:#667085;--line:#e4e7ec;--soft:#f6f7f9;color-scheme:light}
*{box-sizing:border-box}
body{margin:0;background:#f3f4f6;color:var(--ink);
font:14px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:900px;margin:0 auto;padding:32px 28px;background:#fff;min-height:100vh}
h1{margin:0 0 4px;font-size:26px;line-height:1.25}
.eyebrow{margin:0 0 18px;color:var(--muted);font-size:12px;letter-spacing:.06em;
text-transform:uppercase}
dl.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px 20px;
margin:0 0 24px;padding:14px 16px;background:var(--soft);border:1px solid var(--line);
border-radius:10px}
dl.facts dt{color:var(--muted);font-size:11px;font-weight:700;letter-spacing:.05em;
text-transform:uppercase}
dl.facts dd{margin:2px 0 0;overflow-wrap:anywhere}
p{margin:0 0 10px}code{font:12px ui-monospace,Menlo,monospace;background:var(--soft);
border:1px solid var(--line);border-radius:4px;padding:1px 5px}
.md-h1{font-size:20px;font-weight:700;margin:20px 0 8px}
.md-h2{font-size:17px;font-weight:700;margin:16px 0 6px}
.md-h3{font-size:15px;font-weight:700;color:var(--muted);margin:14px 0 4px}
.md-h4{font-size:14px;font-weight:700;margin:12px 0 4px}
.md-h5{font-size:12px;font-weight:700;color:var(--muted);margin:10px 0 4px;text-transform:uppercase}
.md-list{margin:0 0 10px;padding-left:24px}
.md-list li.check{display:flex;gap:8px;list-style:none;margin-left:-24px}
.md-list li.check input{margin-top:6px}
.md-list li.is-done span{color:var(--muted);text-decoration:line-through}
.md-table{width:100%;margin:0 0 12px;border-collapse:collapse;font-size:13px}
.md-table th{background:var(--soft)}
.md-table th,.md-table td{padding:6px 10px;border:1px solid var(--line);text-align:left;
vertical-align:top}
.md-code{margin:0 0 10px;padding:10px 12px;background:var(--soft);border:1px solid var(--line);
border-radius:8px;font:12px/1.5 ui-monospace,Menlo,monospace;white-space:pre-wrap;
word-break:break-word}
.att{margin:10px 0 14px;padding:8px;background:var(--soft);border:1px solid var(--line);
border-radius:8px}
.att img{display:block;max-width:100%;max-height:600px;margin-top:6px;border-radius:6px;
background:#fff}
.att pre{white-space:pre-wrap;font-size:12px;margin:6px 0 0}
.att-name{font-size:12px;font-weight:600}.muted{color:var(--muted)}
.print-only{display:none}
footer{margin-top:32px;padding-top:12px;border-top:1px solid var(--line);color:var(--muted);
font-size:12px}
@media print{body{background:#fff}main{padding:0;max-width:none}.att{break-inside:avoid}}
"""


def export_html(
    entry: Dict[str, Any],
    attachments: Sequence[Dict[str, Any]],
    root: Path,
    members: Dict[str, str],
    project: str,
) -> str:
    body, _ = _description(entry.get("body") or "", list(attachments), root)
    facts = "".join(
        f"<div><dt>{escape(label)}</dt><dd>{escape(value)}</dd></div>"
        for label, value in fields(entry, members)
    )
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(entry['title'])}</title><style>{_STYLE}</style></head><body><main>"
        f'<p class="eyebrow">Knowledge base · {escape(project)}</p>'
        f"<h1>{escape(entry['title'])}</h1>"
        f'<dl class="facts">{facts}</dl>'
        f"<article>{body}</article>"
        f"<footer>Exported from Entropy on {escape(generated)}.</footer>"
        "</main></body></html>"
    )


# ----------------------------------------------------------------------
# PDF
# ----------------------------------------------------------------------


def export_pdf(
    entry: Dict[str, Any],
    attachments: Sequence[Dict[str, Any]],
    root: Path,
    members: Dict[str, str],
    project: str,
) -> bytes:
    report = _Report(members=members, group_names={}, attachment_root=root, images={})
    canvas = report.canvas
    report.lines(
        f"KNOWLEDGE BASE · {project.upper()}", font="bold", size=7.5, color=_COLORS["muted"]
    )
    canvas.y += 4
    report.lines(entry["title"], font="bold", size=17)
    canvas.y += 6
    for label, value in fields(entry, members):
        canvas.need(14)
        canvas.text(MARGIN, canvas.y, label.upper(), "bold", 7, _COLORS["muted"])
        report.lines(value, size=9, x=MARGIN + 80, width=CONTENT_W - 80)
    canvas.y += 8
    canvas.line(MARGIN, canvas.y, MARGIN + CONTENT_W, canvas.y, _COLORS["line"], width=0.6)
    canvas.y += 12
    if (entry.get("body") or "").strip():
        report.blocks(entry["body"], list(attachments))
    else:
        report.lines("Nothing written on how.", color=_COLORS["muted"])
    add_page_numbers(canvas, f"Entropy · {entry['title']}", _COLORS["muted"])
    return write_pdf(canvas.pages, entry["title"], canvas.images)
