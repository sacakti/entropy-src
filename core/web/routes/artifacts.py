"""Project artifact inventory and package upload endpoints."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.web.projects import current_project, require
from core.web.routes.auth import _current_session, verify_csrf
from lib.artifacts.store import ArtifactStore
from lib.models.session import Session
from lib.models.users import User

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])
SessionRecord = Tuple[Session, str, User]
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
MAX_BULK_DOWNLOAD_BYTES = 10 * 1024 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024


class ServerPathCreate(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    tags: List[str] = Field(default_factory=list, max_length=20)


class TagsUpdate(BaseModel):
    tags: List[str] = Field(default_factory=list, max_length=20)


class ArtifactSelection(BaseModel):
    artifact_ids: List[int] = Field(min_length=1, max_length=500)


class ArtifactHousekeeping(BaseModel):
    older_than_days: int = Field(ge=1, le=36500)
    classification: str
    tag: str = Field(default="", max_length=50)


def _clean_tags(values: List[str]) -> List[str]:
    tags: List[str] = []
    seen = set()
    for value in values:
        tag = value.strip()
        if not tag:
            continue
        if len(tag) > 50:
            raise HTTPException(status_code=422, detail="Tags must be 50 characters or fewer.")
        key = tag.casefold()
        if key not in seen:
            tags.append(tag)
            seen.add(key)
    if len(tags) > 20:
        raise HTTPException(status_code=422, detail="An artifact can have at most 20 tags.")
    return tags


def _system_tags(item: Dict[str, Any]) -> List[str]:
    run_id = item.get("run_id")
    return ["run:" + hashlib.sha256(str(run_id).encode("utf-8")).hexdigest()[:16]] if run_id else []


def _store(request: Request) -> ArtifactStore:
    return ArtifactStore(request.app.state.entropy_context.database_manager.connection)


def _project(request: Request, user: User, permission: str) -> Dict[str, Any]:
    project = current_project(request, user)
    require(request, user, permission, project["id"])
    return project


def _root(request: Request, project_id: int) -> Path:
    context = request.app.state.entropy_context
    return Path(context.bootstrap.home) / "artifacts" / str(project_id)


def _public(item: Dict[str, Any], root: Path) -> Dict[str, Any]:
    result = {key: value for key, value in item.items() if key != "storage_name"}
    try:
        result["tags"] = json.loads(item.get("tags") or "[]")
    except (TypeError, ValueError):
        result["tags"] = []
    result["path"] = item.get("server_path") if item["source"] == "server_path" else str(root / item["storage_name"])
    result["download_url"] = f"/api/artifacts/{item['id']}/download"
    return result


def _file_path(item: Dict[str, Any], root: Path) -> Path:
    if item["source"] == "upload":
        target = (root / item["storage_name"]).resolve()
        if root.resolve() not in target.parents:
            raise HTTPException(status_code=404, detail="Artifact file is unavailable.")
    else:
        target = Path(item["server_path"] or "").resolve()
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"Artifact file '{item['name']}' is missing or unavailable.")
    return target


def _delete_item(item: Dict[str, Any], root: Path, store: ArtifactStore) -> None:
    if item["source"] == "upload" and item.get("storage_name"):
        target = (root / item["storage_name"]).resolve()
        if root.resolve() in target.parents:
            target.unlink(missing_ok=True)
    store.delete(item["id"])


@router.get("")
def list_artifacts(request: Request, record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project = _project(request, user, "artifacts.read")
    root = _root(request, project["id"])
    items = [_public(item, root) for item in _store(request).list(project["id"])]
    assert user.id is not None
    return {"items": items, "permissions": {
        "artifacts.write": request.app.state.entropy_context.authorization.has_permission(user.id, "artifacts.write", project["id"]),
    }}


@router.post("/upload", status_code=201, dependencies=[Depends(verify_csrf)])
async def upload_artifact(request: Request, file: UploadFile = File(...), tags: str = Form(""),
                          record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project = _project(request, user, "artifacts.write")
    name = Path((file.filename or "").replace("\\", "/")).name.strip()
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Choose a file with a valid name.")
    root = _root(request, project["id"])
    root.mkdir(parents=True, exist_ok=True)
    extension = "".join(Path(name).suffixes)[-64:]
    storage_name = f"{uuid.uuid4().hex}{extension}"
    target = root / storage_name
    temporary = root / f".{storage_name}.part"
    size = 0
    digest = hashlib.sha256()
    try:
        with temporary.open("xb") as output:
            while chunk := await file.read(CHUNK_BYTES):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Artifacts cannot exceed 2 GiB.")
                digest.update(chunk)
                output.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="The selected artifact is empty.")
        os.replace(temporary, target)
        item = _store(request).create(project["id"], name, "upload", size, user.username,
                                      storage_name=storage_name, sha256=digest.hexdigest(),
                                      tags=json.dumps(_clean_tags(tags.split(",")), ensure_ascii=False))
        return _public(item, root)
    except Exception:
        temporary.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@router.post("/server-path", status_code=201, dependencies=[Depends(verify_csrf)])
def register_server_path(payload: ServerPathCreate, request: Request,
                         record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project = _project(request, user, "artifacts.write")
    try:
        source = Path(os.path.expanduser(payload.path.strip())).resolve(strict=True)
        if not source.is_file():
            raise HTTPException(status_code=422, detail="The path must point to a file on the Entropy server.")
        stat = source.stat()
        with source.open("rb") as handle:
            os.read(handle.fileno(), 1)
    except HTTPException:
        raise
    except (OSError, RuntimeError, ValueError):
        raise HTTPException(status_code=422, detail="The Entropy server cannot access that file path.") from None
    item = _store(request).create(project["id"], source.name, "server_path", stat.st_size,
                                  user.username, server_path=str(source),
                                  tags=json.dumps(_clean_tags(payload.tags), ensure_ascii=False))
    return _public(item, _root(request, project["id"]))


@router.get("/{artifact_id}/download")
def download_artifact(artifact_id: int, request: Request,
                      record: SessionRecord = Depends(_current_session)) -> FileResponse:
    _, _, user = record
    project = _project(request, user, "artifacts.read")
    item = _store(request).get(artifact_id)
    if item is None or item["project_id"] != project["id"]:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    target = _file_path(item, _root(request, project["id"]))
    return FileResponse(target, filename=item["name"], headers={"Cache-Control": "no-store"})


@router.post("/bulk-download", dependencies=[Depends(verify_csrf)])
def download_selected(payload: ArtifactSelection, request: Request,
                      record: SessionRecord = Depends(_current_session)) -> FileResponse:
    _, _, user = record
    project = _project(request, user, "artifacts.read")
    store = _store(request)
    items = []
    for artifact_id in dict.fromkeys(payload.artifact_ids):
        item = store.get(artifact_id)
        if item is None or item["project_id"] != project["id"]:
            raise HTTPException(status_code=404, detail="One or more selected artifacts were not found.")
        items.append(item)
    root = _root(request, project["id"])
    files = [(item, _file_path(item, root)) for item in items]
    total_size = sum(path.stat().st_size for _, path in files)
    if total_size > MAX_BULK_DOWNLOAD_BYTES:
        raise HTTPException(status_code=413, detail="The selected artifacts exceed the 10 GiB bulk download limit.")
    archive_dir = Path(request.app.state.entropy_context.bootstrap.home) / "tmp"
    archive_dir.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(prefix="entropy-artifacts-", suffix=".zip", dir=archive_dir, delete=False)
    archive_path = Path(handle.name)
    handle.close()
    try:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for item, path in files:
                archive.write(path, arcname=f"{item['id']}-{Path(item['name']).name}")
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise
    from starlette.background import BackgroundTask
    return FileResponse(archive_path, filename="entropy-artifacts.zip", media_type="application/zip",
                        headers={"Cache-Control": "no-store"},
                        background=BackgroundTask(lambda: archive_path.unlink(missing_ok=True)))


@router.post("/housekeeping", dependencies=[Depends(verify_csrf)])
def artifact_housekeeping(payload: ArtifactHousekeeping, request: Request,
                          record: SessionRecord = Depends(_current_session)) -> Dict[str, int]:
    _, _, user = record
    project = _project(request, user, "artifacts.write")
    if payload.classification not in {"added", "generated"}:
        raise HTTPException(status_code=422, detail="Classification must be added or generated.")
    connection = request.app.state.entropy_context.database_manager.connection
    rows = connection.fetchall(
        "SELECT * FROM artifacts WHERE project_id = ? AND classification = ? "
        "AND created_at < datetime('now', ?)",
        (project["id"], payload.classification, f"-{payload.older_than_days} days"),
    )
    wanted_tag = payload.tag.strip().casefold()
    matching = []
    for row in rows:
        item = dict(row)
        try:
            item_tags = json.loads(item.get("tags") or "[]")
        except (TypeError, ValueError):
            item_tags = []
        if not wanted_tag or any(str(tag).casefold() == wanted_tag for tag in item_tags):
            matching.append(item)
    store = _store(request)
    root = _root(request, project["id"])
    for item in matching:
        _delete_item(item, root, store)
    return {"deleted": len(matching)}


@router.post("/bulk-delete", status_code=200, dependencies=[Depends(verify_csrf)])
def delete_selected(payload: ArtifactSelection, request: Request,
                    record: SessionRecord = Depends(_current_session)) -> Dict[str, int]:
    _, _, user = record
    project = _project(request, user, "artifacts.write")
    store = _store(request)
    items = []
    for artifact_id in dict.fromkeys(payload.artifact_ids):
        item = store.get(artifact_id)
        if item is None or item["project_id"] != project["id"]:
            raise HTTPException(status_code=404, detail="One or more selected artifacts were not found.")
        items.append(item)
    root = _root(request, project["id"])
    for item in items:
        _delete_item(item, root, store)
    return {"deleted": len(items)}


@router.patch("/{artifact_id}/tags", dependencies=[Depends(verify_csrf)])
def update_artifact_tags(artifact_id: int, payload: TagsUpdate, request: Request,
                         record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project = _project(request, user, "artifacts.write")
    item = _store(request).get(artifact_id)
    if item is None or item["project_id"] != project["id"]:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    tags = _clean_tags([*_system_tags(item), *payload.tags])
    updated = _store(request).set_tags(artifact_id, json.dumps(tags, ensure_ascii=False))
    return _public(updated, _root(request, project["id"]))


@router.delete("/{artifact_id}", status_code=204, dependencies=[Depends(verify_csrf)])
def delete_artifact(artifact_id: int, request: Request,
                    record: SessionRecord = Depends(_current_session)) -> None:
    _, _, user = record
    project = _project(request, user, "artifacts.write")
    item = _store(request).get(artifact_id)
    if item is None or item["project_id"] != project["id"]:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    _delete_item(item, _root(request, project["id"]), _store(request))
