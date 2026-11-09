"""
Word documents (.docx) written and read with the standard library only.

A .docx file is a zip of XML parts (Office Open XML). `write_docx` makes one from a
description (lib/tasks/markup.py): headings 1-5, paragraphs with bold, italic, underline,
strikethrough and code, bulleted and numbered lists, checklists, tables, code blocks and
images. `read_docx` turns a document back into a description, with its images, so Word
documents can be imported; what a description cannot hold (colours, fonts, page layout)
is left out.
"""

from __future__ import annotations

import io
import posixpath
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Sequence, Tuple
from xml.etree import ElementTree
from xml.sax.saxutils import escape

from lib.pdf.images import load_image
from lib.tasks.markup import parse_blocks, parse_inline

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
REL_IMAGE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
_NS = f'xmlns:w="{W}" xmlns:r="{R}"'

# Reading: a document larger than this, unpacked, is refused (a zip can hide a lot).
MAX_UNPACKED_BYTES = 200 * 1024 * 1024
MAX_IMAGES = 100
# Writing: images are at most this wide on the page (6 inches, in EMU).
_MAX_IMAGE_EMU = 6 * 914400
_EMU_PER_PIXEL = 9525
_CODE_FONT = "Consolas"
_IMAGE_TYPES = {"png": "image/png", "jpeg": "image/jpeg", "jpg": "image/jpeg", "gif": "image/gif"}


class DocxError(ValueError):
    """A file that is not a Word document this can read."""


# ----------------------------------------------------------------------
# Writing
# ----------------------------------------------------------------------


@dataclass
class DocxImage:
    """An image to place: its bytes and the name it came with."""

    data: bytes
    filename: str


