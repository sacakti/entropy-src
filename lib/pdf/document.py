"""
PDF files with the standard library, so reports need no dependency.

Text uses PDF's built-in fonts, which cover Western European characters; others print as "?".
Draw on a Canvas with the origin at the top left, as on screen, then write_pdf its pages.
"""

from __future__ import annotations

import math
import textwrap
import zlib
from typing import Any, Dict, List, Optional, Tuple

PAGE_W, PAGE_H = 595.0, 842.0
MARGIN = 30.0
BOTTOM = 30.0
CONTENT_W = PAGE_W - 2 * MARGIN
MONO = 0.6  # Courier: every character is this share of the font size.
_FONTS = {"regular": "F1", "bold": "F2", "mono": "F3", "italic": "F4", "bolditalic": "F5"}

# Helvetica and Helvetica-Bold, characters 32 to 126, in thousandths of the font size.
_REGULAR_WIDTHS = (
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
)  # fmt: skip
_BOLD_WIDTHS = (
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,
    975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,
    333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611,
    611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584,
)  # fmt: skip


def _rgb(color: str) -> str:
    return " ".join(f"{int(color[index:index + 2], 16) / 255:.3f}" for index in (1, 3, 5))


def text_width(text: str, font: str, size: float) -> float:
    if font == "mono":
        return len(text) * size * MONO
    widths = _BOLD_WIDTHS if font.startswith("bold") else _REGULAR_WIDTHS
    units = sum(widths[ord(char) - 32] if 32 <= ord(char) < 127 else 556 for char in text)
    return units * size / 1000


def fit(text: str, font: str, size: float, width: float) -> str:
    """The text, cut with an ellipsis if it would not fit."""

    if text_width(text, font, size) <= width:
        return text
    while text and text_width(text + "…", font, size) > width:
        text = text[:-1]
    return text + "…"


def wrap(text: str, characters: int) -> List[str]:
    """Lines of at most `characters`, keeping the text's own line breaks."""

    lines: List[str] = []
    for line in text.split("\n"):
        lines.extend(textwrap.wrap(line, max(1, characters), drop_whitespace=False) or [""])
    return lines


