"""
Presentation-ready Excel workbooks with the standard library only.

Data sheets get a bold white-on-blue header, borders, wrapped text,
filter buttons, a frozen header row and fitted column widths. A summary
sheet can hold real pivot tables (one row field by one column field,
counting records) over a hidden data sheet: Excel refreshes them on
open, and their current values are written into the cells so the file
reads correctly even before that (Protected View, other viewers).
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape, quoteattr

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")
SHEET_NAME = re.compile(r"[\[\]:*?/\\]")
# Excel limits for cell text and pivot items.
MAX_CELL = 32767
MAX_ITEM = 255

# Cell styles (indexes into cellXfs below).
PLAIN, HEADER, BODY, TITLE, TOTAL, NUMBER, NOTE = range(7)

STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="5">
<font><sz val="11"/><name val="Calibri"/><family val="2"/></font>
<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/><family val="2"/></font>
<font><b/><sz val="14"/><color rgb="FF1F4E78"/><name val="Calibri"/><family val="2"/></font>
<font><b/><sz val="11"/><name val="Calibri"/><family val="2"/></font>
<font><i/><sz val="10"/><color rgb="FF595959"/><name val="Calibri"/><family val="2"/></font>
</fonts>
<fills count="4">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF1F4E78"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFDDEBF7"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left style="thin"><color rgb="FFBFBFBF"/></left><right style="thin"><color rgb="FFBFBFBF"/></right><top style="thin"><color rgb="FFBFBFBF"/></top><bottom style="thin"><color rgb="FFBFBFBF"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="7">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
<xf numFmtId="49" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="3" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="1" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>
<xf numFmtId="0" fontId="4" fillId="0" borderId="0" xfId="0" applyFont="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>
"""


@dataclass
class Sheet:
    """A data sheet: header row, then rows of text."""

    name: str
    header: List[str]
    rows: List[List[str]]
    title: str = ""
    note: str = ""
    widths: Optional[List[float]] = None
    hidden: bool = False


@dataclass
class Pivot:
    """Count of records by `rows` (down) and `columns` (across), both data field names."""

    title: str
    rows: str
    columns: str
    column_order: Sequence[str] = ()


@dataclass
class Summary:
    """A sheet of pivot tables over `data` (its header names the fields)."""

    name: str
    data: Sheet
    pivots: List[Pivot]
    title: str = ""
    note: str = ""
    counted: str = ""  # Field counted (the first one when empty).
    _placed: List[Tuple[int, int, int, int]] = field(default_factory=list)


def column_letter(index: int) -> str:
    name, value = "", index + 1
    while value > 0:
        value, rest = divmod(value - 1, 26)
        name = chr(65 + rest) + name
    return name


def _ref(column: int, row: int) -> str:
    return f"{column_letter(column)}{row + 1}"


def _clean(value: object, limit: int = MAX_CELL) -> str:
    return ILLEGAL.sub("", "" if value is None else str(value))[:limit]


def _names(names: Sequence[str]) -> List[str]:
    result, seen = [], set()
    for position, name in enumerate(names, start=1):
        base = SHEET_NAME.sub("_", name).strip("' ")[:31] or f"Sheet{position}"
        candidate, number = base, 2
        while candidate.casefold() in seen:
            suffix = f" ({number})"
            candidate, number = base[: 31 - len(suffix)] + suffix, number + 1
        seen.add(candidate.casefold())
        result.append(candidate)
    return result


def _cell(column: int, row: int, value: object, style: int) -> str:
    reference = _ref(column, row)
    if isinstance(value, int) and not isinstance(value, bool):
        return f'<c r="{reference}" s="{style}"><v>{value}</v></c>'
    text = _clean(value)
    if text == "":
        return f'<c r="{reference}" s="{style}"/>'
    return f'<c r="{reference}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(text)}</t></is></c>'


def _width(values: Sequence[str]) -> float:
    longest = max((len(line) for value in values for line in str(value).split("\n")), default=0)
    return float(min(max(longest + 3, 9), 60))


