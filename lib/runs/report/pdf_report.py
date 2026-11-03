"""
The report as a PDF that looks like the run page: all its tabs, one after the other.

Drawn with lib.pdf, whose built-in fonts cover Western European text; others print as "?".
"""

from __future__ import annotations

import math
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from lib.pdf.document import (
    CONTENT_W,
    MARGIN,
    MONO,
    PAGE_H,
    PAGE_W,
    add_page_numbers,
    fit,
    text_width,
    wrap,
    wrap_proportional,
    write_pdf,
)
from lib.pdf.document import Canvas as BaseCanvas

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


def _rgb(color: str) -> str:
    return " ".join(f"{int(color[index:index + 2], 16) / 255:.3f}" for index in (1, 3, 5))


# ----------------------------------------------------------------------
# Icons: SVG shapes as PDF paths
# ----------------------------------------------------------------------


def _arc(
    start: Tuple[float, float],
    radii: Tuple[float, float],
    large: bool,
    sweep: bool,
    end: Tuple[float, float],
) -> List[Tuple[float, ...]]:
    """An SVG circular or elliptical arc (without rotation) as Bezier curves."""

    rx, ry = abs(radii[0]), abs(radii[1])
    if not rx or not ry or start == end:
        return [end]
    half_x, half_y = (start[0] - end[0]) / 2, (start[1] - end[1]) / 2
    scale = (half_x / rx) ** 2 + (half_y / ry) ** 2
    if scale > 1:
        rx, ry = rx * math.sqrt(scale), ry * math.sqrt(scale)
    top = (rx * ry) ** 2 - (rx * half_y) ** 2 - (ry * half_x) ** 2
    bottom = (rx * half_y) ** 2 + (ry * half_x) ** 2
    root = math.sqrt(max(0.0, top / bottom)) if bottom else 0.0
    if large == sweep:
        root = -root
    center_x = root * rx * half_y / ry + (start[0] + end[0]) / 2
    center_y = -root * ry * half_x / rx + (start[1] + end[1]) / 2
    first = math.atan2((start[1] - center_y) / ry, (start[0] - center_x) / rx)
    last = math.atan2((end[1] - center_y) / ry, (end[0] - center_x) / rx)
    delta = last - first
    if sweep and delta < 0:
        delta += 2 * math.pi
    elif not sweep and delta > 0:
        delta -= 2 * math.pi
    pieces = max(1, math.ceil(abs(delta) / (math.pi / 2) - 1e-9))
    step = delta / pieces
    handle = 4 / 3 * math.tan(step / 4)
    curves: List[Tuple[float, ...]] = []
    angle = first
    for _ in range(pieces):
        following = angle + step
        cos_a, sin_a, cos_b, sin_b = (
            math.cos(angle),
            math.sin(angle),
            math.cos(following),
            math.sin(following),
        )
        curves.append(
            (
                center_x + rx * (cos_a - handle * sin_a),
                center_y + ry * (sin_a + handle * cos_a),
                center_x + rx * (cos_b + handle * sin_b),
                center_y + ry * (sin_b - handle * cos_b),
                center_x + rx * cos_b,
                center_y + ry * sin_b,
            )
        )
        angle = following
    return curves


_ARITY = {"m": 2, "l": 2, "h": 1, "v": 1, "a": 7, "z": 0}
_TOKEN = re.compile(r"[a-zA-Z]|-?\d*\.?\d+(?:e-?\d+)?")


