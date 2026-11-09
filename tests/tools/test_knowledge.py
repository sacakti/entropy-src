"""The knowledge base: entries, their history, search, attachments and who may do what."""

from __future__ import annotations

import asyncio
import io
import struct
import zipfile
import zlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, UploadFile

from core.web.routes import knowledge as routes
from lib.authorization.constants import PERMISSIONS
from lib.authorization.projects import BUILTIN_ROLES, PROJECT_PERMISSIONS
from lib.database.connection import DatabaseConnection
from lib.knowledge import store as store_module
from lib.knowledge.docx import DocxError, DocxImage, read_docx, write_docx
from lib.knowledge.markdown import convert_markdown
from lib.knowledge.store import KnowledgeError, KnowledgeStore

PROJECT, OTHER_PROJECT = 2, 3
ARAVINTHAN, PRAVIN, READER, STRANGER = 1, 2, 3, 4
NAMES = {ARAVINTHAN: "aravinthan", PRAVIN: "pravin", READER: "rita", STRANGER: "sam"}


@pytest.fixture()
def connection(tmp_path: Path) -> DatabaseConnection:
    connection = DatabaseConnection(tmp_path / "entropy.db")
    with connection.transaction():
        connection.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, full_name TEXT,"
            " is_active INTEGER NOT NULL DEFAULT 1)"
        )
        for user_id, name in NAMES.items():
            connection.execute(
                "INSERT INTO users (id, username, full_name) VALUES (?, ?, ?)",
                (user_id, name, name.title()),
            )
    return connection


# ----------------------------------------------------------------------
# Store
# ----------------------------------------------------------------------


def _entry(store: KnowledgeStore, project: int = PROJECT, **values: Any) -> Dict[str, Any]:
    base = {
        "title": "Rotated the APP1 password",
        "body": "# Steps\n1. Stop **the app**\n2. Change it",
        "location": "SIT",
        "happened_on": "2026-11-07",
        "happened_time": "21:30",
        "people": ["pravin", "Vendor DBA"],
        "tags": ["Oracle", "password", "oracle"],
        "reference": "CHG-1042",
    }
    return store.create(project, {**base, **values}, "aravinthan")


def test_an_entry_keeps_what_where_when_how_and_who(connection) -> None:
    store = KnowledgeStore(connection)
    entry = _entry(store)

    assert entry["title"] == "Rotated the APP1 password" and entry["location"] == "SIT"
    assert (entry["happened_on"], entry["happened_time"]) == ("2026-11-07", "21:30")
    assert entry["people"] == ["pravin", "Vendor DBA"]
    # Tags are lower case, each once.
    assert entry["tags"] == ["oracle", "password"]
    assert entry["created_by"] == entry["updated_by"] == "aravinthan"


@pytest.mark.parametrize(
    "values, message",
    [
        ({"title": "  "}, "title"),
        ({"happened_on": "07/11/2026"}, "date"),
        ({"happened_time": "9pm"}, "HH:MM"),
        ({"tags": ["no<tags>"]}, "tag"),
        ({"tags": [f"t{index}" for index in range(21)]}, "at most"),
    ],
)
def test_values_an_entry_cannot_hold_are_refused(connection, values, message) -> None:
    with pytest.raises(KnowledgeError, match=message):
        _entry(KnowledgeStore(connection), **values)


def test_each_save_keeps_the_version_it_replaced(connection) -> None:
    store = KnowledgeStore(connection)
    entry = _entry(store)

    store.update(entry["id"], {"body": "Changed"}, "pravin")
    updated = store.update(entry["id"], {"title": "Rotated it again", "tags": ["db"]}, "rita")
    # Saving without a change keeps no version.
    store.update(entry["id"], {"title": "Rotated it again"}, "rita")

    assert updated["updated_by"] == "rita"
    assert [revision["edited_by"] for revision in updated["revisions"]] == ["pravin", "aravinthan"]
    first = store.revision(updated["revisions"][-1]["id"])
    assert first["body"].startswith("# Steps") and first["tags"] == ["oracle", "password"]
    assert len(store.get(entry["id"])["revisions"]) == 2


def test_only_the_newest_versions_are_kept(connection, monkeypatch) -> None:
    monkeypatch.setattr(store_module, "MAX_REVISIONS", 3)
    store = KnowledgeStore(connection)
    entry = _entry(store)
    for index in range(6):
        store.update(entry["id"], {"body": f"version {index}"}, "pravin")

    kept = store.get(entry["id"])["revisions"]
    assert len(kept) == 3
    assert store.revision(kept[0]["id"])["body"] == "version 4"