@dataclass
class _Writer:
    images: Callable[[int], Optional[DocxImage]]
    body: List[str] = field(default_factory=list)
    media: List[Tuple[str, bytes]] = field(default_factory=list)
    relationships: List[Tuple[str, str, str]] = field(default_factory=list)
    # One numbering instance per numbered list, so each starts again at its own number.
    numbered: List[int] = field(default_factory=list)

    # Runs and paragraphs ----------------------------------------------

    def runs(self, text: str, *, bold: bool = False) -> str:
        parts = []
        for run in parse_inline(text):
            properties = []
            if run.get("code"):
                properties.append(
                    f'<w:rFonts w:ascii="{_CODE_FONT}" w:hAnsi="{_CODE_FONT}" w:cs="{_CODE_FONT}"/>'
                    '<w:shd w:val="clear" w:color="auto" w:fill="F2F4F7"/>'
                )
            if bold or run.get("bold"):
                properties.append("<w:b/>")
            if run.get("italic"):
                properties.append("<w:i/>")
            if run.get("strike"):
                properties.append("<w:strike/>")
            if run.get("underline"):
                properties.append('<w:u w:val="single"/>')
            style = f"<w:rPr>{''.join(properties)}</w:rPr>" if properties else ""
            lines = run["text"].split("\n")
            for index, line in enumerate(lines):
                if index:
                    parts.append(f"<w:r>{style}<w:br/></w:r>")
                if line:
                    parts.append(
                        f'<w:r>{style}<w:t xml:space="preserve">{escape(line)}</w:t></w:r>'
                    )
        return "".join(parts)

    def paragraph(self, content: str, *, style: str = "", extra: str = "") -> None:
        properties = f'<w:pStyle w:val="{style}"/>' if style else ""
        self.body.append(f"<w:p><w:pPr>{properties}{extra}</w:pPr>{content}</w:p>")

    # Blocks ------------------------------------------------------------

    def list_block(self, block: Dict) -> None:
        if block["ordered"]:
            # Numbering ids 1 and 2 are the shared bullet and checklist definitions.
            number_id = 3 + len(self.numbered)
            self.numbered.append(int(block["start"]))
        for item in block["items"]:
            level = min(int(item["indent"]), 8)
            text = self.runs(item["text"])
            if item["checked"] is not None:
                box = "☑ " if item["checked"] else "☐ "
                self.paragraph(
                    f'<w:r><w:t xml:space="preserve">{box}</w:t></w:r>{text}',
                    style="ListParagraph",
                    extra=f'<w:ind w:left="{360 + level * 360}" w:hanging="0"/>',
                )
                continue
            numbering = number_id if block["ordered"] else 1
            self.paragraph(
                text,
                style="ListParagraph",
                extra=f'<w:numPr><w:ilvl w:val="{level}"/><w:numId w:val="{numbering}"/></w:numPr>',
            )

    def facts(self, rows: Sequence[Tuple[str, str]]) -> None:
        """Label and value in two columns, labels shaded."""

        cells = "".join(
            "<w:tr>"
            '<w:tc><w:tcPr><w:tcW w:w="2200" w:type="dxa"/>'
            '<w:shd w:val="clear" w:color="auto" w:fill="F2F4F7"/></w:tcPr>'
            f'<w:p><w:r><w:rPr><w:b/></w:rPr><w:t xml:space="preserve">{escape(label)}</w:t>'
            "</w:r></w:p></w:tc>"
            '<w:tc><w:tcPr><w:tcW w:w="6800" w:type="dxa"/></w:tcPr>'
            f'<w:p><w:r><w:t xml:space="preserve">{escape(value)}</w:t></w:r></w:p></w:tc>'
            "</w:tr>"
            for label, value in rows
        )
        # Its own style, so importing an exported document leaves it out of the text.
        self.body.append(
            '<w:tbl><w:tblPr><w:tblStyle w:val="EntropyFacts"/><w:tblW w:w="0" w:type="auto"/>'
            "</w:tblPr>"
            f'<w:tblGrid><w:gridCol w:w="2200"/><w:gridCol w:w="6800"/></w:tblGrid>{cells}</w:tbl>'
        )
        self.paragraph("")

    def table_block(self, block: Dict) -> None:
        columns = len(block["header"])
        width = 9000 // max(1, columns)
        grid = "".join(f'<w:gridCol w:w="{width}"/>' for _ in range(columns))

        def row(cells: Sequence[str], head: bool) -> str:
            shading = '<w:shd w:val="clear" w:color="auto" w:fill="F2F4F7"/>' if head else ""
            header = "<w:trPr><w:tblHeader/></w:trPr>" if head else ""
            return (
                f"<w:tr>{header}"
                + "".join(
                    f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{shading}</w:tcPr>'
                    f"<w:p>{self.runs(cell, bold=head)}</w:p></w:tc>"
                    for cell in cells
                )
                + "</w:tr>"
            )

        rows = [row(block["header"], True)] + [row(cells, False) for cells in block["rows"]]
        self.body.append(
            '<w:tbl><w:tblPr><w:tblStyle w:val="EntropyTable"/><w:tblW w:w="0" w:type="auto"/>'
            '<w:tblLook w:val="04A0" w:firstRow="1"/></w:tblPr>'
            f"<w:tblGrid>{grid}</w:tblGrid>{''.join(rows)}</w:tbl>"
        )
        self.paragraph("")

    def image_block(self, attachment_id: int, caption: str) -> None:
        image = self.images(attachment_id)
        label = caption or (image.filename if image else "attachment")
        if image is None:
            self.paragraph(self.runs(f"[{label}]"), style="Caption")
            return
        loaded = load_image(image.data)
        extension = image.filename.rsplit(".", 1)[-1].lower() if "." in image.filename else ""
        if extension not in _IMAGE_TYPES or (loaded is None and extension != "gif"):
            # Not an image Word shows: named, as in the PDF.
            self.paragraph(self.runs(f"[{label}]"), style="Caption")
            return
        width_px, height_px = (loaded.width, loaded.height) if loaded else (640, 480)
        width = width_px * _EMU_PER_PIXEL
        height = height_px * _EMU_PER_PIXEL
        if width > _MAX_IMAGE_EMU:
            height = int(height * _MAX_IMAGE_EMU / width)
            width = _MAX_IMAGE_EMU
        number = len(self.media) + 1
        name = f"image{number}.{'jpeg' if extension == 'jpg' else extension}"
        relationship = f"rIdImage{number}"
        self.media.append((name, image.data))
        self.relationships.append((relationship, REL_IMAGE, f"media/{name}"))
        drawing = (
            f'<w:r><w:drawing><wp:inline xmlns:wp="{WP}"><wp:extent cx="{width}" cy="{height}"/>'
            f'<wp:docPr id="{number}" name="{escape(label, {chr(34): "&quot;"})}"/>'
            f'<a:graphic xmlns:a="{A}"><a:graphicData uri="{PIC}"><pic:pic xmlns:pic="{PIC}">'
            f'<pic:nvPicPr><pic:cNvPr id="{number}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{relationship}"/><a:stretch><a:fillRect/></a:stretch>'
            f'</pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{width}"'
            f' cy="{height}"/>'
            '</a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
            "</a:graphicData></a:graphic></wp:inline></w:drawing></w:r>"
        )
        self.paragraph(drawing)
        self.paragraph(self.runs(label), style="Caption")

    def description(self, text: str) -> None:
        for block in parse_blocks(text):
            kind = block["type"]
            if kind == "heading":
                self.paragraph(self.runs(block["text"]), style=f"Heading{block['level']}")
            elif kind == "paragraph":
                self.paragraph(self.runs(block["text"]))
            elif kind == "list":
                self.list_block(block)
            elif kind == "table":
                self.table_block(block)
            elif kind == "code":
                for line in block["text"].split("\n"):
                    self.paragraph(
                        f'<w:r><w:t xml:space="preserve">{escape(line)}</w:t></w:r>', style="Code"
                    )
            else:
                self.image_block(int(block["id"]), block["caption"])


