"""
Project knowledge base API: entries of what was done, where, when, how and by whom,
written with the task description editor, with attachments placed in them.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.web.projects import current_project, require
from core.web.routes.auth import _current_session, verify_csrf
from lib.knowledge.store import KnowledgeError, KnowledgeStore
from lib.models.session import Session
from lib.models.users import User

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
SessionRecord = Tuple[Session, str, User]

MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
MENTION = re.compile(r"(?<![\w@.])@([A-Za-z0-9_.-]+)")
# Shown in the browser rather than downloaded.
INLINE_TYPES = ("image/", "application/pdf", "text/plain")


class EntryValues(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    body: Optional[str] = Field(default=None, max_length=200_000)
    location: Optional[str] = Field(default=None, max_length=120)
    happened_on: Optional[str] = Field(default=None, max_length=10)
    happened_time: Optional[str] = Field(default=None, max_length=5)
    people: Optional[List[str]] = Field(default=None, max_length=50)
    tags: Optional[List[str]] = Field(default=None, max_length=20)
    reference: Optional[str] = Field(default=None, max_length=200)


def _store(request: Request) -> KnowledgeStore:
    return KnowledgeStore(request.app.state.entropy_context.database_manager.connection)


def _project_id(request: Request, user: User, permission: str) -> int:
    project = current_project(request, user)
    require(request, user, permission, project["id"])
    return int(project["id"])


def _entry(request: Request, user: User, entry_id: int, permission: str) -> Dict[str, Any]:
    item = _store(request).get(entry_id)
    project_id = _project_id(request, user, permission)
    if item is None or item["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Entry not found in the current project.")
    return item


def _members(request: Request, project_id: int) -> List[Dict[str, Any]]:
    """Who can read the project's knowledge base: those offered as people and mentions."""

    context = request.app.state.entropy_context
    rows = context.database_manager.connection.fetchall(
        "SELECT id, username, full_name FROM users WHERE is_active = 1"
        " ORDER BY username COLLATE NOCASE"
    )
    return [
        {"id": row["id"], "username": row["username"], "full_name": row["full_name"]}
        for row in rows
        if context.authorization.has_permission(row["id"], "knowledge.read", project_id)
    ]


def _notify(
    request: Request, item: Dict[str, Any], user: User, earlier: Optional[Dict[str, Any]] = None
) -> None:
    """Tell members newly named as taking part, or newly @mentioned, about the entry."""

    def named(entry: Optional[Dict[str, Any]]) -> set:
        if entry is None:
            return set()
        mentioned = {name.lower().rstrip(".") for name in MENTION.findall(entry.get("body") or "")}
        return mentioned | {person.lower() for person in entry.get("people") or []}

    new = named(item) - named(earlier)
    if not new:
        return
    from lib.database.repositories.notifications import notify_user

    context = request.app.state.entropy_context
    for member in _members(request, item["project_id"]):
        if member["username"].lower() in new and member["id"] != user.id:
            notify_user(
                context,
                member["id"],
                f"{user.username} named you in the knowledge base",
                item["title"],
                "info",
                f"knowledge:{item['id']}",
            )


def _values(payload: EntryValues) -> Dict[str, Any]:
    return payload.model_dump(exclude_unset=True)


def _attachment_root(request: Request, project_id: int) -> Path:
    return (
        Path(request.app.state.entropy_context.bootstrap.home)
        / "knowledge-attachments"
        / str(project_id)
    )


# ----------------------------------------------------------------------
# Entries
# ----------------------------------------------------------------------