def _worksheet(cells: Dict[int, List[str]], columns: int, widths: List[float], *,
               last_row: int, freeze: Optional[int] = None, autofilter: Optional[str] = None,
               extra: str = "") -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<worksheet xmlns="{MAIN}" xmlns:r="{RELS}">',
        f'<dimension ref="A1:{_ref(max(columns - 1, 0), max(last_row, 0))}"/>',
        '<sheetViews><sheetView workbookViewId="0">',
    ]
    if freeze is not None:
        lines.append(f'<pane ySplit="{freeze}" topLeftCell="A{freeze + 1}" activePane="bottomLeft" state="frozen"/>')
    lines.append("</sheetView></sheetViews>")
    lines.append('<sheetFormatPr defaultRowHeight="15"/>')
    lines.append("<cols>" + "".join(
        f'<col min="{i + 1}" max="{i + 1}" width="{width:.1f}" customWidth="1"/>' for i, width in enumerate(widths)
    ) + "</cols>")
    lines.append("<sheetData>")
    for row in sorted(cells):
        lines.append(f'<row r="{row + 1}">{"".join(cells[row])}</row>')
    lines.append("</sheetData>")
    if autofilter:
        lines.append(f'<autoFilter ref="{autofilter}"/>')
    lines.append('<pageMargins left="0.5" right="0.5" top="0.6" bottom="0.6" header="0.3" footer="0.3"/>')
    lines.append('<pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/>')
    lines.append(extra)
    lines.append("</worksheet>")
    return "".join(lines)


def _data_sheet(sheet: Sheet) -> str:
    columns = max([len(sheet.header)] + [len(row) for row in sheet.rows]) or 1
    cells: Dict[int, List[str]] = {}
    top = 0
    if sheet.title:
        cells[0] = [_cell(0, 0, sheet.title, TITLE)]
        top = 1
        if sheet.note:
            cells[1] = [_cell(0, 1, sheet.note, NOTE)]
            top = 2
        top += 1  # A blank line before the table.
    cells[top] = [_cell(i, top, name, HEADER) for i, name in enumerate(sheet.header)]
    for offset, row in enumerate(sheet.rows, start=1):
        cells[top + offset] = [
            _cell(i, top + offset, row[i] if i < len(row) else "", BODY) for i in range(columns)
        ]
    widths = sheet.widths or [
        _width([sheet.header[i] if i < len(sheet.header) else ""] + [r[i] if i < len(r) else "" for r in sheet.rows])
        for i in range(columns)
    ]
    last = top + len(sheet.rows)
    return _worksheet(cells, columns, widths, last_row=last, freeze=top + 1,
                      autofilter=f"A{top + 1}:{_ref(columns - 1, last)}")


# ----------------------------------------------------------------------
# Pivot tables
# ----------------------------------------------------------------------


def _items(values: Sequence[str], order: Sequence[str] = ()) -> List[str]:
    unique = list(dict.fromkeys(values))
    ranked = [value for value in order if value in unique]
    return ranked + sorted((v for v in unique if v not in ranked), key=str.casefold)


def _axis_item(position: int) -> str:
    return "<i><x/></i>" if position == 0 else f'<i><x v="{position}"/></i>'