def _path_ops(path: str, place: Callable[[float, float], Tuple[float, float]]) -> List[str]:
    """The commands lucide's paths use (M L H V A Z), as absolute PDF path operators."""

    tokens = _TOKEN.findall(path)
    ops: List[str] = []
    x = y = start_x = start_y = 0.0
    position = 0
    command = ""

    def point(px: float, py: float) -> str:
        placed = place(px, py)
        return f"{placed[0]:.3f} {placed[1]:.3f}"

    while position < len(tokens):
        if tokens[position].isalpha():
            command = tokens[position]
            position += 1
        lower = command.lower()
        count = _ARITY[lower]
        values = [float(item) for item in tokens[position : position + count]]
        position += count
        relative = command == lower
        if lower == "z":
            ops.append("h")
            x, y = start_x, start_y
        elif lower in ("m", "l"):
            x = values[0] + (x if relative else 0)
            y = values[1] + (y if relative else 0)
            ops.append(f"{point(x, y)} {'m' if lower == 'm' else 'l'}")
            if lower == "m":
                start_x, start_y = x, y
                command = "l" if relative else "L"
        elif lower == "h":
            x = values[0] + (x if relative else 0)
            ops.append(f"{point(x, y)} l")
        elif lower == "v":
            y = values[0] + (y if relative else 0)
            ops.append(f"{point(x, y)} l")
        else:
            end = (values[5] + (x if relative else 0), values[6] + (y if relative else 0))
            for curve in _arc(
                (x, y), (values[0], values[1]), bool(values[3]), bool(values[4]), end
            ):
                if len(curve) == 2:
                    ops.append(f"{point(curve[0], curve[1])} l")
                else:
                    ops.append(
                        f"{point(curve[0], curve[1])} {point(curve[2], curve[3])}"
                        f" {point(curve[4], curve[5])} c"
                    )
            x, y = end
    return ops


def _attributes(shape: str) -> Dict[str, str]:
    return dict(re.findall(r'([\w-]+)="([^"]*)"', shape))


def _shape_ops(
    tag: str, shape: str, place: Callable[[float, float], Tuple[float, float]]
) -> List[str]:
    attributes = _attributes(shape)

    def number(name: str) -> float:
        return float(attributes.get(name, "0"))

    if tag == "path":
        return _path_ops(attributes["d"], place)
    if tag == "line":
        return _path_ops(f"M{number('x1')} {number('y1')}L{number('x2')} {number('y2')}", place)
    if tag == "polyline":
        values = re.findall(r"-?\d*\.?\d+", attributes["points"])
        pairs = [f"{values[i]} {values[i + 1]}" for i in range(0, len(values), 2)]
        return _path_ops("M" + "L".join(pairs), place)
    if tag == "circle":
        cx, cy, r = number("cx"), number("cy"), number("r")
        return _path_ops(
            f"M{cx - r} {cy}A{r} {r} 0 1 1 {cx + r} {cy}A{r} {r} 0 1 1 {cx - r} {cy}Z", place
        )
    x, y, w, h, r = number("x"), number("y"), number("width"), number("height"), number("rx")
    if r:
        return _path_ops(
            f"M{x + r} {y}L{x + w - r} {y}A{r} {r} 0 0 1 {x + w} {y + r}L{x + w} {y + h - r}"
            f"A{r} {r} 0 0 1 {x + w - r} {y + h}L{x + r} {y + h}A{r} {r} 0 0 1 {x} {y + h - r}"
            f"L{x} {y + r}A{r} {r} 0 0 1 {x + r} {y}Z",
            place,
        )
    return _path_ops(f"M{x} {y}L{x + w} {y}L{x + w} {y + h}L{x} {y + h}Z", place)


# ----------------------------------------------------------------------
# Drawing
# ----------------------------------------------------------------------


class Canvas(BaseCanvas):
    """The shared canvas, and the run page's icons."""

    def icon(self, name: str, x: float, y: float, size: float, color: str) -> None:
        scale = size / 24

        def place(px: float, py: float) -> Tuple[float, float]:
            return x + px * scale, PAGE_H - y - py * scale

        ops: List[str] = []
        for tag, shape in re.findall(r"<(\w+)\s([^>]*)/>", ICONS[name]):
            ops.extend(_shape_ops(tag, shape, place))
            ops.append("S")
        self.pages[-1].append(
            f"q {_rgb(color)} RG {2 * scale:.3f} w 1 J 1 j " + " ".join(ops) + " Q"
        )


Row = Tuple[float, Callable[[float], None]]