def test_search_finds_every_word_anywhere_and_filters_narrow(connection) -> None:
    store = KnowledgeStore(connection)
    _entry(store)
    _entry(
        store,
        title="Restarted payments",
        location="PROD",
        tags=["restart"],
        people=["rita"],
        body="Rolled **pods** one by one",
        happened_on="2026-10-01",
    )
    _entry(store, project=OTHER_PROJECT, title="Rotated elsewhere")

    def titles(**filters: Any) -> List[str]:
        return [item["title"] for item in store.list(PROJECT, **filters)]

    assert titles() == ["Rotated the APP1 password", "Restarted payments"]
    assert titles(query="pods one") == ["Restarted payments"]
    assert titles(query="vendor stop") == ["Rotated the APP1 password"]
    assert titles(tag="restart") == ["Restarted payments"]
    assert titles(location="prod") == ["Restarted payments"]
    assert titles(person="pravin") == ["Rotated the APP1 password"]
    assert titles(start="2026-11-01") == ["Rotated the APP1 password"]
    assert titles(end="2026-10-31") == ["Restarted payments"]
    # Wildcards typed are text, not patterns.
    assert titles(query="%") == [] and titles(query="_") == []
    listed = store.list(PROJECT)[0]
    assert "body" not in listed and listed["excerpt"] == "Steps Stop the app Change it"


def test_facets_offer_what_the_project_uses(connection) -> None:
    store = KnowledgeStore(connection)
    _entry(store)
    _entry(store, location="PROD", tags=["restart"], people=["rita"])

    assert store.facets(PROJECT) == {
        "tags": ["oracle", "password", "restart"],
        "locations": ["PROD", "SIT"],
        "people": ["pravin", "rita", "Vendor DBA"],
    }


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------


@pytest.fixture()
def world(connection, monkeypatch, tmp_path) -> SimpleNamespace:
    """Aravinthan writes and deletes, Pravin writes, Rita only reads, Sam is not in it."""

    grants = {
        ARAVINTHAN: {"knowledge.read", "knowledge.write", "knowledge.delete"},
        PRAVIN: {"knowledge.read", "knowledge.write"},
        READER: {"knowledge.read"},
        STRANGER: set(),
    }
    state = SimpleNamespace(project=PROJECT, sent=[])
    context = SimpleNamespace(
        database_manager=SimpleNamespace(connection=connection),
        authorization=SimpleNamespace(
            has_permission=lambda user_id, name, project: name in grants[user_id]
        ),
        bootstrap=SimpleNamespace(home=str(tmp_path / "home")),
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(entropy_context=context)))

    def require(request, user, permission, project_id):
        if permission not in grants[user.id]:
            raise HTTPException(status_code=403, detail="Permission denied.")

    def notify(context, user_id, title, message="", level="info", source=None):
        state.sent.append({"user": user_id, "title": title, "source": source})

    monkeypatch.setattr(routes, "require", require)
    monkeypatch.setattr(routes, "current_project", lambda request, user: {"id": state.project})
    monkeypatch.setattr("lib.database.repositories.notifications.notify_user", notify)
    state.request = request
    state.home = tmp_path / "home"
    return state


def _record(user_id: int) -> tuple:
    return ("token", MagicMock(), SimpleNamespace(id=user_id, username=NAMES[user_id]))


def _list(world, actor: int) -> Dict[str, Any]:
    # Called directly, the route's Query() defaults are not filled in.
    return routes.list_entries(
        world.request,
        q=None,
        tag=None,
        location=None,
        person=None,
        start=None,
        end=None,
        record=_record(actor),
    )


def _create(world, actor: int = ARAVINTHAN, **values: Any) -> Dict[str, Any]:
    payload = routes.EntryValues(title=values.pop("title", "Rotated it"), **values)
    return routes.create_entry(payload, world.request, _record(actor))