def _styles() -> str:
    headings = "".join(
        f'<w:style w:type="paragraph" w:styleId="Heading{level}"><w:name w:val="heading {level}"/>'
        f'<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
        f'<w:pPr><w:keepNext/><w:spacing w:before="{280 - level * 30}" w:after="80"/>'
        f'<w:outlineLvl w:val="{level - 1}"/></w:pPr>'
        f'<w:rPr><w:b/><w:color w:val="{"1F4E99" if level < 3 else "344054"}"/>'
        f'<w:sz w:val="{[36, 30, 26, 24, 22][level - 1]}"/></w:rPr></w:style>'
        for level in range(1, 6)
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {_NS}>'
        '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"'
        ' w:cs="Calibri"/>'
        '<w:sz w:val="22"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>'
        '<w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault>'
        "</w:docDefaults>"
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>'
        "<w:qFormat/></w:style>"
        '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn'
        ' w:val="Normal"/>'
        '<w:qFormat/><w:pPr><w:spacing w:after="60"/></w:pPr><w:rPr><w:b/><w:sz w:val="44"/>'
        "</w:rPr></w:style>"
        '<w:style w:type="paragraph" w:styleId="EntropyEyebrow"><w:name w:val="Entropy Eyebrow"/>'
        '<w:basedOn w:val="Normal"/><w:rPr><w:color w:val="667085"/><w:sz w:val="18"/>'
        "<w:caps/></w:rPr>"
        "</w:style>"
        f"{headings}"
        '<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/>'
        '<w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="40"/></w:pPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Code"><w:name w:val="Code"/><w:basedOn'
        ' w:val="Normal"/>'
        '<w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/>'
        '<w:shd w:val="clear" w:color="auto" w:fill="F2F4F7"/></w:pPr>'
        f'<w:rPr><w:rFonts w:ascii="{_CODE_FONT}" w:hAnsi="{_CODE_FONT}" w:cs="{_CODE_FONT}"/>'
        '<w:sz w:val="18"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="caption"/><w:basedOn'
        ' w:val="Normal"/>'
        '<w:rPr><w:i/><w:color w:val="667085"/><w:sz w:val="18"/></w:rPr></w:style>'
        '<w:style w:type="table" w:styleId="EntropyTable"><w:name w:val="Entropy Table"/><w:tblPr>'
        '<w:tblBorders><w:top w:val="single" w:sz="4" w:color="D0D5DD"/>'
        '<w:left w:val="single" w:sz="4" w:color="D0D5DD"/><w:bottom w:val="single" w:sz="4"'
        ' w:color="D0D5DD"/>'
        '<w:right w:val="single" w:sz="4" w:color="D0D5DD"/><w:insideH w:val="single" w:sz="4"'
        ' w:color="D0D5DD"/>'
        '<w:insideV w:val="single" w:sz="4" w:color="D0D5DD"/></w:tblBorders>'
        '<w:tblCellMar><w:left w:w="100" w:type="dxa"/><w:right w:w="100" w:type="dxa"/>'
        "</w:tblCellMar>"
        "</w:tblPr></w:style>"
        '<w:style w:type="table" w:styleId="EntropyFacts"><w:name w:val="Entropy Facts"/>'
        '<w:basedOn w:val="EntropyTable"/></w:style></w:styles>'
    )