def panel(
    canvas: Canvas,
    rows: Sequence[Row],
    *,
    fill: str,
    border: str,
    edge: Optional[str] = None,
    pad: float = 8.0,
) -> None:
    """Rows in a rounded box that continues on the next page when it fills up."""

    index = 0
    while index < len(rows):
        canvas.need(min(rows[index][0] + 2 * pad, 200.0))
        room = canvas.left - 2 * pad
        chosen = 0
        height = 0.0
        for row_height, _ in rows[index:]:
            if height + row_height > room and chosen:
                break
            height += row_height
            chosen += 1
        top = canvas.y
        canvas.box(MARGIN, top, CONTENT_W, height + 2 * pad, fill=fill, stroke=border, radius=8)
        if edge:
            canvas.box(MARGIN, top + 3, 2.4, height + 2 * pad - 6, fill=edge, radius=1.2)
        y = top + pad
        for row_height, draw in rows[index : index + chosen]:
            draw(y)
            y += row_height
        canvas.y = top + height + 2 * pad
        index += chosen
        if index < len(rows):
            canvas.new_page()


def _tab_title(canvas: Canvas, icon: str, label: str) -> None:
    """The tab this part of the page shows, as the page's active tab looks."""

    colors = canvas.colors
    canvas.need(60)
    width = text_width(label, "bold", 9.5) + 32
    canvas.box(MARGIN, canvas.y, width, 21, fill=colors["accent"], radius=6)
    canvas.icon(icon, MARGIN + 8, canvas.y + 5, 11, colors["accent_text"])
    canvas.text(MARGIN + 23, canvas.y + 5.5, label, "bold", 9.5, colors["accent_text"])
    canvas.y += 29


def _note(canvas: Canvas, text: str) -> None:
    canvas.need(14)
    canvas.text(MARGIN, canvas.y, text, "regular", 8, canvas.colors["muted"])
    canvas.y += 13


def _line_rows(
    canvas: Canvas,
    items: Sequence[Dict[str, Any]],
    *,
    x: float,
    width: float,
    with_step: bool = False,
    size: float = 7.5,
) -> List[Row]:
    """Log lines as on the page: time, optional step, then the text, tinted by tone."""

    colors = canvas.colors
    time_w = 12 * size * MONO + 6
    step_w = 92.0 if with_step else 0.0
    characters = int((width - time_w - step_w - 8) / (size * MONO))
    line_h = size * 1.42
    rows: List[Row] = []

    tones = {
        "error": (colors["danger"], colors["danger_soft"]),
        "warning": (colors["warning"], colors["warning_soft"]),
        "success": (colors["success"], None),
        "meta": (colors["muted"], None),
        "debug": (colors["muted"], None),
    }
    for item in items:
        color, strip = tones.get(item["tone"], (colors["text"], None))
        for number, line in enumerate(wrap(item["text"], characters)):

            def draw(
                y: float,
                line: str = line,
                first: bool = number == 0,
                color: str = color,
                strip: Optional[str] = strip,
                item: Dict[str, Any] = item,
            ) -> None:
                if strip:
                    canvas.box(x, y - 0.5, width, line_h, fill=strip)
                if first:
                    canvas.text(x + 4, y + 0.6, item["time"], "mono", size, colors["subtle"])
                    if with_step and item.get("step"):
                        canvas.text(
                            x + 4 + time_w,
                            y + 0.6,
                            fit(item["step"], "mono", size, step_w - 6),
                            "mono",
                            size,
                            colors["accent"],
                        )
                canvas.text(x + 4 + time_w + step_w, y + 0.6, line, "mono", size, color)

            rows.append((line_h, draw))
    return rows


def _mono_rows(
    canvas: Canvas,
    text: str,
    *,
    x: float,
    width: float,
    size: float = 7.5,
    color: Optional[str] = None,
    fill: Optional[str] = None,
) -> List[Row]:
    line_h = size * 1.42
    rows: List[Row] = []
    for line in wrap(text, int((width - 12) / (size * MONO))):

        def draw(y: float, line: str = line) -> None:
            if fill:
                canvas.box(x, y - 0.5, width, line_h + 0.5, fill=fill)
            canvas.text(x + 6, y + 0.6, line, "mono", size, color or canvas.colors["text"])

        rows.append((line_h, draw))
    return rows


def _gap(height: float) -> Row:
    return height, lambda y: None


