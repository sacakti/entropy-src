# ruff: noqa: E501
"""The report as one self-contained web page, with the run page's look and tabs but no scripts."""

from __future__ import annotations

from html import escape as esc
from typing import Any, Dict, List

from .icons import ICONS
from .model import (
    BUBBLE_H,
    BUBBLE_W,
    CONSOLE_CUT_NOTE,
    layout_diagram,
    node_tint,
    omitted_note,
    status_color,
)

_STYLE = """
*{box-sizing:border-box}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{margin:0;color:var(--text);background:var(--bg);
font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
main{display:grid;gap:18px;max-width:1280px;margin:0 auto;padding:24px}
svg.icon{flex:none;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;
stroke-linejoin:round}
.top{display:flex;align-items:center;gap:14px}
.mark{display:grid;flex:none;place-items:center;width:40px;height:40px;color:var(--accent);
background:var(--accent-soft);border:1px solid var(--accent-border);border-radius:11px}
.title{flex:1;min-width:0}
h1{margin:0;font-size:20px;line-height:1.25;overflow-wrap:anywhere}
.title p{margin:2px 0 0;color:var(--muted);font-size:13px;overflow-wrap:anywhere}
.status{display:inline-flex;flex:none;align-items:center;gap:6px;padding:4px 11px;border:1px solid;
border-radius:999px;font-size:12.5px;font-weight:650}
.meta{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;margin:14px 0 0}
.meta div{min-width:0;padding:10px 12px;background:var(--surface);border:1px solid var(--line);
border-radius:10px}
.meta dt{color:var(--subtle);font-size:11px;font-weight:600;letter-spacing:.02em;
text-transform:uppercase}
.meta dd{margin:4px 0 0;font-size:13.5px;font-weight:600;overflow-wrap:anywhere}
.options{display:grid;gap:6px;margin:14px 0 0;font-size:12.5px}
.options div{display:flex;flex-wrap:wrap;align-items:center;gap:6px}
.options dt{min-width:64px;color:var(--subtle);font-weight:600}
.options dd{display:flex;flex-wrap:wrap;gap:5px;margin:0}
.tag{padding:1px 8px;color:var(--muted);background:var(--bg);border:1px solid var(--line);
border-radius:999px;font-size:11.5px}
.bar{height:6px;margin:16px 0 0;overflow:hidden;background:var(--surface);border-radius:999px}
.bar span{display:block;height:100%;border-radius:inherit}
.alert{display:flex;align-items:flex-start;gap:10px;margin:16px 0 0;padding:12px 14px;border:1px solid;
border-radius:10px;overflow-wrap:anywhere;white-space:pre-wrap}
.tabs,.source{position:absolute;opacity:0;pointer-events:none}
.seg{display:inline-flex;gap:2px;padding:3px;background:var(--surface);border:1px solid var(--line);
border-radius:10px}
.seg label{display:inline-flex;align-items:center;gap:6px;padding:6px 12px;color:var(--muted);
border-radius:7px;font-size:13px;font-weight:600;cursor:pointer}
.view{display:none;margin-top:14px}
.print-title{display:none;margin:0 0 10px;font-size:15px}
#t-progress:checked~.seg label[for=t-progress],#t-diagram:checked~.seg label[for=t-diagram],
#t-log:checked~.seg label[for=t-log],#t-app:checked~.seg label[for=t-app],
#s-steps:checked~.seg label[for=s-steps],#s-console:checked~.seg label[for=s-console]{
color:var(--accent-text);background:var(--accent)}
.tabs:focus-visible~.seg{outline:2px solid var(--accent);outline-offset:2px}
#t-progress:checked~.v-progress,#t-diagram:checked~.v-diagram,#t-log:checked~.v-log,
#t-app:checked~.v-app,#s-steps:checked~.s-steps,#s-console:checked~.s-console{display:block}
.cards{display:grid;gap:10px;margin:0;padding:0;list-style:none}
.card{overflow:hidden;background:var(--surface);border:1px solid var(--line);border-left-width:3px;
border-radius:12px}
.card summary{display:flex;align-items:center;gap:12px;padding:12px 14px;cursor:pointer;list-style:none}
.card summary::-webkit-details-marker{display:none}
.chevron{transition:transform .15s;color:var(--subtle)}
details[open]>summary .chevron{transform:rotate(180deg)}
.index{display:grid;flex:0 0 24px;place-items:center;height:24px;color:var(--muted);background:var(--bg);
border:1px solid var(--line);border-radius:7px;font-size:12px;font-weight:700}
.name{flex:1;min-width:0}
.name strong{display:block;font-size:14px;overflow-wrap:anywhere}
.name span{display:block;color:var(--subtle);font:12px ui-monospace,SFMono-Regular,Menlo,monospace}
.state{flex:none;color:var(--muted);font-size:12.5px;font-weight:600;text-align:right}
.state small{display:block;color:var(--subtle);font-size:11.5px;font-weight:500}
.tags{display:flex;flex-wrap:wrap;gap:4px}
.body{padding:0 14px 12px}
.artifacts{display:grid;gap:3px;margin:0;padding:0 14px 10px;list-style:none;font-size:12.5px}
.artifacts li{display:flex;flex-wrap:wrap;align-items:center;gap:8px;color:var(--muted)}
.artifacts small{color:var(--subtle)}
.lines{display:grid;gap:1px;margin:0;padding:0;list-style:none;
font:12.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
.lines li{display:flex;gap:10px;padding:2px 6px;border-radius:6px}
.lines time{flex:none;color:var(--subtle)}
.lines em{flex:none;max-width:180px;overflow:hidden;color:var(--accent);font-style:normal;font-weight:600;
text-overflow:ellipsis;white-space:nowrap}
.lines span{min-width:0;overflow-wrap:anywhere;white-space:pre-wrap}
.is-meta span,.is-debug span{color:var(--muted)}
.is-success span{color:var(--success)}
.is-warning{background:var(--warning-soft)}
.is-warning span{color:var(--warning)}
.is-error{background:var(--danger-soft)}
.is-error span{color:var(--danger)}
.result{max-height:320px;margin:10px 0 0;padding:10px 12px;overflow:auto;background:var(--bg);
border:1px solid var(--line);border-radius:9px;font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace}
.log{max-height:640px;padding:12px;overflow:auto;background:var(--bg);border:1px solid var(--line);
border-radius:12px}
.log pre{margin:0;font:12.5px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;
white-space:pre-wrap;overflow-wrap:anywhere}
.muted{margin:0;color:var(--muted)}
.note{margin:0 0 10px;color:var(--muted);font-size:12px}
.legend{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:0 0 10px;color:var(--muted);
font-size:12px}
.legend i{display:inline-block;width:22px;border-top:2px dashed var(--subtle)}
.legend i.dep{border-top:2px solid var(--accent)}
.legend b{padding:1px 8px;border:1px solid var(--line);border-radius:999px;font-weight:500}
.canvas{overflow:hidden;background:var(--bg);border:1px solid var(--line);border-radius:12px}
.canvas svg{display:block;width:100%;height:auto}
.app{display:grid;gap:12px;margin-bottom:18px}
.app h3{margin:0;font-size:15px}
.app h4{margin:0 0 6px;font-size:13px}
.panel{padding:12px 14px;overflow:auto;background:var(--surface);border:1px solid var(--line);border-radius:10px}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{padding:6px 10px;border-top:1px solid var(--line);text-align:left;vertical-align:top}
th{border-top:0;color:var(--subtle);font-weight:600}
.pairs{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin:0}
.pairs dt{color:var(--subtle);font-size:11.5px}
.pairs dd{margin:2px 0 0;font-weight:600;overflow-wrap:anywhere}
footer{color:var(--subtle);font-size:12px}
@media (max-width:900px){.meta{grid-template-columns:repeat(2,minmax(0,1fr))}.lines li{flex-wrap:wrap}}
@media print{.seg{display:none}.view{display:block!important;margin:0 0 22px}.print-title{display:block}
.log,.result{max-height:none;overflow:visible}.card,.panel{break-inside:avoid-page}}
""".strip()


