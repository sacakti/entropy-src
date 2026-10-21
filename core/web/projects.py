"""
The project a web request works in, and project-aware permission checks.

The web UI sends the current project's key in the `X-Entropy-Project`
header (the ent client may pass `?project=`). Without it, or when the user
may not see that project, the Default project is used if they can see it,
else their first project.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Set

from fastapi import HTTPException, Request

from lib.authorization.projects import DEFAULT_PROJECT, Projects
from lib.models.users import User

PROJECT_HEADER = "x-entropy-project"


def projects(request: Request) -> Projects:
    context = request.app.state.entropy_context
    if context.database_manager is None:
        raise HTTPException(status_code=503, detail="Database is unavailable.")
    return Projects(context.database_manager.connection)


def authorization(request: Request) -> Any:
    service = request.app.state.entropy_context.authorization
    if service is None:
        raise HTTPException(status_code=503, detail="Authorization service unavailable.")
    return service


def visible_projects(request: Request, user: User) -> Optional[Set[int]]:
    """Projects the user may see; None means all of them."""

    assert user.id is not None
    return authorization(request).member_projects(user.id)


def current_project(request: Request, user: User) -> Dict[str, Any]:
    store = projects(request)
    visible = visible_projects(request, user)
    wanted = (
        request.headers.get(PROJECT_HEADER) or request.query_params.get("project") or ""
    ).strip()
    if wanted:
        project = store.get(wanted)
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project '{wanted}' not found.")
        if visible is not None and project["id"] not in visible:
            raise HTTPException(status_code=403, detail=f"You are not a member of '{wanted}'.")
        return project
    default = store.get(DEFAULT_PROJECT)
    if default is not None and (visible is None or default["id"] in visible):
        return default
    mine = store.list(visible)
    # Without any project, the Default project is used; its checks then refuse.
    return mine[0] if mine else default  # type: ignore[return-value]


def require(
    request: Request, user: User, permission: str, project_id: Optional[int] = None
) -> None:
    """403 unless the user has `permission` (in `project_id`, when given)."""

    if user.id is None or not authorization(request).has_permission(
        user.id, permission, project_id
    ):
        raise HTTPException(status_code=403, detail="Permission denied.")


def allowed(request: Request, user: User, permission: str) -> Optional[Set[int]]:
    """Projects where the user has `permission`; None means every project."""

    assert user.id is not None
    return authorization(request).projects_with(user.id, permission)