# ----------------------------------------------------------------------
# The sections
# ----------------------------------------------------------------------


def _header(canvas: Canvas, report: Dict[str, Any]) -> None:
    colors = canvas.colors
    state = status_color(report["state"])
    icon = report["state"] if report["state"] in ICONS else "pending"
    top = canvas.y

    canvas.box(
        MARGIN, top, 30, 30, fill=colors["accent_soft"], stroke=colors["accent_border"], radius=8
    )
    canvas.icon(report["kind"], MARGIN + 7.5, top + 7.5, 15, colors["accent"])

    label_w = text_width(report["state_label"], "bold", 9) + 28
    soft = colors.get(f"{state}_soft", colors["surface"])
    edge = colors.get(f"{state}_border", colors["line"])
    canvas.box(PAGE_W - MARGIN - label_w, top + 5, label_w, 20, fill=soft, stroke=edge, radius=10)
    canvas.icon(icon, PAGE_W - MARGIN - label_w + 7, top + 9.5, 11, colors[state])
    canvas.text(
        PAGE_W - MARGIN - label_w + 21, top + 10, report["state_label"], "bold", 9, colors[state]
    )

    text_x = MARGIN + 40
    title_w = CONTENT_W - 40 - label_w - 10
    canvas.y = top
    for line in wrap_proportional(report["title"], "bold", 15, title_w)[:2]:
        canvas.text(text_x, canvas.y, line, "bold", 15)
        canvas.y += 18
    for line in wrap_proportional(report["subtitle"], "regular", 9, title_w)[:2]:
        canvas.text(text_x, canvas.y, line, "regular", 9, colors["muted"])
        canvas.y += 12
    canvas.y = max(canvas.y, top + 32) + 8

    # Six cards as on the page, three to a row so long values have room.
    width = (CONTENT_W - 2 * 8) / 3
    for index, (label, value) in enumerate(report["meta"]):
        x = MARGIN + (index % 3) * (width + 8)
        y = canvas.y + (index // 3) * 44
        canvas.box(x, y, width, 37, fill=colors["surface"], stroke=colors["line"], radius=7)
        canvas.text(x + 9, y + 7, label.upper(), "bold", 7, colors["subtle"])
        canvas.text(x + 9, y + 18, fit(value, "bold", 10, width - 18), "bold", 10)
    canvas.y += (len(report["meta"]) + 2) // 3 * 44 + 2

    for label, items in report["options"]:
        lines = wrap_proportional(", ".join(items), "regular", 8, CONTENT_W - 60)
        canvas.need(len(lines) * 11 + 2)
        canvas.text(MARGIN, canvas.y, label, "bold", 8, colors["subtle"])
        for line in lines:
            canvas.text(MARGIN + 60, canvas.y, line, "regular", 8, colors["muted"])
            canvas.y += 11
    canvas.y += 5

    bar = colors["accent"] if state in ("accent", "muted") else colors[state]
    canvas.box(MARGIN, canvas.y, CONTENT_W, 5, fill=colors["surface"], radius=2.5)
    if report["progress"]:
        canvas.box(MARGIN, canvas.y, CONTENT_W * report["progress"] / 100, 5, fill=bar, radius=2.5)
    canvas.y += 14

    if report["alert"]:
        kind = report["alert"]["kind"]
        lines = wrap_proportional(report["alert"]["text"], "regular", 9.5, CONTENT_W - 44)[:12]
        height = len(lines) * 13 + 16
        canvas.need(height)
        canvas.box(
            MARGIN,
            canvas.y,
            CONTENT_W,
            height,
            fill=colors[f"{kind}_soft"],
            stroke=colors[f"{kind}_border"],
            radius=8,
        )
        canvas.icon(
            "alert" if kind == "danger" else "cancelled",
            MARGIN + 11,
            canvas.y + 8,
            13,
            colors[kind],
        )
        for number, line in enumerate(lines):
            canvas.text(MARGIN + 31, canvas.y + 9 + number * 13, line, "regular", 9.5, colors[kind])
        canvas.y += height + 12
    canvas.y += 6


def _card_rows(canvas: Canvas, card: Dict[str, Any]) -> List[Row]:
    colors = canvas.colors
    left = MARGIN + 11
    width = CONTENT_W - 22
    status = card["status"]
    color = colors["subtle"] if status in ("pending", "skipped") else colors[status_color(status)]

    def head(y: float) -> None:
        canvas.box(left, y + 2, 18, 18, fill=colors["bg"], stroke=colors["line"], radius=5)
        number = str(card["index"])
        canvas.text(
            left + 9 - text_width(number, "bold", 8.5) / 2,
            y + 7,
            number,
            "bold",
            8.5,
            colors["muted"],
        )
        canvas.icon(status if status in ICONS else "pending", left + 25, y + 4, 14, color)
        name_w = width - 44 - 74
        canvas.text(left + 45, y, fit(card["name"], "bold", 10.5, name_w), "bold", 10.5)
        plugin = card["plugin"] + (f" · on {card['node']}" if card["node"] else "")
        canvas.text(
            left + 45, y + 13.5, fit(plugin, "mono", 7.5, name_w), "mono", 7.5, colors["subtle"]
        )
        right = left + width
        canvas.text(
            right - text_width(card["label"], "bold", 9),
            y + 1,
            card["label"],
            "bold",
            9,
            colors["muted"],
        )
        if card["duration"]:
            canvas.text(
                right - text_width(card["duration"], "regular", 8),
                y + 13,
                card["duration"],
                "regular",
                8,
                colors["subtle"],
            )

    rows: List[Row] = [(27.0, head)]
    if card["tags"]:

        def tags(y: float) -> None:
            canvas.text(
                left + 45,
                y,
                fit("  ·  ".join(card["tags"]), "regular", 7.5, width - 45),
                "regular",
                7.5,
                colors["muted"],
            )

        rows.append((12.0, tags))
    for artifact in card["artifacts"]:

        def line(y: float, artifact: Dict[str, str] = artifact) -> None:
            canvas.icon("package", left, y, 9, colors["muted"])
            canvas.text(
                left + 13,
                y + 0.5,
                fit(artifact["name"], "regular", 8, width - 120),
                "regular",
                8,
                colors["muted"],
            )
            canvas.text(
                left + width - 95, y + 0.5, artifact["size"], "regular", 7.5, colors["subtle"]
            )

        rows.append((12.0, line))
    if card["artifacts"]:
        rows.append(_gap(3))
    rows.extend(_line_rows(canvas, card["lines"], x=left, width=width))
    if not card["lines"]:

        def nothing(y: float) -> None:
            canvas.text(left, y, "Nothing reported.", "regular", 8, colors["muted"])

        rows.append((12.0, nothing))
    if card["result"]:
        rows.append(_gap(6))
        rows.extend(
            _mono_rows(canvas, card["result"], x=left, width=width, size=7, fill=colors["bg"])
        )
    return rows


def _progress(canvas: Canvas, report: Dict[str, Any]) -> None:
    colors = canvas.colors
    _tab_title(canvas, "progress", "Progress")
    if not report["cards"]:
        _note(canvas, "No steps were reported.")
    for card in report["cards"]:
        status = card["status"]
        edge = colors["line"] if status == "pending" else colors[status_color(status)]
        panel(
            canvas,
            _card_rows(canvas, card),
            fill=colors["surface"],
            border=colors["line"],
            edge=edge,
        )
        canvas.y += 7
    canvas.y += 8


def _diagram(canvas: Canvas, report: Dict[str, Any]) -> None:
    colors = canvas.colors
    layout = layout_diagram(report, 760)
    scale = CONTENT_W / layout["width"]
    height = layout["height"] * scale
    canvas.need(height + 50)
    _tab_title(canvas, "diagram", "Diagram")
    if not layout["bubbles"]:
        _note(canvas, "No steps were planned.")
        return

    legend_y = canvas.y
    canvas.line(
        MARGIN, legend_y + 5, MARGIN + 18, legend_y + 5, colors["subtle"], width=1.2, dash="4 3"
    )
    canvas.text(MARGIN + 22, legend_y, "runs after", "regular", 8, colors["muted"])
    canvas.line(MARGIN + 72, legend_y + 5, MARGIN + 90, legend_y + 5, colors["accent"], width=1.2)
    canvas.text(MARGIN + 94, legend_y, "uses output of", "regular", 8, colors["muted"])
    x = MARGIN + 168
    for node, _ in layout["nodes"] if len(layout["nodes"]) > 1 else ():
        canvas.text(x, legend_y, node, "bold", 8, colors["muted"])
        x += text_width(node, "bold", 8) + 12
    canvas.y += 14

    top = canvas.y
    canvas.box(MARGIN, top, CONTENT_W, height, fill=colors["bg"], stroke=colors["line"], radius=8)

    def at(point: Tuple[float, float]) -> Tuple[float, float]:
        return MARGIN + point[0] * scale, top + point[1] * scale

    for start, end in layout["sequence"]:
        a, b = at(start), at(end)
        canvas.line(a[0], a[1], b[0], b[1], colors["subtle"], width=1.3, dash="4 3")
        canvas.arrow(b, a, colors["subtle"], 6)
    for item in layout["dependencies"]:
        a, control, b = at(item["start"]), at(item["middle"]), at(item["end"])
        canvas.curve(a, control, b, colors["accent"], width=1.3)
        canvas.arrow(b, control, colors["accent"], 6)
        label_x, label_y = at(item["label_at"])
        canvas.text(
            label_x - text_width(item["label"], "regular", 7.5) / 2,
            label_y - 6,
            item["label"],
            "regular",
            7.5,
            colors["accent"],
        )
    for bubble in layout["bubbles"]:
        status = bubble["status"]
        stroke = colors["line"] if status == "pending" else colors[status_color(status)]
        fill = (
            node_tint(bubble["hue"], colors["surface"])
            if bubble["hue"] is not None
            else colors["surface"]
        )
        x, y = at((bubble["x"], bubble["y"]))
        w, h = BUBBLE_W * scale, BUBBLE_H * scale
        canvas.box(
            x,
            y,
            w,
            h,
            fill=fill,
            stroke=stroke,
            radius=h / 2,
            width=1.4,
            dash="4 3" if status in ("cancelled", "skipped") else None,
        )
        center_y = y + h / 2
        solved = status in ("completed", "failed")
        canvas.circle(x + 13, center_y, 7.5, stroke if solved else colors["bg"])
        number = str(bubble["index"])
        canvas.text(
            x + 13 - text_width(number, "bold", 8) / 2,
            center_y - 4,
            number,
            "bold",
            8,
            colors["bg"] if solved else colors["muted"],
        )
        room = w - 25 - h / 3
        canvas.text(x + 25, y + 11, fit(bubble["name"], "bold", 9, room), "bold", 9)
        small = bubble["plugin"] + (
            f" · {bubble['node']}" if len(layout["nodes"]) > 1 and bubble["node"] else ""
        )
        canvas.text(
            x + 25, y + 24, fit(small, "regular", 7.5, room), "regular", 7.5, colors["subtle"]
        )
    canvas.y = top + height + 18


def _log(canvas: Canvas, report: Dict[str, Any]) -> None:
    colors = canvas.colors
    _tab_title(canvas, "log", "Live log · Steps")
    if report["omitted"]:
        _note(canvas, omitted_note(report["omitted"]))
    rows = _line_rows(canvas, report["log"], x=MARGIN + 6, width=CONTENT_W - 12, with_step=True)
    if rows:
        panel(canvas, rows, fill=colors["bg"], border=colors["line"])
    else:
        _note(canvas, "No events.")
    canvas.y += 16

    _tab_title(canvas, "console", "Live log · Console")
    if report["console_cut"]:
        _note(canvas, CONSOLE_CUT_NOTE)
    if report["console"]:
        rows = _mono_rows(canvas, report["console"], x=MARGIN + 6, width=CONTENT_W - 12)
        panel(canvas, rows, fill=colors["bg"], border=colors["line"])
    else:
        _note(canvas, "The worker wrote no console output.")
    canvas.y += 16


def _pair_rows(canvas: Canvas, items: Sequence[Tuple[str, str]]) -> List[Row]:
    colors = canvas.colors
    rows: List[Row] = []
    for label, value in items:
        lines = wrap_proportional(value, "regular", 8.5, CONTENT_W - 170) or [""]
        for number, line in enumerate(lines):

            def draw(
                y: float, line: str = line, first: bool = number == 0, label: str = label
            ) -> None:
                if first:
                    canvas.text(
                        MARGIN + 10,
                        y,
                        fit(label, "regular", 8.5, 140),
                        "regular",
                        8.5,
                        colors["subtle"],
                    )
                canvas.text(MARGIN + 155, y, line, "regular", 8.5)

            rows.append((12.0, draw))
    return rows


def _heading_row(canvas: Canvas, text: str, *, font: str = "bold", size: float = 9.5) -> Row:
    def draw(y: float) -> None:
        canvas.text(MARGIN + 10, y, fit(text, font, size, CONTENT_W - 20), font, size)

    return size * 1.6, draw


def _table_rows(canvas: Canvas, view: Dict[str, Any]) -> List[Row]:
    colors = canvas.colors
    columns = view["columns"][:8] or [""]
    width = (CONTENT_W - 20) / len(columns)

    def cells(values: Sequence[str], font: str, color: str) -> Callable[[float], None]:
        def draw(y: float) -> None:
            for index, value in enumerate(values[: len(columns)]):
                canvas.text(
                    MARGIN + 10 + index * width,
                    y,
                    fit(value, font, 7.5, width - 6),
                    font,
                    7.5,
                    color,
                )

        return draw

    rows: List[Row] = [(12.0, cells(columns, "bold", colors["subtle"]))]
    rows.extend((11.0, cells(row, "regular", colors["text"])) for row in view["rows"])
    return rows


def _apps(canvas: Canvas, report: Dict[str, Any]) -> None:
    colors = canvas.colors
    if not report["apps"]:
        return
    _tab_title(canvas, "app", "App")
    for app in report["apps"]:
        rows: List[Row] = [_heading_row(canvas, app["title"], size=11)]
        if app["description"]:
            rows.extend(
                _mono_rows(
                    canvas,
                    app["description"],
                    x=MARGIN + 4,
                    width=CONTENT_W - 8,
                    color=colors["muted"],
                )
            )
        rows.extend(_pair_rows(canvas, app["inputs"]))
        for view in app["views"]:
            rows.append(_gap(6))
            rows.append(_heading_row(canvas, view["label"]))
            if view["description"]:
                rows.extend(
                    _mono_rows(
                        canvas,
                        view["description"],
                        x=MARGIN + 4,
                        width=CONTENT_W - 8,
                        color=colors["muted"],
                    )
                )
            if view["type"] == "table":
                rows.extend(_table_rows(canvas, view))
                more = view["total"] - len(view["rows"])
                if more > 0:
                    rows.append(
                        _heading_row(
                            canvas,
                            f"Showing {len(view['rows'])} of {view['total']}.",
                            font="regular",
                            size=8,
                        )
                    )
            elif view["type"] in ("stats", "keyvalue"):
                rows.extend(_pair_rows(canvas, view["items"]))
            elif view["type"] == "log":
                rows.extend(
                    _mono_rows(canvas, "\n".join(view["lines"]), x=MARGIN + 4, width=CONTENT_W - 8)
                )
            else:
                rows.extend(_mono_rows(canvas, view["text"], x=MARGIN + 4, width=CONTENT_W - 8))
        panel(canvas, rows, fill=colors["surface"], border=colors["line"])
        canvas.y += 10


# ----------------------------------------------------------------------
# The file
# ----------------------------------------------------------------------


def render_pdf(report: Dict[str, Any]) -> bytes:
    canvas = Canvas(report["colors"])
    _header(canvas, report)
    _progress(canvas, report)
    _diagram(canvas, report)
    _log(canvas, report)
    _apps(canvas, report)

    add_page_numbers(canvas, report["footer"], report["colors"]["subtle"])
    return write_pdf(canvas.pages, f"{report['title']} · Run report")