def wrap_proportional(text: str, font: str, size: float, width: float) -> List[str]:
    """Lines that fit `width`, measured, breaking words only if one is too long by itself."""

    lines: List[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for word in paragraph.split(" "):
            candidate = f"{current} {word}" if current else word
            if text_width(candidate, font, size) <= width:
                current = candidate
                continue
            if current:
                lines.append(current)
            while text_width(word, font, size) > width and len(word) > 1:
                cut = len(word) - 1
                while cut > 1 and text_width(word[:cut], font, size) > width:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            current = word
        lines.append(current)
    return lines


class Canvas:
    """A4 pages drawn with the origin at the top left, as on screen."""

    def __init__(self, colors: Dict[str, str]) -> None:
        self.colors = colors
        self.pages: List[List[str]] = []
        self.images: List[Any] = []
        self.y = 0.0
        self.new_page()

    def new_page(self) -> None:
        self.pages.append([f"{_rgb(self.colors['bg'])} rg 0 0 {PAGE_W:.0f} {PAGE_H:.0f} re f"])
        self.y = MARGIN

    @property
    def left(self) -> float:
        """Room on this page for content, down to the footer."""

        return PAGE_H - BOTTOM - 14 - self.y

    def need(self, height: float) -> None:
        if height > self.left:
            self.new_page()

    def _rounded(self, x: float, y: float, w: float, h: float, r: float) -> str:
        r = min(r, w / 2, h / 2)
        top, bottom = PAGE_H - y, PAGE_H - y - h
        k = r * 0.5523
        return (
            f"{x + r:.2f} {top:.2f} m {x + w - r:.2f} {top:.2f} l "
            f"{x + w - r + k:.2f} {top:.2f} {x + w:.2f} {top - r + k:.2f}"
            f" {x + w:.2f} {top - r:.2f} c "
            f"{x + w:.2f} {bottom + r:.2f} l "
            f"{x + w:.2f} {bottom + r - k:.2f} {x + w - r + k:.2f} {bottom:.2f}"
            f" {x + w - r:.2f} {bottom:.2f} c "
            f"{x + r:.2f} {bottom:.2f} l "
            f"{x + r - k:.2f} {bottom:.2f} {x:.2f} {bottom + r - k:.2f} {x:.2f} {bottom + r:.2f} c "
            f"{x:.2f} {top - r:.2f} l "
            f"{x:.2f} {top - r + k:.2f} {x + r - k:.2f} {top:.2f} {x + r:.2f} {top:.2f} c h"
        )

    def box(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        fill: Optional[str] = None,
        stroke: Optional[str] = None,
        radius: float = 0.0,
        width: float = 0.75,
        dash: Optional[str] = None,
    ) -> None:
        if not fill and not stroke:
            return
        parts = ["q"]
        if fill:
            parts.append(f"{_rgb(fill)} rg")
        if stroke:
            parts.append(f"{_rgb(stroke)} RG {width} w")
        if dash:
            parts.append(f"[{dash}] 0 d")
        parts.append(self._rounded(x, y, w, h, radius))
        parts.append("B" if fill and stroke else "f" if fill else "S")
        parts.append("Q")
        self.pages[-1].append(" ".join(parts))

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        color: str,
        *,
        width: float = 1.0,
        dash: Optional[str] = None,
    ) -> None:
        pattern = f"[{dash}] 0 d " if dash else ""
        self.pages[-1].append(
            f"q {_rgb(color)} RG {width} w {pattern}{x1:.2f} {PAGE_H - y1:.2f} m"
            f" {x2:.2f} {PAGE_H - y2:.2f} l S Q"
        )

    def curve(
        self,
        start: Tuple[float, float],
        control: Tuple[float, float],
        end: Tuple[float, float],
        color: str,
        *,
        width: float = 1.0,
    ) -> None:
        """A quadratic curve, as PDF's cubic."""

        c1 = (
            start[0] + 2 / 3 * (control[0] - start[0]),
            start[1] + 2 / 3 * (control[1] - start[1]),
        )
        c2 = (end[0] + 2 / 3 * (control[0] - end[0]), end[1] + 2 / 3 * (control[1] - end[1]))
        self.pages[-1].append(
            f"q {_rgb(color)} RG {width} w {start[0]:.2f} {PAGE_H - start[1]:.2f} m"
            f" {c1[0]:.2f} {PAGE_H - c1[1]:.2f} {c2[0]:.2f} {PAGE_H - c2[1]:.2f}"
            f" {end[0]:.2f} {PAGE_H - end[1]:.2f} c S Q"
        )

    def arrow(
        self, tip: Tuple[float, float], base: Tuple[float, float], color: str, size: float
    ) -> None:
        angle = math.atan2(tip[1] - base[1], tip[0] - base[0])
        points = [
            tip,
            (tip[0] - size * math.cos(angle - 0.45), tip[1] - size * math.sin(angle - 0.45)),
            (tip[0] - size * math.cos(angle + 0.45), tip[1] - size * math.sin(angle + 0.45)),
        ]
        path = " ".join(
            f"{x:.2f} {PAGE_H - y:.2f} {'m' if index == 0 else 'l'}"
            for index, (x, y) in enumerate(points)
        )
        self.pages[-1].append(f"q {_rgb(color)} rg {path} h f Q")

    def circle(self, cx: float, cy: float, r: float, fill: str) -> None:
        self.box(cx - r, cy - r, 2 * r, 2 * r, fill=fill, radius=r)

    def text(
        self,
        x: float,
        y: float,
        text: str,
        font: str = "regular",
        size: float = 9.0,
        color: Optional[str] = None,
    ) -> None:
        """Text with its line box starting at y."""

        # A hex string needs no escaping; the fonts read it as Windows-1252.
        encoded = text.replace("→", "->").encode("cp1252", "replace").hex()
        baseline = PAGE_H - y - size * 0.92
        self.pages[-1].append(
            f"BT {_rgb(color or self.colors['text'])} rg /{_FONTS[font]} {size} Tf"
            f" {x:.2f} {baseline:.2f} Td <{encoded}> Tj ET"
        )

    def image(self, image: Any, x: float, y: float, width: float, height: float) -> None:
        """Draw an image from lib.pdf.images; the file holds it once however often it is drawn."""

        if image not in self.images:
            self.images.append(image)
        name = f"Im{self.images.index(image) + 1}"
        self.pages[-1].append(
            f"q {width:.2f} 0 0 {height:.2f} {x:.2f} {PAGE_H - y - height:.2f} cm /{name} Do Q"
        )


