"""
Previews of Office Open XML files (xlsx, docx) with the standard library.

Both formats are ZIP archives of XML parts. Spreadsheets become rows of
display strings per sheet; documents become simple, escaped HTML (headings,
paragraphs, lists, tables, bold and italic). Legacy binary .xls/.doc files
are not supported.
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime, timedelta
from html import escape
from typing import Any, Dict, Iterator, List, Optional, Set
from xml.etree import ElementTree

from lib.artifacts.archive import ArchiveError

MAX_ROWS = 1000
MAX_COLUMNS = 100
# Parts larger than this (uncompressed) are not parsed.
MAX_PART_BYTES = 64 * 1024 * 1024

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# Built-in number formats that are dates or times (ECMA-376 18.8.30).
DATE_FORMAT_IDS = {14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 46, 47}
DATE_CODE = re.compile(r"[dmyhs]", re.IGNORECASE)
CELL_REF = re.compile(r"([A-Z]+)(\d+)")


def _open(data: bytes) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ArchiveError("This file is not a valid Office document.") from exc


def _part(archive: zipfile.ZipFile, name: str) -> Optional[bytes]:
    try:
        info = archive.getinfo(name)
    except KeyError:
        return None
    if info.file_size > MAX_PART_BYTES:
        raise ArchiveError("The document is too large to preview; download it instead.")
    data = archive.read(info)
    # Entity declarations are never needed here; refusing them avoids entity expansion attacks.
    if b"<!DOCTYPE" in data[:4096] or b"<!ENTITY" in data[:4096]:
        raise ArchiveError("The document contains unsupported XML declarations.")
    return data


def _xml(archive: zipfile.ZipFile, name: str) -> Optional[ElementTree.Element]:
    data = _part(archive, name)
    if data is None:
        return None
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise ArchiveError(f"Unable to read '{name}': {exc}") from exc


# ----------------------------------------------------------------------
# Spreadsheets
# ----------------------------------------------------------------------


def _column(letters: str) -> int:
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter) - 64
    return index - 1


def _shared_strings(archive: zipfile.ZipFile) -> List[str]:
    root = _xml(archive, "xl/sharedStrings.xml")
    if root is None:
        return []
    return [
        "".join(node.text or "" for node in item.iter(f"{MAIN}t"))
        for item in root.findall(f"{MAIN}si")
    ]


def _date_styles(archive: zipfile.ZipFile) -> Set[int]:
    """Indexes of cell styles that show numbers as dates."""

    root = _xml(archive, "xl/styles.xml")
    if root is None:
        return set()
    custom = {
        int(item.get("numFmtId", "0")): item.get("formatCode", "")
        for item in root.iter(f"{MAIN}numFmt")
    }
    dates: Set[int] = set()
    cell_formats = root.find(f"{MAIN}cellXfs")
    for index, xf in enumerate(cell_formats if cell_formats is not None else []):
        format_id = int(xf.get("numFmtId", "0"))
        code = re.sub(r'"[^"]*"|\[[^\]]*\]', "", custom.get(format_id, ""))
        if format_id in DATE_FORMAT_IDS or (format_id in custom and DATE_CODE.search(code)):
            dates.add(index)
    return dates


def _number(value: str, as_date: bool) -> str:
    try:
        number = float(value)
    except ValueError:
        return value
    if as_date and 0 <= number < 2958466:
        moment = datetime(1899, 12, 30) + timedelta(days=number)
        return moment.strftime("%Y-%m-%d" if number == int(number) else "%Y-%m-%d %H:%M:%S")
    return str(int(number)) if number == int(number) and abs(number) < 1e15 else value


def _cell(cell: ElementTree.Element, strings: List[str], dates: Set[int]) -> str:
    kind = cell.get("t", "n")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{MAIN}t"))
    value = cell.findtext(f"{MAIN}v") or ""
    if kind == "s":
        try:
            return strings[int(value)]
        except (ValueError, IndexError):
            return ""
    if kind == "b":
        return "TRUE" if value == "1" else "FALSE"
    if kind in ("str", "e"):
        return value
    return _number(value, int(cell.get("s", "0")) in dates)


def _rows(root: ElementTree.Element, strings: List[str], dates: Set[int]) -> Iterator[List[str]]:
    data = root.find(f"{MAIN}sheetData")
    expected = 0
    for row in data if data is not None else []:
        number = int(row.get("r", expected + 1))
        # Rows missing from the file are empty; keep them so row numbers match.
        while expected + 1 < number:
            expected += 1
            yield []
        expected = number
        values: List[str] = []
        for position, cell in enumerate(row.findall(f"{MAIN}c")):
            match = CELL_REF.match(cell.get("r", ""))
            column = _column(match.group(1)) if match else position
            if column >= MAX_COLUMNS:
                continue
            values.extend([""] * (column - len(values)))
            values.append(_cell(cell, strings, dates))
        yield values


def xlsx_preview(data: bytes, max_rows: int = MAX_ROWS) -> Dict[str, Any]:
    """Each sheet's name and first rows as display strings."""

    archive = _open(data)
    workbook = _xml(archive, "xl/workbook.xml")
    if workbook is None:
        raise ArchiveError("This file is not an Excel workbook.")
    relations = _xml(archive, "xl/_rels/workbook.xml.rels")
    targets = {
        item.get("Id"): item.get("Target", "")
        for item in (relations.iter(f"{PKG_REL}Relationship") if relations is not None else [])
    }
    strings = _shared_strings(archive)
    dates = _date_styles(archive)
    sheets: List[Dict[str, Any]] = []
    for sheet in workbook.iter(f"{MAIN}sheet"):
        target = targets.get(sheet.get(f"{REL}id"), "")
        path = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
        root = _xml(archive, path) if target else None
        rows: List[List[str]] = []
        total = 0
        if root is not None:
            for values in _rows(root, strings, dates):
                total += 1
                if len(rows) < max_rows:
                    rows.append(values)
        while rows and not any(rows[-1]):
            rows.pop()
        sheets.append({
            "name": sheet.get("name", f"Sheet {len(sheets) + 1}"),
            "rows": rows,
            "total_rows": total,
            "truncated": total > max_rows,
        })
    return {"sheets": sheets}


