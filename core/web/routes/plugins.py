"""
Installed plugin inventory and browser plugin development API.
"""

from datetime import datetime
from typing import Any, Dict, Optional

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
from core.web.plugin_studio.sdk import build_catalog
from core.web.plugin_studio.workspace import (
    PluginStudio,
    PluginStudioError,
    PluginValidationFailed,
)
from core.web.routes.auth import _current_session, verify_csrf
from core.web.routes.workflows import _require_permission
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
        "qualified_name": (
            f"{plugin.namespace}.{plugin.name}"
        ),
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
        "plugins.list",
    )

    manager = _plugin_manager(request)

    try:
        plugins = manager.list()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve installed plugins.",
        ) from exc

    items = [
        _serialize_plugin(plugin)
        for plugin in [*plugins, *_studio(request).drafts()]
    ]

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
        items = [
            item
            for item in items
            if item["namespace"] == namespace
        ]

    if enabled is not None:
        items = [
            item
            for item in items
            if item["enabled"] is enabled
        ]

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

    paged_items = items[
        start : start + page_size
    ]

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


class PluginSaveRequest(PluginFilesRequest):
    """Changed files plus the revision they were edited from."""

    revision: str
    install: bool = False


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
    return {
        "plugin": _serialize_plugin(result["plugin"]),
        "files": [
            {"path": path, "content": content}
            for path, content in result["files"].items()
        ],
        "revision": result["revision"],
    }


@router.get("/sdk")
def plugin_sdk(
    request: Request,
    response: Response,
    session_record: tuple = Depends(_current_session),
) -> dict[str, Any]:
    """Describe the Plugin SDK for editor completion and hover help."""

    _, _, user = session_record
    _require_permission(request, user, "plugins.list")

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
    _require_permission(request, user, "plugins.list")

    manager = _plugin_manager(request)
    items = []

    for plugin in manager.list():
        contract = plugin_contract(plugin.path) if plugin.path.is_dir() else {
            "description": None,
            "arguments": [],
            "outputs": [],
        }
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
    _require_permission(request, user, "plugins.install")

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
    _require_permission(request, user, "plugins.install")

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
    _require_permission(request, user, "plugins.list")

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
    _require_permission(request, user, "plugins.install")

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
    _require_permission(request, user, "plugins.install")

    try:
        plugin = _studio(request).install(qualified_name)
    except Exception as exc:
        raise _translate(exc) from exc

    return _serialize_plugin(plugin)


@router.get("/{qualified_name}/files")
def plugin_files(
    qualified_name: str,
    request: Request,
    response: Response,
    session_record: tuple = Depends(_current_session),
) -> dict[str, Any]:
    """Return the editable source files of an installed plugin."""

    _, _, user = session_record
    _require_permission(request, user, "plugins.list")

    try:
        result = _studio(request).files(qualified_name)
    except Exception as exc:
        raise _translate(exc) from exc

    response.headers["Cache-Control"] = "no-store"
    return _files_payload(result)


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
    _require_permission(request, user, "plugins.install")

    try:
        diagnostics = _studio(request).validate(qualified_name, payload.files)
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
    _require_permission(request, user, "plugins.install")

    try:
        result = _studio(request).save(
            qualified_name,
            payload.files,
            payload.revision,
            install=payload.install,
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
    _require_permission(request, user, "plugins.uninstall")

    try:
        _studio(request).delete(qualified_name)
    except Exception as exc:
        raise _translate(exc) from exc

    response.headers["Cache-Control"] = "no-store"
    return {"deleted": True, "qualified_name": qualified_name}
