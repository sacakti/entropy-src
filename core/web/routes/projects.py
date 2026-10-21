"""
Projects: create them, choose who belongs with which project role, and
which nodes they may run on.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core.web.projects import authorization, current_project, projects, require
from core.web.routes.auth import _current_session, verify_csrf
from lib.models.session import Session
from lib.models.users import User

router = APIRouter(prefix="/api/projects", tags=["projects"])

SessionRecord = Tuple[Session, str, User]


class ProjectCreate(BaseModel):
    key: str = Field(min_length=1, max_length=40)
    name: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=1000)


class ProjectUpdate(BaseModel):
    name: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=1000)


class Member(BaseModel):
    kind: Literal["user", "group"] = "user"
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=100)


class MembersUpdate(BaseModel):
    members: List[Member] = Field(default_factory=list, max_length=1000)


def _project(request: Request, key: str) -> Dict[str, Any]:
    project = projects(request).get(key)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{key}' not found.")
    return project


def _can_manage_members(request: Request, user: User, project_id: int) -> bool:
    service = authorization(request)
    assert user.id is not None
    return service.has_permission(user.id, "projects.manage") or service.has_permission(
        user.id, "projects.members", project_id
    )


@router.get("")
def list_projects(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Projects the user may see, with their roles there and what they may do."""

    _, _, user = record
    assert user.id is not None
    store = projects(request)
    visible = authorization(request).member_projects(user.id)
    roles: Dict[str, List[str]] = {}
    for membership in store.memberships(user.id):
        roles.setdefault(membership["key"], []).append(membership["role_title"])
    current = current_project(request, user)
    items = []
    for project in store.list(visible):
        items.append(
            {
                **project,
                "my_roles": sorted(set(roles.get(project["key"], []))),
                "can_manage_members": _can_manage_members(request, user, project["id"]),
                **store.usage(project["id"]),
            }
        )
    response.headers["Cache-Control"] = "no-store"
    return {
        "items": items,
        "current": current["key"] if current else None,
        "can_create": authorization(request).has_permission(user.id, "projects.manage"),
    }


@router.post("", status_code=201, dependencies=[Depends(verify_csrf)])
def create_project(
    payload: ProjectCreate,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _, _, user = record
    require(request, user, "projects.manage")
    try:
        return projects(request).create(
            payload.key, payload.name, payload.description, user.username
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.patch("/{key}", dependencies=[Depends(verify_csrf)])
def update_project(
    key: str,
    payload: ProjectUpdate,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _, _, user = record
    require(request, user, "projects.manage")
    _project(request, key)
    return projects(request).update(key, payload.name, payload.description)


@router.delete("/{key}", dependencies=[Depends(verify_csrf)])
def delete_project(
    key: str,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _, _, user = record
    require(request, user, "projects.manage")
    try:
        projects(request).delete(key)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return {"deleted": True}


@router.get("/{key}/members")
def project_members(
    key: str,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _, _, user = record
    project = _project(request, key)
    assert user.id is not None
    # Members of a project see who else is in it.
    visible = authorization(request).member_projects(user.id)
    if visible is not None and project["id"] not in visible:
        raise HTTPException(status_code=403, detail="Permission denied.")
    response.headers["Cache-Control"] = "no-store"
    return {
        "project": project,
        "members": projects(request).members(project["id"]),
        "can_manage": _can_manage_members(request, user, project["id"]),
    }


@router.put("/{key}/members", dependencies=[Depends(verify_csrf)])
def set_project_members(
    key: str,
    payload: MembersUpdate,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _, _, user = record
    project = _project(request, key)
    if not _can_manage_members(request, user, project["id"]):
        raise HTTPException(status_code=403, detail="Permission denied.")
    store = projects(request)
    members = [member.model_dump() for member in payload.members]
    # A maintainer must not lock themselves out by accident.
    service = authorization(request)
    assert user.id is not None
    if not service.has_permission(user.id, "projects.manage"):
        keeps_access = any(
            member["kind"] == "user" and member["name"] == user.username for member in members
        ) or any(member["kind"] == "group" for member in members)
        if not keeps_access:
            raise HTTPException(
                status_code=409,
                detail="Keep yourself in the project, or ask an administrator to remove you.",
            )
    try:
        store.set_members(project["id"], members)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"members": store.members(project["id"])}