def _icon(name: str, size: int = 16) -> str:
    return (
        f'<svg class="icon" width="{size}" height="{size}" viewBox="0 0 24 24" aria-hidden="true">'
        f"{ICONS[name]}</svg>"
    )


def _lines(items: List[Dict[str, Any]], *, steps: bool = False) -> str:
    rows = []
    for item in items:
        step = f"<em>{esc(item['step'])}</em>" if steps and item.get("step") else ""
        rows.append(
            f'<li class="is-{esc(item["tone"])}"><time>{esc(item["time"])}</time>{step}'
            f"<span>{esc(item['text'])}</span></li>"
        )
    return f'<ul class="lines">{"".join(rows)}</ul>'


def _card(card: Dict[str, Any], colors: Dict[str, str]) -> str:
    color = colors.get(status_color(card["status"]), colors["line"])
    border = colors["line"] if card["status"] == "pending" else color
    plugin = card["plugin"] + (f" · on {card['node']}" if card["node"] else "")
    tags = "".join(f'<span class="tag">{esc(tag)}</span>' for tag in card["tags"])
    tags = f'<span class="tags">{tags}</span>' if tags else ""
    icon_color = colors["subtle"] if card["status"] in ("pending", "skipped") else color
    duration = f"<small>{esc(card['duration'])}</small>" if card["duration"] else ""
    artifacts = "".join(
        f'<li>{_icon("package", 14)}{esc(item["name"])}<small>{esc(item["size"])}</small></li>'
        for item in card["artifacts"]
    )
    artifacts = f'<ul class="artifacts">{artifacts}</ul>' if artifacts else ""
    body = (
        _lines(card["lines"]) if card["lines"] else '<p class="muted">Nothing reported.</p>'
    ) + (f'<pre class="result">{esc(card["result"])}</pre>' if card["result"] else "")
    return (
        f'<li class="card" style="border-left-color:{border}"><details open><summary>'
        f'<span class="index">{card["index"]}</span>'
        f'<span style="color:{icon_color};display:inline-flex">{_icon(card["status"], 18)}</span>'
        f'<span class="name"><strong>{esc(card["name"])}</strong><span>{esc(plugin)}</span></span>'
        f"{tags}"
        f'<span class="state">{esc(card["label"])}{duration}</span>'
        f'<span class="chevron" style="display:inline-flex">{_icon("chevron")}</span></summary>'
        f'{artifacts}<div class="body">{body}</div></details></li>'
    )