def _image_objects(objects: List[bytes], image: Any) -> int:
    """Add an image, and the mask of its transparency; returns its object number."""

    mask = ""
    if image.mask is not None:
        objects.append(
            f"<< /Type /XObject /Subtype /Image /Width {image.width} /Height {image.height}"
            " /ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode"
            f" /Length {len(image.mask)} >>\nstream\n".encode() + image.mask + b"\nendstream"
        )
        mask = f" /SMask {len(objects)} 0 R"
    objects.append(
        f"<< /Type /XObject /Subtype /Image /Width {image.width} /Height {image.height}"
        f" /ColorSpace {image.color_space} /BitsPerComponent {image.bits}{image.extra}{mask}"
        f" /Length {len(image.data)} >>\nstream\n".encode() + image.data + b"\nendstream"
    )
    return len(objects)


def write_pdf(
    pages: List[List[str]], title: str, images: Tuple[Any, ...] | List[Any] = ()
) -> bytes:
    fonts = ("Helvetica", "Helvetica-Bold", "Courier", "Helvetica-Oblique", "Helvetica-BoldOblique")
    objects: List[bytes] = [b"", b""]  # 1: catalog, 2: page tree
    font_ids = {}
    for index, name in enumerate(fonts, start=1):
        objects.append(
            f"<< /Type /Font /Subtype /Type1 /BaseFont /{name}"
            " /Encoding /WinAnsiEncoding >>".encode()
        )
        font_ids[f"F{index}"] = len(objects)
    font_list = " ".join(f"/{key} {value} 0 R" for key, value in font_ids.items())
    image_list = " ".join(
        f"/Im{index} {_image_objects(objects, image)} 0 R"
        for index, image in enumerate(images, start=1)
    )
    x_objects = f" /XObject << {image_list} >>" if image_list else ""
    objects.append(f"<< /Font << {font_list} >>{x_objects} >>".encode())
    resources = len(objects)

    kids = []
    for commands in pages:
        stream = zlib.compress("\n".join(commands).encode("ascii"))
        objects.append(
            f"<< /Length {len(stream)} /Filter /FlateDecode >>\nstream\n".encode()
            + stream
            + b"\nendstream"
        )
        content = len(objects)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W:.0f} {PAGE_H:.0f}]"
            f" /Resources {resources} 0 R /Contents {content} 0 R >>".encode()
        )
        kids.append(f"{len(objects)} 0 R")

    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode()
    objects.append(f"<< /Title <FEFF{title.encode('utf-16-be').hex()}> >>".encode())
    info = len(objects)

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    start = len(output)
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        output += f"{offset:010d} 00000 n \n".encode()
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info {info} 0 R >>\n"
        f"startxref\n{start}\n%%EOF\n".encode()
    )
    return bytes(output)


def add_page_numbers(canvas: Canvas, footer: str, color: str) -> None:
    """A footer on every page, with "Page x of y"; call it when all pages are drawn."""

    pages = canvas.pages
    for number, commands in enumerate(pages, start=1):
        canvas.pages = [commands]
        text = fit(footer, "regular", 7, CONTENT_W - 70)
        canvas.text(MARGIN, PAGE_H - BOTTOM, text, "regular", 7, color)
        label = f"Page {number} of {len(pages)}"
        x = PAGE_W - MARGIN - text_width(label, "regular", 7)
        canvas.text(x, PAGE_H - BOTTOM, label, "regular", 7, color)
    canvas.pages = pages
