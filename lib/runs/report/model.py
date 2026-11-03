"""What a report shows: the run page's content worked out on the server, as plain data."""

from __future__ import annotations

import colorsys
import json
import re
from collections import deque
from datetime import datetime, timezone, tzinfo
from typing import Any, Deque, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# The end of a long run matters most: that is where it failed.
MAX_EVENTS = 5000
MAX_CONSOLE_CHARS = 1_000_000
MAX_APP_ROWS = 500
MAX_RESULT_CHARS = 20_000
_PAGE_OF_EVENTS = 2000

ACTIVE_STATES = ("queued", "starting", "running", "paused")
STATE_LABELS = {
    "queued": "Queued",
    "starting": "Starting",
    "running": "Running",
    "paused": "Paused",
    "completed": "Completed",
    "failed": "Failed",
    "cancelled": "Cancelled",
}
CARD_LABELS = {
    "pending": "Pending",
    "running": "Running",
    "completed": "Completed",
    "failed": "Failed",
    "skipped": "Skipped",
    "cancelled": "Cancelled",
}
TRIGGER_LABELS = {"manual": "Manual", "schedule": "Schedule", "retry": "Retry", "cli": "CLI"}
SKIP_REASONS = {"disabled": "disabled", "tag filter": "tag filter", "not selected": "deselected"}

# The diagram, as on the page (RunDiagram.tsx).
BUBBLE_W = 168
BUBBLE_H = 64
_DIAGRAM_MARGIN = 24

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

_THEMES = {
    "dark": {
        "bg": "#090b0f",
        "surface": "#11151b",
        "text": "#f2f4f7",
        "muted": "#9ba5b3",
        "subtle": "#7d8796",
        "accent": "#d7ff63",
        "danger": "#ff7b72",
        "success": "#56d38a",
        "warning": "#f2c14e",
        "line_from": "#ffffff",
        "line_share": 9,
    },
    "light": {
        "bg": "#f4f6ee",
        "surface": "#ffffff",
        "text": "#171b15",
        "muted": "#5c6458",
        "subtle": "#6a7166",
        "accent": "#658a12",
        "danger": "#c0262d",
        "success": "#1a7f37",
        "warning": "#8f5e00",
        "line_from": "#171b15",
        "line_share": 12,
    },
}
_DEFAULT_ACCENT = "#d7ff63"


# ----------------------------------------------------------------------
# Colours
# ----------------------------------------------------------------------


def mix(color: str, share: float, base: str) -> str:
    """`share` percent of `color` over `base`, as a colour both formats can use."""

    parts = []
    for index in (1, 3, 5):
        top, bottom = int(color[index : index + 2], 16), int(base[index : index + 2], 16)
        parts.append(round(top * share / 100 + bottom * (1 - share / 100)))
    return "#" + "".join(f"{part:02x}" for part in parts)


def _luminance(color: str) -> float:
    red, green, blue = (int(color[index : index + 2], 16) / 255 for index in (1, 3, 5))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def palette(theme: str, accent: Optional[str]) -> Dict[str, str]:
    """The page's colours for this person's theme and accent."""

    tokens = dict(_THEMES["light" if theme == "light" else "dark"])
    # The default accent is made for dark backgrounds; the light theme has its own.
    if accent and _HEX.match(accent) and accent.lower() != _DEFAULT_ACCENT:
        tokens["accent"] = accent.lower()
    line = mix(
        str(tokens.pop("line_from")), float(str(tokens.pop("line_share"))), str(tokens["bg"])
    )
    colors: Dict[str, str] = {key: str(value) for key, value in tokens.items()}
    colors["line"] = line
    colors["accent_text"] = "#090b0f" if _luminance(colors["accent"]) > 0.5 else "#ffffff"
    colors["accent_soft"] = mix(colors["accent"], 14, colors["surface"])
    colors["accent_border"] = mix(colors["accent"], 38, line)
    for name in ("danger", "success", "warning"):
        colors[f"{name}_soft"] = mix(colors[name], 11, colors["surface"])
        colors[f"{name}_border"] = mix(colors[name], 38, line)
    return colors


def status_color(status: str) -> str:
    """The palette colour of a run state or a step status."""

    return {
        "completed": "success",
        "failed": "danger",
        "cancelled": "warning",
        "paused": "warning",
        "skipped": "warning",
        "running": "accent",
        "starting": "accent",
    }.get(status, "muted")


