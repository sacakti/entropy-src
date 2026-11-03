"""Task descriptions: read alike by the server and the browser, and shown in the reports."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import zlib
from pathlib import Path

import pytest

from lib.tasks.markup import parse_blocks, parse_inline, plain_text
from lib.tasks.report import build_report
from lib.tasks.report_pdf import build_pdf

HERE = Path(__file__).parent
CASES = json.loads((HERE / "fixtures" / "task_markup.json").read_text(encoding="utf-8"))


def _blocks(name: str):
    return parse_blocks(next(case["text"] for case in CASES if case["name"] == name))


def test_the_common_forms_are_read() -> None:
    assert [(b["level"], b["text"]) for b in _blocks("headings") if b["type"] == "heading"] == [
        (1, "One"),
        (2, "Two"),
        (3, "Three"),
    ]
    [checklist] = _blocks("checklist")
    assert [item["checked"] for item in checklist["items"]] == [False, True, True, False, None]
    [_, _] = numbered = _blocks("numbered")
    assert numbered[0]["start"] == 3 and numbered[1]["ordered"] is False


def test_a_table_has_every_row_as_wide_as_its_headings() -> None:
    table, after = _blocks("table")

    assert table["header"] == ["A", "B"]
    assert table["rows"] == [["1", "**2**"], ["only", ""], ["x", "y"]]
    assert after == {"type": "paragraph", "text": "after"}


def test_an_escaped_pipe_stays_in_its_cell() -> None:
    [table] = _blocks("table pipes")

    assert table["rows"] == [["1 | 2", "3"]]


def test_pipes_without_a_rule_are_only_text() -> None:
    assert all(block["type"] != "table" for block in _blocks("not a table"))


def test_a_code_block_is_taken_as_it_is_even_unclosed() -> None:
    code, after, unclosed = _blocks("code")

    assert code["text"] == "# not a heading\n**raw**"
    assert after["text"] == "after" and unclosed == {"type": "code", "text": "unclosed"}


def test_attachments_split_the_text_around_them() -> None:
    kinds = [(b["type"], b.get("id")) for b in _blocks("attachments")]

    assert kinds == [
        ("paragraph", None),
        ("attachment", 7),
        ("paragraph", None),
        ("attachment", 8),
        ("list", None),
    ]


def test_list_items_know_their_line_to_be_ticked_from_the_view() -> None:
    [_, _, checklist] = parse_blocks("## S\ntext\n\n- [ ] a\n- [x] b")

    assert [item["line"] for item in checklist["items"]] == [3, 4]


def test_inline_styles_nest() -> None:
    assert parse_inline("**a *b* c**") == [
        {"bold": True, "text": "a "},
        {"bold": True, "italic": True, "text": "b"},
        {"bold": True, "text": " c"},
    ]
    assert parse_inline("***x***") == [{"bold": True, "italic": True, "text": "x"}]


@pytest.mark.parametrize("text", ["2 * 3 * 4", "snake_case_name", "a ** b", "~ ~", "* not closed"])
def test_ordinary_text_stays_as_written(text) -> None:
    assert parse_inline(text) == [{"text": text}]


def test_plain_text_has_no_markers() -> None:
    text = "# Head\n**bold** ~~x~~\n- [x] done\n| A |\n|---|\n| `b` |\n![c](attachment:1)"

    assert plain_text(text) == "Head\nbold x\n[x] done\nA\nb"


def test_the_browser_reads_every_case_the_same() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed.")
    version = subprocess.run([node, "--version"], capture_output=True, text=True, check=True).stdout
    if int(version.lstrip("v").split(".")[0]) < 23:
        pytest.skip("This Node cannot run TypeScript directly.")
    result = subprocess.run(
        [
            node,
            "--no-warnings",
            str(HERE / "task_markup_parity.mts"),
            str(HERE / "fixtures" / "task_markup.json"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    for read, case in zip(json.loads(result.stdout), CASES, strict=True):
        assert read["blocks"] == parse_blocks(case["text"]), case["name"]
        assert read["inline"] == parse_inline(case["text"]), case["name"]
        assert read["plain"] == plain_text(case["text"]), case["name"]


def test_the_editors_changes_to_the_text(tmp_path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed.")
    version = subprocess.run([node, "--version"], capture_output=True, text=True, check=True).stdout
    if int(version.lstrip("v").split(".")[0]) < 23:
        pytest.skip("This Node cannot run TypeScript directly.")
    # Node needs file extensions on imports, which the frontend's build does not allow.
    source = HERE.parents[1] / "frontend/src/features/tools/tasks"
    shutil.copy(source / "markup.ts", tmp_path / "markup.ts")
    edit = (source / "markupEdit.ts").read_text(encoding="utf-8")
    (tmp_path / "markupEdit.ts").write_text(edit.replace("'./markup'", "'./markup.ts'"), "utf-8")
    result = subprocess.run(
        [
            node,
            "--no-warnings",
            str(HERE / "task_markup_edit.mts"),
            str(tmp_path / "markupEdit.ts"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


# ----------------------------------------------------------------------
# In the reports
# ----------------------------------------------------------------------


FORMATTED = """# Summary
## Steps
### Detail
Plain with **bold**, *italic*, ~~gone~~ and `code`.