def _numbering(starts: Sequence[int]) -> str:
    def levels(bullet: bool) -> str:
        marks = ["•", "◦", "▪"]
        formats = ["decimal", "lowerLetter", "lowerRoman"]
        return "".join(
            f'<w:lvl w:ilvl="{level}"><w:start w:val="1"/>'
            f'<w:numFmt w:val="{"bullet" if bullet else formats[level % 3]}"/>'
            f'<w:lvlText w:val="{marks[level % 3] if bullet else f"%{level + 1}."}"/>'
            f'<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="{720 + level * 360}"'
            ' w:hanging="360"/></w:pPr>'
            "</w:lvl>"
            for level in range(9)
        )

    numbered = "".join(
        f'<w:num w:numId="{3 + index}"><w:abstractNumId w:val="1"/>'
        f'<w:lvlOverride w:ilvl="0"><w:startOverride w:val="{start}"/></w:lvlOverride></w:num>'
        for index, start in enumerate(starts)
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:numbering {_NS}>'
        '<w:abstractNum w:abstractNumId="0"><w:multiLevelType'
        f' w:val="hybridMultilevel"/>{levels(True)}</w:abstractNum>'
        '<w:abstractNum w:abstractNumId="1"><w:multiLevelType'
        f' w:val="hybridMultilevel"/>{levels(False)}</w:abstractNum>'
        '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
        '<w:num w:numId="2"><w:abstractNumId w:val="0"/></w:num>'
        f"{numbered}</w:numbering>"
    )


def write_docx(
    *,
    title: str,
    subtitle: str,
    facts: Sequence[Tuple[str, str]],
    body: str,
    images: Callable[[int], Optional[DocxImage]],
    author: str = "Entropy",
) -> bytes:
    """A Word document: the title, a table of facts, then the description."""

    writer = _Writer(images=images)
    writer.paragraph(writer.runs(subtitle), style="EntropyEyebrow")
    writer.paragraph(f'<w:r><w:t xml:space="preserve">{escape(title)}</w:t></w:r>', style="Title")
    if facts:
        writer.facts(facts)
    writer.description(body or "")

    document = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {_NS}><w:body>'
        + "".join(writer.body)
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" '
        'w:bottom="1134" w:left="1134" w:header="567" w:footer="567" w:gutter="0"/></w:sectPr>'
        "</w:body></w:document>"
    )
    relationships = "".join(
        f'<Relationship Id="{rid}" Type="{kind}" Target="{target}"/>'
        for rid, kind, target in writer.relationships
    )
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    defaults = "".join(
        f'<Default Extension="{extension}" ContentType="{kind}"/>'
        for extension, kind in _IMAGE_TYPES.items()
    )
    parts = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels"'
            ' ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            f"{defaults}"
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
            'officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-'
            'officedocument.wordprocessingml.styles+xml"/>'
            '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-'
            'officedocument.wordprocessingml.numbering+xml"/>'
            '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-'
            'package.core-properties+xml"/></Types>'
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="word/document.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/'
            'metadata/core-properties" Target="docProps/core.xml"/></Relationships>'
        ),
        "word/_rels/document.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/styles" Target="styles.xml"/>'
            '<Relationship Id="rIdNumbering" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/numbering" Target="numbering.xml"/>'
            f"{relationships}</Relationships>"
        ),
        "word/document.xml": document,
        "word/styles.xml": _styles(),
        "word/numbering.xml": _numbering(writer.numbered),
        "docProps/core.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/'
            'core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/'
            'dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f"<dc:title>{escape(title)}</dc:title><dc:creator>{escape(author)}</dc:creator>"
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
            "</cp:coreProperties>"
        ),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in parts.items():
            archive.writestr(name, text)
        for name, data in writer.media:
            archive.writestr(f"word/media/{name}", data)
    return buffer.getvalue()


# ----------------------------------------------------------------------
# Reading
# ----------------------------------------------------------------------


@dataclass
class ImportedImage:
    filename: str
    content_type: str
    data: bytes
    # The caption written under it, if any.
    caption: str = ""


@dataclass
class ImportedDocument:
    """A description, with IMAGE_TOKEN lines where its images go, in order."""

    title: str
    body: str
    images: List[ImportedImage] = field(default_factory=list)


IMAGE_TOKEN = "[[entropy-image-{index}]]"
_TITLE = "\x00title\x00"


