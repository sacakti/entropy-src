"""Spreadsheet and Word previews built with the standard library."""

from __future__ import annotations

import io
import zipfile

import pytest

from lib.artifacts.archive import ArchiveError
from lib.artifacts.office import docx_preview, office_preview, xlsx_preview

MAIN = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
REL = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
WORD = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _zip(parts: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in parts.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def _workbook(sheet: str) -> bytes:
    return _zip({
        "xl/workbook.xml": f'<workbook {MAIN} {REL}><sheets>'
                           '<sheet name="Releases" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="worksheet"/>'
            "</Relationships>"
        ),
        "xl/sharedStrings.xml": f"<sst {MAIN}><si><t>Name</t></si><si><t>Due</t></si>"
                                "<si><r><t>App </t></r><r><t>1</t></r></si></sst>",
        "xl/styles.xml": f'<styleSheet {MAIN}><cellXfs count="2"><xf numFmtId="0"/>'
                         '<xf numFmtId="14"/></cellXfs></styleSheet>',
        "xl/worksheets/sheet1.xml": sheet,
    })


def test_xlsx_rows_strings_dates_and_gaps() -> None:
    sheet = (
        f"<worksheet {MAIN}><sheetData>"
        '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
        '<row r="3"><c r="A3" t="s"><v>2</v></c><c r="B3" s="1"><v>45292</v></c>'
        '<c r="D3"><v>2.5</v></c><c r="E3" t="b"><v>1</v></c></row>'
        "</sheetData></worksheet>"
    )
    preview = xlsx_preview(_workbook(sheet))
    [releases] = preview["sheets"]
    assert releases["name"] == "Releases"
    assert releases["rows"] == [
        ["Name", "Due"],
        [],
        ["App 1", "2024-01-01", "", "2.5", "TRUE"],
    ]
    assert not releases["truncated"]

    assert xlsx_preview(_workbook(sheet), max_rows=1)["sheets"][0]["truncated"] is True


def test_docx_headings_lists_tables_are_escaped() -> None:
    document = _zip({
        "word/document.xml": (
            f"<w:document {WORD}><w:body>"
            '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Install</w:t></w:r></w:p>'
            "<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Run</w:t></w:r>"
            "<w:r><w:t> &lt;script&gt;</w:t></w:r></w:p>"
            "<w:p><w:pPr><w:numPr/></w:pPr><w:r><w:t>Step one</w:t></w:r></w:p>"
            "<w:p><w:pPr><w:numPr/></w:pPr><w:r><w:t>Step two</w:t></w:r></w:p>"
            "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
            "</w:body></w:document>"
        ),
    })
    html = docx_preview(document)["html"]
    assert "<h2>Install</h2>" in html
    assert "<strong>Run</strong> &lt;script&gt;" in html and "<script>" not in html
    assert "<ul><li>Step one</li><li>Step two</li></ul>" in html
    assert "<table><tr><td>Cell</td></tr></table>" in html


def test_rejects_other_files_and_entity_declarations() -> None:
    with pytest.raises(ArchiveError, match="not a valid Office"):
        office_preview("report.xlsx", b"not a zip")
    with pytest.raises(ArchiveError, match="no preview"):
        office_preview("old.doc", b"")
    bomb = _zip({"word/document.xml": '<!DOCTYPE x [<!ENTITY a "aaaa">]><w:document/>'})
    with pytest.raises(ArchiveError, match="unsupported XML"):
        docx_preview(bomb)