def _pivot_parts(summary: Summary, data_name: str) -> Tuple[str, str, str, List[str]]:
    """Summary sheet XML, cache definition, cache records, pivot table XMLs."""

    data = summary.data
    fields = data.header
    rows = [[_clean(row[i] if i < len(row) else "", MAX_ITEM) for i in range(len(fields))] for row in data.rows]
    order: Dict[str, Sequence[str]] = {}
    for pivot in summary.pivots:
        if pivot.column_order:
            order[pivot.columns] = pivot.column_order
    shared = [_items([row[i] for row in rows], order.get(name, ())) for i, name in enumerate(fields)]
    index = [{value: position for position, value in enumerate(items)} for items in shared]
    counted = fields.index(summary.counted) if summary.counted in fields else 0

    definition = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<pivotCacheDefinition xmlns="{MAIN}" xmlns:r="{RELS}" r:id="rId1" refreshOnLoad="1" '
        f'createdVersion="6" refreshedVersion="6" minRefreshableVersion="3" recordCount="{len(rows)}">'
        f'<cacheSource type="worksheet"><worksheetSource ref="A1:{_ref(len(fields) - 1, len(rows))}" '
        f"sheet={quoteattr(data_name)}/></cacheSource>"
        f'<cacheFields count="{len(fields)}">'
        + "".join(
            f"<cacheField name={quoteattr(_clean(name, MAX_ITEM))} numFmtId=\"0\">"
            f'<sharedItems containsBlank="{int("" in items)}" count="{len(items)}">'
            + "".join(f"<s v={quoteattr(value)}/>" for value in items)
            + "</sharedItems></cacheField>"
            for name, items in zip(fields, shared)
        )
        + "</cacheFields></pivotCacheDefinition>"
    )
    records = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<pivotCacheRecords xmlns="{MAIN}" xmlns:r="{RELS}" count="{len(rows)}">'
        + "".join("<r>" + "".join(f'<x v="{index[i][value]}"/>' for i, value in enumerate(row)) + "</r>"
                  for row in rows)
        + "</pivotCacheRecords>"
    )

    cells: Dict[int, List[str]] = {}
    widths = [24.0, 14.0]
    top = 0
    if summary.title:
        cells[0] = [_cell(0, 0, summary.title, TITLE)]
        top = 1
        if summary.note:
            cells[1] = [_cell(0, 1, summary.note, NOTE)]
            top = 2
        top += 1
    tables: List[str] = []
    last_column = 1
    for number, pivot in enumerate(summary.pivots, start=1):
        row_field, column_field = fields.index(pivot.rows), fields.index(pivot.columns)
        row_items, column_items = shared[row_field], shared[column_field]
        counts: Dict[Tuple[int, int], int] = {}
        for row in rows:
            key = (index[row_field][row[row_field]], index[column_field][row[column_field]])
            counts[key] = counts.get(key, 0) + 1

        cells[top] = [_cell(0, top, pivot.title, TOTAL)]
        start = top + 1
        width = len(column_items) + 2
        height = len(row_items) + 3
        last_column = max(last_column, width - 1)
        widths = widths + [14.0] * max(0, width - len(widths))
        # Values as Excel lays the table out (compact form).
        cells[start] = [_cell(0, start, "Tasks", TOTAL), _cell(1, start, pivot.columns, TOTAL)]
        header = start + 1
        cells[header] = (
            [_cell(0, header, pivot.rows, TOTAL)]
            + [_cell(1 + c, header, value or "(blank)", TOTAL) for c, value in enumerate(column_items)]
            + [_cell(width - 1, header, "Grand Total", TOTAL)]
        )
        for r, value in enumerate(row_items):
            line = header + 1 + r
            row_cells = [_cell(0, line, value or "(blank)", BODY)]
            for c in range(len(column_items)):
                count = counts.get((r, c))
                row_cells.append(_cell(1 + c, line, count if count else "", NUMBER))
            row_cells.append(_cell(width - 1, line, sum(counts.get((r, c), 0) for c in range(len(column_items))), TOTAL))
            cells[line] = row_cells
        grand = header + 1 + len(row_items)
        cells[grand] = (
            [_cell(0, grand, "Grand Total", TOTAL)]
            + [_cell(1 + c, grand, sum(counts.get((r, c), 0) for r in range(len(row_items))), TOTAL)
               for c in range(len(column_items))]
            + [_cell(width - 1, grand, len(rows), TOTAL)]
        )

        location = f"A{start + 1}:{_ref(width - 1, start + height - 1)}"
        pivot_fields = []
        data_flag = ' dataField="1"'
        for i in range(len(fields)):
            if i in (row_field, column_field):
                axis = "axisRow" if i == row_field else "axisCol"
                count = len(shared[i])
                pivot_fields.append(
                    f'<pivotField axis="{axis}" showAll="0"{data_flag if i == counted else ""}>'
                    f'<items count="{count + 1}">'
                    + "".join(f'<item x="{x}"/>' for x in range(count))
                    + '<item t="default"/></items></pivotField>'
                )
            else:
                pivot_fields.append(f'<pivotField showAll="0"{data_flag if i == counted else ""}/>')
        row_list = "".join(_axis_item(r) for r in range(len(row_items))) + '<i t="grand"><x/></i>'
        column_list = "".join(_axis_item(c) for c in range(len(column_items))) + '<i t="grand"><x/></i>'
        tables.append(
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<pivotTableDefinition xmlns="{MAIN}" name={quoteattr(f"Pivot{number}")} cacheId="1" '
            'applyNumberFormats="0" applyBorderFormats="0" applyFontFormats="0" applyPatternFormats="0" '
            'applyAlignmentFormats="0" applyWidthHeightFormats="1" dataCaption="Values" updatedVersion="6" '
            'minRefreshableVersion="3" createdVersion="6" useAutoFormatting="1" itemPrintTitles="1" indent="0" '
            f'outline="1" outlineData="1" multipleFieldFilters="0" rowHeaderCaption={quoteattr(pivot.rows)} '
            f'colHeaderCaption={quoteattr(pivot.columns)}>'
            f'<location ref="{location}" firstHeaderRow="1" firstDataRow="2" firstDataCol="1"/>'
            f'<pivotFields count="{len(fields)}">{"".join(pivot_fields)}</pivotFields>'
            f'<rowFields count="1"><field x="{row_field}"/></rowFields>'
            f'<rowItems count="{len(row_items) + 1}">{row_list}</rowItems>'
            f'<colFields count="1"><field x="{column_field}"/></colFields>'
            f'<colItems count="{len(column_items) + 1}">{column_list}</colItems>'
            f'<dataFields count="1"><dataField name="Tasks" fld="{counted}" subtotal="count" '
            'baseField="0" baseItem="0"/></dataFields>'
            '<pivotTableStyleInfo name="PivotStyleMedium9" showRowHeaders="1" showColHeaders="1" '
            'showRowStripes="0" showColStripes="0" showLastColumn="1"/>'
            "</pivotTableDefinition>"
        )
        top = start + height + 1

    sheet = _worksheet(cells, last_column + 1, widths, last_row=max(top - 1, 0))
    return sheet, definition, records, tables