def _diagram(report: Dict[str, Any]) -> str:
    colors = report["colors"]
    layout = layout_diagram(report, 1000)
    if not layout["bubbles"]:
        return '<p class="muted">No steps were planned.</p>'
    edges = []
    for start, end in layout["sequence"]:
        edges.append(
            f'<line x1="{start[0]:.1f}" y1="{start[1]:.1f}" x2="{end[0]:.1f}" y2="{end[1]:.1f}"'
            f' stroke="{colors["subtle"]}" stroke-width="2" stroke-dasharray="6 5"'
            ' marker-end="url(#seq)"/>'
        )
    for item in layout["dependencies"]:
        start, middle, end = item["start"], item["middle"], item["end"]
        edges.append(
            f'<path d="M{start[0]:.1f},{start[1]:.1f} Q{middle[0]:.1f},{middle[1]:.1f}'
            f' {end[0]:.1f},{end[1]:.1f}" fill="none" stroke="{colors["accent"]}" stroke-width="2"'
            ' marker-end="url(#dep)"/>'
            f'<text x="{item["label_at"][0]:.1f}" y="{item["label_at"][1]:.1f}" text-anchor="middle"'
            f' font-size="11" fill="{colors["accent"]}">{esc(item["label"])}</text>'
        )
    bubbles = []
    for bubble in layout["bubbles"]:
        status = bubble["status"]
        stroke = colors["line"] if status == "pending" else colors[status_color(status)]
        fill = (
            node_tint(bubble["hue"], colors["surface"])
            if bubble["hue"] is not None
            else colors["surface"]
        )
        dash = ' stroke-dasharray="6 4"' if status in ("cancelled", "skipped") else ""
        solved = status in ("completed", "failed")
        index_fill = stroke if solved else colors["bg"]
        index_text = colors["bg"] if solved else colors["muted"]
        x, y = bubble["x"], bubble["y"]
        name = bubble["name"] if len(bubble["name"]) <= 18 else bubble["name"][:17] + "…"
        small = bubble["plugin"] + (
            f" · {bubble['node']}" if len(layout["nodes"]) > 1 and bubble["node"] else ""
        )
        small = small if len(small) <= 22 else small[:21] + "…"
        bubbles.append(
            f'<g><title>{esc(bubble["name"])} · {esc(status)}</title>'
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{BUBBLE_W}" height="{BUBBLE_H}" rx="32"'
            f' fill="{fill}" stroke="{stroke}" stroke-width="2"{dash}/>'
            f'<circle cx="{x + 18:.1f}" cy="{y + BUBBLE_H / 2:.1f}" r="10" fill="{index_fill}"/>'
            f'<text x="{x + 18:.1f}" y="{y + BUBBLE_H / 2 + 4:.1f}" text-anchor="middle" font-size="11"'
            f' font-weight="700" fill="{index_text}">{bubble["index"]}</text>'
            f'<text x="{x + 36:.1f}" y="{y + 28:.1f}" font-size="13" font-weight="700"'
            f' fill="{colors["text"]}">{esc(name)}</text>'
            f'<text x="{x + 36:.1f}" y="{y + 45:.1f}" font-size="11"'
            f' fill="{colors["subtle"]}">{esc(small)}</text></g>'
        )
    keys = "".join(
        f'<b style="background:{node_tint(hue, colors["surface"])}">{esc(node)}</b>'
        for node, hue in (layout["nodes"] if len(layout["nodes"]) > 1 else ())
    )
    marker = (
        '<marker id="{}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"'
        ' orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{}"/></marker>'
    )
    defs = (
        f'<defs>{marker.format("seq", colors["subtle"])}{marker.format("dep", colors["accent"])}'
        '<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse">'
        f'<circle cx="1" cy="1" r="1" fill="{colors["line"]}"/></pattern></defs>'
    )
    width, height = layout["width"], layout["height"]
    return (
        f'<p class="legend"><i></i> runs after <i class="dep"></i> uses output of {keys}</p>'
        f'<div class="canvas"><svg viewBox="0 0 {width:.0f} {height:.0f}" role="img"'
        f' aria-label="Diagram of the run\'s steps" font-family="-apple-system,Segoe UI,Arial,sans-serif">'
        f'{defs}<rect width="{width:.0f}" height="{height:.0f}" fill="url(#dots)"/>'
        f'{"".join(edges)}{"".join(bubbles)}</svg></div>'
    )


