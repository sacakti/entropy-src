"""The task report as a real PDF file, images included, with no browser involved."""

from __future__ import annotations

import re
import struct
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.web.routes import tasks as routes
from lib.pdf.document import text_width, wrap_proportional
from lib.pdf.images import MAX_UNPACKED_PIXELS, _unfilter, load_image
from lib.tasks.report_pdf import build_pdf

MEMBERS = [{"username": "will", "full_name": "Will Writer"}]


def _chunk(kind: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(kind + data)
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)


def _png(width, height, color, rows, *, bits=8, interlace=0, palette=b"") -> bytes:
    header = struct.pack(">IIBBBBB", width, height, bits, color, 0, 0, interlace)
    plte = _chunk(b"PLTE", palette) if palette else b""
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + plte
        + _chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + _chunk(b"IEND", b"")
    )


RGB = _png(2, 1, 2, [b"\x00\x01\x02\x03\x04\x05\x06"])
RGBA = _png(1, 2, 6, [b"\x00\x0a\x14\x1e\xff", b"\x00\x28\x32\x3c\x00"])
JPEG = (
    b"\xff\xd8\xff\xe0\x00\x04\x00\x00"
    + b"\xff\xc0\x00\x0b\x08\x00\x20\x00\x40\x03\x00\x00\x00"
    + b"\xff\xd9"
)


def _text(pdf: bytes) -> str:
    drawn = []
    for stream in re.findall(rb"/FlateDecode >>\nstream\n(.*?)\nendstream", pdf, re.S):
        try:
            content = zlib.decompress(stream).decode("ascii")
        except (zlib.error, UnicodeDecodeError):
            continue
        for part in re.findall(r"<([0-9a-f]*)> Tj", content):
            drawn.append(bytes.fromhex(part).decode("cp1252"))
    return "\n".join(drawn)


def _pages(pdf: bytes) -> int:
    return int(re.search(rb"/Count (\d+)", pdf)[1])


def _task(number=1, **extra):
    return {
        "id": number,
        "key": f"APP-{number}",
        "title": f"Task {number}",
        "status": "todo",
        "description": "",
        "group_ids": [],
        **extra,
    }


def _build(tmp_path: Path, tasks, *, groups=(), attachments=None) -> bytes:
    return build_pdf(
        project="Payments",
        scope="All tasks",
        tasks=tasks,
        groups=groups,
        members=MEMBERS,
        attachments=attachments or {},
        attachment_root=tmp_path,
        generated_by="Admin",
    )


def _attached(tmp_path: Path, name: str, data: bytes, number=9, **extra):
    (tmp_path / name).write_bytes(data)
    return {
        "id": number,
        "filename": name,
        "storage_name": name,
        "size_bytes": len(data),
        **extra,
    }


# ----------------------------------------------------------------------
# Images
# ----------------------------------------------------------------------


def test_a_jpeg_goes_in_as_it_is() -> None:
    image = load_image(JPEG)

    assert (image.width, image.height) == (64, 32)
    assert image.color_space == "/DeviceRGB" and "/DCTDecode" in image.extra
    assert image.data == JPEG


def test_a_png_without_transparency_is_not_unpacked() -> None:
    image = load_image(RGB)

    assert (image.width, image.height, image.bits) == (2, 1, 8)
    assert "/Predictor 15" in image.extra and image.mask is None


def test_transparency_becomes_a_separate_mask() -> None:
    image = load_image(RGBA)

    assert zlib.decompress(image.data) == bytes([10, 20, 30, 40, 50, 60])
    assert zlib.decompress(image.mask) == bytes([255, 0])


def test_a_grey_image_with_transparency_is_split_too() -> None:
    image = load_image(_png(2, 1, 4, [b"\x00\x10\x20\x30\x40"]))

    assert image.color_space == "/DeviceGray"
    assert zlib.decompress(image.data) == bytes([0x10, 0x30])
    assert zlib.decompress(image.mask) == bytes([0x20, 0x40])


def test_a_palette_image_keeps_its_colours() -> None:
    image = load_image(_png(1, 1, 3, [b"\x00\x00"], palette=b"\xff\x00\x00"))

    assert image.color_space == "[/Indexed /DeviceRGB 0 <ff0000>]"