# ----------------------------------------------------------------------
# Workbook
# ----------------------------------------------------------------------


def write_workbook(path: Path, sheets: Sequence[Sheet], summary: Optional[Summary] = None) -> None:
    """Write the sheets; a summary comes first, its data sheet (hidden) last."""

    ordered: List[Tuple[str, object]] = []
    if summary is not None:
        ordered.append(("summary", summary))
    ordered += [("sheet", sheet) for sheet in sheets]
    if summary is not None:
        summary.data.hidden = True
        ordered.append(("sheet", summary.data))
    names = _names([item.name for _, item in ordered])  # type: ignore[attr-defined]

    parts: Dict[str, str] = {}
    overrides = [
        ("/xl/workbook.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"),
        ("/xl/styles.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"),
    ]
    workbook_rels = []
    pivot_caches = ""
    for position, ((kind, item), name) in enumerate(zip(ordered, names), start=1):
        target = f"worksheets/sheet{position}.xml"
        if kind == "summary":
            assert isinstance(item, Summary)
            sheet_xml, definition, records, tables = _pivot_parts(item, names[-1])
            parts[f"xl/{target}"] = sheet_xml
            parts["xl/pivotCache/pivotCacheDefinition1.xml"] = definition
            parts["xl/pivotCache/pivotCacheRecords1.xml"] = records
            parts["xl/pivotCache/_rels/pivotCacheDefinition1.xml.rels"] = (
                f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{PACKAGE_RELS}">'
                f'<Relationship Id="rId1" Type="{REL_TYPE}pivotCacheRecords" Target="pivotCacheRecords1.xml"/>'
                "</Relationships>"
            )
            sheet_rels = []
            for number, table in enumerate(tables, start=1):
                parts[f"xl/pivotTables/pivotTable{number}.xml"] = table
                parts[f"xl/pivotTables/_rels/pivotTable{number}.xml.rels"] = (
                    f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{PACKAGE_RELS}">'
                    f'<Relationship Id="rId1" Type="{REL_TYPE}pivotCacheDefinition" '
                    'Target="../pivotCache/pivotCacheDefinition1.xml"/></Relationships>'
                )
                overrides.append((f"/xl/pivotTables/pivotTable{number}.xml",
                                  "application/vnd.openxmlformats-officedocument.spreadsheetml.pivotTable+xml"))
                sheet_rels.append(f'<Relationship Id="rId{number}" Type="{REL_TYPE}pivotTable" '
                                  f'Target="../pivotTables/pivotTable{number}.xml"/>')
            parts[f"xl/worksheets/_rels/sheet{position}.xml.rels"] = (
                f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{PACKAGE_RELS}">'
                + "".join(sheet_rels) + "</Relationships>"
            )
            overrides += [
                ("/xl/pivotCache/pivotCacheDefinition1.xml",
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.pivotCacheDefinition+xml"),
                ("/xl/pivotCache/pivotCacheRecords1.xml",
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.pivotCacheRecords+xml"),
            ]
            pivot_caches = f'<pivotCaches><pivotCache cacheId="1" r:id="rId{len(ordered) + 2}"/></pivotCaches>'
        else:
            assert isinstance(item, Sheet)
            parts[f"xl/{target}"] = _data_sheet(item)
        overrides.append((f"/xl/{target}", "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"))
        workbook_rels.append(f'<Relationship Id="rId{position}" Type="{REL_TYPE}worksheet" Target="{target}"/>')

    workbook_rels.append(f'<Relationship Id="rId{len(ordered) + 1}" Type="{REL_TYPE}styles" Target="styles.xml"/>')
    if pivot_caches:
        workbook_rels.append(f'<Relationship Id="rId{len(ordered) + 2}" Type="{REL_TYPE}pivotCacheDefinition" '
                             'Target="pivotCache/pivotCacheDefinition1.xml"/>')
    sheets_xml = "".join(
        f"<sheet name={quoteattr(name)} sheetId=\"{position}\""
        + (' state="hidden"' if isinstance(item, Sheet) and item.hidden else "")
        + f' r:id="rId{position}"/>'
        for position, ((_, item), name) in enumerate(zip(ordered, names), start=1)
    )
    parts["xl/workbook.xml"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<workbook xmlns="{MAIN}" xmlns:r="{RELS}"><bookViews><workbookView activeTab="0"/></bookViews>'
        f"<sheets>{sheets_xml}</sheets>{pivot_caches}</workbook>"
    )
    parts["xl/_rels/workbook.xml.rels"] = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{PACKAGE_RELS}">'
        + "".join(workbook_rels) + "</Relationships>"
    )
    parts["xl/styles.xml"] = STYLES
    parts["_rels/.rels"] = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{PACKAGE_RELS}">'
        f'<Relationship Id="rId1" Type="{REL_TYPE}officeDocument" Target="xl/workbook.xml"/></Relationships>'
    )
    parts["[Content_Types].xml"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        + "".join(f'<Override PartName="{part}" ContentType="{kind}"/>' for part, kind in overrides)
        + "</Types>"
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("[Content_Types].xml", "_rels/.rels"):
            archive.writestr(name, parts.pop(name))
        for name, content in parts.items():
            archive.writestr(name, content)
    temporary.replace(path)