# ----------------------------------------------------------------------
# Text, times and levels
# ----------------------------------------------------------------------


def clean(text: Any) -> str:
    """Without terminal colours and control characters, which neither format can show."""

    cleaned = _ANSI.sub("", str(text if text is not None else ""))
    return _CONTROL.sub("", cleaned.replace("\r\n", "\n").replace("\t", "    "))


def resolve_zone(name: Optional[str]) -> Tuple[tzinfo, str]:
    """The browser's time zone, so times read as on the page; UTC if it is not a known zone."""

    if name:
        try:
            return ZoneInfo(name), name
        except (ZoneInfoNotFoundError, ValueError, OSError):
            pass
    return timezone.utc, "UTC"


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def format_time(value: Optional[str], zone: tzinfo) -> str:
    parsed = _parse(value)
    if parsed is None:
        return ""
    local = parsed.astimezone(zone)
    return f"{local.hour % 12 or 12}:{local:%M:%S} {'PM' if local.hour >= 12 else 'AM'}"


def format_datetime(value: Optional[str], zone: tzinfo) -> str:
    parsed = _parse(value)
    if parsed is None:
        return "—"
    local = parsed.astimezone(zone)
    return f"{local:%b} {local.day}, {local.year}, {format_time(value, zone)}"


def format_duration(milliseconds: Optional[float]) -> str:
    if milliseconds is None or milliseconds < 0:
        return "—"
    seconds = int(milliseconds // 1000)
    if seconds < 1:
        return f"{round(milliseconds)} ms"
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m {seconds % 60}s"
    return f"{minutes // 60}h {minutes % 60}m"


def format_bytes(size: float) -> str:
    if size < 1024:
        return f"{int(size)} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def level_name(level: Any) -> str:
    """Levels arrive as logging numbers (20, 25, 40) or names."""

    if level in (None, ""):
        return "info"
    text = str(level)
    try:
        number = float(text)
    except ValueError:
        name = text.lower()
        if name.startswith("err") or name == "critical":
            return "error"
        if name.startswith("warn"):
            return "warning"
        return name if name in ("success", "debug") else "info"
    for bottom, name in ((40, "error"), (30, "warning"), (25, "success"), (20, "info")):
        if number >= bottom:
            return name
    return "debug"


# ----------------------------------------------------------------------
# Reading the run
# ----------------------------------------------------------------------


def _shown(event: Dict[str, Any], run: Dict[str, Any]) -> bool:
    # As the page opens: debug messages only for a debug run.
    if event.get("type") == "message" and level_name(event.get("level")) == "debug":
        return bool(run.get("debug"))
    return True


def collect_events(store: Any, job_id: int, run: Dict[str, Any]) -> Tuple[List[Dict], int]:
    """
    The events to show, in order, and how many were left out: at most the last MAX_EVENTS
    messages, but always what says how each step and the run went.
    """

    job_ids = store.job_ids(job_id)
    archived = bool(run.get("archived"))
    lifecycle: List[Dict[str, Any]] = []
    others: Deque[Dict[str, Any]] = deque(maxlen=MAX_EVENTS)
    seen = 0
    after: Optional[int] = None
    while True:
        page = store.events(job_ids, after, _PAGE_OF_EVENTS, archived=archived)
        if not page:
            break
        for event in page:
            if not _shown(event, run):
                continue
            if str(event.get("type") or "").startswith(("step.", "execution.")):
                lifecycle.append(event)
            else:
                seen += 1
                others.append(event)
        after = page[-1]["id"]
    return sorted([*lifecycle, *others], key=lambda item: item["id"]), seen - len(others)


def read_console(service: Any, job_id: int, run: Dict[str, Any]) -> Tuple[str, bool]:
    """The worker's console output, and whether its beginning was left out."""

    if run.get("archived"):
        return "", False
    text = ""
    cut = False
    offset = 0
    while True:
        part = service.log(job_id, offset)
        if not part.get("text"):
            break
        text += part["text"]
        if len(text) > MAX_CONSOLE_CHARS:
            text, cut = text[-MAX_CONSOLE_CHARS:], True
        if part["offset"] <= offset:
            break
        offset = part["offset"]
    return clean(text), cut


# ----------------------------------------------------------------------
# Events as the page words them (RunDetail.tsx)
# ----------------------------------------------------------------------


def _metadata(event: Dict[str, Any]) -> Dict[str, Any]:
    metadata = (event.get("payload") or {}).get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _compact(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=str)


def event_text(event: Dict[str, Any]) -> str:
    if event.get("message"):
        return clean(event["message"])

    payload = event.get("payload") or {}
    metadata = _metadata(event)
    kind = str(event.get("type") or "")
    subject = clean(event.get("node_name"))
    took = payload.get("duration_ms")
    duration = f" in {format_duration(took)}" if isinstance(took, (int, float)) else ""
    reason = f": {clean(metadata['exception'])}" if metadata.get("exception") else ""

    fixed = {
        "execution.started": f"Run started: {subject}",
        "execution.completed": f"Run completed{duration}",
        "execution.failed": f"Run failed{duration}{reason}",
        "execution.cancelled": "Run cancelled",
        "step.started": f"Step '{subject}' started ({clean(metadata.get('plugin'))})",
        "step.completed": f"Step '{subject}' completed{duration}",
        "step.failed": f"Step '{subject}' failed{duration}{reason}",
        "step.skipped": f"Step '{subject}' skipped",
        "activity.started": f"{subject}…",
        "activity.completed": f"{subject} done{duration}",
        "activity.failed": f"{subject} failed{reason}",
    }
    if kind in fixed:
        return fixed[kind]
    if kind == "plugin_result":
        result = payload.get("result") or {}
        outcome = "unsuccessful" if result.get("success") is False else "success"
        outputs = f" · outputs {_compact(result['outputs'])}" if result.get("outputs") else ""
        return clean(f"Result: {outcome}{outputs}")
    if kind == "render":
        title = f"{payload['title']}\n" if payload.get("title") else ""
        if isinstance(payload.get("lines"), list):
            return clean(title + "\n".join(str(line) for line in payload["lines"]))
        if isinstance(payload.get("rows"), list):
            columns = "  ·  ".join(str(item) for item in payload.get("columns") or [])
            rows = ["  ·  ".join(str(cell) for cell in row) for row in payload["rows"]]
            return clean(title + "\n".join(line for line in (columns, *rows) if line))
        return clean(title.strip() or "Output")
    return kind


def event_tone(event: Dict[str, Any]) -> str:
    kind = str(event.get("type") or "")
    if kind.endswith(".failed"):
        return "error"
    if kind.endswith(".completed"):
        return "success"
    if kind == "message":
        return level_name(event.get("level"))
    return "meta"


def events_by_step(events: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Messages and results belong to the step that was running when they arrived."""

    groups: Dict[str, List[Dict[str, Any]]] = {}
    current: Optional[str] = None
    for event in events:
        kind = str(event.get("type") or "")
        key: Optional[str] = None
        if event.get("node_type") == "step":
            key = event.get("node_name")
            if kind == "step.started":
                current = key
        elif event.get("node_type") != "workflow":
            key = current
        if key:
            groups.setdefault(key, []).append(event)
        if event.get("node_type") == "step" and kind != "step.started" and kind.startswith("step."):
            current = None
    return groups


def _is_selected(step: Dict[str, Any]) -> bool:
    selected = step.get("selected")
    return bool(step.get("enabled") if selected is None else selected)


def _card_status(step: Optional[Dict[str, Any]], state: str) -> str:
    active = state in ACTIVE_STATES
    if step is None:
        if active:
            return "pending"
        return "skipped" if state == "completed" else "cancelled"
    status = str(step.get("status") or "")
    if status == "started":
        status = "running" if active else "cancelled" if state == "cancelled" else "failed"
    elif status not in ("completed", "failed", "skipped"):
        status = "running"
    return "cancelled" if state == "cancelled" and status == "failed" else status


def _result_text(result: Any) -> Optional[str]:
    if not result:
        return None
    text = json.dumps(result, indent=2, ensure_ascii=False, default=str)
    if len(text) > MAX_RESULT_CHARS:
        return f"{text[:MAX_RESULT_CHARS]}\n… cut: the result is {len(text)} characters long."
    return clean(text)


def _cards(
    run: Dict[str, Any],
    plan: Sequence[Dict[str, Any]],
    steps: Sequence[Dict[str, Any]],
    grouped: Dict[str, List[Dict[str, Any]]],
    artifacts: Sequence[Dict[str, Any]],
    now_ms: float,
    zone: tzinfo,
) -> List[Dict[str, Any]]:
    by_name = {step.get("name"): step for step in steps}
    planned = {step["name"]: step for step in plan}
    names = [step["name"] for step in plan if _is_selected(step)]
    names += [step.get("name") for step in steps if step.get("name") not in planned]

    multi_node = len((run.get("options") or {}).get("nodes") or []) > 1
    cards = []
    for index, name in enumerate(names, start=1):
        step = by_name.get(name)
        events = grouped.get(name, [])
        status = _card_status(step, str(run.get("state")))
        started = next((item for item in events if item.get("type") == "step.started"), None)
        result = next((item for item in events if item.get("type") == "plugin_result"), None)
        failure = next((item for item in events if item.get("type") == "step.failed"), None)
        plugin = planned.get(name, {}).get("plugin") or (
            _metadata(started).get("plugin") if started else ""
        )

        duration = step.get("duration_ms") if step else None
        begun = _parse(step.get("started_at")) if step else None
        if status == "running" and begun:
            duration = now_ms - begun.timestamp() * 1000

        card_artifacts = [
            {
                "name": clean(item.get("name")),
                "size": (
                    format_bytes(item.get("size_bytes") or 0)
                    if item.get("available")
                    else "no longer available"
                ),
            }
            for item in artifacts
            if item.get("step_name") == name
            or (not item.get("step_name") and item.get("origin") == plugin and index == 1)
        ]
        cards.append(
            {
                "index": index,
                "name": clean(name),
                "plugin": clean(plugin),
                "node": clean(planned.get(name, {}).get("node")) if multi_node else "",
                "tags": [clean(tag) for tag in planned.get(name, {}).get("tags") or []],
                "status": status,
                "label": CARD_LABELS[status],
                "duration": (
                    format_duration(duration)
                    if status != "pending" and duration is not None
                    else ""
                ),
                "error": (
                    clean(_metadata(failure).get("exception"))
                    if failure and status == "failed"
                    else ""
                ),
                "lines": [
                    {
                        "time": format_time(item.get("created_at"), zone),
                        "text": event_text(item),
                        "tone": event_tone(item),
                    }
                    for item in events
                ],
                "result": _result_text(
                    (result.get("payload") or {}).get("result") if result else None
                ),
                "artifacts": card_artifacts,
            }
        )
    return cards


def _options(options: Dict[str, Any]) -> List[Tuple[str, List[str]]]:
    """What the run was started with (RunOptionsSummary.tsx): names of inputs, never values."""

    if not options.get("nodes"):
        return []
    skipped = options.get("skipped") or []
    reasons = {step.get("name"): step.get("skip_reason") for step in options.get("steps") or []}
    everything = all(reasons.get(name) == "disabled" for name in skipped)
    selected = options.get("selected") or []
    rows: List[Tuple[str, List[str]]] = []
    if options.get("tags"):
        rows.append(("Tags", [clean(tag) for tag in options["tags"]]))
    rows.append(("Steps", [f"All {len(selected)}"] if everything else [clean(i) for i in selected]))
    if skipped:
        named = []
        for name in skipped:
            reason = reasons.get(name)
            shown = f"{name} ({SKIP_REASONS.get(reason, reason)})" if reason else name
            named.append(clean(shown))
        rows.append(("Skipped", named))
    segments = options.get("segments") or []
    if len(segments) > 1:
        rows.append(("Nodes", [" → ".join(clean(item.get("node")) for item in segments)]))
    if options.get("variables"):
        rows.append(("Inputs", [clean(name) for name in options["variables"]]))
    return rows


def _display(value: Any) -> str:
    if value is None:
        return ""
    return clean(_compact(value) if isinstance(value, (dict, list)) else value)


def _apps(apps: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The app pages (RunApp.tsx), as their last published state."""

    shown = []
    for app in apps:
        definition = app.get("definition") or {}
        values = app.get("inputs") or {}
        inputs = [
            (clean(item.get("label") or item.get("name")), _display(values.get(item.get("name"))))
            for item in definition.get("inputs") or []
            if item.get("type") != "button"
        ]
        views = []
        for view in definition.get("views") or []:
            data = (app.get("views") or {}).get(view.get("name")) or {}
            rows = data.get("rows") or []
            columns = (
                data.get("columns")
                or view.get("columns")
                or [{"key": key, "label": key} for key in (rows[0] if rows else {})]
            )
            views.append(
                {
                    "label": clean(view.get("title") or view.get("label") or view.get("name")),
                    "description": clean(view.get("description")),
                    "type": view.get("type"),
                    "columns": [clean(item.get("label") or item.get("key")) for item in columns],
                    "rows": [
                        [_display(row.get(item.get("key"))) for item in columns]
                        for row in rows[:MAX_APP_ROWS]
                    ],
                    "total": data.get("total") if data.get("total") is not None else len(rows),
                    "items": [
                        (clean(item.get("label") or item.get("key")), _display(item.get("value")))
                        for item in data.get("items") or []
                    ],
                    "lines": [clean(line) for line in data.get("lines") or []],
                    "text": clean(data.get("text")),
                }
            )
        shown.append(
            {
                "title": clean(definition.get("title") or app.get("step")),
                "description": clean(definition.get("description")),
                "state": clean(app.get("state")),
                "inputs": inputs,
                "views": views,
            }
        )
    return shown


# ----------------------------------------------------------------------
# The diagram
# ----------------------------------------------------------------------


def _edge_point(center: Tuple[float, float], toward: Tuple[float, float]) -> Tuple[float, float]:
    """Where a line from a bubble's centre towards `toward` leaves the bubble."""

    delta_x, delta_y = toward[0] - center[0], toward[1] - center[1]
    if not delta_x and not delta_y:
        return center
    scale = min(
        BUBBLE_W / 2 / abs(delta_x) if delta_x else float("inf"),
        BUBBLE_H / 2 / abs(delta_y) if delta_y else float("inf"),
    )
    return center[0] + delta_x * scale, center[1] + delta_y * scale


def layout_diagram(report: Dict[str, Any], width: float) -> Dict[str, Any]:
    """Steps left to right on a gentle wave, wrapping back on new rows, as the page lays them."""

    steps = report["diagram_steps"]
    margin = _DIAGRAM_MARGIN
    columns = max(1, int((width - margin * 2 + 40) // (BUBBLE_W + 40)))
    rows = -(-len(steps) // columns)
    height = max(300.0, rows * 150 + 110.0)
    row_gap = min(150.0, (height - margin * 2 - BUBBLE_H) / max(1, rows))
    span = max(1, min(columns, len(steps)) - 1)
    usable = width - margin * 2 - BUBBLE_W

    nodes = list(dict.fromkeys(step["node"] for step in steps if step["node"]))
    bubbles = []
    centers = {}
    for index, step in enumerate(steps):
        row, column = index // columns, index % columns
        position = column if row % 2 == 0 else columns - 1 - column
        wave = 0 if index % 2 == 0 else 36
        x = margin + (usable * min(position, span) / span if span and columns > 1 else usable / 2)
        y = margin + 20 + row * row_gap + wave
        hue = None
        if len(nodes) > 1 and step["node"]:
            hue = (200 + nodes.index(step["node"]) * 67) % 360
        centers[step["name"]] = (x + BUBBLE_W / 2, y + BUBBLE_H / 2)
        bubbles.append({**step, "index": index + 1, "x": x, "y": y, "hue": hue})

    sequence = []
    for first, second in zip(steps, steps[1:]):
        a, b = centers[first["name"]], centers[second["name"]]
        sequence.append((_edge_point(a, b), _edge_point(b, a)))

    dependencies: List[Dict[str, Any]] = []
    for step in steps:
        for dependency in step["depends_on"]:
            if dependency["step"] not in centers:
                continue
            a, b = centers[dependency["step"]], centers[step["name"]]
            start, end = _edge_point(a, b), _edge_point(b, a)
            middle = (
                (start[0] + end[0]) / 2,
                (start[1] + end[1]) / 2 - 46 - len(dependencies) % 3 * 14,
            )
            dependencies.append(
                {
                    "start": start,
                    "middle": middle,
                    "end": end,
                    "label": f"outputs.{dependency['output']}",
                    "label_at": (middle[0], (start[1] + end[1]) / 4 + middle[1] / 2 - 4),
                }
            )
    return {
        "width": width,
        "height": height,
        "bubbles": bubbles,
        "sequence": sequence,
        "dependencies": dependencies,
        "nodes": [(node, (200 + index * 67) % 360) for index, node in enumerate(nodes)],
    }


def node_tint(hue: int, surface: str) -> str:
    red, green, blue = colorsys.hls_to_rgb(hue / 360, 0.5, 0.7)
    color = f"#{round(red * 255):02x}{round(green * 255):02x}{round(blue * 255):02x}"
    return mix(color, 12, surface)


# ----------------------------------------------------------------------
# The report
# ----------------------------------------------------------------------


def build_report(
    run: Dict[str, Any],
    plan: Sequence[Dict[str, Any]],
    steps: Sequence[Dict[str, Any]],
    events: Sequence[Dict[str, Any]],
    *,
    now: datetime,
    omitted: int = 0,
    console: str = "",
    console_cut: bool = False,
    artifacts: Sequence[Dict[str, Any]] = (),
    apps: Sequence[Dict[str, Any]] = (),
    zone: Optional[tzinfo] = None,
    zone_name: str = "UTC",
    theme: str = "dark",
    accent: Optional[str] = None,
    version: str = "",
) -> Dict[str, Any]:
    zone = zone or timezone.utc
    now_ms = now.timestamp() * 1000
    state = str(run.get("state") or "")
    options = run.get("options") or {}
    cards = _cards(run, plan, steps, events_by_step(events), artifacts, now_ms, zone)
    done = sum(1 for card in cards if card["status"] in ("completed", "skipped"))

    begun = _parse(run.get("started_at") or run.get("created_at"))
    finished = _parse(run.get("finished_at"))
    elapsed = (
        ((finished.timestamp() * 1000 if finished else now_ms) - begun.timestamp() * 1000)
        if begun
        else None
    )

    nodes = options.get("nodes") or []
    meta = [
        ("Executed by", clean(run.get("full_name") or run.get("username") or "Unknown")),
        ("Trigger", TRIGGER_LABELS.get(str(run.get("trigger")), clean(run.get("trigger")))),
        (
            "Nodes" if len(nodes) > 1 else "Node",
            ", ".join(nodes) if len(nodes) > 1 else clean(run.get("node")),
        ),
        ("Started", format_datetime(run.get("started_at") or run.get("created_at"), zone)),
        ("Duration", format_duration(elapsed)),
        ("Steps", f"{done} / {len(cards)}"),
    ]

    alert = None
    if state == "cancelled":
        stopped = (
            f" at {format_datetime(run['finished_at'], zone)}" if run.get("finished_at") else ""
        )
        alert = {
            "kind": "warning",
            "text": f"Stopped{stopped}. Steps after the interrupted one did not run.",
        }
    elif state == "failed":
        failure = next((item for item in events if item.get("type") == "execution.failed"), None)
        if failure:
            alert = {"kind": "danger", "text": event_text(failure)}

    # The diagram shows what was planned, and what ran where nothing was recorded.
    planned = [step for step in plan if _is_selected(step)] or [
        {"name": card["name"], "plugin": card["plugin"]} for card in cards
    ]
    status_of = {card["name"]: card["status"] for card in cards}
    diagram_steps = [
        {
            "name": clean(step["name"]),
            "plugin": clean(step.get("plugin")),
            "node": clean(step.get("node")),
            "status": status_of.get(clean(step["name"]), "pending"),
            "depends_on": step.get("depends_on") or [],
        }
        for step in planned
    ]

    stamp = now.astimezone(zone)
    generated = f"{stamp:%b} {stamp.day}, {stamp.year}, {format_time(now.isoformat(), zone)}"
    return {
        "title": clean(run.get("target")),
        "subtitle": (
            f"Run #{run['id']} · {'Plugin test run' if run.get('kind') == 'plugin' else 'Workflow'}"
            f" · {clean(run.get('execution_id'))}"
        ),
        "kind": "plugin" if run.get("kind") == "plugin" else "workflow",
        "state": state,
        "state_label": STATE_LABELS.get(state, state.capitalize()),
        "meta": meta,
        "options": _options(options),
        "progress": 100 if state == "completed" else round(done / len(cards) * 100) if cards else 0,
        "alert": alert,
        "cards": cards,
        "diagram_steps": diagram_steps,
        "log": [
            {
                "time": format_time(item.get("created_at"), zone),
                "step": clean(item.get("node_name")) if item.get("node_type") == "step" else "",
                "text": event_text(item),
                "tone": event_tone(item),
            }
            for item in events
        ],
        "omitted": omitted,
        "console": console,
        "console_cut": console_cut,
        "apps": _apps(apps),
        "footer": (
            f"Entropy{f' {version}' if version else ''}"
            f" · generated {generated} · times in {zone_name}"
        ),
        "colors": palette(theme, accent),
    }


def omitted_note(count: int) -> str:
    noun = "message is" if count == 1 else "messages are"
    return f"The first {count} {noun} left out; the last {MAX_EVENTS} follow."


CONSOLE_CUT_NOTE = f"The beginning is left out; the last {MAX_CONSOLE_CHARS} characters follow."
