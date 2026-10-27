"""
A self-contained task report for people outside the tool.

One HTML file: a summary, then each group's tasks with their fields,
comments, status history and attachments. Images are embedded, text
files shown inline, videos playable in the file. Printed from a browser
it becomes the PDF (videos are then named, not played).
"""

from __future__ import annotations

import base64
import mimetypes
from datetime import date, datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from lib.tasks.store import CLOSED, REOPENED

STATUS_LABELS = {"todo": "Open", "in_progress": "In progress", CLOSED: "Closed", REOPENED: "Reopened"}
# Embedded inline; larger files are listed by name.
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_VIDEO_BYTES = 25 * 1024 * 1024
MAX_TEXT_BYTES = 64 * 1024
TEXT_TYPES = (".txt", ".log", ".md", ".csv", ".json", ".yaml", ".yml", ".xml")


def _status(value: str) -> str:
    return STATUS_LABELS.get(value, value.replace("_", " ").title())


def _when(value: Optional[str]) -> str:
    if not value:
        return "—"
    return value.replace("T", " ")[:16]


def _overdue(task: Dict[str, Any]) -> bool:
    due = task.get("due_date")
    return bool(due) and task["status"] != CLOSED and due < date.today().isoformat()


def _paragraphs(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return '<p class="muted">—</p>'
    return "".join(f"<p>{escape(part).replace(chr(10), '<br>')}</p>" for part in text.split("\n\n"))


def _kind(attachment: Dict[str, Any]) -> str:
    content_type = attachment.get("content_type") or mimetypes.guess_type(attachment["filename"])[0] or ""
    if content_type.startswith("image/"):
        return "image"
    if content_type.startswith("video/"):
        return "video"
    if content_type.startswith("text/") or attachment["filename"].lower().endswith(TEXT_TYPES):
        return "text"
    return "file"


def _attachment(attachment: Dict[str, Any], root: Path) -> str:
    name = escape(attachment["filename"])
    size = attachment.get("size_bytes") or 0
    label = f'<div class="att-name">{name} <span class="muted">· {_size(size)}</span></div>'
    path = None
    if attachment.get("storage_name"):
        candidate = (root / attachment["storage_name"]).resolve()
        if root.resolve() in candidate.parents and candidate.is_file():
            path = candidate
    if path is None:
        link = attachment.get("url")
        target = f' — <a href="{escape(link)}">{escape(link)}</a>' if link else ""
        return f'<div class="att file">{label}<div class="muted">Linked file{target}</div></div>'

    kind = _kind(attachment)
    content_type = attachment.get("content_type") or mimetypes.guess_type(attachment["filename"])[0]
    data = path.stat().st_size
    if kind == "image" and data <= MAX_IMAGE_BYTES:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return (f'<figure class="att image"><img src="data:{escape(content_type or "image/png")};base64,'
                f'{encoded}" alt="{name}"><figcaption>{label}</figcaption></figure>')
    if kind == "video" and data <= MAX_VIDEO_BYTES:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return (f'<div class="att video">{label}<video controls preload="metadata" '
                f'src="data:{escape(content_type or "video/mp4")};base64,{encoded}"></video>'
                f'<div class="print-only muted">Video — play it in the HTML report.</div></div>')
    if kind == "text":
        raw = path.read_bytes()[:MAX_TEXT_BYTES].decode("utf-8", "replace")
        more = '<div class="muted">… shortened</div>' if data > MAX_TEXT_BYTES else ""
        return f'<div class="att text">{label}<pre>{escape(raw)}</pre>{more}</div>'
    note = "Too large to include." if kind in ("image", "video") else "Attached file."
    return f'<div class="att file">{label}<div class="muted">{note}</div></div>'


def _size(value: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024  # type: ignore[assignment]
    return ""


def _task(task: Dict[str, Any], members: Dict[str, str], groups: Dict[int, str], root: Path,
          attachments: List[Dict[str, Any]]) -> str:
    assignee = task.get("assignee")
    fields = [
        ("Status", f'<span class="status s-{escape(task["status"])}">{escape(_status(task["status"]))}</span>'),
        ("Type", escape(task.get("type", "issue").replace("_", " ").title())),
        ("Assignee", escape(members.get((assignee or "").lower(), assignee or "") or "Unassigned")),
        ("Due date", escape(task.get("due_date") or "—")
         + (' <span class="overdue">Overdue</span>' if _overdue(task) else "")),
        ("External reference", escape(task.get("external_ref") or "—")),
        ("Groups", escape(", ".join(groups[g] for g in task.get("group_ids", []) if g in groups) or "—")),
        ("Created by", escape(task.get("creator") or "—")),
        ("Created", escape(_when(task.get("created_at")))),
        ("Last updated", escape(_when(task.get("updated_at")))),
    ]
    grid = "".join(f"<div><dt>{label}</dt><dd>{value}</dd></div>" for label, value in fields)
    parts = [
        f'<article class="task" id="task-{task["id"]}">',
        f'<header><span class="key">{escape(task.get("key") or "")}</span><h3>{escape(task["title"])}</h3></header>',
        f"<dl class=\"fields\">{grid}</dl>",
        "<h4>Description</h4>", _paragraphs(task.get("description", "")),
    ]
    if (task.get("remarks") or "").strip():
        parts += ["<h4>Remarks</h4>", _paragraphs(task["remarks"])]
    if task.get("comments"):
        parts.append("<h4>Comments</h4><ul class=\"comments\">")
        for comment in task["comments"]:
            parts.append(f"<li><div class=\"meta\">{escape(comment['author'])} · {escape(_when(comment['created_at']))}"
                         f"</div>{_paragraphs(comment['body'])}</li>")
        parts.append("</ul>")
    history = task.get("history") or []
    if len(history) > 1 or any(item.get("reason") for item in history):
        parts.append("<h4>Status history</h4><table class=\"history\"><tbody>")
        for item in history:
            moved = (f"{escape(_status(item['from_status']))} → " if item.get("from_status") else "Created as ")
            reason = f"<div class=\"muted\">Reason: {escape(item['reason'])}</div>" if item.get("reason") else ""
            parts.append(f"<tr><td>{escape(_when(item['changed_at']))}</td><td>{moved}"
                         f"<strong>{escape(_status(item['to_status']))}</strong>{reason}</td>"
                         f"<td>{escape(item['changed_by'])}</td></tr>")
        parts.append("</tbody></table>")
    if attachments:
        parts.append(f"<h4>Attachments ({len(attachments)})</h4><div class=\"attachments\">")
        parts += [_attachment(item, root) for item in attachments]
        parts.append("</div>")
    parts.append("</article>")
    return "".join(parts)


def build_report(
    *,
    project: str,
    scope: str,
    tasks: List[Dict[str, Any]],
    groups: Iterable[Dict[str, Any]],
    members: Iterable[Dict[str, Any]],
    attachments: Dict[int, List[Dict[str, Any]]],
    attachment_root: Path,
    generated_by: str,
    print_mode: bool = False,
) -> str:
    """The report's HTML; `attachments` maps task id to its stored attachments."""

    group_list = list(groups)
    group_names = {group["id"]: group["name"] for group in group_list}
    member_names = {m["username"].lower(): (m.get("full_name") or m["username"]) for m in members}

    sections: List[tuple] = []
    for group in group_list:
        in_group = [task for task in tasks if group["id"] in task.get("group_ids", [])]
        if in_group:
            sections.append((group["name"], group.get("kind", ""), group.get("description", ""), in_group))
    ungrouped = [task for task in tasks if not any(g in group_names for g in task.get("group_ids", []))]
    if ungrouped:
        sections.append(("Not in a group", "", "", ungrouped))

    counts = {status: sum(1 for task in tasks if task["status"] == status) for status in STATUS_LABELS}
    overdue = sum(1 for task in tasks if _overdue(task))
    total = len(tasks) or 1
    bar = "".join(
        f'<span class="s-{status}" style="width:{counts[status] * 100 / total:.2f}%"></span>'
        for status in STATUS_LABELS if counts[status]
    )
    tiles = [("Tasks", len(tasks), "")] + [(_status(s), counts[s], f"s-{s}") for s in STATUS_LABELS] + [
        ("Overdue", overdue, "overdue-tile")
    ]
    tile_html = "".join(f'<div class="tile {cls}"><b>{value}</b><span>{label}</span></div>'
                        for label, value, cls in tiles)

    contents = []
    body = []
    for index, (name, kind, description, items) in enumerate(sections, start=1):
        anchor = f"group-{index}"
        done = sum(1 for task in items if task["status"] == CLOSED)
        contents.append(f'<li><a href="#{anchor}">{escape(name)}</a> <span class="muted">'
                        f'{done}/{len(items)} closed</span></li>')
        rows = "".join(
            f'<tr><td><a href="#task-{task["id"]}">{escape(task.get("key") or "")}</a></td>'
            f'<td>{escape(task["title"])}</td><td><span class="status s-{escape(task["status"])}">'
            f'{escape(_status(task["status"]))}</span></td>'
            f'<td>{escape(member_names.get((task.get("assignee") or "").lower(), task.get("assignee") or "—"))}</td>'
            f'<td>{escape(task.get("due_date") or "—")}</td></tr>'
            for task in items
        )
        cards = "".join(_task(task, member_names, group_names, attachment_root,
                              attachments.get(task["id"], [])) for task in items)
        kind_label = f'<span class="chip">{escape(kind.title())}</span>' if kind else ""
        body.append(
            f'<section class="group" id="{anchor}"><h2>{escape(name)} {kind_label}</h2>'
            + (f'<p class="muted">{escape(description)}</p>' if description else "")
            + '<table class="overview"><thead><tr><th>ID</th><th>Task</th><th>Status</th>'
              f'<th>Assignee</th><th>Due</th></tr></thead><tbody>{rows}</tbody></table>{cards}</section>'
        )

    generated = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    auto_print = "<script>window.addEventListener('load',()=>setTimeout(()=>window.print(),300))</script>" \
        if print_mode else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Task report — {escape(project)}</title>
<style>{CSS}</style></head>
<body><main>
<header class="cover"><div class="brand">Entropy · Task report</div>
<h1>{escape(project)}</h1>
<p class="muted">{escape(scope)} · {len(tasks)} task{'s' if len(tasks) != 1 else ''} · generated {generated} by {escape(generated_by)}</p>
</header>
<section class="summary"><div class="tiles">{tile_html}</div><div class="bar">{bar}</div></section>
{('<nav class="toc"><h2>Contents</h2><ol>' + ''.join(contents) + '</ol></nav>') if len(sections) > 1 else ''}
{''.join(body) or '<p class="muted">No tasks to report.</p>'}
</main>{auto_print}</body></html>"""


CSS = """
:root{--ink:#1d2433;--muted:#667085;--line:#e4e7ec;--soft:#f6f7f9;--accent:#1f5fbf;
--open:#5b6b86;--progress:#c27c0e;--closed:#2e7d4f;--reopened:#b4363a}
*{box-sizing:border-box}body{margin:0;background:#eef1f5;color:var(--ink);
font:15px/1.55 "Segoe UI",system-ui,-apple-system,Roboto,Arial,sans-serif}
main{max-width:980px;margin:0 auto;padding:32px 20px 60px}
h1{font-size:30px;margin:6px 0 4px}h2{font-size:21px;margin:0 0 10px}
h3{font-size:17px;margin:0}h4{font-size:13px;text-transform:uppercase;letter-spacing:.05em;
color:var(--muted);margin:18px 0 6px}p{margin:0 0 8px}.muted{color:var(--muted)}
a{color:var(--accent);text-decoration:none}
.cover,.summary,.toc,.group{background:#fff;border:1px solid var(--line);border-radius:12px;
padding:22px 24px;margin-bottom:18px}
.brand{font-size:12px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px}
.tile{border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:var(--soft)}
.tile b{display:block;font-size:24px}.tile span{font-size:12px;color:var(--muted)}
.tile.s-todo b{color:var(--open)}.tile.s-in_progress b{color:var(--progress)}
.tile.s-done b{color:var(--closed)}.tile.s-reopened b,.overdue-tile b{color:var(--reopened)}
.bar{display:flex;height:10px;border-radius:5px;overflow:hidden;margin-top:14px;background:var(--line)}
.bar span.s-todo{background:var(--open)}.bar span.s-in_progress{background:var(--progress)}
.bar span.s-done{background:var(--closed)}.bar span.s-reopened{background:var(--reopened)}
.toc ol{margin:0;padding-left:20px}
.chip{font-size:11px;font-weight:600;border:1px solid var(--line);border-radius:999px;padding:2px 8px;
vertical-align:middle;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{background:#1f4e99;color:#fff;font-weight:600}
.overview{margin-bottom:8px}
.status{display:inline-block;font-size:12px;font-weight:600;border-radius:999px;padding:1px 9px;color:#fff}
.status.s-todo{background:var(--open)}.status.s-in_progress{background:var(--progress)}
.status.s-done{background:var(--closed)}.status.s-reopened{background:var(--reopened)}
.overdue{font-size:11px;font-weight:700;color:var(--reopened);margin-left:6px}
.task{border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin-top:16px;
break-inside:avoid-page}
.task header{display:flex;gap:10px;align-items:baseline;border-bottom:1px solid var(--line);
padding-bottom:8px;margin-bottom:10px}
.key{font:600 13px ui-monospace,Consolas,monospace;color:var(--accent);white-space:nowrap}
.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px 18px;margin:0}
.fields dt{font-size:12px;color:var(--muted)}.fields dd{margin:0;font-weight:500}
.comments{list-style:none;margin:0;padding:0}
.comments li{background:var(--soft);border-radius:8px;padding:8px 12px;margin-bottom:6px}
.meta{font-size:12px;color:var(--muted);margin-bottom:2px}
.history td{border-bottom:1px dashed var(--line)}
.attachments{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.att{border:1px solid var(--line);border-radius:8px;padding:8px;margin:0;background:var(--soft)}
.att img,.att video{display:block;width:100%;max-height:360px;object-fit:contain;background:#fff;
border-radius:6px;margin-top:6px}
.att pre{white-space:pre-wrap;word-break:break-word;font-size:12px;max-height:320px;overflow:auto;
background:#fff;border-radius:6px;padding:8px;margin:6px 0 0}
.att.text{grid-column:1/-1}.att-name{font-size:13px;font-weight:600;word-break:break-all}
.print-only{display:none}
@media print{body{background:#fff}main{padding:0;max-width:none}
.cover,.summary,.toc,.group{border:none;padding:0 0 12px;margin:0 0 12px}
.group{break-before:page}.att video{display:none}.print-only{display:block}
.att pre{max-height:none;overflow:visible}
th{-webkit-print-color-adjust:exact;print-color-adjust:exact}
.status,.bar span,.tile{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
"""