def test_readers_read_writers_write_and_only_some_delete(world) -> None:
    entry = _create(world, PRAVIN, body="How", people=["rita"])

    listing = _list(world, READER)
    assert [item["id"] for item in listing["items"]] == [entry["id"]]
    assert listing["permissions"] == {"knowledge.write": False, "knowledge.delete": False}
    assert {member["username"] for member in listing["members"]} == {"aravinthan", "pravin", "rita"}

    for call in (
        lambda: _create(world, READER),
        lambda: routes.update_entry(
            entry["id"], routes.EntryValues(title="x"), world.request, _record(READER)
        ),
        lambda: routes.delete_entry(entry["id"], world.request, _record(PRAVIN)),
        lambda: _list(world, STRANGER),
    ):
        with pytest.raises(HTTPException) as caught:
            call()
        assert caught.value.status_code == 403

    routes.delete_entry(entry["id"], world.request, _record(ARAVINTHAN))
    assert _list(world, READER)["items"] == []


def test_an_entry_of_another_project_does_not_exist(world) -> None:
    entry = _create(world)
    world.project = OTHER_PROJECT
    with pytest.raises(HTTPException) as caught:
        routes.get_entry(entry["id"], world.request, _record(ARAVINTHAN))
    assert caught.value.status_code == 404


def test_people_named_or_mentioned_are_told_once(world) -> None:
    entry = _create(world, people=["pravin", "Outside Vendor"], body="Ask @rita next time")

    told = sorted(item["user"] for item in world.sent)
    assert told == [PRAVIN, READER]
    assert world.sent[0]["source"] == f"knowledge:{entry['id']}"

    world.sent.clear()
    routes.update_entry(
        entry["id"],
        routes.EntryValues(body="Ask @rita and @aravinthan"),
        world.request,
        _record(PRAVIN),
    )
    # Rita was named already; Aravinthan is new; nobody hears about themselves.
    assert [item["user"] for item in world.sent] == [ARAVINTHAN]


def _upload(world, entry_id: int, actor: int, name: str, data: bytes, kind: str) -> Dict[str, Any]:
    upload = UploadFile(io.BytesIO(data), filename=name, headers={"content-type": kind})  # type: ignore[arg-type]
    return asyncio.run(routes.upload_attachments(entry_id, world.request, [upload], _record(actor)))


def test_attachments_are_kept_and_served_safely(world) -> None:
    entry = _create(world)
    result = _upload(world, entry["id"], PRAVIN, "../shot.png", b"\x89PNG", "image/png")
    [added] = result["added"]
    assert added["filename"] == "shot.png" and "storage_name" not in added
    assert result["entry"]["attachments"][0]["id"] == added["id"]

    image = routes.download_attachment(entry["id"], added["id"], world.request, _record(READER))
    assert image.media_type == "image/png" and "inline" in image.headers["content-disposition"]

    page = _upload(world, entry["id"], PRAVIN, "page.html", b"<script>", "text/html")["added"][0]
    served = routes.download_attachment(entry["id"], page["id"], world.request, _record(READER))
    # HTML is never shown in the browser from here.
    assert served.media_type == "application/octet-stream"
    assert served.headers["content-disposition"].startswith("attachment")

    # Someone else's file needs the right to delete; the uploader removes their own.
    with pytest.raises(HTTPException):
        routes.delete_attachment(entry["id"], added["id"], world.request, _record(READER))
    routes.delete_attachment(entry["id"], added["id"], world.request, _record(PRAVIN))
    files = list((world.home / "knowledge-attachments" / str(PROJECT)).iterdir())
    assert len(files) == 1

    routes.delete_entry(entry["id"], world.request, _record(ARAVINTHAN))
    assert list((world.home / "knowledge-attachments" / str(PROJECT)).iterdir()) == []


def test_earlier_versions_are_read_through_their_entry(world) -> None:
    entry = _create(world, body="first")
    updated = routes.update_entry(
        entry["id"], routes.EntryValues(body="second"), world.request, _record(PRAVIN)
    )
    [revision] = updated["revisions"]

    old = routes.get_revision(entry["id"], revision["id"], world.request, _record(READER))
    assert old["body"] == "first"

    other = _create(world, title="Another")
    with pytest.raises(HTTPException) as caught:
        routes.get_revision(other["id"], revision["id"], world.request, _record(READER))
    assert caught.value.status_code == 404