def _tag(element: ElementTree.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _attr(element: Optional[ElementTree.Element], name: str, namespace: str = W) -> Optional[str]:
    return None if element is None else element.get(f"{{{namespace}}}{name}")


def _on(element: Optional[ElementTree.Element]) -> bool:
    """A toggle such as <w:b/> (on) or <w:b w:val="false"/> (off)."""

    if element is None:
        return False
    return (_attr(element, "val") or "true").lower() not in ("false", "0", "off", "none")


def escape_text(text: str) -> str:
    """Text as a description reads it literally: marks that would format it escaped."""

    parsed = parse_inline(text)
    if len(parsed) == 1 and set(parsed[0]) == {"text"} and parsed[0]["text"] == text:
        return text
    return re.sub(r"([\\*~`+])", r"\\\1", text)


def escape_line_start(line: str) -> str:
    line = re.sub(r"^(\s*)(#{1,6}\s)", r"\1\\\2", line)
    line = re.sub(r"^(\s*)([-*+]\s)", r"\1\\\2", line)
    line = re.sub(r"^(\s*)(\d+)\.(\s)", r"\1\2\\.\3", line)
    return re.sub(r"^(\s*)```", r"\1\\`\\`\\`", line)


def _marked(text: str, bold: bool, italic: bool, underline: bool, strike: bool, code: bool) -> str:
    if not text.strip():
        return text
    lead = text[: len(text) - len(text.lstrip())]
    tail = text[len(text.rstrip()) :]
    core = text.strip()
    core = f"`{core.replace('`', chr(39))}`" if code else escape_text(core)
    if strike:
        core = f"~~{core}~~"
    if underline:
        core = f"++{core}++"
    if italic:
        core = f"*{core}*"
    if bold:
        core = f"**{core}**"
    return lead + core + tail


class _Reader:
    def __init__(self, archive: zipfile.ZipFile) -> None:
        self.archive = archive
        self.styles = self._styles()
        self.numbering = self._numbering()
        self.relationships = self._relationships()
        self.images: List[ImportedImage] = []
        self.after_image: Optional[ImportedImage] = None

    def _xml(self, name: str) -> Optional[ElementTree.Element]:
        try:
            return ElementTree.fromstring(self.archive.read(name))
        except KeyError:
            return None
        except ElementTree.ParseError as exc:
            raise DocxError(f"The document's {name} cannot be read: {exc}") from None

    def _styles(self) -> Dict[str, str]:
        """Style id -> its name in lower case ("heading 1", "title", "list bullet")."""

        root = self._xml("word/styles.xml")
        names: Dict[str, str] = {}
        for style in [] if root is None else root.iter(f"{{{W}}}style"):
            identifier = _attr(style, "styleId") or ""
            name = _attr(style.find(f"{{{W}}}name"), "val") or identifier
            names[identifier] = name.lower()
        return names

    def _numbering(self) -> Dict[Tuple[str, str], str]:
        """(numId, level) -> its number format ("bullet", "decimal", ...)."""

        root = self._xml("word/numbering.xml")
        if root is None:
            return {}
        abstract: Dict[str, Dict[str, str]] = {}
        for item in root.iter(f"{{{W}}}abstractNum"):
            levels = {}
            for level in item.iter(f"{{{W}}}lvl"):
                levels[_attr(level, "ilvl") or "0"] = (
                    _attr(level.find(f"{{{W}}}numFmt"), "val") or "bullet"
                )
            abstract[_attr(item, "abstractNumId") or ""] = levels
        formats: Dict[Tuple[str, str], str] = {}
        for number in root.iter(f"{{{W}}}num"):
            base = _attr(number.find(f"{{{W}}}abstractNumId"), "val") or ""
            for depth, kind in abstract.get(base, {}).items():
                formats[(_attr(number, "numId") or "", depth)] = kind
        return formats

    def _relationships(self) -> Dict[str, str]:
        root = self._xml("word/_rels/document.xml.rels")
        return {} if root is None else {item.get("Id", ""): item.get("Target", "") for item in root}

    # Text --------------------------------------------------------------

    def _image(self, element: ElementTree.Element) -> Optional[str]:
        blip = next(element.iter(f"{{{A}}}blip"), None)
        target = self.relationships.get(_attr(blip, "embed", R) or "")
        if not target or len(self.images) >= MAX_IMAGES:
            return None
        path = (
            posixpath.normpath(posixpath.join("word", target))
            if not target.startswith("/")
            else target[1:]
        )
        try:
            data = self.archive.read(path)
        except KeyError:
            return None
        extension = path.rsplit(".", 1)[-1].lower()
        kind = _IMAGE_TYPES.get(extension) or f"image/{extension}"
        index = len(self.images)
        self.images.append(ImportedImage(f"image-{index + 1}.{extension}", kind, data))
        return IMAGE_TOKEN.format(index=index)

    def runs(self, paragraph: ElementTree.Element) -> Tuple[str, List[str]]:
        """The paragraph's text with its formatting, and the image tokens found in it."""

        pieces: List[str] = []
        tokens: List[str] = []
        for run in paragraph.iter(f"{{{W}}}r"):
            properties = run.find(f"{{{W}}}rPr")

            def get(
                name: str, found: Optional[ElementTree.Element] = properties
            ) -> Optional[ElementTree.Element]:
                return None if found is None else found.find(f"{{{W}}}{name}")

            font = " ".join(
                filter(None, [_attr(get("rFonts"), "ascii"), _attr(get("rStyle"), "val")])
            ).lower()
            underline = get("u")
            style = (
                _on(get("b")),
                _on(get("i")),
                underline is not None and (_attr(underline, "val") or "single") != "none",
                _on(get("strike")) or _on(get("dstrike")),
                any(name in font for name in ("consolas", "courier", "mono", "code")),
            )
            text = ""
            for child in run:
                kind = _tag(child)
                if kind == "t":
                    text += child.text or ""
                elif kind == "tab":
                    text += " "
                elif kind in ("br", "cr"):
                    pieces.append(_marked(text, *style))
                    pieces.append("\n")
                    text = ""
                elif kind in ("drawing", "pict", "object"):
                    token = self._image(child)
                    if token:
                        tokens.append(token)
            pieces.append(_marked(text, *style))
        # Neighbouring runs of one style write "**a****b**": join them.
        joined = "".join(pieces)
        joined = re.sub(r"(\*\*|\+\+|~~)\1", "", joined)
        return joined, tokens

    def paragraph(self, element: ElementTree.Element) -> List[str]:
        properties = element.find(f"{{{W}}}pPr")
        style_id = (
            _attr(properties.find(f"{{{W}}}pStyle"), "val") if properties is not None else None
        )
        style = self.styles.get(style_id or "", (style_id or "").lower())
        text, tokens = self.runs(element)
        lines: List[str] = []
        stripped = text.strip()
        heading = re.match(r"heading\s*(\d)", style)
        number = properties.find(f"{{{W}}}numPr") if properties is not None else None
        if style == "entropy eyebrow":
            return tokens
        if stripped and style == "caption" and self.after_image is not None:
            # The caption of the image just above: its name, not a paragraph.
            self.after_image.caption = re.sub(r"[\\*~`+]", "", stripped)[:200]
            self.after_image = None
            return tokens
        if stripped and style == "title":
            lines.append(f"{_TITLE}{stripped}")
        elif stripped and style == "subtitle":
            lines.append(f"## {stripped}")
        elif stripped and heading:
            lines.append(
                f"{'#' * min(5, max(1, int(heading.group(1))))} {stripped.replace(chr(10), ' ')}"
            )
        elif stripped and (number is not None or style.startswith("list")):
            level = _attr(number.find(f"{{{W}}}ilvl"), "val") if number is not None else "0"
            number_id = _attr(number.find(f"{{{W}}}numId"), "val") if number is not None else ""
            kind = self.numbering.get(
                (number_id or "", level or "0"), "decimal" if "number" in style else "bullet"
            )
            marker = "-" if kind in ("bullet", "none") else "1."
            box = re.match(r"^([☐☑☒])\s*", stripped)
            if box:
                stripped = stripped[box.end() :]
                marker = f"- [{' ' if box.group(1) == chr(0x2610) else 'x'}]"
            lines.append(f"{'  ' * int(level or 0)}{marker} {stripped.replace(chr(10), ' ')}")
        elif stripped and re.match(r"^[☐☑☒]\s*", stripped):
            checked = "x" if stripped[0] != "☐" else " "
            lines.append(f"- [{checked}] {stripped[1:].strip()}")
        elif stripped and ("code" in style or "source" in style or "preformatted" in style):
            lines.append("\x00code\x00" + re.sub(r"^`|`$", "", text))
        elif stripped:
            lines.append("\n".join(escape_line_start(line) for line in text.split("\n")).strip())
        lines.extend(tokens)
        self.after_image = self.images[-1] if tokens else None
        return lines

    def table(self, element: ElementTree.Element) -> List[str]:
        properties = element.find(f"{{{W}}}tblPr")
        style = _attr(properties.find(f"{{{W}}}tblStyle"), "val") if properties is not None else ""
        if style == "EntropyFacts":
            # The facts of an exported entry: they come back as its fields, not text.
            return []
        rows: List[List[str]] = []
        for row in element.findall(f"{{{W}}}tr"):
            cells = []
            for cell in row.findall(f"{{{W}}}tc"):
                texts = [self.runs(paragraph)[0].strip() for paragraph in cell.iter(f"{{{W}}}p")]
                cells.append(
                    " ".join(text.replace("\n", " ") for text in texts if text).replace("|", "\\|")
                    or " "
                )
            if cells:
                rows.append(cells)
        if not rows:
            return []
        width = max(len(row) for row in rows)
        rows = [row + [" "] * (width - len(row)) for row in rows]

        def line(cells: List[str]) -> str:
            return "| " + " | ".join(cells) + " |"

        # A heading row is bold anyway: its cells need no marks of their own.
        head = [re.sub(r"^\*\*(.+)\*\*$", r"\1", cell) for cell in rows[0]]
        table = [line(head), line(["---"] * width), *[line(row) for row in rows[1:]]]
        # One block: its rows stay together.
        return ["\n".join(table)]

    def document(self) -> List[List[str]]:
        root = self._xml("word/document.xml")
        if root is None:
            raise DocxError("This is not a Word document: word/document.xml is missing.")
        body = root.find(f"{{{W}}}body")
        blocks: List[List[str]] = []
        for element in [] if body is None else body:
            kind = _tag(element)
            if kind == "p":
                lines = self.paragraph(element)
                if lines:
                    blocks.append(lines)
            elif kind == "tbl":
                lines = self.table(element)
                if lines:
                    blocks.append(lines)
            elif kind == "sdt":
                # A content control (a table of contents, say): read what it holds.
                content = element.find(f"{{{W}}}sdtContent")
                for child in [] if content is None else content:
                    if _tag(child) == "p" and (lines := self.paragraph(child)):
                        blocks.append(lines)
        return blocks


def _join(blocks: List[List[str]]) -> str:
    """Blocks as description text: list items together, code lines fenced, a blank line between."""

    out: List[str] = []
    previous = ""
    code: List[str] = []

    def flush_code() -> None:
        if code:
            out.append("```\n" + "\n".join(code) + "\n```")
            code.clear()

    for lines in blocks:
        for line in lines:
            if line.startswith("\x00code\x00"):
                code.append(line[len("\x00code\x00") :])
                previous = "code"
                continue
            flush_code()
            kind = "list" if re.match(r"^\s*(?:-|\d+\.)\s", line) else "other"
            if out and kind == "list" and previous == "list":
                out[-1] += "\n" + line
            else:
                out.append(line)
            previous = kind
    flush_code()
    return "\n\n".join(part for part in out if part.strip())


def read_docx(data: bytes, fallback_title: str) -> ImportedDocument:
    """A Word document as a description: the first heading (or Title) becomes the title."""

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise DocxError("This is not a Word (.docx) document.") from None
    with archive:
        if sum(item.file_size for item in archive.infolist()) > MAX_UNPACKED_BYTES:
            raise DocxError("The document is too large to import.")
        reader = _Reader(archive)
        blocks = reader.document()
    title = ""
    # The Title paragraph names the entry; without one, a heading the document starts with.
    for block in blocks:
        for index, line in enumerate(block):
            if line.startswith(_TITLE):
                title = title or line[len(_TITLE) :].strip()
                block[index] = ""
    blocks = [[line for line in block if line] for block in blocks]
    if not title and blocks and blocks[0] and re.match(r"^#{1,2} ", blocks[0][0]):
        title = re.sub(r"^#{1,2} ", "", blocks[0][0]).strip()
        blocks[0] = blocks[0][1:]
    title = title or fallback_title
    return ImportedDocument(
        title=title[:200], body=_join([block for block in blocks if block]), images=reader.images
    )
