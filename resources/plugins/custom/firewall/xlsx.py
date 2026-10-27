"""
Excel (.xlsx) files with the standard library only.

The writer produces a small Office Open XML workbook: one or more sheets,
a bold header row with a fill, borders, frozen header, filter buttons and
column widths fitted to the content. The reader returns the cells of the
first sheet as text (enough to use an Excel file as a template).
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import List, Sequence, Tuple
from xml.etree import ElementTree
from xml.sax.saxutils import escape

Sheet = Tuple[str, List[str], List[List[str]]]

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"

# Characters XML 1.0 does not allow (Excel refuses the file otherwise).
ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")
INTEGER = re.compile(r"^-?[1-9]\d{0,14}$|^0$")
SHEET_NAME_CHARACTERS = re.compile(r"[\[\]:*?/\\]")


def column_letter(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""

    name = ""
    value = index + 1
    while value > 0:
        value, rest = divmod(value - 1, 26)
        name = chr(65 + rest) + name
    return name


def column_index(reference: str) -> int:
    """'C7' -> 2."""

    index = 0
    for char in reference:
        if not char.isalpha():
            break
        index = index * 26 + ord(char.upper()) - 64
    return index - 1


def sheet_names(names: Sequence[str]) -> List[str]:
    """Names Excel accepts: 31 characters, no []:*?/\\, unique (case-insensitive)."""

    result: List[str] = []
    seen = set()
    for position, name in enumerate(names, start=1):
        base = SHEET_NAME_CHARACTERS.sub("_", name).strip("' ")[:31] or f"Sheet{position}"
        candidate, number = base, 2
        while candidate.casefold() in seen:
            suffix = f" ({number})"
            candidate = base[: 31 - len(suffix)] + suffix
            number += 1
        seen.add(candidate.casefold())
        result.append(candidate)
    return result


# ----------------------------------------------------------------------
# Writer
# ----------------------------------------------------------------------

STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2">
<font><sz val="11"/><name val="Calibri"/><family val="2"/></font>
<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/><family val="2"/></font>
</fonts>
<fills count="3">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF1F4E78"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left style="thin"><color rgb="FFBFBFBF"/></left><right style="thin"><color rgb="FFBFBFBF"/></right><top style="thin"><color rgb="FFBFBFBF"/></top><bottom style="thin"><color rgb="FFBFBFBF"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="3">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="49" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>
"""


def _text(value: str) -> str:
    return escape(ILLEGAL.sub("", value))


def _cell(reference: str, value: str, style: int, numbers: bool) -> str:
    if value == "":
        return f'<c r="{reference}" s="{style}"/>'
    if numbers and INTEGER.match(value):
        return f'<c r="{reference}" s="{style}"><v>{value}</v></c>'
    return (
        f'<c r="{reference}" s="{style}" t="inlineStr">'
        f'<is><t xml:space="preserve">{_text(value)}</t></is></c>'
    )


def _width(values: Sequence[str]) -> float:
    longest = max((len(line) for value in values for line in value.split("\n")), default=0)
    return float(min(max(longest + 3, 10), 60))


def _sheet(header: List[str], rows: List[List[str]], numbers: bool) -> str:
    columns = max([len(header)] + [len(row) for row in rows]) or 1
    last = column_letter(columns - 1)
    widths = [
        _width(
            [header[col] if col < len(header) else ""]
            + [row[col] if col < len(row) else "" for row in rows]
        )
        for col in range(columns)
    ]

    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<worksheet xmlns="{MAIN}" xmlns:r="{RELS}">',
        f'<dimension ref="A1:{last}{len(rows) + 1}"/>',
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '<selection pane="bottomLeft" activeCell="A2" sqref="A2"/>'
        "</sheetView></sheetViews>",
        '<sheetFormatPr defaultRowHeight="15"/>',
        "<cols>",
    ]
    lines.extend(
        f'<col min="{col + 1}" max="{col + 1}" width="{width}" customWidth="1"/>'
        for col, width in enumerate(widths)
    )
    lines.append("</cols><sheetData>")

    cells = "".join(
        _cell(f"{column_letter(col)}1", value, 1, False) for col, value in enumerate(header)
    )
    lines.append(f'<row r="1" ht="20" customHeight="1">{cells}</row>')
    for number, row in enumerate(rows, start=2):
        padded = list(row) + [""] * (columns - len(row))
        cells = "".join(
            _cell(f"{column_letter(col)}{number}", value, 2, numbers)
            for col, value in enumerate(padded)
        )
        lines.append(f'<row r="{number}">{cells}</row>')

    lines.append("</sheetData>")
    lines.append(f'<autoFilter ref="A1:{last}{len(rows) + 1}"/>')
    lines.append(
        '<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>'
    )
    lines.append("</worksheet>")
    return "\n".join(lines)


