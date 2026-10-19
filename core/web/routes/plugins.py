"""
Installed plugin inventory API.
"""

from typing import Any, Optional

from datetime import datetime
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
)
from fastapi.responses import JSONResponse

from core.web.routes.auth import _current_session
from core.web.routes.workflows import _require_permission


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
    }


@router.get("")
async def list_plugins(
    request: Request,
    session_record: tuple = Depends(_current_session),
    q: str = Query(
        default="",
        max_length=200,
    ),
    enabled: Optional[bool] = Query(
        default=None,
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
        for plugin in plugins
    ]

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