@router.get("")
def list_entries(
    request: Request,
    q: Optional[str] = Query(default=None, max_length=200),
    tag: Optional[str] = Query(default=None, max_length=40),
    location: Optional[str] = Query(default=None, max_length=120),
    person: Optional[str] = Query(default=None, max_length=200),
    start: Optional[str] = Query(default=None, max_length=10),
    end: Optional[str] = Query(default=None, max_length=10),
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Dict[str, Any]:
    """Entries of the current project, newest first, with what the filters can offer."""

    _, _, user = record
    project_id = _project_id(request, user, "knowledge.read")
    store = _store(request)
    authorization = request.app.state.entropy_context.authorization
    try:
        items = store.list(
            project_id, query=q, tag=tag, location=location, person=person, start=start, end=end
        )
    except KnowledgeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {
        "items": items,
        "facets": store.facets(project_id),
        "members": _members(request, project_id),
        "username": user.username,
        "permissions": {
            name: bool(
                user.id is not None and authorization.has_permission(user.id, name, project_id)
            )
            for name in ("knowledge.write", "knowledge.delete")
        },
    }


@router.get("/{entry_id}")
def get_entry(
    entry_id: int,
    request: Request,
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Dict[str, Any]:
    return _entry(request, record[2], entry_id, "knowledge.read")


@router.post("", status_code=201, dependencies=[Depends(verify_csrf)])
def create_entry(
    payload: EntryValues,
    request: Request,
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Dict[str, Any]:
    _, _, user = record
    project_id = _project_id(request, user, "knowledge.write")
    try:
        item = _store(request).create(project_id, _values(payload), user.username)
    except KnowledgeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    _notify(request, item, user)
    return item


@router.patch("/{entry_id}", dependencies=[Depends(verify_csrf)])
def update_entry(
    entry_id: int,
    payload: EntryValues,
    request: Request,
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Dict[str, Any]:
    _, _, user = record
    earlier = _entry(request, user, entry_id, "knowledge.write")
    try:
        item = _store(request).update(entry_id, _values(payload), user.username)
    except KnowledgeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    _notify(request, item, user, earlier)
    return item


@router.delete("/{entry_id}", status_code=204, dependencies=[Depends(verify_csrf)])
def delete_entry(
    entry_id: int,
    request: Request,
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Response:
    _, _, user = record
    item = _entry(request, user, entry_id, "knowledge.delete")
    root = _attachment_root(request, item["project_id"])
    for attachment in _store(request).delete(entry_id):
        target = (root / attachment["storage_name"]).resolve()
        if root.resolve() in target.parents:
            target.unlink(missing_ok=True)
    return Response(status_code=204)


@router.get("/{entry_id}/revisions/{revision_id}")
def get_revision(
    entry_id: int,
    revision_id: int,
    request: Request,
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Dict[str, Any]:
    """An earlier version of the entry, as it read then."""

    _entry(request, record[2], entry_id, "knowledge.read")
    revision = _store(request).revision(revision_id)
    if revision is None or revision["entry_id"] != entry_id:
        raise HTTPException(status_code=404, detail="That version is not kept.")
    return revision


# ----------------------------------------------------------------------
# Attachments
# ----------------------------------------------------------------------


@router.post("/{entry_id}/attachments", status_code=201, dependencies=[Depends(verify_csrf)])
async def upload_attachments(
    entry_id: int,
    request: Request,
    files: List[UploadFile] = File(...),  # noqa: B008
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Dict[str, Any]:
    _, _, user = record
    item = _entry(request, user, entry_id, "knowledge.write")
    store = _store(request)
    root = _attachment_root(request, item["project_id"])
    root.mkdir(parents=True, exist_ok=True)
    added: List[Dict[str, Any]] = []
    for upload in files[:20]:
        name = Path((upload.filename or "").replace("\\", "/")).name.strip()[:255]
        if not name or name in {".", ".."}:
            raise HTTPException(status_code=400, detail="Choose files with valid names.")
        storage_name = f"{entry_id}-{uuid.uuid4().hex}{''.join(Path(name).suffixes)[-32:]}"
        temporary = root / f".{storage_name}.part"
        size = 0
        try:
            with temporary.open("xb") as output:
                while chunk := await upload.read(CHUNK_BYTES):
                    size += len(chunk)
                    if size > MAX_ATTACHMENT_BYTES:
                        raise HTTPException(
                            status_code=413, detail=f"'{name}' is larger than 50 MiB."
                        )
                    output.write(chunk)
            if size == 0:
                raise HTTPException(status_code=400, detail=f"'{name}' is empty.")
            os.replace(temporary, root / storage_name)
            added.append(
                store.add_attachment(
                    entry_id, name, upload.content_type, size, storage_name, user.username
                )
            )
        finally:
            temporary.unlink(missing_ok=True)
            await upload.close()
    return {
        "entry": store.get(entry_id),
        "added": [
            {key: value for key, value in item.items() if key != "storage_name"} for item in added
        ],
    }


def _attachment(
    request: Request, user: User, entry_id: int, attachment_id: int, permission: str
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    item = _entry(request, user, entry_id, permission)
    attachment = _store(request).get_attachment(attachment_id)
    if attachment is None or attachment["entry_id"] != entry_id:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    return item, attachment


@router.get("/{entry_id}/attachments/{attachment_id}")
def download_attachment(
    entry_id: int,
    attachment_id: int,
    request: Request,
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Response:
    item, attachment = _attachment(request, record[2], entry_id, attachment_id, "knowledge.read")
    root = _attachment_root(request, item["project_id"])
    target = (root / attachment["storage_name"]).resolve()
    if root.resolve() not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="The attachment file is missing.")
    media_type = attachment.get("content_type") or "application/octet-stream"
    # Images and PDFs open in the browser; anything else is a download. Never HTML.
    inline = media_type.startswith(INLINE_TYPES) and "svg" not in media_type
    return FileResponse(
        target,
        filename=attachment["filename"],
        media_type=media_type if inline else "application/octet-stream",
        content_disposition_type="inline" if inline else "attachment",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.delete(
    "/{entry_id}/attachments/{attachment_id}",
    status_code=204,
    dependencies=[Depends(verify_csrf)],
)
def delete_attachment(
    entry_id: int,
    attachment_id: int,
    request: Request,
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Response:
    _, _, user = record
    item, attachment = _attachment(request, user, entry_id, attachment_id, "knowledge.write")
    # The uploader removes their own files; others need the right to delete entries.
    if attachment["uploaded_by"].lower() != user.username.lower():
        require(request, user, "knowledge.delete", item["project_id"])
    root = _attachment_root(request, item["project_id"])
    target = (root / attachment["storage_name"]).resolve()
    if root.resolve() in target.parents:
        target.unlink(missing_ok=True)
    _store(request).delete_attachment(attachment_id)
    return Response(status_code=204)


# ----------------------------------------------------------------------
# Versions, export and import
# ----------------------------------------------------------------------

MAX_IMPORT_BYTES = 50 * 1024 * 1024
EXPORT_TYPES = {
    "html": "text/html; charset=utf-8",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.post("/{entry_id}/revisions/{revision_id}/restore", dependencies=[Depends(verify_csrf)])
def restore_revision(
    entry_id: int,
    revision_id: int,
    request: Request,
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Dict[str, Any]:
    """Save an earlier version again as the newest; the one it replaces is kept."""

    _, _, user = record
    _entry(request, user, entry_id, "knowledge.write")
    try:
        return _store(request).restore(entry_id, revision_id, user.username)
    except KnowledgeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.get("/{entry_id}/export")
def export_entry(
    entry_id: int,
    request: Request,
    format: str = Query(default="pdf", pattern="^(html|pdf|docx)$"),  # noqa: A002
    revision: Optional[int] = Query(default=None),
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Response:
    """The entry (or one of its earlier versions) as an HTML, PDF or Word file."""

    from lib.knowledge.docx import DocxImage, write_docx
    from lib.knowledge.export import export_html, export_pdf, fields, file_name

    _, _, user = record
    entry = _entry(request, user, entry_id, "knowledge.read")
    store = _store(request)
    if revision is not None:
        earlier = store.revision(revision)
        if earlier is None or earlier["entry_id"] != entry_id:
            raise HTTPException(status_code=404, detail="That version is not kept.")
        # The version as it read then, under its own number, author and date.
        entry = {
            **entry,
            **{key: value for key, value in earlier.items() if key not in ("id", "entry_id")},
            "version": earlier.get("version") or "earlier",
            "updated_by": earlier["edited_by"],
            "updated_at": earlier["edited_at"],
        }
    attachments = [store.get_attachment(item["id"]) or item for item in store.attachments(entry_id)]
    root = _attachment_root(request, entry["project_id"])
    project = current_project(request, user)
    project_name = str(project.get("name") or project.get("key") or "")
    members = {
        member["username"].lower(): member.get("full_name") or member["username"]
        for member in _members(request, entry["project_id"])
    }

    if format == "html":
        content: bytes = export_html(entry, attachments, root, members, project_name).encode()
    elif format == "pdf":
        content = export_pdf(entry, attachments, root, members, project_name)
    else:
        by_id = {item["id"]: item for item in attachments}

        def image(attachment_id: int) -> Optional[DocxImage]:
            item = by_id.get(attachment_id)
            if not item or not item.get("storage_name"):
                return None
            path = (root / item["storage_name"]).resolve()
            if root.resolve() not in path.parents or not path.is_file():
                return None
            return DocxImage(path.read_bytes(), item["filename"])

        content = write_docx(
            title=entry["title"],
            subtitle=f"Knowledge base · {project_name}",
            facts=fields(entry, members),
            body=entry.get("body") or "",
            images=image,
            author=members.get(user.username.lower(), user.username),
        )
    name = file_name(entry, format)
    return Response(
        content=content,
        media_type=EXPORT_TYPES[format],
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/import", status_code=201, dependencies=[Depends(verify_csrf)])
async def import_entry(
    request: Request,
    file: UploadFile = File(...),  # noqa: B008
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Dict[str, Any]:
    """
    A new entry from a Word (.docx) or Markdown (.md) file: its first heading (or Title)
    names it, and a Word document's images become its attachments, in place.
    """

    from lib.knowledge.docx import IMAGE_TOKEN, DocxError, read_docx
    from lib.knowledge.markdown import convert_markdown

    _, _, user = record
    project_id = _project_id(request, user, "knowledge.write")
    name = Path((file.filename or "").replace("\\", "/")).name.strip()
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if extension not in ("docx", "md", "markdown", "txt"):
        raise HTTPException(status_code=422, detail="Import a Word (.docx) or Markdown (.md) file.")
    data = await file.read(MAX_IMPORT_BYTES + 1)
    await file.close()
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="The file is larger than 50 MiB.")
    stem = name.rsplit(".", 1)[0] or "Imported"

    images = []
    try:
        if extension == "docx":
            document = read_docx(data, stem)
            title, body, images = document.title, document.body, document.images
        else:
            title, body = convert_markdown(data.decode("utf-8-sig", errors="replace"), stem)
    except DocxError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    store = _store(request)
    try:
        entry = store.create(
            project_id, {"title": title, "body": body, "reference": name[:200]}, user.username
        )
    except KnowledgeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    if images:
        root = _attachment_root(request, project_id)
        root.mkdir(parents=True, exist_ok=True)
        for index, image in enumerate(images):
            storage_name = (
                f"{entry['id']}-{uuid.uuid4().hex}.{image.filename.rsplit('.', 1)[-1][:10]}"
            )
            (root / storage_name).write_bytes(image.data)
            filename = image.filename
            if image.caption:
                # Named after its caption, keeping the image's own extension.
                named = re.sub(r"[^A-Za-z0-9 ._-]+", "", image.caption).strip()[:80] or "image"
                filename = f"{named}.{image.filename.rsplit('.', 1)[-1]}"
            added = store.add_attachment(
                entry["id"],
                filename,
                image.content_type,
                len(image.data),
                storage_name,
                user.username,
            )
            caption = (image.caption or filename).replace("]", " ")
            body = body.replace(
                IMAGE_TOKEN.format(index=index), f"![{caption}](attachment:{added['id']})"
            )
        # Placing the images is not a version of its own.
        entry = store.set_imported_body(entry["id"], body)
    return entry
