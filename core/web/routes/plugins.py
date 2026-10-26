"""
Installed plugin inventory and browser plugin development API.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.web.plugin_studio.analysis import Diagnostic
from core.web.plugin_studio.contract import plugin_contract
from core.web.plugin_studio.docs import plugin_docs
from core.web.plugin_studio.sdk import build_catalog
from core.web.plugin_studio.workspace import (
    PluginStudio,
    PluginStudioError,
    PluginValidationFailed,
)
from core.web.routes.auth import _current_session, verify_csrf
from core.web.routes.workflows import _require_permission
from lib.history import DefinitionHistory
from lib.plugins.exceptions import InvalidPluginNameError, PluginNotFoundError

router = APIRouter(
    prefix="/api/plugins",
    tags=["plugins"],
)


def _plugin_manager(request: Request) -> Any:
    """Return the PluginManager owned by the active Entropy context."""

    context = getattr(
        request.app.state,
        "entropy_context",
        None,
    )

    if context is None:
        raise HTTPException(
            status_code=503,
            detail="Entropy context is not available.",
        )

    manager = getattr(
        context,
        "plugin_manager",
        None,
    )

    if manager is None:
        raise HTTPException(
            status_code=503,
            detail="Plugin manager is not available.",
        )

    return manager


def _serialize_plugin(plugin: Any) -> dict[str, Any]:
    """Serialize fields supported by the plugin registry."""

    installed_at = getattr(
        plugin,
        "installed_at",
        None,
    )

    if isinstance(installed_at, datetime):
        installed_at = installed_at.isoformat()

    return {
        "id": plugin.id,
        "namespace": plugin.namespace,
        "name": plugin.name,
        "qualified_name": (f"{plugin.namespace}.{plugin.name}"),
        "version": plugin.version,
        "enabled": bool(plugin.enabled),
        "installed_at": installed_at,
        # Drafts are saved but not installed; workflows cannot use them.
        "draft": bool(getattr(plugin, "draft", False)),
    }


@router.get("")
def list_plugins(
    request: Request,
    session_record: tuple = Depends(_current_session),
    q: str = Query(
        default="",
        max_length=200,
    ),
    enabled: Optional[bool] = Query(
        default=None,
    ),
    draft: Optional[bool] = Query(
        default=None,
    ),
    namespace: str = Query(
        default="",
        max_length=200,
    ),
    sort_by: str = Query(
        default="name",
        pattern="^(name|namespace|version|enabled|installed_at)$",
    ),
    order: str = Query(
        default="asc",
        pattern="^(asc|desc)$",
    ),
    page: int = Query(
        default=1,
        ge=1,
    ),
    page_size: int = Query(
        default=10,
        ge=1,
        le=10,
    ),
) -> JSONResponse:
    """List installed plugins with search, sorting, and pagination."""

    _, _, user = session_record

    _require_permission(
        request,
        user,
        "plugins.read",
    )

    manager = _plugin_manager(request)

    try:
        plugins = manager.list()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve installed plugins.",
        ) from exc

    items = [_serialize_plugin(plugin) for plugin in [*plugins, *_studio(request).drafts()]]

    summary = {
        "total": len(items),
        "enabled": sum(1 for item in items if item["enabled"]),
        "drafts": sum(1 for item in items if item["draft"]),
        "namespaces": sorted(
            {item["namespace"] for item in items},
            key=str.casefold,
        ),
    }

    search = q.strip().casefold()

    if search:
        items = [
            item
            for item in items
            if search in item["name"].casefold()
            or search in item["namespace"].casefold()
            or search in item["qualified_name"].casefold()
            or search in item["version"].casefold()
        ]

    if namespace:
        items = [item for item in items if item["namespace"] == namespace]

    if enabled is not None:
        items = [item for item in items if item["enabled"] is enabled and not item["draft"]]

    if draft is not None:
        items = [item for item in items if item["draft"] is draft]

    def sort_key(item: dict[str, Any]) -> tuple[bool, str]:
        value = item.get(sort_by)

        if value is None:
            return True, ""

        return False, str(value).casefold()

    items.sort(
        key=sort_key,
        reverse=order == "desc",
    )

    total = len(items)
    total_pages = (total + page_size - 1) // page_size
    start = (page - 1) * page_size

    paged_items = items[start : start + page_size]

    return JSONResponse(
        content={
            "items": paged_items,
            "summary": summary,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
            },
        },
        headers={
            "Cache-Control": "no-store",
        },
    )


# ----------------------------------------------------------------------
# Plugin development
# ----------------------------------------------------------------------


class PluginCreateRequest(BaseModel):
    """A new plugin scaffolded from the plugin template."""

    namespace: str = Field(max_length=64)
    name: str = Field(max_length=64)
    description: str = Field(default="", max_length=200)
    install: bool = False


class PluginNamesRequest(BaseModel):
    """Several plugins, for bulk export."""

    names: list[str] = Field(min_length=1, max_length=500)


class PluginFilesRequest(BaseModel):
    """Changed plugin files keyed by plugin-relative path."""

    files: Dict[str, str]
    # Files to delete (moving a file is a new path plus the old one removed).
    removed: List[str] = Field(default_factory=list, max_length=1000)


class PluginSaveRequest(PluginFilesRequest):
    """Changed files plus the revision they were edited from."""

    revision: str
    install: bool = False


def _history(request: Request) -> DefinitionHistory:
    connection = request.app.state.entropy_context.database_manager.connection
    return DefinitionHistory(connection, "plugin")


def _keep(request: Request, qualified_name: str, user: Any, reason: str = "edit"):
    """A studio backup callback recording the replaced files in the history."""

    history = _history(request)

    def backup(files: dict, version: str) -> None:
        history.record(qualified_name, version, files, user=user.username, reason=reason)

    return backup


def _studio(request: Request) -> PluginStudio:
    _plugin_manager(request)  # 503 when the plugin subsystem is unavailable
    return PluginStudio(request.app.state.entropy_context)


def _diagnostics(items: list[Diagnostic]) -> list[dict[str, Any]]:
    return [item.to_dict() for item in items]


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, PluginValidationFailed):
        return HTTPException(
            status_code=422,
            detail={
                "message": str(exc),
                "diagnostics": _diagnostics(exc.diagnostics),
            },
        )

    if isinstance(exc, PluginStudioError):
        return HTTPException(status_code=exc.status_code, detail=str(exc))

    if isinstance(exc, PluginNotFoundError):
        return HTTPException(status_code=404, detail="Plugin not found.")

    if isinstance(exc, InvalidPluginNameError):
        return HTTPException(status_code=422, detail=str(exc))

    return HTTPException(status_code=422, detail=str(exc))


def _files_payload(result: dict[str, Any]) -> dict[str, Any]:
    root = Path(result["plugin"].path)

    def info(path: str, content: str) -> dict[str, Any]:
        entry: dict[str, Any] = {"path": path, "content": content}
        try:
            stat = (root / path).stat()
            entry["size"] = stat.st_size
            entry["modified"] = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
        except OSError:
            entry["size"] = len(content.encode("utf-8"))
        return entry

    return {
        "plugin": _serialize_plugin(result["plugin"]),
        "files": [info(path, content) for path, content in result["files"].items()],
        "revision": result["revision"],
    }


@router.get("/updates")
def bundled_updates(
    request: Request,
    response: Response,
    session_record: tuple = Depends(_current_session),
) -> dict[str, Any]:
    """Plugins shipped with Entropy that are not installed, or newer than installed."""

    _, _, user = session_record
    _require_permission(request, user, "plugins.read")
    from lib.authorization.service import AuthorizationService
    from lib.plugins.bundled import INSTALL_PERMISSION, available

    context = request.app.state.entropy_context
    result = available(context)
    response.headers["Cache-Control"] = "no-store"
    return {
        **result,
        "can_install": AuthorizationService(context.database_manager.connection).has_permission(
            user.id, INSTALL_PERMISSION
        ),
    }


@router.post("/updates/install")
def install_bundled_updates(
    payload: PluginNamesRequest,
    request: Request,
    session_record: tuple = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> dict[str, Any]:
    """Install or upgrade the chosen bundled plugins; upgrades keep a backup in History."""

    _, _, user = session_record
    _require_permission(request, user, "plugins.write")
    from lib.plugins.bundled import changes_for

    context = request.app.state.entropy_context
    manager = _plugin_manager(request)
    studio = _studio(request)
    installed: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    changes = changes_for(context, payload.names)
    found = {change.qualified_name for change in changes}
    for name in payload.names:
        if name not in found:
            failed.append({"qualified_name": name, "error": "No newer version is bundled."})
    with PluginStudio._lock:
        for change in changes:
            name = change.qualified_name
            try:
                upgrade = change.installed is not None
                if upgrade:
                    current = studio.files(name)
                    _keep(request, name, user, reason="upgrade")(
                        current["files"], change.installed_version or ""
                    )
                plugin = manager.install(change.source, reinstall=upgrade)
                installed.append(_serialize_plugin(plugin))
            except Exception as exc:  # noqa: BLE001 - report each plugin's own failure
                failed.append({"qualified_name": name, "error": str(exc)})
    return {"installed": installed, "failed": failed}


@router.get("/sdk")
def plugin_sdk(
    request: Request,
    response: Response,
    session_record: tuple = Depends(_current_session),
) -> dict[str, Any]:
    """Describe the Plugin SDK for editor completion and hover help."""

    _, _, user = session_record
    _require_permission(request, user, "plugins.read")

    response.headers["Cache-Control"] = "no-store"
    return build_catalog()


@router.get("/contracts")
def plugin_contracts(
    request: Request,
    response: Response,
    session_record: tuple = Depends(_current_session),
) -> dict[str, Any]:
    """Arguments and outputs of every installed plugin, for the workflow builder."""

    _, _, user = session_record
    _require_permission(request, user, "plugins.read")

    manager = _plugin_manager(request)
    items = []

    for plugin in manager.list():
        contract = (
            plugin_contract(plugin.path)
            if plugin.path.is_dir()
            else {
                "description": None,
                "arguments": [],
                "outputs": [],
            }
        )
        items.append({**_serialize_plugin(plugin), **contract})

    items.sort(key=lambda item: item["qualified_name"])

    response.headers["Cache-Control"] = "no-store"
    return {"items": items}


@router.get("/availability")
def plugin_availability(
    request: Request,
    response: Response,
    namespace: str = Query(max_length=64),
    name: str = Query(max_length=64),
    session_record: tuple = Depends(_current_session),
) -> dict[str, Any]:
    """Report whether a namespace/name pair can be used for a new plugin."""

    _, _, user = session_record
    _require_permission(request, user, "plugins.write")

    response.headers["Cache-Control"] = "no-store"

    try:
        _studio(request).check_name(namespace.strip(), name.strip())
    except PluginStudioError as exc:
        return {"available": False, "reason": str(exc)}

    return {"available": True, "reason": None}


@router.post("", status_code=201)
def create_plugin(
    payload: PluginCreateRequest,
    request: Request,
    response: Response,
    session_record: tuple = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> dict[str, Any]:
    """Scaffold a plugin from the template as a draft (or install it)."""

    _, _, user = session_record
    _require_permission(request, user, "plugins.write")

    try:
        plugin = _studio(request).create(
            payload.namespace.strip(),
            payload.name.strip(),
            payload.description,
            install=payload.install,
        )
    except Exception as exc:
        raise _translate(exc) from exc

    response.headers["Cache-Control"] = "no-store"
    return _serialize_plugin(plugin)


@router.post("/export")
def export_plugins(
    payload: PluginNamesRequest,
    request: Request,
    session_record: tuple = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Response:
    """Download plugins (installed or draft) as one zip, a folder each."""

    _, _, user = session_record
    _require_permission(request, user, "plugins.read")

    try:
        data = _studio(request).export(payload.names)
    except Exception as exc:
        raise _translate(exc) from exc

    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="entropy-plugins.zip"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/import", status_code=201)
async def import_plugins(
    request: Request,
    file: UploadFile = File(...),
    install: bool = Form(False),
    session_record: tuple = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> dict[str, Any]:
    """Import plugin folders from a zip as drafts, or install them."""

    _, _, user = session_record
    _require_permission(request, user, "plugins.write")

    from core.web.plugin_studio.workspace import MAX_IMPORT_BYTES

    data = await file.read(MAX_IMPORT_BYTES + 1)

    try:
        plugins = _studio(request).import_archive(data, install=install)
    except Exception as exc:
        raise _translate(exc) from exc

    return {"items": [_serialize_plugin(plugin) for plugin in plugins]}


@router.post("/{qualified_name}/install")
def install_draft(
    qualified_name: str,
    request: Request,
    session_record: tuple = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> dict[str, Any]:
    """Install a draft so workflows can use it."""

    _, _, user = session_record
    _require_permission(request, user, "plugins.write")

    try:
        plugin = _studio(request).install(qualified_name)
    except Exception as exc:
        raise _translate(exc) from exc

    return _serialize_plugin(plugin)


@router.get("/{qualified_name}/docs")
def plugin_help(
    qualified_name: str,
    request: Request,
    response: Response,
    session_record: tuple = Depends(_current_session),
) -> dict[str, Any]:
    """Help page: description, inputs, outputs, a usage example, the manual, users."""

    _, _, user = session_record
    _require_permission(request, user, "plugins.read")

    try:
        plugin = _studio(request)._resolve(qualified_name)
    except Exception as exc:
        raise _translate(exc) from exc

    context = request.app.state.entropy_context
    authorization = context.authorization
    # Which workflows use it is only shown to those who may read workflows.
    workflows = (
        context.workflow_manager
        if authorization is not None
        and user.id is not None
        and authorization.has_permission(user.id, "workflows.read")
        else None
    )

    response.headers["Cache-Control"] = "no-store"
    return {**_serialize_plugin(plugin), **plugin_docs(plugin, workflows)}


@router.get("/{qualified_name}/files")
def plugin_files(
    qualified_name: str,
    request: Request,
    response: Response,
    session_record: tuple = Depends(_current_session),
) -> dict[str, Any]:
    """Return the editable source files of an installed plugin."""

    _, _, user = session_record
    _require_permission(request, user, "plugins.read")

    try:
        result = _studio(request).files(qualified_name)
    except Exception as exc:
        raise _translate(exc) from exc

    response.headers["Cache-Control"] = "no-store"
    return _files_payload(result)


@router.post("/{qualified_name}/contract")
def generate_contract(
    qualified_name: str,
    payload: PluginFilesRequest,
    request: Request,
    session_record: tuple = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> dict[str, Any]:
    """
    plugin.json with "arguments" and "outputs" filled in from the source (the
    current edits included); what is already declared is kept.
    """

    import json
    import tempfile

    from core.web.plugin_studio.workspace import read_files
    from lib.plugins.contract import inferred

    _, _, user = session_record
    _require_permission(request, user, "plugins.write")

    try:
        plugin = _studio(request)._resolve(qualified_name)
    except Exception as exc:
        raise _translate(exc) from exc
    files = {**read_files(plugin.path), **payload.files}
    for path in payload.removed:
        files.pop(path, None)
    try:
        manifest = json.loads(files.get("plugin.json") or "{}")
    except ValueError:
        raise HTTPException(status_code=422, detail="plugin.json is not valid JSON.") from None
    with tempfile.TemporaryDirectory(prefix="entropy-contract-") as directory:
        root = Path(directory)
        for path, content in files.items():
            if path.endswith(".py"):
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
        found = inferred(root)

    def merge(existing: Any, found_items: list, fields: tuple) -> list:
        items = (
            [item for item in existing if isinstance(item, dict)]
            if isinstance(existing, list)
            else []
        )
        names = {item.get("name") for item in items}
        for item in found_items:
            if item["name"] not in names:
                entry = {key: item[key] for key in fields if item.get(key) not in (None, "")}
                entry.setdefault("description", "")
                items.append(entry)
        return items

    arguments = merge(
        manifest.get("arguments"),
        found["arguments"],
        ("name", "type", "required", "default", "minimum", "maximum"),
    )
    for item in arguments:
        # A required argument takes no default; types the builder cannot name become "any".
        if item.get("required"):
            item.pop("default", None)
        if item.get("type") == "any" and "type" in item:
            item["type"] = "any"
    outputs = merge(manifest.get("outputs"), found["outputs"], ("name", "type"))
    ordered: Dict[str, Any] = {}
    for key, value in manifest.items():
        if key in ("arguments", "outputs"):
            continue
        ordered[key] = value
        if key in ("dependencies", "required_plugins"):
            ordered["arguments"] = arguments
            ordered["outputs"] = outputs
    ordered.setdefault("arguments", arguments)
    ordered.setdefault("outputs", outputs)
    return {
        "content": json.dumps(ordered, indent=4, ensure_ascii=False) + "\n",
        "added": {
            "arguments": [
                i["name"]
                for i in arguments
                if i["name"]
                not in {
                    x.get("name") for x in (manifest.get("arguments") or []) if isinstance(x, dict)
                }
            ],
            "outputs": [
                i["name"]
                for i in outputs
                if i["name"]
                not in {
                    x.get("name") for x in (manifest.get("outputs") or []) if isinstance(x, dict)
                }
            ],
        },
    }


@router.post("/{qualified_name}/validate")
def validate_plugin(
    qualified_name: str,
    payload: PluginFilesRequest,
    request: Request,
    response: Response,
    session_record: tuple = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> dict[str, Any]:
    """Check changed files against the Plugin SDK without saving them."""

    _, _, user = session_record
    _require_permission(request, user, "plugins.write")

    try:
        diagnostics = _studio(request).validate(
            qualified_name, payload.files, removed=payload.removed
        )
    except Exception as exc:
        raise _translate(exc) from exc

    response.headers["Cache-Control"] = "no-store"
    return {
        "valid": not any(item.severity == "error" for item in diagnostics),
        "diagnostics": _diagnostics(diagnostics),
    }


@router.put("/{qualified_name}/files")
def save_plugin_files(
    qualified_name: str,
    payload: PluginSaveRequest,
    request: Request,
    response: Response,
    session_record: tuple = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> dict[str, Any]:
    """Validate changed files and reinstall the plugin with them."""

    _, _, user = session_record
    _require_permission(request, user, "plugins.write")

    try:
        result = _studio(request).save(
            qualified_name,
            payload.files,
            payload.revision,
            install=payload.install,
            backup=_keep(request, qualified_name, user),
            removed=payload.removed,
        )
    except Exception as exc:
        raise _translate(exc) from exc

    response.headers["Cache-Control"] = "no-store"
    return _files_payload(result)


@router.delete("/{qualified_name}")
def delete_plugin(
    qualified_name: str,
    request: Request,
    response: Response,
    session_record: tuple = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> dict[str, Any]:
    """Uninstall a plugin and remove its module directory."""

    _, _, user = session_record
    _require_permission(request, user, "plugins.delete")

    try:
        _studio(request).delete(qualified_name)
    except Exception as exc:
        raise _translate(exc) from exc

    _history(request).forget(qualified_name)

    response.headers["Cache-Control"] = "no-store"
    return {"deleted": True, "qualified_name": qualified_name}


# ----------------------------------------------------------------------
# History
# ----------------------------------------------------------------------


@router.get("/{qualified_name}/history")
def plugin_history(
    qualified_name: str,
    request: Request,
    response: Response,
    session_record: tuple = Depends(_current_session),
) -> dict[str, Any]:
    """Earlier versions kept before each change (the last five)."""

    _, _, user = session_record
    _require_permission(request, user, "plugins.read")

    try:
        current = _studio(request).files(qualified_name)
    except Exception as exc:
        raise _translate(exc) from exc

    response.headers["Cache-Control"] = "no-store"
    return {
        "current_version": getattr(current["plugin"], "version", ""),
        "items": _history(request).list(qualified_name),
    }


@router.get("/{qualified_name}/history/{entry_id}")
def plugin_history_entry(
    qualified_name: str,
    entry_id: int,
    request: Request,
    response: Response,
    session_record: tuple = Depends(_current_session),
) -> dict[str, Any]:
    """One kept version's files."""

    _, _, user = session_record
    _require_permission(request, user, "plugins.read")

    entry = _history(request).get(qualified_name, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="That version is no longer kept.")

    response.headers["Cache-Control"] = "no-store"
    return {
        "id": entry["id"],
        "version": entry["version"],
        "reason": entry["reason"],
        "created_by": entry["created_by"],
        "created_at": entry["created_at"],
        "files": entry["content"],
    }


@router.post("/{qualified_name}/history/{entry_id}/restore")
def restore_plugin_version(
    qualified_name: str,
    entry_id: int,
    request: Request,
    response: Response,
    session_record: tuple = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> dict[str, Any]:
    """
    Make a kept version current again (validated like an edit). The current
    files are kept first; the restored version gets the next version number.
    """

    _, _, user = session_record
    _require_permission(request, user, "plugins.write")

    entry = _history(request).get(qualified_name, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="That version is no longer kept.")

    try:
        result = _studio(request).restore(
            qualified_name,
            entry["content"],
            backup=_keep(request, qualified_name, user, reason="restore"),
        )
    except Exception as exc:
        raise _translate(exc) from exc

    response.headers["Cache-Control"] = "no-store"
    return {**_files_payload(result), "restored_from": entry["version"]}