def _pairs(items: List[Any]) -> str:
    rows = "".join(
        f"<div><dt>{esc(label)}</dt><dd>{esc(value)}</dd></div>" for label, value in items
    )
    return f'<dl class="pairs">{rows}</dl>'


def _view(view: Dict[str, Any]) -> str:
    kind = view["type"]
    if kind == "table":
        head = "".join(f"<th>{esc(column)}</th>" for column in view["columns"])
        rows = "".join(
            "<tr>" + "".join(f"<td>{esc(cell)}</td>" for cell in row) + "</tr>"
            for row in view["rows"]
        )
        more = view["total"] - len(view["rows"])
        note = (
            f'<p class="note">Showing {len(view["rows"])} of {view["total"]}.</p>'
            if more > 0
            else ""
        )
        content = (
            f"{note}<table><tr>{head}</tr>{rows}</table>"
            if rows
            else '<p class="muted">No rows.</p>'
        )
    elif kind in ("stats", "keyvalue"):
        content = _pairs(view["items"]) if view["items"] else '<p class="muted">Nothing yet.</p>'
    elif kind == "log":
        content = (
            f"<pre>{esc(chr(10).join(view['lines']))}</pre>"
            if view["lines"]
            else '<p class="muted">Nothing yet.</p>'
        )
    else:
        content = f'<pre style="margin:0;white-space:pre-wrap">{esc(view["text"])}</pre>'
    description = f'<p class="note">{esc(view["description"])}</p>' if view["description"] else ""
    return f'<div class="panel"><h4>{esc(view["label"])}</h4>{description}{content}</div>'


def _app(app: Dict[str, Any]) -> str:
    description = f'<p class="muted">{esc(app["description"])}</p>' if app["description"] else ""
    inputs = f'<div class="panel">{_pairs(app["inputs"])}</div>' if app["inputs"] else ""
    return (
        f'<section class="app"><h3>{esc(app["title"])}</h3>{description}{inputs}'
        f'{"".join(_view(view) for view in app["views"])}</section>'
    )