def test_the_permissions_exist_and_roles_hold_them() -> None:
    names = {item.name for item in PERMISSIONS}
    assert {"knowledge.read", "knowledge.write", "knowledge.delete"} <= names
    assert {"knowledge.read", "knowledge.write", "knowledge.delete"} <= PROJECT_PERMISSIONS
    viewer, operator, developer, maintainer = (
        set(BUILTIN_ROLES[name][3]) for name in ("viewer", "operator", "developer", "maintainer")
    )
    assert "knowledge.read" in viewer and "knowledge.write" not in viewer
    assert "knowledge.write" in operator and "knowledge.delete" not in developer
    assert "knowledge.delete" in maintainer


# ======================================================================
# Versions, export (HTML, PDF, Word) and import (Word, Markdown)
# ======================================================================

BODY = (
    "# Steps\n\nRun **bold** *it* ++under++ ~~gone~~ `ls -l` and C++\n\n"
    "1. one\n2. two\n\n- [ ] todo\n- [x] done\n\n"
    "| Env | Ok |\n| --- | --- |\n| SIT | **yes** |\n\n"
    "```\nselect 1;\n  indented\n```\n\n##### Small\n\n\\# not a heading"
)


def _png(width: int = 20, height: int = 10) -> bytes:
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


# ----------------------------------------------------------------------
# Versions
# ----------------------------------------------------------------------


def test_versions_count_up_and_a_restore_is_the_newest(connection) -> None:
    store = KnowledgeStore(connection)
    entry = store.create(2, {"title": "First", "body": "one"}, "aravinthan")
    assert entry["version"] == 1

    second = store.update(entry["id"], {"body": "two"}, "pravin")
    unchanged = store.update(entry["id"], {"body": "two"}, "pravin")
    assert second["version"] == unchanged["version"] == 2
    [kept] = second["revisions"]
    assert kept["version"] == 1

    restored = store.restore(entry["id"], kept["id"], "rita")
    assert restored["version"] == 3 and restored["body"] == "one"
    assert [item["version"] for item in restored["revisions"]] == [2, 1]


def test_restoring_through_the_route_needs_write(world) -> None:
    entry = _create(world, body="one")
    updated = routes.update_entry(
        entry["id"], routes.EntryValues(body="two"), world.request, _record(PRAVIN)
    )
    revision = updated["revisions"][0]["id"]
    with pytest.raises(HTTPException) as caught:
        routes.restore_revision(entry["id"], revision, world.request, _record(READER))
    assert caught.value.status_code == 403
    restored = routes.restore_revision(entry["id"], revision, world.request, _record(PRAVIN))
    assert (restored["version"], restored["body"]) == (3, "one")


# ----------------------------------------------------------------------
# Export
# ----------------------------------------------------------------------


def _export(world, entry_id: int, format: str, revision: Any = None):  # noqa: A002
    return routes.export_entry(
        entry_id, world.request, format=format, revision=revision, record=_record(READER)
    )


def test_an_entry_exports_as_html_pdf_and_word(world) -> None:
    entry = _create(
        world, title="Rotated <b>it</b>", body=BODY, location="SIT", people=["pravin"], tags=["db"]
    )

    html = _export(world, entry["id"], "html")
    page = html.body.decode()
    assert html.media_type.startswith("text/html")
    assert 'filename="Rotated-b-it-b-v1.html"' in html.headers["content-disposition"]
    assert "Rotated &lt;b&gt;it&lt;/b&gt;" in page and "<b>it</b>" not in page
    assert "<u>under</u>" in page and "<s>gone</s>" in page and "Pravin" in page

    pdf = _export(world, entry["id"], "pdf")
    assert pdf.body.startswith(b"%PDF") and pdf.media_type == "application/pdf"

    word = _export(world, entry["id"], "docx")
    with zipfile.ZipFile(io.BytesIO(word.body)) as archive:
        document = archive.read("word/document.xml").decode()
    assert '<w:u w:val="single"/>' in document and "Heading5" in document
    assert "Rotated &lt;b&gt;it&lt;/b&gt;" in document


def test_an_earlier_version_exports_as_it_read(world) -> None:
    entry = _create(world, body="first words")
    updated = routes.update_entry(
        entry["id"], routes.EntryValues(body="second words"), world.request, _record(PRAVIN)
    )
    revision = updated["revisions"][0]["id"]

    page = _export(world, entry["id"], "html", revision).body.decode()
    assert "first words" in page and "second words" not in page
    other = _create(world, title="Other")
    with pytest.raises(HTTPException) as caught:
        _export(world, other["id"], "html", revision)
    assert caught.value.status_code == 404