def write_workbook(path: Path, sheets: Sequence[Sheet], numbers: bool = True) -> None:
    """Write `sheets` (name, header, rows) to `path`."""

    if not sheets:
        raise ValueError("A workbook needs at least one sheet.")

    names = sheet_names([name for name, _, _ in sheets])
    count = len(sheets)

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        + "".join(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for index in range(1, count + 1)
        )
        + "</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{PACKAGE_RELS}">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<workbook xmlns="{MAIN}" xmlns:r="{RELS}"><bookViews><workbookView/></bookViews><sheets>'
        + "".join(
            f'<sheet name="{_text(name)}" sheetId="{index}" r:id="rId{index}"/>'
            for index, name in enumerate(names, start=1)
        )
        + "</sheets></workbook>"
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{PACKAGE_RELS}">'
        + "".join(
            f'<Relationship Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
            for index in range(1, count + 1)
        )
        + f'<Relationship Id="rId{count + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/></Relationships>'
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/styles.xml", STYLES)
        for index, (_, header, rows) in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet(header, rows, numbers))
    temporary.replace(path)


# ----------------------------------------------------------------------
# Reader
# ----------------------------------------------------------------------


def _join(base: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    parts = base.split("/")[:-1] + target.split("/")
    resolved: List[str] = []
    for part in parts:
        if part == "..":
            if resolved:
                resolved.pop()
        elif part not in ("", "."):
            resolved.append(part)
    return "/".join(resolved)


def _number(value: str) -> str:
    # Excel keeps whole numbers as floats ("22.0"); show them as written.
    try:
        number = float(value)
    except ValueError:
        return value
    if number.is_integer() and abs(number) < 1e15:
        return str(int(number))
    return value


def read_first_sheet(path: Path) -> List[List[str]]:
    """Rows of the first sheet of an .xlsx file, as text, trailing empty cells removed."""

    ns = {"m": MAIN}
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as error:
        raise ValueError(f"'{path.name}' is not an .xlsx file.") from error

    with archive:
        names = set(archive.namelist())
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        first = workbook.find("m:sheets/m:sheet", ns)
        if first is None:
            raise ValueError(f"'{path.name}' has no sheets.")
        relation = first.get(f"{{{RELS}}}id")
        rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = next(
            (item.get("Target", "") for item in rels if item.get("Id") == relation),
            "worksheets/sheet1.xml",
        )
        sheet_path = _join("xl/workbook.xml", target)

        shared: List[str] = []
        if "xl/sharedStrings.xml" in names:
            for item in ElementTree.fromstring(archive.read("xl/sharedStrings.xml")).findall(
                "m:si", ns
            ):
                shared.append("".join(text.text or "" for text in item.iter(f"{{{MAIN}}}t")))

        sheet = ElementTree.fromstring(archive.read(sheet_path))

    rows: List[List[str]] = []
    for row in sheet.findall("m:sheetData/m:row", ns):
        number = int(row.get("r", len(rows) + 1))
        while len(rows) < number - 1:
            rows.append([])
        values: List[str] = []
        for cell in row.findall("m:c", ns):
            reference = cell.get("r")
            col = column_index(reference) if reference else len(values)
            kind = cell.get("t", "n")
            raw = cell.find("m:v", ns)
            if kind == "s" and raw is not None and raw.text is not None:
                value = shared[int(raw.text)]
            elif kind == "inlineStr":
                value = "".join(text.text or "" for text in cell.iter(f"{{{MAIN}}}t"))
            elif kind == "b":
                value = "TRUE" if raw is not None and raw.text == "1" else "FALSE"
            elif raw is not None and raw.text is not None:
                value = raw.text if kind in ("str", "e") else _number(raw.text)
            else:
                value = ""
            while len(values) < col:
                values.append("")
            values.append(value)
        while values and values[-1] == "":
            values.pop()
        rows.append(values)

    while rows and not rows[-1]:
        rows.pop()
    return rows