# ----------------------------------------------------------------------
# Documents
# ----------------------------------------------------------------------


def _runs(paragraph: ElementTree.Element) -> str:
    parts: List[str] = []
    for run in paragraph.iter(f"{WORD}r"):
        properties = run.find(f"{WORD}rPr")
        bold = properties is not None and properties.find(f"{WORD}b") is not None
        italic = properties is not None and properties.find(f"{WORD}i") is not None
        text = ""
        for node in run:
            if node.tag == f"{WORD}t":
                text += escape(node.text or "")
            elif node.tag == f"{WORD}tab":
                text += "&emsp;"
            elif node.tag in (f"{WORD}br", f"{WORD}cr"):
                text += "<br>"
        if text and bold:
            text = f"<strong>{text}</strong>"
        if text and italic:
            text = f"<em>{text}</em>"
        parts.append(text)
    return "".join(parts)


def _paragraph(paragraph: ElementTree.Element) -> str:
    properties = paragraph.find(f"{WORD}pPr")
    style = ""
    listed = False
    if properties is not None:
        style_node = properties.find(f"{WORD}pStyle")
        style = (style_node.get(f"{WORD}val", "") if style_node is not None else "").lower()
        listed = properties.find(f"{WORD}numPr") is not None
    text = _runs(paragraph)
    heading = re.match(r"heading(\d)", style)
    if style == "title":
        return f"<h1>{text}</h1>"
    if heading:
        level = min(int(heading.group(1)) + 1, 6)
        return f"<h{level}>{text}</h{level}>"
    if listed:
        return f"<li>{text}</li>"
    return f"<p>{text or '&nbsp;'}</p>"


def _table(table: ElementTree.Element) -> str:
    rows = []
    for row in table.findall(f"{WORD}tr"):
        cells = [
            "<td>" + "<br>".join(_runs(p) for p in cell.findall(f"{WORD}p")) + "</td>"
            for cell in row.findall(f"{WORD}tc")
        ]
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return "<table>" + "".join(rows) + "</table>"


def docx_preview(data: bytes) -> Dict[str, Any]:
    """The document body as escaped HTML; images and layout are left out."""

    archive = _open(data)
    root = _xml(archive, "word/document.xml")
    body = root.find(f"{WORD}body") if root is not None else None
    if body is None:
        raise ArchiveError("This file is not a Word document.")
    blocks: List[str] = []
    for node in body:
        if node.tag == f"{WORD}p":
            blocks.append(_paragraph(node))
        elif node.tag == f"{WORD}tbl":
            blocks.append(_table(node))
    html = "".join(blocks)
    # Consecutive list items share one list.
    html = re.sub(r"((?:<li>.*?</li>)+)", r"<ul>\1</ul>", html)
    return {"html": html}


def office_preview(name: str, data: bytes) -> Dict[str, Any]:
    """The preview for a file by its name: a workbook or a document."""

    lowered = name.lower()
    if lowered.endswith((".xlsx", ".xlsm")):
        return {"kind": "sheet", **xlsx_preview(data)}
    if lowered.endswith((".docx", ".docm")):
        return {"kind": "document", **docx_preview(data)}
    raise ArchiveError("There is no preview for this type of file.")