# ----------------------------------------------------------------------
# Word
# ----------------------------------------------------------------------


def test_word_round_trips_the_description_and_its_images() -> None:
    body = BODY + "\n\n![Login screen](attachment:7)"
    data = write_docx(
        title="Rotated",
        subtitle="Knowledge base · app1",
        facts=[("Where", "SIT")],
        body=body,
        images=lambda attachment_id: DocxImage(_png(), "shot.png") if attachment_id == 7 else None,
    )

    document = read_docx(data, "fallback")

    assert document.title == "Rotated"
    # The header line and the facts table are the export's own: they stay out of the text.
    assert "Knowledge base" not in document.body and "Where" not in document.body
    for part in (
        "# Steps",
        "Run **bold** *it* ++under++ ~~gone~~ `ls -l` and C++",
        # Word numbers the items itself: each comes back as "1.", which reads as 1, 2.
        "1. one\n1. two",
        "- [ ] todo\n- [x] done",
        "| Env | Ok |\n| --- | --- |\n| SIT | **yes** |",
        "```\nselect 1;\n  indented\n```",
        "##### Small",
        "\\# not a heading",
        "[[entropy-image-0]]",
    ):
        assert part in document.body, part
    [image] = document.images
    assert image.caption == "Login screen" and image.data == _png()


def test_a_file_that_is_not_word_is_refused() -> None:
    with pytest.raises(DocxError):
        read_docx(b"not a zip", "x")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("hello.txt", "hi")
    with pytest.raises(DocxError, match="document.xml"):
        read_docx(buffer.getvalue(), "x")


# ----------------------------------------------------------------------
# Markdown
# ----------------------------------------------------------------------


def test_markdown_becomes_a_description() -> None:
    source = (
        "Runbook\n=======\n\nWith __bold__, _italic_, snake_case_name, <u>under</u>,"
        " a [link](https://x.io) and <script>x</script>.\n\nSteps\n-----\n\n1) Stop\n2) Start\n\n"
        "* item\n\n> quoted\n\n###### Deep\n\n---\n\n```bash\n# kept as code\n```\n\n"
        "![diagram](img/d.png)"
    )

    title, body = convert_markdown(source, "file")

    assert title == "Runbook"
    assert "**bold**, *italic*, snake_case_name, ++under++, a link (https://x.io)" in body
    assert "<script>" not in body
    assert "## Steps" in body and "1. Stop\n2. Start" in body and "- item" in body
    assert "\nquoted\n" in f"\n{body}\n" and "##### Deep" in body
    assert "```bash\n# kept as code\n```" in body and "diagram (img/d.png)" in body


def _import(world, name: str, data: bytes, actor: int = PRAVIN) -> Dict[str, Any]:
    upload = UploadFile(io.BytesIO(data), filename=name)
    return asyncio.run(routes.import_entry(world.request, upload, _record(actor)))


def test_importing_makes_a_first_version_with_the_images_in_place(world) -> None:
    data = write_docx(
        title="Imported runbook",
        subtitle="",
        facts=[],
        body="Before\n\n![Login](attachment:1)\n\nAfter",
        images=lambda attachment_id: DocxImage(_png(), "a.png"),
    )

    entry = _import(world, "runbook.docx", data)

    assert entry["title"] == "Imported runbook" and entry["version"] == 1
    assert entry["revisions"] == [] and entry["reference"] == "runbook.docx"
    [attachment] = entry["attachments"]
    assert attachment["filename"] == "Login.png"
    assert f"![Login](attachment:{attachment['id']})" in entry["body"]
    served = routes.download_attachment(
        entry["id"], attachment["id"], world.request, _record(READER)
    )
    assert served.media_type == "image/png"

    markdown = _import(world, "notes.md", b"# Notes\n\nSome *text*.")
    assert (markdown["title"], markdown["body"]) == ("Notes", "Some *text*.")


@pytest.mark.parametrize("name, status", [("notes.pdf", 422), ("bad.docx", 422)])
def test_other_files_cannot_be_imported(world, name, status) -> None:
    with pytest.raises(HTTPException) as caught:
        _import(world, name, b"plain bytes")
    assert caught.value.status_code == status


def test_reading_only_cannot_import(world) -> None:
    with pytest.raises(HTTPException) as caught:
        _import(world, "notes.md", b"# x", actor=READER)
    assert caught.value.status_code == 403