def render_html(report: Dict[str, Any]) -> bytes:
    colors = report["colors"]
    variables = ";".join(f"--{key.replace('_', '-')}:{value}" for key, value in colors.items())
    state = status_color(report["state"])
    title, subtitle = esc(report["title"]), esc(report["subtitle"])

    badge_soft = colors.get(f"{state}_soft", colors["surface"])
    badge_border = colors.get(f"{state}_border", colors["line"])
    badge = (
        f'<span class="status" style="color:{colors[state]};background:{badge_soft};'
        f'border-color:{badge_border}">{_icon(report["state"] if report["state"] in ICONS else "pending", 14)}'
        f'{esc(report["state_label"])}</span>'
    )
    meta = "".join(
        f"<div><dt>{esc(key)}</dt><dd>{esc(value)}</dd></div>" for key, value in report["meta"]
    )
    options = "".join(
        f"<div><dt>{esc(label)}</dt><dd>"
        + "".join(f'<span class="tag">{esc(item)}</span>' for item in items)
        + "</dd></div>"
        for label, items in report["options"]
    )
    options = f'<dl class="options">{options}</dl>' if options else ""
    bar_color = colors["accent"] if state in ("accent", "muted") else colors[state]
    alert = ""
    if report["alert"]:
        kind = report["alert"]["kind"]
        icon = "alert" if kind == "danger" else "cancelled"
        alert = (
            f'<div class="alert" style="color:{colors[kind]};background:{colors[f"{kind}_soft"]};'
            f'border-color:{colors[f"{kind}_border"]}">{_icon(icon)}<span>{esc(report["alert"]["text"])}</span></div>'
        )
    cards = "".join(_card(card, colors) for card in report["cards"])
    progress = (
        f'<ol class="cards">{cards}</ol>'
        if cards
        else '<p class="muted">No steps were reported.</p>'
    )

    omitted = (
        f'<p class="note">{esc(omitted_note(report["omitted"]))}</p>' if report["omitted"] else ""
    )
    steps_log = (
        _lines(report["log"], steps=True) if report["log"] else '<p class="muted">No events.</p>'
    )
    console_note = f'<p class="note">{esc(CONSOLE_CUT_NOTE)}</p>' if report["console_cut"] else ""
    console = (
        f"<pre>{esc(report['console'])}</pre>"
        if report["console"]
        else '<p class="muted">The worker wrote no console output.</p>'
    )

    tabs = [
        ("progress", "Progress", "progress"),
        ("diagram", "Diagram", "diagram"),
        ("log", "Live log", "log"),
    ]
    if report["apps"]:
        tabs.append(("app", "App", "app"))
    inputs = "".join(
        f'<input class="tabs" type="radio" name="view" id="t-{key}" aria-label="{esc(label)}"'
        f'{" checked" if index == 0 else ""}>'
        for index, (key, label, _) in enumerate(tabs)
    )
    labels = "".join(
        f'<label for="t-{key}">{_icon(icon, 13)} {esc(label)}</label>' for key, label, icon in tabs
    )
    apps = (
        f'<div class="view v-app"><h2 class="print-title">App</h2>{"".join(_app(app) for app in report["apps"])}</div>'
        if report["apps"]
        else ""
    )
    page = (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">"
        f"<title>{title} · Run report</title><style>:root{{{variables}}}{_STYLE}</style></head><body><main>"
        f'<header><div class="top"><span class="mark">{_icon(report["kind"], 18)}</span>'
        f'<div class="title"><h1>{title}</h1><p>{subtitle}</p></div>{badge}</div>'
        f'<dl class="meta">{meta}</dl>{options}'
        f'<div class="bar"><span style="width:{report["progress"]}%;background:{bar_color}"></span></div>'
        f"{alert}</header>"
        f'<section>{inputs}<div class="seg">{labels}</div>'
        f'<div class="view v-progress"><h2 class="print-title">Progress</h2>{progress}</div>'
        f'<div class="view v-diagram"><h2 class="print-title">Diagram</h2>{_diagram(report)}</div>'
        '<div class="view v-log"><h2 class="print-title">Live log</h2>'
        '<input class="source" type="radio" name="source" id="s-steps" aria-label="Steps" checked>'
        '<input class="source" type="radio" name="source" id="s-console" aria-label="Console">'
        '<div class="seg" style="margin-bottom:10px"><label for="s-steps">Steps</label>'
        f'<label for="s-console">{_icon("console", 13)} Console</label></div>'
        f'<div class="view s-steps" style="margin:0"><div class="log">{omitted}{steps_log}</div></div>'
        f'<div class="view s-console" style="margin:0"><h2 class="print-title">Console</h2>'
        f'<div class="log">{console_note}{console}</div></div></div>'
        f"{apps}</section>"
        f"<footer>{esc(report['footer'])}</footer></main></body></html>"
    )
    return page.encode("utf-8")