@pytest.mark.parametrize(
    ("kind", "row", "expected"),
    [
        (0, [5, 6], [5, 6]),
        (1, [5, 6], [5, 11]),
        (2, [5, 6], [15, 26]),
        (3, [5, 6], [10, 6 + (10 + 20) // 2]),
        (4, [5, 6], [15, 6 + 20]),
    ],
)
def test_each_png_filter_is_undone(kind, row, expected) -> None:
    raw = bytes([0, 10, 20, kind, *row])

    assert list(_unfilter(raw, 2, 2, 1)[2:]) == expected


def test_a_filter_wraps_around_at_a_byte() -> None:
    assert list(_unfilter(bytes([1, 200, 100]), 2, 1, 1)) == [200, 44]


@pytest.mark.parametrize(
    "data",
    [
        b"GIF89a....",
        b"RIFF....WEBP",
        b"<svg></svg>",
        b"",
        b"\x89PNG\r\n\x1a\nbroken",
        b"\xff\xd8broken",
        _png(1, 1, 2, [b"\x00\x01\x02\x03"], interlace=1),
        _png(1, 1, 6, [b"\x00\x01"]),  # too little data
        _png(1, 1, 6, [b"\x09\x01\x02\x03\x04"]),  # unknown filter
    ],
)
def test_what_cannot_be_embedded_is_refused_not_an_error(data) -> None:
    assert load_image(data) is None


def test_a_huge_transparent_image_is_not_unpacked() -> None:
    side = int(MAX_UNPACKED_PIXELS**0.5) + 1

    assert load_image(_png(side, side, 6, [b""])) is None


def test_measured_text_never_overflows_and_long_words_are_cut() -> None:
    text = "short words then " + "x" * 300 + " end"

    lines = wrap_proportional(text, "regular", 10, 200)

    assert all(text_width(line, "regular", 10) <= 200 for line in lines)
    assert "".join(lines).replace(" ", "") == text.replace(" ", "")


# ----------------------------------------------------------------------
# The report
# ----------------------------------------------------------------------


def test_the_file_is_a_valid_pdf(tmp_path) -> None:
    image = _attached(tmp_path, "a.png", RGBA)
    pdf = _build(tmp_path, [_task()], attachments={1: [image]})

    assert pdf.startswith(b"%PDF-1.4") and pdf.endswith(b"%%EOF\n")
    start = int(re.search(rb"startxref\n(\d+)", pdf)[1])
    assert pdf[start:].startswith(b"xref")
    for number, offset in enumerate(re.findall(rb"(\d{10}) 00000 n ", pdf[start:]), start=1):
        assert pdf[int(offset) :].startswith(f"{number} 0 obj".encode())


def test_it_shows_what_the_html_report_shows(tmp_path) -> None:
    task = _task(
        title="Fix the login",
        status="in_progress",
        assignee="will",
        creator="admin",
        external_ref="JIRA-7",
        severity="high",
        type="bug",
        due_date="2000-01-01",
        description="Broken since `/etc/app.conf` changed.",
        remarks="Handle with care.",
        group_ids=[5],
        comments=[{"author": "pravin", "created_at": "2026-01-02T03:04:05", "body": "On it."}],
        history=[
            {
                "from_status": None,
                "to_status": "todo",
                "changed_at": "2026-01-01T00:00",
                "changed_by": "admin",
            },
            {
                "from_status": "todo",
                "to_status": "in_progress",
                "changed_at": "2026-01-02T00:00",
                "changed_by": "will",
                "reason": "Started",
            },
        ],
    )

    text = _text(
        _build(
            tmp_path,
            [task, _task(2, title="Loose end")],
            groups=[{"id": 5, "name": "Release 2.4", "kind": "release", "description": "Spring"}],
        )
    )

    for expected in (
        "ENTROPY · TASK REPORT",
        "Payments",
        "APP-1",
        "Fix the login",
        "In progress",
        "Will Writer",
        "JIRA-7",
        "Bug",
        "High",
        "Overdue",
        "Release 2.4",
        "Release",
        "Spring",
        "Not in a group",
        "Loose end",
        "DESCRIPTION",
        "/etc/app.conf",
        "REMARKS",
        "Handle with care.",
        "COMMENTS",
        "On it.",
        "STATUS HISTORY",
        "Reason: Started",
        "Contents",
        "0/1 closed",
    ):
        assert expected in text, expected


def test_the_contents_name_the_page_each_group_starts_on(tmp_path) -> None:
    groups = [{"id": n, "name": f"Group {n}"} for n in (1, 2)]
    tasks = [_task(1, group_ids=[1]), _task(2, group_ids=[2])]

    text = _text(_build(tmp_path, tasks, groups=groups))

    assert "page 2" in text and "page 3" in text
    assert "Page 3 of 3" in text


def test_one_group_has_no_contents(tmp_path) -> None:
    assert "Contents" not in _text(_build(tmp_path, [_task()]))


def test_an_empty_report_says_so(tmp_path) -> None:
    pdf = _build(tmp_path, [])

    assert "No tasks to report." in _text(pdf) and _pages(pdf) == 1


def test_a_png_attachment_is_embedded_with_its_mask(tmp_path) -> None:
    pdf = _build(tmp_path, [_task()], attachments={1: [_attached(tmp_path, "shot.png", RGBA)]})

    assert b"/Subtype /Image" in pdf and b"/SMask" in pdf
    assert "shot.png" in _text(pdf) and "ATTACHMENTS (1)" in _text(pdf)


def test_an_image_used_in_the_description_is_not_listed_again(tmp_path) -> None:
    attachment = _attached(tmp_path, "shot.jpg", JPEG)
    task = _task(description="Before\n\n![The error](attachment:9)\n\nAfter")

    pdf = _build(tmp_path, [task], attachments={1: [attachment]})
    text = _text(pdf)

    assert pdf.count(b"/DCTDecode") == 1
    assert "ATTACHMENTS" not in text
    assert "The error · shot.jpg" in text
    assert text.index("Before") < text.index("The error") < text.index("After")


def test_a_removed_attachment_is_noted_in_place(tmp_path) -> None:
    task = _task(description="![Gone](attachment:77)")

    assert "[Gone — removed]" in _text(_build(tmp_path, [task]))


def test_a_text_file_is_shown_and_long_ones_shortened(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("lib.tasks.report_pdf.MAX_TEXT_BYTES", 10)
    attachment = _attached(
        tmp_path, "run.log", b"line <one>\nsecond line", content_type="text/plain"
    )

    text = _text(_build(tmp_path, [_task()], attachments={1: [attachment]}))

    assert "line <one>" in text and "second" not in text and "… shortened" in text


def test_a_video_is_named_rather_than_played(tmp_path) -> None:
    attachment = _attached(tmp_path, "demo.mp4", b"video", content_type="video/mp4")

    text = _text(_build(tmp_path, [_task()], attachments={1: [attachment]}))

    assert "demo.mp4" in text and "play it in the HTML report" in text


def test_an_image_it_cannot_embed_points_to_the_html_report(tmp_path) -> None:
    attachment = _attached(tmp_path, "a.gif", b"GIF89a", content_type="image/gif")

    pdf = _build(tmp_path, [_task()], attachments={1: [attachment]})

    assert "see the HTML report" in _text(pdf) and b"/Subtype /Image" not in pdf


def test_a_linked_file_shows_its_address(tmp_path) -> None:
    attachment = {"id": 3, "filename": "spec", "url": "https://example.test/spec"}

    assert "https://example.test/spec" in _text(
        _build(tmp_path, [_task()], attachments={1: [attachment]})
    )


def test_files_outside_the_attachments_folder_are_not_read(tmp_path) -> None:
    root = tmp_path / "attachments"
    root.mkdir()
    (tmp_path / "secret.txt").write_text("do not leak")
    attachment = {"id": 3, "filename": "x.txt", "storage_name": "../secret.txt"}

    assert "do not leak" not in _text(_build(root, [_task()], attachments={1: [attachment]}))


def test_a_long_task_flows_over_pages_without_losing_text(tmp_path) -> None:
    body = "\n\n".join(f"Paragraph {n} of a long description." for n in range(300))

    pdf = _build(tmp_path, [_task(description=body)])
    text = _text(pdf)

    assert _pages(pdf) > 2 and text.count("Paragraph") == 300 and "299" in text


def test_characters_the_fonts_lack_do_not_break_it(tmp_path) -> None:
    text = _text(_build(tmp_path, [_task(title="Café 日本語 (ok) \\ end")]))

    assert "Café ??? (ok) \\ end" in text


# ----------------------------------------------------------------------
# The route
# ----------------------------------------------------------------------


@pytest.fixture
def world(tmp_path, monkeypatch) -> SimpleNamespace:
    store = SimpleNamespace(
        list=lambda project: [_task()],
        groups=lambda project: [],
        attachments=lambda task: [],
    )
    denied = set()

    def require(request, user, permission, project=None):
        if permission in denied:
            raise routes.HTTPException(status_code=403, detail="Permission denied.")

    monkeypatch.setattr(
        routes, "current_project", lambda request, user: {"id": 1, "name": "Payments"}
    )
    monkeypatch.setattr(routes, "require", require)
    monkeypatch.setattr(routes, "_store", lambda request: store)
    monkeypatch.setattr(routes, "_members", lambda request, project: MEMBERS)
    monkeypatch.setattr(routes, "_attachment_root", lambda request, project: tmp_path)
    return SimpleNamespace(
        denied=denied,
        record=("session", "token", SimpleNamespace(id=1, username="me", full_name="Me")),
    )


def _call(world, format):
    return routes.task_report(SimpleNamespace(), "all", "", None, format, world.record)


def test_the_pdf_downloads_as_a_file(world) -> None:
    response = _call(world, "pdf")

    assert response.media_type == "application/pdf" and response.body.startswith(b"%PDF-")
    assert re.fullmatch(
        r'attachment; filename="task-report-\d{8}-\d{4}\.pdf"',
        response.headers["content-disposition"],
    )


def test_the_html_report_still_downloads_and_never_prints(world) -> None:
    response = _call(world, "html")

    assert response.body.startswith(b"<!doctype html>")
    assert b"window.print" not in response.body
    assert response.headers["content-disposition"].endswith('.html"')


def test_a_report_needs_access_to_tasks(world) -> None:
    world.denied.add("tasks.read")

    with pytest.raises(routes.HTTPException) as caught:
        _call(world, "pdf")
    assert caught.value.status_code == 403
