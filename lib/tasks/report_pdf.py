"""
The task report as a PDF file: what the HTML report shows, laid out for pages.

Drawn with lib.pdf, so no browser is involved. Its built-in fonts cover Western European text;
other characters print as "?". Videos are named, as they cannot play on paper.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from lib.pdf.document import (
    CONTENT_W,
    MARGIN,
    Canvas,
    add_page_numbers,
    fit,
    text_width,
    wrap,
    wrap_proportional,
    write_pdf,
)
from lib.pdf.images import Image, load_image
from lib.tasks.markup import parse_blocks, parse_inline
from lib.tasks.report import (
    MAX_IMAGE_BYTES,
    MAX_TEXT_BYTES,
    MAX_VIDEO_BYTES,
    STATUS_LABELS,
    _attachment_path,
    _kind,
    _overdue,
    _sections,
    _size,
    _status,
    _when,
)
from lib.tasks.store import CLOSED, REOPENED

_COLORS = {
    "bg": "#ffffff",
    "text": "#1d2433",
    "muted": "#667085",
    "line": "#e4e7ec",
    "soft": "#f6f7f9",
    "accent": "#1f5fbf",
    "head": "#1f4e99",
    "todo": "#5b6b86",
    "in_progress": "#c27c0e",
    CLOSED: "#2e7d4f",
    REOPENED: "#b4363a",
}
_LINE = 1.4  # Line height, as a share of the font size.
_IMAGE_MAX_H = 380.0


def _font_of(run: Dict[str, Any], bold: bool) -> str:
    if run.get("code"):
        return "mono"
    if bold or run.get("bold"):
        return "bolditalic" if run.get("italic") else "bold"
    return "italic" if run.get("italic") else "regular"


class _Report:
    """One pass over the report's pages; the first finds where groups start for the contents."""

    def __init__(
        self,
        *,
        members: Dict[str, str],
        group_names: Dict[int, str],
        attachment_root: Path,
        images: Dict[int, Optional[Image]],
    ) -> None:
        self.canvas = Canvas(_COLORS)
        self.members = members
        self.group_names = group_names
        self.root = attachment_root
        self.images = images
        self.group_pages: List[int] = []

    # ------------------------------------------------------------------
    # Text
    # ------------------------------------------------------------------

    def lines(
        self,
        text: str,
        *,
        font: str = "regular",
        size: float = 9.5,
        color: Optional[str] = None,
        x: float = MARGIN,
        width: float = CONTENT_W,
        fill: Optional[str] = None,
    ) -> None:
        """Text flowing down the page, one line at a time."""

        canvas = self.canvas
        height = size * _LINE
        rows = (
            wrap(text, int(width / (size * 0.6)))
            if font == "mono"
            else wrap_proportional(text, font, size, width)
        )
        for row in rows:
            canvas.need(height)
            if fill:
                canvas.box(x - 6, canvas.y - 1, width + 12, height + 0.5, fill=fill)
            canvas.text(x, canvas.y, row, font, size, color)
            canvas.y += height

    def layout(
        self, text: str, *, size: float, width: float, bold: bool = False
    ) -> List[List[Tuple[str, str, float, float, Dict[str, Any]]]]:
        """Lines of (text, font, size, x offset, run): formatted words, wrapped to `width`."""

        lines: List[List[Tuple[str, str, float, float, Dict[str, Any]]]] = [[]]
        cursor = 0.0
        space = text_width(" ", "regular", size)
        for run in parse_inline(text):
            font = _font_of(run, bold)
            word_size = size - 1 if run.get("code") else size
            for line_index, source in enumerate(run["text"].split("\n")):
                if line_index:
                    lines.append([])
                    cursor = 0.0
                for word in source.split():
                    # A word longer than the line is cut to fit: paths often are.
                    pieces = (
                        wrap_proportional(word, font, word_size, width)
                        if text_width(word, font, word_size) > width
                        else [word]
                    )
                    for piece in pieces:
                        measured = text_width(piece, font, word_size)
                        if cursor and cursor + measured > width:
                            lines.append([])
                            cursor = 0.0
                        lines[-1].append((piece, font, word_size, cursor, run))
                        cursor += measured + space
        return lines

    def draw_line(
        self,
        line: Sequence[Tuple[str, str, float, float, Dict[str, Any]]],
        x: float,
        y: float,
        size: float,
        color: Optional[str] = None,
    ) -> None:
        canvas = self.canvas
        height = size * _LINE
        for piece, font, word_size, offset, run in line:
            measured = text_width(piece, font, word_size)
            if run.get("code"):
                canvas.box(
                    x + offset - 1.5,
                    y - 0.5,
                    measured + 3,
                    height - 1,
                    fill=_COLORS["soft"],
                    stroke=_COLORS["line"],
                    radius=2,
                    width=0.4,
                )
            canvas.text(x + offset, y + 0.6, piece, font, word_size, color or _COLORS["text"])
            if run.get("underline"):
                base = y + 0.6 + word_size * 0.98
                canvas.line(
                    x + offset,
                    base,
                    x + offset + measured,
                    base,
                    color or _COLORS["text"],
                    width=0.5,
                )
            if run.get("strike"):
                middle = y + 0.6 + word_size * 0.58
                canvas.line(
                    x + offset,
                    middle,
                    x + offset + measured,
                    middle,
                    color or _COLORS["text"],
                    width=0.6,
                )

    def formatted(
        self,
        text: str,
        *,
        size: float = 9.5,
        bold: bool = False,
        color: Optional[str] = None,
        x: float = MARGIN,
        width: float = CONTENT_W,
    ) -> None:
        """Formatted text flowing down the page."""

        height = size * _LINE
        for line in self.layout(text, size=size, width=width, bold=bold):
            self.canvas.need(height)
            self.draw_line(line, x, self.canvas.y, size, color)
            self.canvas.y += height

    def list_block(self, block: Dict[str, Any]) -> None:
        canvas = self.canvas
        size = 9.5
        height = size * _LINE
        number = block["start"]
        for item in block["items"]:
            x = MARGIN + 4 + item["indent"] * 14
            done = item["checked"] is True
            lines = self.layout(item["text"], size=size, width=MARGIN + CONTENT_W - x - 16)
            canvas.need(height)
            if item["checked"] is not None:
                canvas.box(x, canvas.y + 1.5, 9, 9, stroke=_COLORS["muted"], radius=1.5, width=0.7)
                if done:
                    canvas.box(x, canvas.y + 1.5, 9, 9, fill=_COLORS["accent"], radius=1.5)
                    canvas.line(x + 2, canvas.y + 6, x + 4, canvas.y + 8.2, "#ffffff", width=1.1)
                    canvas.line(
                        x + 4, canvas.y + 8.2, x + 7.2, canvas.y + 3.4, "#ffffff", width=1.1
                    )
            elif block["ordered"]:
                canvas.text(x, canvas.y + 0.6, f"{number}.", "regular", size, _COLORS["muted"])
            else:
                canvas.text(x + 2, canvas.y + 0.6, "•", "regular", size, _COLORS["muted"])
            for line in lines:
                canvas.need(height)
                self.draw_line(line, x + 16, canvas.y, size, _COLORS["muted"] if done else None)
                if done:
                    for piece, font, word_size, offset, _ in line:
                        middle = canvas.y + 0.6 + word_size * 0.58
                        end = x + 16 + offset + text_width(piece, font, word_size)
                        canvas.line(
                            x + 16 + offset, middle, end, middle, _COLORS["muted"], width=0.5
                        )
                canvas.y += height
            number += 1
        canvas.y += 4

    def table_block(self, block: Dict[str, Any]) -> None:
        canvas = self.canvas
        size = 8.5
        height = size * _LINE
        count = max(1, len(block["header"]))
        width = CONTENT_W / count
        pad = 5.0

        def row(cells: Sequence[str], *, head: bool) -> None:
            laid = [
                self.layout(cell, size=size, width=width - 2 * pad, bold=head) for cell in cells
            ]
            tall = max((len(lines) for lines in laid), default=1) * height + 8
            canvas.need(min(tall, 200.0))
            top = canvas.y
            for index, lines in enumerate(laid):
                x = MARGIN + index * width
                canvas.box(
                    x,
                    top,
                    width,
                    tall,
                    fill=_COLORS["soft"] if head else None,
                    stroke=_COLORS["line"],
                    width=0.5,
                )
                for number, line in enumerate(lines):
                    self.draw_line(line, x + pad, top + 4 + number * height, size)
            canvas.y = top + tall

        canvas.need(40)
        row(block["header"], head=True)
        for cells in block["rows"]:
            probe = max(
                (len(self.layout(cell, size=size, width=width - 2 * pad)) for cell in cells),
                default=1,
            )
            if probe * height + 8 > canvas.left:
                canvas.new_page()
                row(block["header"], head=True)
            row(cells, head=False)
        canvas.y += 8

    def blocks(self, text: str, attachments: List[Dict[str, Any]]) -> set:
        """The formatted description with attachments in place; returns the ids it showed."""

        by_id = {item["id"]: item for item in attachments}
        shown = set()
        canvas = self.canvas
        for block in parse_blocks(text):
            kind = block["type"]
            if kind == "heading":
                size = {1: 13.0, 2: 11.5, 3: 10.0, 4: 9.5, 5: 9.0}[block["level"]]
                canvas.need(size * _LINE + 22)
                canvas.y += 5
                color = _COLORS["muted"] if block["level"] in (3, 5) else None
                self.formatted(block["text"], size=size, bold=True, color=color)
                canvas.y += 2
            elif kind == "paragraph":
                self.formatted(block["text"])
                canvas.y += 4
            elif kind == "list":
                self.list_block(block)
            elif kind == "table":
                self.table_block(block)
            elif kind == "code":
                self.lines(
                    block["text"],
                    font="mono",
                    size=7.5,
                    x=MARGIN + 6,
                    width=CONTENT_W - 12,
                    fill=_COLORS["soft"],
                )
                canvas.y += 6
            else:
                attachment = by_id.get(block["id"])
                if attachment is None:
                    caption = block["caption"] or "attachment"
                    self.lines(f"[{caption} — removed]", color=_COLORS["muted"])
                else:
                    shown.add(attachment["id"])
                    self.attachment(attachment, caption=block["caption"])
                    canvas.y += 6
        return shown

    def label(self, text: str) -> None:
        """A small heading inside a task."""

        self.canvas.need(34)
        self.canvas.y += 8
        self.canvas.text(MARGIN, self.canvas.y, text.upper(), "bold", 7.5, _COLORS["muted"])
        self.canvas.y += 13

    def pill(self, x: float, y: float, status: str) -> float:
        """A task's status; returns its width."""

        label = _status(status)
        width = text_width(label, "bold", 7.5) + 12
        fill = _COLORS.get(status, _COLORS["todo"])
        self.canvas.box(x, y, width, 12.5, fill=fill, radius=6.2)
        self.canvas.text(x + 6, y + 2.8, label, "bold", 7.5, "#ffffff")
        return width

    def name_of(self, username: Optional[str]) -> str:
        return self.members.get((username or "").lower(), username or "")

    # ------------------------------------------------------------------
    # The start of the report
    # ------------------------------------------------------------------

    def cover(self, project: str, line: str) -> None:
        canvas = self.canvas
        canvas.text(MARGIN, canvas.y, "ENTROPY · TASK REPORT", "bold", 8, _COLORS["accent"])
        canvas.y += 15
        self.lines(project, font="bold", size=22)
        canvas.y += 3
        self.lines(line, color=_COLORS["muted"], size=9)
        canvas.y += 14

    def summary(self, tasks: Sequence[Dict[str, Any]]) -> None:
        canvas = self.canvas
        counts = {
            status: sum(1 for t in tasks if t["status"] == status) for status in STATUS_LABELS
        }
        overdue = sum(1 for task in tasks if _overdue(task))
        tiles: List[Tuple[str, int, str]] = [("Tasks", len(tasks), _COLORS["text"])]
        tiles += [(_status(s), counts[s], _COLORS.get(s, _COLORS["todo"])) for s in STATUS_LABELS]
        tiles.append(("Overdue", overdue, _COLORS[REOPENED]))

        gap = 8.0
        width = (CONTENT_W - gap * (len(tiles) - 1)) / len(tiles)
        for index, (label, value, color) in enumerate(tiles):
            x = MARGIN + index * (width + gap)
            canvas.box(
                x, canvas.y, width, 48, fill=_COLORS["soft"], stroke=_COLORS["line"], radius=7
            )
            canvas.text(x + 9, canvas.y + 8, str(value), "bold", 17, color)
            canvas.text(
                x + 9,
                canvas.y + 31,
                fit(label, "regular", 8, width - 14),
                "regular",
                8,
                _COLORS["muted"],
            )
        canvas.y += 58

        canvas.box(MARGIN, canvas.y, CONTENT_W, 7, fill=_COLORS["line"], radius=3.5)
        x = MARGIN
        for status in STATUS_LABELS:
            if counts[status]:
                share = CONTENT_W * counts[status] / (len(tasks) or 1)
                canvas.box(x, canvas.y, share, 7, fill=_COLORS.get(status, _COLORS["todo"]))
                x += share
        canvas.y += 22

    def contents(self, sections: Sequence[Tuple], pages: Sequence[int]) -> None:
        canvas = self.canvas
        canvas.need(40)
        self.lines("Contents", font="bold", size=13)
        canvas.y += 4
        for index, (name, _, _, items) in enumerate(sections):
            canvas.need(15)
            done = sum(1 for task in items if task["status"] == CLOSED)
            canvas.text(MARGIN, canvas.y, f"{index + 1}.", "regular", 9.5, _COLORS["muted"])
            canvas.text(
                MARGIN + 18,
                canvas.y,
                fit(name, "regular", 9.5, CONTENT_W - 170),
                "regular",
                9.5,
                _COLORS["accent"],
            )
            note = f"{done}/{len(items)} closed"
            canvas.text(MARGIN + CONTENT_W - 130, canvas.y, note, "regular", 8.5, _COLORS["muted"])
            if index < len(pages):
                page = f"page {pages[index]}"
                canvas.text(
                    MARGIN + CONTENT_W - text_width(page, "regular", 8.5),
                    canvas.y,
                    page,
                    "regular",
                    8.5,
                    _COLORS["muted"],
                )
            canvas.y += 15

    # ------------------------------------------------------------------
    # A group
    # ------------------------------------------------------------------

    def group(self, section: Tuple, attachments: Dict[int, List[Dict[str, Any]]]) -> None:
        name, kind, description, items = section
        canvas = self.canvas
        canvas.new_page()
        self.group_pages.append(len(canvas.pages))

        heading = wrap_proportional(name, "bold", 16, CONTENT_W - 80)
        for row in heading:
            canvas.text(MARGIN, canvas.y, row, "bold", 16)
            canvas.y += 21
        if kind:
            chip = kind.title()
            width = text_width(chip, "bold", 7.5) + 12
            x = MARGIN + min(text_width(heading[-1], "bold", 16) + 8, CONTENT_W - width)
            canvas.box(x, canvas.y - 19, width, 13, stroke=_COLORS["line"], radius=6.5)
            canvas.text(x + 6, canvas.y - 16, chip, "bold", 7.5, _COLORS["muted"])
        if description:
            self.lines(description, color=_COLORS["muted"], size=9)
        canvas.y += 6

        self.overview(items)
        for task in items:
            canvas.y += 14
            self.task(task, attachments.get(task["id"], []))

    def overview(self, items: Sequence[Dict[str, Any]]) -> None:
        canvas = self.canvas
        columns = (
            ("ID", 0.0),
            ("Task", 62.0),
            ("Status", 315.0),
            ("Assignee", 395.0),
            ("Due", 478.0),
        )

        def header() -> None:
            canvas.box(MARGIN, canvas.y, CONTENT_W, 18, fill=_COLORS["head"])
            for label, offset in columns:
                canvas.text(MARGIN + 6 + offset, canvas.y + 4.5, label, "bold", 8.5, "#ffffff")
            canvas.y += 18

        canvas.need(40)
        header()
        for task in items:
            rows = wrap_proportional(task["title"], "regular", 8.5, 245)
            height = max(len(rows) * 11.5, 12.5) + 8
            if height > canvas.left:
                canvas.new_page()
                header()
            y = canvas.y + 4
            canvas.text(
                MARGIN + 6,
                y,
                fit(task.get("key") or "", "mono", 8, 54),
                "mono",
                8,
                _COLORS["accent"],
            )
            for number, row in enumerate(rows):
                canvas.text(MARGIN + 68, y + number * 11.5, row, "regular", 8.5)
            self.pill(MARGIN + 321, y - 1, task["status"])
            assignee = self.name_of(task.get("assignee")) or "—"
            canvas.text(MARGIN + 401, y, fit(assignee, "regular", 8.5, 76), "regular", 8.5)
            canvas.text(
                MARGIN + 484,
                y,
                fit(task.get("due_date") or "—", "regular", 8.5, 46),
                "regular",
                8.5,
            )
            canvas.y += height
            canvas.line(MARGIN, canvas.y, MARGIN + CONTENT_W, canvas.y, _COLORS["line"], width=0.6)

    def task(self, task: Dict[str, Any], attachments: List[Dict[str, Any]]) -> None:
        canvas = self.canvas
        key = task.get("key") or ""
        key_w = text_width(key, "mono", 9.5) + 10 if key else 0.0
        title = wrap_proportional(task["title"], "bold", 12, CONTENT_W - key_w - 16)
        canvas.need(len(title) * 16 + 80)

        height = len(title) * 16 + 12
        canvas.box(
            MARGIN,
            canvas.y,
            CONTENT_W,
            height,
            fill=_COLORS["soft"],
            stroke=_COLORS["line"],
            radius=6,
        )
        canvas.text(MARGIN + 8, canvas.y + 7.5, key, "mono", 9.5, _COLORS["accent"])
        for number, row in enumerate(title):
            canvas.text(MARGIN + 8 + key_w, canvas.y + 6 + number * 16, row, "bold", 12)
        canvas.y += height + 8

        self.fields(task)

        self.label("Description")
        description = task.get("description") or ""
        shown = self.blocks(description, attachments)
        if not description.strip():
            self.lines("—", color=_COLORS["muted"])
        remaining = [item for item in attachments if item["id"] not in shown]

        if (task.get("remarks") or "").strip():
            self.label("Remarks")
            self.plain(task["remarks"])
        if task.get("comments"):
            self.label("Comments")
            for comment in task["comments"]:
                meta = f"{comment['author']} · {_when(comment['created_at'])}"
                self.lines(
                    meta,
                    size=7.5,
                    color=_COLORS["muted"],
                    x=MARGIN + 6,
                    width=CONTENT_W - 12,
                    fill=_COLORS["soft"],
                )
                self.lines(
                    comment["body"].strip(),
                    x=MARGIN + 6,
                    width=CONTENT_W - 12,
                    fill=_COLORS["soft"],
                )
                canvas.y += 5
        history = task.get("history") or []
        if len(history) > 1 or any(item.get("reason") for item in history):
            self.label("Status history")
            self.history(history)
        if remaining:
            self.label(f"Attachments ({len(remaining)})")
            for item in remaining:
                self.attachment(item)
                canvas.y += 7
        canvas.y += 6
        canvas.need(2)
        canvas.line(MARGIN, canvas.y, MARGIN + CONTENT_W, canvas.y, _COLORS["line"], width=0.75)

    def fields(self, task: Dict[str, Any]) -> None:
        canvas = self.canvas
        groups = ", ".join(
            self.group_names[g] for g in task.get("group_ids", []) if g in self.group_names
        )
        fields = [
            ("Status", None),
            ("Type", task.get("type", "issue").replace("_", " ").title()),
            ("Severity", (task.get("severity") or "medium").title()),
            ("Assignee", self.name_of(task.get("assignee")) or "Unassigned"),
            ("Due date", task.get("due_date") or "—"),
            ("External reference", task.get("external_ref") or "—"),
            ("Groups", groups or "—"),
            ("Created by", task.get("creator") or "—"),
            ("Created", _when(task.get("created_at"))),
            ("Last updated", _when(task.get("updated_at"))),
        ]
        width = (CONTENT_W - 2 * 12) / 3
        for start in range(0, len(fields), 3):
            row = fields[start : start + 3]
            wrapped = [
                wrap_proportional(str(value), "bold", 8.5, width) if value is not None else [""]
                for _, value in row
            ]
            height = 12 + max(len(item) for item in wrapped) * 11.5 + 4
            canvas.need(height)
            for index, ((label, value), rows) in enumerate(zip(row, wrapped)):
                x = MARGIN + index * (width + 12)
                canvas.text(x, canvas.y, label, "regular", 7.5, _COLORS["muted"])
                if value is None:
                    self.pill(x, canvas.y + 11, task["status"])
                for number, line in enumerate(rows):
                    canvas.text(x, canvas.y + 12 + number * 11.5, line, "bold", 8.5)
                if label == "Due date" and _overdue(task):
                    x_after = x + text_width(rows[0], "bold", 8.5) + 6
                    canvas.text(x_after, canvas.y + 12.5, "Overdue", "bold", 7.5, _COLORS[REOPENED])
            canvas.y += height

    def plain(self, text: str) -> None:
        for paragraph in text.strip().split("\n\n"):
            self.lines(paragraph)
            self.canvas.y += 4

    def history(self, history: Sequence[Dict[str, Any]]) -> None:
        canvas = self.canvas
        for item in history:
            moved = (
                f"{_status(item['from_status'])} → " if item.get("from_status") else "Created as "
            )
            text = f"{moved}{_status(item['to_status'])}"
            reason = (
                wrap_proportional(f"Reason: {item['reason']}", "regular", 8, 330)
                if item.get("reason")
                else []
            )
            height = 13 + len(reason) * 11 + 3
            canvas.need(height)
            canvas.text(
                MARGIN, canvas.y, _when(item["changed_at"]), "regular", 8.5, _COLORS["muted"]
            )
            canvas.text(MARGIN + 90, canvas.y, fit(text, "bold", 8.5, 340), "bold", 8.5)
            by = fit(item.get("changed_by") or "", "regular", 8.5, 90)
            canvas.text(
                MARGIN + CONTENT_W - text_width(by, "regular", 8.5),
                canvas.y,
                by,
                "regular",
                8.5,
                _COLORS["muted"],
            )
            for number, row in enumerate(reason):
                canvas.text(
                    MARGIN + 90, canvas.y + 13 + number * 11, row, "regular", 8, _COLORS["muted"]
                )
            canvas.y += height
            canvas.line(
                MARGIN,
                canvas.y - 1.5,
                MARGIN + CONTENT_W,
                canvas.y - 1.5,
                _COLORS["line"],
                width=0.4,
                dash="2 2",
            )

    # ------------------------------------------------------------------
    # Attachments
    # ------------------------------------------------------------------

    def _image(self, attachment: Dict[str, Any], path: Path) -> Optional[Image]:
        key = attachment["id"]
        if key not in self.images:
            self.images[key] = load_image(path.read_bytes())
        return self.images[key]

    def attachment(self, attachment: Dict[str, Any], caption: str = "") -> None:
        name = attachment["filename"]
        size = _size(attachment.get("size_bytes") or 0)
        title = f"{name} · {size}"
        if caption.strip() and caption.strip() != name:
            title = f"{caption.strip()} · {name}"

        path = _attachment_path(attachment, self.root)
        if path is None:
            link = attachment.get("url")
            self._named(title, f"Linked file — {link}" if link else "Linked file")
            return

        kind = _kind(attachment)
        length = path.stat().st_size
        if kind == "image":
            if length > MAX_IMAGE_BYTES:
                self._named(title, "Too large to include.")
                return
            image = self._image(attachment, path)
            if image is None:
                self._named(title, "This image format cannot go in a PDF; see the HTML report.")
                return
            self._draw_image(image, title)
        elif kind == "video":
            note = "Video — play it in the HTML report."
            self._named(title, note if length <= MAX_VIDEO_BYTES else "Too large to include.")
        elif kind == "text":
            raw = path.read_bytes()[:MAX_TEXT_BYTES].decode("utf-8", "replace")
            self.lines(title, font="bold", size=8.5)
            self.canvas.y += 2
            self.lines(
                raw.replace("\r\n", "\n").replace("\t", "    ").rstrip(),
                font="mono",
                size=7.5,
                x=MARGIN + 6,
                width=CONTENT_W - 12,
                fill=_COLORS["soft"],
            )
            if length > MAX_TEXT_BYTES:
                self.lines("… shortened", size=8, color=_COLORS["muted"])
        else:
            self._named(title, "Attached file.")

    def _named(self, title: str, note: str) -> None:
        self.lines(
            title, font="bold", size=8.5, x=MARGIN + 6, width=CONTENT_W - 12, fill=_COLORS["soft"]
        )
        self.lines(
            note,
            size=8,
            color=_COLORS["muted"],
            x=MARGIN + 6,
            width=CONTENT_W - 12,
            fill=_COLORS["soft"],
        )

    def _draw_image(self, image: Image, title: str) -> None:
        canvas = self.canvas
        # At most its natural size at 96 dots per inch, so small screenshots stay sharp.
        scale = min(CONTENT_W / image.width, _IMAGE_MAX_H / image.height, 0.75)
        width, height = image.width * scale, image.height * scale
        captions = wrap_proportional(title, "bold", 8, CONTENT_W)
        canvas.need(height + 8 + len(captions) * 11)
        canvas.box(
            MARGIN - 0.5, canvas.y - 0.5, width + 1, height + 1, stroke=_COLORS["line"], width=0.5
        )
        canvas.image(image, MARGIN, canvas.y, width, height)
        canvas.y += height + 4
        for row in captions:
            canvas.text(MARGIN, canvas.y, row, "bold", 8, _COLORS["muted"])
            canvas.y += 11


