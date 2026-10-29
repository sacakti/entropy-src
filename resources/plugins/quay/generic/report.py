"""
The Quay report: one self-contained HTML file (no scripts, no external files)
listing every tag of every repository with what the retention policy did.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any, Dict, List, Optional

STYLE = """
:root{--ink:#1f2328;--muted:#656d76;--line:#d0d7de;--soft:#f6f8fa;--keep:#1a7f37;--del:#cf222e;
--warn:#9a6700}
*{box-sizing:border-box}
body{margin:0;font:14px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;color:var(--ink);
background:#fff}
main{max-width:1180px;margin:0 auto;padding:28px 24px 60px}
h1{margin:0 0 4px;font-size:24px}
h2{margin:0;font-size:16px}
.meta{color:var(--muted);margin:0 0 20px}
.meta code{color:var(--ink)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;
margin:0 0 20px}
.tile{border:1px solid var(--line);border-radius:10px;padding:12px 14px;background:var(--soft)}
.tile b{display:block;font-size:24px}
.tile span{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.tile.keep b{color:var(--keep)}
.tile.delete b{color:var(--del)}
.tile.failed b{color:var(--warn)}
.policy{border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:0 0 20px}
.policy ul{margin:6px 0 0;padding-left:20px}
nav.toc{border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:0 0 24px}
nav.toc ol{margin:6px 0 0;padding-left:20px;columns:2}
nav.toc a{color:inherit}
section.repo{border:1px solid var(--line);border-radius:12px;margin:0 0 18px;overflow:hidden;
break-inside:avoid}
section.repo header{display:flex;justify-content:space-between;gap:12px;padding:10px 14px;
background:var(--soft);border-bottom:1px solid var(--line)}
section.repo header span{color:var(--muted)}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:6px 14px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
tr:last-child td{border-bottom:0}
td.num{text-align:right;white-space:nowrap}
code{font:12px ui-monospace,SFMono-Regular,Menlo,monospace}
.badge{display:inline-block;border-radius:999px;padding:0 8px;font-size:12px;font-weight:600;
border:1px solid currentColor}
.badge.keep{color:var(--keep)}
.badge.delete,.badge.deleted{color:var(--del)}
.badge.failed{color:var(--warn)}
tr.delete td,tr.deleted td{background:#fff5f5}
.empty{color:var(--muted);padding:10px 14px}
@media print{main{padding:0}section.repo{break-inside:avoid}}
"""

STATUS_LABELS = {
    "keep": "keep",
    "delete": "would delete",
    "deleted": "deleted",
    "failed": "failed",
}


def _size(value: Optional[int]) -> str:
    if value is None:
        return "-"
    amount = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if amount < 1024 or unit == "GB":
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return "-"


def _pushed(start_ts: Optional[int], now: float) -> str:
    if not start_ts:
        return "-"
    moment = datetime.fromtimestamp(int(start_ts), tz=timezone.utc)
    days = max(0, int((now - int(start_ts)) // 86_400))
    return f"{moment.strftime('%Y-%m-%d %H:%M')} UTC <span>({days}d)</span>"


def _anchor(repository: str) -> str:
    return "repo-" + "".join(ch if ch.isalnum() else "-" for ch in repository)


def _tile(value: Any, label: str, kind: str = "") -> str:
    return f'<div class="tile {kind}"><b>{escape(str(value))}</b><span>{escape(label)}</span></div>'


def build_report(meta: Dict[str, Any], plan: Dict[str, List[Dict[str, Any]]], now: float) -> str:
    """
    `meta`: title, registry, namespace, operation, dry_run, keep, protect,
    min_age_days, rules, generated. `plan`: per repository, the tags newest
    first, each with tag, status (keep/delete/deleted/failed), reason, rule,
    start_ts, manifest_digest, size and error.
    """

    rows = [tag for tags in plan.values() for tag in tags]
    counts = {status: sum(1 for tag in rows if tag["status"] == status) for status in STATUS_LABELS}
    removable = [tag for tag in rows if tag["status"] in ("delete", "deleted")]
    reclaim = sum(tag.get("size") or 0 for tag in removable)

    listing = meta["operation"] == "list"
    tiles = [
        _tile(len(plan), "repositories"),
        _tile(len(rows), "tags"),
        _tile(counts["keep"], "kept by policy" if listing else "kept", "keep"),
    ]
    if listing or meta["dry_run"]:
        tiles.append(_tile(counts["delete"], "would delete", "delete"))
    else:
        tiles.append(_tile(counts["deleted"], "deleted", "delete"))
        tiles.append(_tile(counts["failed"], "failed", "failed"))
    if reclaim:
        tiles.append(_tile(_size(reclaim), "tag size removed" if not listing else "size of those"))

    rules = meta.get("rules") or []
    policy = [
        f"Default: keep the newest <b>{escape(str(meta['keep']))}</b> tags per repository.",
        "Never deleted: "
        + (", ".join(f"<code>{escape(p)}</code>" for p in meta.get("protect") or []) or "none")
        + ".",
    ]
    if meta.get("min_age_days"):
        policy.append(f"Tags younger than {escape(str(meta['min_age_days']))} days are kept.")
    for rule in rules:
        scope = (
            " in " + ", ".join(f"<code>{escape(r)}</code>" for r in rule["repositories"])
            if rule.get("repositories")
            else ""
        )
        limit = "keep all" if rule.get("keep") is None else f"keep newest {rule['keep']}"
        policy.append(
            f"<b>{escape(rule['name'])}</b>: "
            + ", ".join(f"<code>{escape(t)}</code>" for t in rule["tags"])
            + f"{scope} &rarr; {escape(limit)}"
            + (f", only older than {rule['min_age_days']} days" if rule.get("min_age_days") else "")
        )

    if listing:
        mode = "List of tags; the actions are what a cleanup with this policy would do."
    elif meta["dry_run"]:
        mode = "Dry run: nothing was deleted."
    else:
        mode = "Cleanup: the tags marked deleted were removed."

    toc = "".join(
        f'<li><a href="#{_anchor(name)}">{escape(name)}</a> '
        f"({len(tags)} tags, {sum(1 for t in tags if t['status'] != 'keep')} to remove)</li>"
        for name, tags in plan.items()
    )

    sections = []
    for name, tags in plan.items():
        if tags:
            body = "".join(
                f'<tr class="{escape(tag["status"])}">'
                f"<td><code>{escape(tag['tag'])}</code></td>"
                f"<td>{_pushed(tag.get('start_ts'), now)}</td>"
                f"<td><code>{escape((tag.get('manifest_digest') or '-')[:19])}</code></td>"
                f'<td class="num">{_size(tag.get("size"))}</td>'
                f'<td><span class="badge {escape(tag["status"])}">'
                f"{escape(STATUS_LABELS[tag['status']])}</span></td>"
                f"<td>{escape(tag.get('error') or tag['reason'])}</td>"
                f"<td>{escape(tag['rule'])}</td></tr>"
                for tag in tags
            )
            table = (
                "<table><thead><tr><th>Tag</th><th>Pushed</th><th>Digest</th>"
                '<th class="num">Size</th><th>Action</th><th>Why</th><th>Rule</th></tr></thead>'
                f"<tbody>{body}</tbody></table>"
            )
        else:
            table = '<p class="empty">No tags.</p>'
        sections.append(
            f'<section class="repo" id="{_anchor(name)}"><header><h2>{escape(name)}</h2>'
            f"<span>{len(tags)} tags</span></header>{table}</section>"
        )

    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(meta['title'])}</title><style>{STYLE}</style></head><body><main>"
        f"<h1>{escape(meta['title'])}</h1>"
        f'<p class="meta">Registry <code>{escape(meta["registry"])}</code> · namespace '
        f"<code>{escape(meta['namespace'])}</code> · generated {escape(meta['generated'])}"
        f"<br>{escape(mode)}</p>"
        f'<div class="tiles">{"".join(tiles)}</div>'
        f'<div class="policy"><b>Retention policy</b><ul>'
        + "".join(f"<li>{line}</li>" for line in policy)
        + "</ul></div>"
        + (f'<nav class="toc"><b>Repositories</b><ol>{toc}</ol></nav>' if plan else "")
        + ("".join(sections) or '<p class="empty">No repositories matched.</p>')
        + "</main></body></html>\n"
    )
