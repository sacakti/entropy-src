"""
Extensions: Python libraries for plugins (third-party and custom), several
versions side by side. Viewing needs extensions.list; installing and
removing need extensions.install.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from packaging.utils import canonicalize_name
from pydantic import BaseModel, Field

from core.web.projects import require
from core.web.routes.auth import _current_session, verify_csrf
from lib.extensions.exceptions import (
    ExtensionError,
    ExtensionExistsError,
    ExtensionNotFoundError,
)
from lib.extensions.resolver import fits, specifier
from lib.models.session import Session
from lib.models.users import User

router = APIRouter(prefix="/api/extensions", tags=["extensions"])

SessionRecord = Tuple[Session, str, User]
MAX_UPLOAD = 200 * 1024 * 1024


class Requirement(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    version: Optional[str] = Field(default=None, max_length=120)


class InstallRequest(Requirement):
    dependencies: bool = True
    index_url: Optional[str] = Field(default=None, max_length=2048)


class CheckRequest(BaseModel):
    requirements: List[Requirement] = Field(default_factory=list, max_length=200)


class InstallMissing(CheckRequest):
    index_url: Optional[str] = Field(default=None, max_length=2048)


def _manager(request: Request) -> Any:
    manager = getattr(request.app.state.entropy_context, "extension_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Extensions are unavailable.")
    return manager


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, ExtensionExistsError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ExtensionNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


def _plugin_requirements(request: Request) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """(plugin, its library requirements) for every installed plugin."""

    plugins = getattr(request.app.state.entropy_context, "plugin_manager", None)
    found = []
    for plugin in plugins.list() if plugins is not None else []:
        try:
            manifest = json.loads((plugin.path / "plugin.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        requirements = [
            {"name": item["name"], "version": item.get("version")}
            for item in manifest.get("dependencies") or []
            if isinstance(item, dict) and item.get("name")
        ]
        if requirements:
            found.append((plugin.qualified_name, requirements))
    return found


def _usage(request: Request, manager: Any) -> Dict[Tuple[str, str], List[str]]:
    """(canonical name, version) -> plugins that use that extension version."""

    usage: Dict[Tuple[str, str], List[str]] = {}
    for plugin, requirements in _plugin_requirements(request):
        for entry in manager.check(requirements):
            if entry["status"] == "extension":
                key = (canonicalize_name(entry["name"]), entry["version"])
                usage.setdefault(key, []).append(plugin)
    return usage


@router.get("")
def list_extensions(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    require(request, record[2], "extensions.list")
    manager = _manager(request)
    usage = _usage(request, manager)
    installed = [
        {**entry, "used_by": usage.get((entry["canonical"], entry["version"]), [])}
        for entry in manager.list()
    ]
    response.headers["Cache-Control"] = "no-store"
    return {"installed": installed, "builtin": manager.builtin()}


@router.post("/check")
def check(
    payload: CheckRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Whether requirements are met: by Entropy, by an extension, or not at all."""

    require(request, record[2], "plugins.read")
    try:
        return {
            "requirements": _manager(request).check(
                [item.model_dump() for item in payload.requirements]
            )
        }
    except ExtensionError as exc:
        raise _error(exc) from None


