"""Browse files on the Entropy server, to pick paths for plugin and workflow arguments."""

from __future__ import annotations

import os
import stat
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from core.web.projects import authorization, current_project
from core.web.routes.auth import _current_session

router = APIRouter(prefix="/api/server-files", tags=["server-files"])

# Who may run plugins or workflows reads server files through them already.
BROWSE_PERMISSIONS = ("plugins.execute", "workflows.execute")
MAX_ENTRIES = 2000


def _roots() -> List[str]:
    if os.name == "nt":
        drives = (f"{letter}:\\" for letter in string.ascii_uppercase)
        return [drive for drive in drives if Path(drive).exists()]
    return ["/"]


def _start(request: Request) -> Path:
    """The workspace (where runs keep their files), else the server user's home."""

    paths = getattr(request.app.state.entropy_context, "paths", None)
    workspace = getattr(getattr(paths, "workspace", None), "root", None)
    if workspace and Path(workspace).is_dir():
        return Path(workspace)
    return Path.home()


def _entry(path: Path) -> Optional[Dict[str, Any]]:
    try:
        info = path.stat()
    except OSError:
        # A dangling link or one we may not look at.
        return None
    directory = stat.S_ISDIR(info.st_mode)
    return {
        "name": path.name,
        "path": str(path),
        "kind": "directory" if directory else "file",
        "size": None if directory else info.st_size,
        "modified": datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(),
        "readable": os.access(path, os.R_OK),
    }


@router.get("")
def browse(
    request: Request,
    response: Response,
    path: str = Query("", max_length=4096),
    hidden: bool = Query(False),
    record: tuple = Depends(_current_session),
) -> Dict[str, Any]:
    """A directory's folders and files, folders first."""

    _, _, user = record
    project = current_project(request, user)
    checks = authorization(request)
    if user.id is None or not any(
        checks.has_permission(user.id, permission, project["id"])
        for permission in BROWSE_PERMISSIONS
    ):
        raise HTTPException(status_code=403, detail="Permission denied.")

    start = _start(request)
    try:
        target = Path(os.path.expanduser(path.strip())).resolve() if path.strip() else start
    except (OSError, RuntimeError, ValueError):
        raise HTTPException(status_code=422, detail="That is not a valid path.") from None
    # A file: show its folder with the file selected.
    selected = None
    if target.is_file():
        selected, target = str(target), target.parent
    if not target.is_dir():
        raise HTTPException(
            status_code=404, detail=f"{target} is not a folder on the Entropy server."
        )

    entries: List[Dict[str, Any]] = []
    truncated = False
    try:
        children = sorted(target.iterdir(), key=lambda item: item.name.lower())
    except PermissionError:
        raise HTTPException(
            status_code=403, detail=f"The Entropy server may not read {target}."
        ) from None
    except OSError as exc:
        raise HTTPException(status_code=422, detail=f"{target} cannot be read: {exc}") from None
    for child in children:
        if not hidden and child.name.startswith("."):
            continue
        entry = _entry(child)
        if entry is None:
            continue
        if len(entries) >= MAX_ENTRIES:
            truncated = True
            break
        entries.append(entry)
    entries.sort(key=lambda item: (item["kind"] != "directory", item["name"].lower()))

    response.headers["Cache-Control"] = "no-store"
    return {
        "path": str(target),
        "parent": str(target.parent) if target.parent != target else None,
        "home": str(start),
        "roots": _roots(),
        "separator": os.sep,
        "selected": selected,
        "entries": entries,
        "truncated": truncated,
    }
