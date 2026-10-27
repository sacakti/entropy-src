"""Project task management API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core.web.projects import current_project, projects, require
from core.web.routes.auth import _current_session, verify_csrf
from lib.models.session import Session
from lib.models.users import User
from lib.tasks.store import STATUSES, TaskStore

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
SessionRecord = Tuple[Session, str, User]


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    remarks: str = Field(default="", max_length=5000)
    assignee: Optional[str] = Field(default=None, max_length=200)
    reminder_at: Optional[str] = Field(default=None, max_length=64)


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=10000)
    remarks: Optional[str] = Field(default=None, max_length=5000)
    status: Optional[str] = None
    assignee: Optional[str] = Field(default=None, max_length=200)
    reminder_at: Optional[str] = Field(default=None, max_length=64)


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class FollowUpdate(BaseModel):
    following: bool


def _store(request: Request) -> TaskStore:
    return TaskStore(request.app.state.entropy_context.database_manager.connection)


def _project_id(request: Request, user: User, permission: str) -> int:
    project = current_project(request, user)
    require(request, user, permission, project["id"])
    return project["id"]


def _task(request: Request, user: User, task_id: int, permission: str) -> Dict[str, Any]:
    item = _store(request).get(task_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    project = current_project(request, user)
    if item["project_id"] != project["id"]:
        raise HTTPException(status_code=404, detail="Task not found in the current project.")
    require(request, user, permission, project["id"])
    return item


def _validate_assignee(request: Request, project_id: int, name: Optional[str]) -> None:
    if not name:
        return
    members = projects(request).members(project_id)
    if not any(m.get("kind") == "user" and m.get("name", "").lower() == name.lower() for m in members):
        raise HTTPException(status_code=422, detail="Assignee must be a user in the current project.")


def _notify_followers(request: Request, item: Dict[str, Any], actor_id: int, message: str) -> None:
    from lib.database.repositories.notifications import notify_user

    for follower_id in item.get("follower_ids", []):
        if follower_id != actor_id:
            notify_user(request.app.state.entropy_context, follower_id,
                        f"Task updated: {item['title']}", message, "info", f"task:{item['id']}")


@router.get("")
def list_tasks(request: Request, response: Response, record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project_id = _project_id(request, user, "tasks.read")
    assert user.id is not None
    response.headers["Cache-Control"] = "no-store"
    connection = request.app.state.entropy_context.database_manager.connection
    members = connection.fetchall(
        "SELECT DISTINCT u.username, u.full_name FROM users u WHERE u.is_active = 1 AND ("
        "EXISTS (SELECT 1 FROM project_members pm WHERE pm.project_id = ? AND pm.user_id = u.id) "
        "OR EXISTS (SELECT 1 FROM project_members pm JOIN user_groups ug ON ug.group_id = pm.group_id "
        "WHERE pm.project_id = ? AND ug.user_id = u.id)) ORDER BY u.username COLLATE NOCASE",
        (project_id, project_id),
    )
    mail_ready = False
    try:
        from lib.system.settings import settings_for

        mail_ready = bool(settings_for(request.app.state.entropy_context).get("smtp")["enabled"])
    except Exception:
        pass
    return {"items": _store(request).list(project_id),
            "members": [{"username": row["username"], "full_name": row["full_name"]} for row in members],
            "user_id": user.id, "username": user.username, "permissions": {name: request.app.state.entropy_context.authorization.has_permission(user.id, name, project_id)
                for name in ("tasks.create", "tasks.manage", "tasks.comment", "tasks.follow")},
            "mail_ready": mail_ready}


@router.post("", status_code=201, dependencies=[Depends(verify_csrf)])
def create_task(payload: TaskCreate, request: Request, record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project_id = _project_id(request, user, "tasks.create")
    _validate_assignee(request, project_id, payload.assignee)
    if payload.reminder_at:
        try:
            datetime.fromisoformat(payload.reminder_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=422, detail="Reminder must be a valid date and time.") from None
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Task title cannot be blank.")
    return _store(request).create(project_id, title, payload.description,
                                  payload.remarks, payload.assignee, payload.reminder_at, user.username)


@router.patch("/{task_id}", dependencies=[Depends(verify_csrf)])
def update_task(task_id: int, payload: TaskUpdate, request: Request, record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    item = _task(request, user, task_id, "tasks.manage")
    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in STATUSES:
        raise HTTPException(status_code=422, detail="Choose a valid task status.")
    if "assignee" in data:
        _validate_assignee(request, item["project_id"], data["assignee"])
    if data.get("reminder_at"):
        try:
            datetime.fromisoformat(data["reminder_at"].replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=422, detail="Reminder must be a valid date and time.") from None
    updated = _store(request).update(task_id, data)
    if data:
        assert user.id is not None
        _notify_followers(request, item, user.id, f"{user.username} updated this task.")
    return updated


@router.delete("/{task_id}", status_code=204, dependencies=[Depends(verify_csrf)])
def delete_task(task_id: int, request: Request, record: SessionRecord = Depends(_current_session)) -> Response:
    _, _, user = record
    _task(request, user, task_id, "tasks.manage")
    connection = request.app.state.entropy_context.database_manager.connection
    with connection.transaction():
        connection.execute("DELETE FROM task_comments WHERE task_id = ?", (task_id,))
        connection.execute("DELETE FROM task_followers WHERE task_id = ?", (task_id,))
        connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return Response(status_code=204)


@router.post("/{task_id}/comments", status_code=201, dependencies=[Depends(verify_csrf)])
def comment_task(task_id: int, payload: CommentCreate, request: Request, record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    _task(request, user, task_id, "tasks.comment")
    store = _store(request)
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="Comment cannot be blank.")
    store.add_comment(task_id, user.username, body)
    assert user.id is not None
    _notify_followers(request, store.get(task_id) or {}, user.id, f"{user.username} added a comment.")
    return store.get(task_id) or {}


@router.put("/{task_id}/follow", dependencies=[Depends(verify_csrf)])
def follow_task(task_id: int, payload: FollowUpdate, request: Request, record: SessionRecord = Depends(_current_session)) -> Dict[str, bool]:
    _, _, user = record
    _task(request, user, task_id, "tasks.follow")
    assert user.id is not None
    _store(request).follow(task_id, user.id, payload.following)
    return {"following": payload.following}