@router.get("/plugin/{qualified_name}")
def plugin_requirements(
    qualified_name: str,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """A plugin's (installed or draft) library requirements and whether they are met."""

    require(request, record[2], "plugins.read")
    from core.web.plugin_studio.workspace import PluginStudio

    try:
        plugin = PluginStudio(request.app.state.entropy_context)._resolve(qualified_name)
        manifest = json.loads((plugin.path / "plugin.json").read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(status_code=404, detail="Plugin not found.") from None
    requirements = [
        {"name": item["name"], "version": item.get("version")}
        for item in manifest.get("dependencies") or []
        if isinstance(item, dict) and item.get("name")
    ]
    try:
        return {"plugin": qualified_name, "requirements": _manager(request).check(requirements)}
    except ExtensionError as exc:
        raise _error(exc) from None


@router.post("/install", status_code=201)
def install(
    payload: InstallRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, Any]:
    """Install a library from the package index (a version or range; newest by default)."""

    user = record[2]
    require(request, user, "extensions.install")
    try:
        entry = _manager(request).install(
            payload.name,
            payload.version,
            dependencies=payload.dependencies,
            index_url=payload.index_url or None,
            user=user.username,
        )
    except ExtensionError as exc:
        raise _error(exc) from None
    return {"extension": entry}


@router.post("/install-missing")
def install_missing(
    payload: InstallMissing,
    request: Request,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, Any]:
    """Install what a plugin needs and does not have yet (each from the package index)."""

    user = record[2]
    require(request, user, "extensions.install")
    manager = _manager(request)
    installed, failed = [], []
    try:
        missing = manager.missing([item.model_dump() for item in payload.requirements])
    except ExtensionError as exc:
        raise _error(exc) from None
    for entry in missing:
        original = next(
            item
            for item in payload.requirements
            if canonicalize_name(item.name) == canonicalize_name(entry["name"])
        )
        try:
            installed.append(
                manager.install(
                    original.name,
                    original.version,
                    index_url=payload.index_url or None,
                    user=user.username,
                )
            )
        except ExtensionError as exc:
            failed.append({"requirement": entry["requirement"], "error": str(exc)})
    return {"installed": installed, "failed": failed}


@router.post("/upload", status_code=201)
async def upload(
    request: Request,
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    version: Optional[str] = Form(None),
    summary: str = Form(""),
    dependencies: bool = Form(True),
    index_url: Optional[str] = Form(None),
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, Any]:
    """
    Install your own library: a wheel, a source archive, a .py module or a
    zipped package folder (the last two need a name and version).
    """

    from starlette.concurrency import run_in_threadpool

    user = record[2]
    require(request, user, "extensions.install")
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="The file is too large (200 MB at most).")
    manager = _manager(request)
    try:
        entry = await run_in_threadpool(
            manager.install_upload,
            file.filename or "",
            data,
            name=(name or "").strip() or None,
            version=(version or "").strip() or None,
            summary=summary.strip()[:300],
            dependencies=dependencies,
            index_url=(index_url or "").strip() or None,
            user=user.username,
        )
    except ExtensionError as exc:
        raise _error(exc) from None
    return {"extension": entry}


@router.delete("/{name}/{version}")
def remove(
    name: str,
    version: str,
    request: Request,
    force: bool = False,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, Any]:
    """Remove a version; refused while installed plugins have nothing else that fits."""

    require(request, record[2], "extensions.install")
    manager = _manager(request)
    if not force:
        others = [
            entry["version"]
            for entry in manager.store.versions(name)
            if entry["version"] != version
        ]
        from lib.extensions.packages import host_distributions

        host = host_distributions().get(canonicalize_name(name))
        stranded = []
        for plugin, requirements in _plugin_requirements(request):
            for requirement in requirements:
                if canonicalize_name(requirement["name"]) != canonicalize_name(name):
                    continue
                spec = specifier(requirement["version"])
                if not fits(version, spec):
                    continue
                if (host and fits(host, spec)) or any(fits(other, spec) for other in others):
                    continue
                stranded.append(plugin)
        if stranded:
            raise HTTPException(
                status_code=409,
                detail=f"{name} {version} is needed by {', '.join(sorted(set(stranded)))}. "
                "Remove or update those plugins first.",
            )
    try:
        manager.uninstall(name, version)
    except ExtensionError as exc:
        raise _error(exc) from None
    return {"removed": f"{name} {version}"}


@router.post("/{name}/{version}/verify")
def verify(
    name: str,
    version: str,
    request: Request,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, Any]:
    require(request, record[2], "extensions.list")
    try:
        return {"problems": _manager(request).verify(name, version)}
    except ExtensionError as exc:
        raise _error(exc) from None


@router.post("/{name}/{version}/repair")
def repair(
    name: str,
    version: str,
    request: Request,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, Any]:
    require(request, record[2], "extensions.install")
    try:
        return {"extension": _manager(request).repair(name, version)}
    except ExtensionError as exc:
        raise _error(exc) from None