def build_pdf(
    *,
    project: str,
    scope: str,
    tasks: List[Dict[str, Any]],
    groups: Iterable[Dict[str, Any]],
    members: Iterable[Dict[str, Any]],
    attachments: Dict[int, List[Dict[str, Any]]],
    attachment_root: Path,
    generated_by: str,
) -> bytes:
    """The report as a PDF; takes what lib.tasks.report.build_report takes."""

    group_list = list(groups)
    group_names = {group["id"]: group["name"] for group in group_list}
    member_names = {m["username"].lower(): (m.get("full_name") or m["username"]) for m in members}
    sections = _sections(tasks, group_list, group_names)
    generated = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    plural = "s" if len(tasks) != 1 else ""
    line = f"{scope} · {len(tasks)} task{plural} · generated {generated} by {generated_by}"

    # Images are read once; the contents need the pages of the first pass.
    images: Dict[int, Optional[Image]] = {}
    pages: List[int] = []
    report = None
    for _ in range(2):
        report = _Report(
            members=member_names,
            group_names=group_names,
            attachment_root=attachment_root,
            images=images,
        )
        report.cover(project, line)
        report.summary(tasks)
        if len(sections) > 1:
            report.contents(sections, pages)
        if not sections:
            report.lines("No tasks to report.", color=_COLORS["muted"])
        for section in sections:
            report.group(section, attachments)
        pages = report.group_pages
        if len(sections) <= 1:
            break

    assert report is not None  # the loop always runs
    add_page_numbers(report.canvas, f"Entropy · Task report · {project}", _COLORS["muted"])
    return write_pdf(report.canvas.pages, f"Task report · {project}", report.canvas.images)