- [x] Done item
- [ ] Open item
- Bullet
1. First

| Env | State |
|---|---|
| UAT | **ok** |

```
raw **text**
```
"""


def _task(description=FORMATTED):
    return {
        "id": 1,
        "key": "APP-1",
        "title": "T",
        "status": "todo",
        "description": description,
        "group_ids": [],
    }


def _args(tmp_path, task):
    return dict(
        project="P",
        scope="All",
        tasks=[task],
        groups=[],
        members=[],
        attachments={},
        attachment_root=tmp_path,
        generated_by="Me",
    )


def test_the_html_report_shows_the_formatting(tmp_path) -> None:
    page = build_report(**_args(tmp_path, _task()))

    for expected in (
        '<div class="md-h1">Summary</div>',
        '<div class="md-h2">Steps</div>',
        "<strong>bold</strong>",
        "<em>italic</em>",
        "<s>gone</s>",
        "<code>code</code>",
        '<input type="checkbox" disabled checked>',
        '<table class="md-table">',
        "<strong>ok</strong>",
        'class="md-code">raw **text**</pre>',
    ):
        assert expected in page, expected
    assert "**bold**" not in page and "- [x]" not in page


def test_the_html_report_escapes_everything(tmp_path) -> None:
    bad = "<script>x</script>"
    forms = ["# {}", "{}", "- {}", "- [ ] {}", "| {} |\n|---|\n| {} |", "```\n{}\n```", "**{}**"]
    text = "\n".join(form.replace("{}", bad) for form in forms)

    page = build_report(**_args(tmp_path, _task(text)))

    assert "<script" not in page


def _drawn(pdf: bytes) -> str:
    text = []
    for stream in re.findall(rb"/FlateDecode >>\nstream\n(.*?)\nendstream", pdf, re.S):
        content = zlib.decompress(stream).decode("ascii")
        for part in re.findall(r"<([0-9a-f]*)> Tj", content):
            text.append(bytes.fromhex(part).decode("cp1252"))
    return "\n".join(text)


def test_the_pdf_shows_the_formatting_without_its_markers(tmp_path) -> None:
    pdf = build_pdf(**_args(tmp_path, _task()))
    text = _drawn(pdf)

    for expected in ("Summary", "Steps", "bold", "italic", "gone", "Done", "Bullet", "UAT", "ok"):
        assert expected in text, expected
    assert "raw **text**" in text  # a code block stays as written
    assert "**bold**" not in text and "- [x]" not in text and "| UAT" not in text
    for font in (b"/Helvetica-Bold", b"/Helvetica-Oblique", b"/Courier"):
        assert font in pdf


def test_the_pdf_draws_each_style_in_its_own_font(tmp_path) -> None:
    pdf = build_pdf(**_args(tmp_path, _task("**thick** *slanted* ***both*** `mono` plain")))
    streams = re.findall(rb"/FlateDecode >>\nstream\n(.*?)\nendstream", pdf, re.S)
    content = "\n".join(zlib.decompress(stream).decode("ascii") for stream in streams)

    def font_of(word: str) -> str:
        pattern = rf"/(F\d) [\d.]+ Tf [^<]*<{word.encode('cp1252').hex()}> Tj"
        return re.search(pattern, content)[1]

    assert font_of("plain") == "F1"
    assert font_of("thick") == "F2"
    assert font_of("mono") == "F3"
    assert font_of("slanted") == "F4"
    assert font_of("both") == "F5"
    # F4 and F5 are the slanted fonts, in that order.
    assert re.search(rb"/F4 (\d+) 0 R", pdf) and pdf.index(b"Oblique") < pdf.index(b"BoldOblique")


def test_a_wide_and_long_table_flows_over_pages(tmp_path) -> None:
    rows = "\n".join(f"| row {n} | {'long words ' * 12} | c |" for n in range(120))
    pdf = build_pdf(**_args(tmp_path, _task(f"| A | B | C |\n|---|---|---|\n{rows}")))
    text = _drawn(pdf)

    assert int(re.search(rb"/Count (\d+)", pdf)[1]) > 2
    assert "119" in text and text.count("\nA\n") > 1  # the headings come again on new pages


def test_reminders_do_not_show_the_markers() -> None:
    source = (Path(__file__).parents[2] / "lib/runs/background.py").read_text(encoding="utf-8")

    assert 'plain_text(task["description"] or "")' in source
    assert "plain_text(task['description'] or '')" in source
