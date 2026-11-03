"""Project task management API."""

from __future__ import annotations

import os
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi import Query
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from core.web.projects import current_project, require
from core.web.routes.auth import _current_session, verify_csrf
from lib.models.session import Session
from lib.models.users import User
from lib.tasks.recurrence import REPEATS
from lib.tasks.store import (
    CLOSED,
    GROUP_KINDS,
    PREFIX,
    REOPENED,
    SEVERITIES,
    STATUSES,
    TYPE_NAME,
    TaskStatusError,
    TaskStore,
    task_version,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
SessionRecord = Tuple[Session, str, User]

MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024
MAX_IMPORT_BYTES = 50 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
MENTION = re.compile(r"(?<![\w@.])@([A-Za-z0-9_.-]+)")


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    remarks: str = Field(default="", max_length=5000)
    assignee: Optional[str] = Field(default=None, max_length=200)
    reminder_at: Optional[str] = Field(default=None, max_length=64)
    type: str = Field(default="issue", max_length=30)
    external_ref: Optional[str] = Field(default=None, max_length=120)
    status: str = "todo"
    group_ids: List[int] = Field(default_factory=list, max_length=50)
    due_date: Optional[str] = Field(default=None, max_length=10)
    due_time: Optional[str] = Field(default=None, max_length=5)
    due_repeat: Optional[str] = Field(default=None, max_length=20)
    reminder_repeat: Optional[str] = Field(default=None, max_length=20)
    severity: str = "medium"


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=10000)
    remarks: Optional[str] = Field(default=None, max_length=5000)
    status: Optional[str] = None
    assignee: Optional[str] = Field(default=None, max_length=200)
    reminder_at: Optional[str] = Field(default=None, max_length=64)
    type: Optional[str] = Field(default=None, max_length=30)
    external_ref: Optional[str] = Field(default=None, max_length=120)
    group_ids: Optional[List[int]] = Field(default=None, max_length=50)
    due_date: Optional[str] = Field(default=None, max_length=10)
    due_time: Optional[str] = Field(default=None, max_length=5)
    due_repeat: Optional[str] = Field(default=None, max_length=20)
    reminder_repeat: Optional[str] = Field(default=None, max_length=20)
    severity: Optional[str] = None
    # Required to reopen a closed task; kept in its status history.
    reason: Optional[str] = Field(default=None, max_length=2000)


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class AttachmentRename(BaseModel):
    filename: str = Field(min_length=1, max_length=255)


class FollowUpdate(BaseModel):
    following: bool


class SettingsUpdate(BaseModel):
    prefix: Optional[str] = Field(default=None, max_length=10)
    types: Optional[List[str]] = Field(default=None, max_length=50)


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = "release"
    description: str = Field(default="", max_length=2000)
    external_ref: Optional[str] = Field(default=None, max_length=120)
    task_ids: List[int] = Field(default_factory=list, max_length=1000)


class GroupUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    kind: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=2000)
    external_ref: Optional[str] = Field(default=None, max_length=120)
    add_task_ids: List[int] = Field(default_factory=list, max_length=1000)


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


def _members(request: Request, project_id: int) -> List[Dict[str, Any]]:
    """
    Who can work on the project's tasks: everyone active who may read them, so also people
    with a global role (an administrator who is not a project member). Assigning and
    mentioning offer exactly these people.
    """

    context = request.app.state.entropy_context
    rows = context.database_manager.connection.fetchall(
        "SELECT id, username, full_name, email FROM users WHERE is_active = 1"
        " ORDER BY username COLLATE NOCASE"
    )
    return [
        dict(row)
        for row in rows
        if context.authorization.has_permission(row["id"], "tasks.read", project_id)
    ]


def _validate_assignee(request: Request, user: User, project_id: int, name: Optional[str]) -> None:
    if not name:
        return
    # Anyone working on the project's tasks may take one.
    if name.lower() == user.username.lower():
        return
    # The people the task forms offer: direct members, and members through a group.
    if not any(m["username"].lower() == name.lower() for m in _members(request, project_id)):
        raise HTTPException(status_code=422, detail="Assignee must be a user in the current project.")


def _validate_type(store: TaskStore, project_id: int, name: Optional[str]) -> None:
    if name is not None and name not in store.settings(project_id)["types"]:
        raise HTTPException(status_code=422, detail=f"'{name}' is not a task type of this project.")


def _validate_severity(value: Optional[str]) -> None:
    if value not in SEVERITIES:
        raise HTTPException(status_code=422, detail="Choose a valid severity.")


def _validate_groups(store: TaskStore, project_id: int, group_ids: Optional[List[int]]) -> None:
    for group_id in group_ids or []:
        group = store.get_group(group_id)
        if group is None or group["project_id"] != project_id:
            raise HTTPException(status_code=422, detail="Choose groups of the current project.")


DUE_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _validate_reminder(value: Optional[str]) -> None:
    if value:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=422, detail="Reminder must be a valid date and time.") from None


def _validate_due(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail="Due date must be a date (YYYY-MM-DD).") from None


def _validate_schedule(due_date: Optional[str], due_time: Optional[str], due_repeat: Optional[str],
                       reminder_at: Optional[str], reminder_repeat: Optional[str]) -> None:
    """A due time or repeat belongs to a due date, and a reminder's repeat to a reminder."""

    if due_time and not DUE_TIME.match(due_time):
        raise HTTPException(status_code=422, detail="Due time must be a time (HH:MM).")
    for value in (due_repeat, reminder_repeat):
        if value and value not in REPEATS:
            raise HTTPException(status_code=422, detail=f"Repeat must be one of {', '.join(REPEATS)}.")
    if (due_time or due_repeat) and not due_date:
        raise HTTPException(status_code=422, detail="Choose a due date first.")
    if reminder_repeat and not reminder_at:
        raise HTTPException(status_code=422, detail="Choose a reminder time first.")


STATUS_LABELS = {"todo": "Open", "in_progress": "In progress", CLOSED: "Closed", REOPENED: "Reopened"}


def _label(item: Dict[str, Any]) -> str:
    return f"{item.get('key')} {item['title']}" if item.get("key") else item["title"]


def _notify_one(request: Request, user_id: int, title: str, message: str, source: str,
                level: str = "info") -> None:
    from lib.database.repositories.notifications import notify_user

    notify_user(request.app.state.entropy_context, user_id, title, message, level, source)


def _notify_watchers(request: Request, item: Dict[str, Any], actor_id: Optional[int], message: str,
                     *, title: Optional[str] = None, skip: Optional[set] = None,
                     source: Optional[str] = None) -> None:
    """Tell everyone watching the task (followers and the assignee) that it changed, once each."""

    for user_id in _store(request).watcher_ids(item):
        if user_id != actor_id and user_id not in (skip or set()):
            _notify_one(request, user_id, title or f"Task updated: {_label(item)}", message,
                        source or f"task:{item['id']}")


def _user_id(request: Request, username: Optional[str]) -> Optional[int]:
    if not username:
        return None
    row = request.app.state.entropy_context.database_manager.connection.fetchone(
        "SELECT id FROM users WHERE lower(username) = lower(?) AND is_active = 1", (username,)
    )
    return int(row["id"]) if row else None


def _notify_assignment(request: Request, item: Dict[str, Any], user: User,
                       previous: Optional[str] = None) -> set:
    """Tell the new assignee and the one replaced; returns who heard, so they hear once."""

    source = f"task:{item['id']}"
    notified = set()
    assignee = _user_id(request, item.get("assignee"))
    if assignee is not None and assignee != user.id:
        _notify_one(request, assignee, f"Assigned to you: {_label(item)}",
                    f"{user.username} assigned this task to you.", source)
        notified.add(assignee)
    replaced = _user_id(request, previous)
    if replaced is not None and replaced not in (user.id, assignee):
        who = f"to {item['assignee']}" if item.get("assignee") else "to nobody"
        _notify_one(request, replaced, f"No longer assigned: {_label(item)}",
                    f"{user.username} assigned this task {who}.", source)
        notified.add(replaced)
    return notified


def _notify_new_task(request: Request, item: Dict[str, Any], user: User, description: str) -> None:
    """A task was created: tell its assignee, and whoever its description mentions."""

    assigned = _notify_assignment(request, item, user)
    _notify_mentions(request, item, user, description, skip=assigned)


def _short(value: Any) -> str:
    return str(value) if value not in (None, "") else "none"


def _describe_changes(store: TaskStore, before: Dict[str, Any], after: Dict[str, Any]) -> List[str]:
    """What changed in a task, in words. Status has its own alert."""

    changes = []
    for key, label in (("title", "title"), ("type", "type"), ("severity", "severity"),
                       ("due_date", "due date"), ("due_time", "due time"),
                       ("due_repeat", "repeat"), ("reminder_at", "reminder"),
                       ("reminder_repeat", "reminder repeat"),
                       ("external_ref", "external reference")):
        if before.get(key) != after.get(key):
            changes.append(f"{label} from {_short(before.get(key))} to {_short(after.get(key))}")
    for key, label in (("description", "description"), ("remarks", "remarks")):
        if (before.get(key) or "") != (after.get(key) or ""):
            changes.append(f"the {label}")
    if (before.get("assignee") or "") != (after.get("assignee") or ""):
        changes.append(f"assignee from {_short(before.get('assignee'))} to {_short(after.get('assignee'))}")
    was, now = set(before.get("group_ids") or []), set(after.get("group_ids") or [])
    if was != now:
        names = {group["id"]: group["name"] for group in store.groups(after["project_id"])}
        for label, ids in (("added to group", now - was), ("removed from group", was - now)):
            changes.extend(f"{label} {names.get(group_id, group_id)}" for group_id in sorted(ids))
    return changes


def _alert_status(request: Request, background: BackgroundTasks, item: Dict[str, Any],
                  user: User, previous: str, reason: Optional[str], changes: List[str],
                  skip: set) -> None:
    """Tell those watching the task that its status changed, and followers by e-mail too."""

    context = request.app.state.entropy_context
    status = STATUS_LABELS.get(item["status"], item["status"])
    message = (f"{user.username} moved {_label(item)} from "
               f"{STATUS_LABELS.get(previous, previous)} to {status}.")
    if reason:
        message += f" Reason: {reason.strip()}"
    if changes:
        message += f" Also changed: {'; '.join(changes)}."
    _notify_watchers(request, item, user.id, message, title=f"Task {status.lower()}: {_label(item)}",
                     skip=skip)
    addresses = [
        follower["email"]
        for follower in _store(request).follower_contacts(item["id"])
        if follower["id"] != user.id and follower.get("email")
    ]
    if addresses:
        background.add_task(_mail_followers, context, addresses, f"[Entropy] {_label(item)} is {status.lower()}",
                            message)


def _mail_followers(context: Any, addresses: List[str], subject: str, text: str) -> None:
    from lib.system.mailer import MailError, send_mail
    from lib.system.settings import settings_for

    try:
        smtp = settings_for(context).values("smtp")
        if smtp.get("enabled"):
            send_mail(smtp, addresses, subject, text + "\n\nYou receive this because you follow the task.")
    except (MailError, Exception):  # noqa: BLE001 - a mail failure never fails the update
        pass


def _notify_mentions(request: Request, item: Dict[str, Any], user: User, body: str,
                     *, earlier: str = "", skip: Optional[set] = None) -> set:
    """Tell those newly named with @username (not already in `earlier`); returns their ids."""

    names = {name.lower().rstrip(".") for name in MENTION.findall(body or "")}
    names -= {name.lower().rstrip(".") for name in MENTION.findall(earlier or "")}
    if not names:
        return set()
    notified = set()
    for member in _members(request, item["project_id"]):
        if member["username"].lower() not in names or member["id"] == user.id:
            continue
        notified.add(member["id"])
        if member["id"] not in (skip or set()):
            _notify_one(request, member["id"], f"{user.username} mentioned you in {_label(item)}",
                        (body or "")[:300], f"task:{item['id']}")
    return notified


def _attachment_root(request: Request, project_id: int) -> Path:
    return Path(request.app.state.entropy_context.bootstrap.home) / "task-attachments" / str(project_id)


# ----------------------------------------------------------------------
# Tasks
# ----------------------------------------------------------------------


@router.get("")
def list_tasks(request: Request, response: Response, record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project_id = _project_id(request, user, "tasks.read")
    assert user.id is not None
    response.headers["Cache-Control"] = "no-store"
    mail_ready = False
    try:
        from lib.system.settings import settings_for

        mail_ready = bool(settings_for(request.app.state.entropy_context).get("smtp")["enabled"])
    except Exception:
        pass
    store = _store(request)
    authorization = request.app.state.entropy_context.authorization
    # Read before the tasks: a change in between then only causes one more reload, never a missed one.
    version = task_version(request.app.state.entropy_context.database_manager.connection, project_id)
    return {"version": version,
            "items": store.list(project_id),
            "groups": store.groups(project_id),
            "settings": store.settings(project_id),
            "statuses": list(STATUSES),
            "severities": list(SEVERITIES),
            "status_labels": STATUS_LABELS,
            "group_kinds": list(GROUP_KINDS),
            "members": [{"username": row["username"], "full_name": row["full_name"]} for row in _members(request, project_id)],
            "user_id": user.id, "username": user.username,
            "permissions": {name: authorization.has_permission(user.id, name, project_id)
                            for name in ("tasks.create", "tasks.manage", "tasks.comment", "tasks.follow")},
            "mail_ready": mail_ready}


@router.get("/version")
def tasks_version(request: Request, response: Response,
                  record: SessionRecord = Depends(_current_session)) -> Dict[str, int]:
    """Whether anything changed, for open pages to ask often: one row, not the whole list."""

    _, _, user = record
    project_id = _project_id(request, user, "tasks.read")
    response.headers["Cache-Control"] = "no-store"
    return {"version": task_version(request.app.state.entropy_context.database_manager.connection, project_id)}


@router.get("/report")
def task_report(request: Request, scope: str = Query("all", pattern="^(all|selected|group)$"),
                ids: str = Query("", max_length=20000), group_id: Optional[int] = None,
                format: str = Query("html", pattern="^(html|pdf)$"),
                record: SessionRecord = Depends(_current_session)) -> Response:
    """A self-contained report to download, as an HTML or a PDF file."""

    from lib.tasks.report import build_report
    from lib.tasks.report_pdf import build_pdf

    _, _, user = record
    project = current_project(request, user)
    require(request, user, "tasks.read", project["id"])
    store = _store(request)
    tasks = store.list(project["id"])
    tasks.sort(key=lambda task: task.get("number") or task["id"])
    groups = store.groups(project["id"])
    label = "All tasks"
    if scope == "selected":
        wanted = {int(part) for part in ids.split(",") if part.strip().isdigit()}
        tasks = [task for task in tasks if task["id"] in wanted]
        label = "Selected tasks"
    elif scope == "group":
        group = next((g for g in groups if g["id"] == group_id), None)
        if group is None:
            raise HTTPException(status_code=404, detail="Choose a group of the current project.")
        tasks = [task for task in tasks if group["id"] in task["group_ids"]]
        groups = [group]
        label = f"Group: {group['name']}"
    groups = sorted(groups, key=lambda g: g["name"].lower())
    content = dict(
        project=project.get("name") or f"Project {project['id']}",
        scope=label,
        tasks=tasks,
        groups=groups,
        members=_members(request, project["id"]),
        attachments={task["id"]: store.attachments(task["id"]) for task in tasks},
        attachment_root=_attachment_root(request, project["id"]),
        generated_by=user.full_name or user.username,
    )
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    headers = {
        "Cache-Control": "no-store",
        "Content-Disposition": f'attachment; filename="task-report-{stamp}.{format}"',
    }
    if format == "pdf":
        return Response(build_pdf(**content), media_type="application/pdf", headers=headers)
    return HTMLResponse(build_report(**content), headers=headers)


@router.post("", status_code=201, dependencies=[Depends(verify_csrf)])
def create_task(payload: TaskCreate, request: Request, record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project_id = _project_id(request, user, "tasks.create")
    store = _store(request)
    _validate_assignee(request, user, project_id, payload.assignee)
    _validate_reminder(payload.reminder_at)
    _validate_type(store, project_id, payload.type)
    _validate_severity(payload.severity)
    _validate_groups(store, project_id, payload.group_ids)
    _validate_schedule(payload.due_date, payload.due_time, payload.due_repeat,
                       payload.reminder_at, payload.reminder_repeat)
    if payload.status not in STATUSES or payload.status == REOPENED:
        raise HTTPException(status_code=422, detail="Choose a valid task status.")
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Task title cannot be blank.")
    item = store.create(project_id, title, payload.description, payload.remarks, payload.assignee,
                        payload.reminder_at, user.username, type=payload.type,
                        external_ref=(payload.external_ref or "").strip() or None,
                        status=payload.status, group_ids=payload.group_ids,
                        due_date=_validate_due(payload.due_date), severity=payload.severity,
                        due_time=payload.due_time or None, due_repeat=payload.due_repeat or None,
                        reminder_repeat=payload.reminder_repeat or None)
    _notify_new_task(request, item, user, payload.description)
    return item


@router.patch("/{task_id}", dependencies=[Depends(verify_csrf)])
def update_task(task_id: int, payload: TaskUpdate, request: Request, background: BackgroundTasks,
                record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    data = payload.model_dump(exclude_unset=True)
    reason = data.pop("reason", None)
    # Taking a task needs no more than commenting on it; everything else needs tasks.manage.
    self_assign = set(data) == {"assignee"} and (data["assignee"] or "").lower() == user.username.lower()
    item = _task(request, user, task_id, "tasks.comment" if self_assign else "tasks.manage")
    store = _store(request)
    if "status" in data and data["status"] not in STATUSES:
        raise HTTPException(status_code=422, detail="Choose a valid task status.")
    if "assignee" in data:
        _validate_assignee(request, user, item["project_id"], data["assignee"])
    if "type" in data:
        _validate_type(store, item["project_id"], data["type"])
    if "severity" in data:
        _validate_severity(data["severity"])
    if "group_ids" in data:
        _validate_groups(store, item["project_id"], data["group_ids"])
    if "external_ref" in data:
        data["external_ref"] = (data["external_ref"] or "").strip() or None
    _validate_reminder(data.get("reminder_at"))
    if "due_date" in data:
        data["due_date"] = _validate_due(data["due_date"])
    # Removing a date removes what depends on it.
    if "due_date" in data and not data["due_date"]:
        data.update(due_time=None, due_repeat=None)
    if "reminder_at" in data and not data["reminder_at"]:
        data["reminder_repeat"] = None
    for key in ("due_time", "due_repeat", "reminder_repeat"):
        if key in data:
            data[key] = data[key] or None
    merged = {**item, **data}
    _validate_schedule(merged.get("due_date"), merged.get("due_time"), merged.get("due_repeat"),
                       merged.get("reminder_at"), merged.get("reminder_repeat"))
    try:
        updated = store.update(task_id, data, user.username, reason)
    except TaskStatusError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    assert user.id is not None
    told: set = set()
    if (updated.get("assignee") or "") != (item.get("assignee") or ""):
        told |= _notify_assignment(request, updated, user, item.get("assignee"))
    told |= _notify_mentions(request, updated, user, updated.get("description") or "",
                             earlier=item.get("description") or "", skip=told)
    changes = _describe_changes(store, item, updated)
    if updated["status"] != item["status"]:
        _alert_status(request, background, updated, user, item["status"], reason, changes, told)
    elif changes:
        _notify_watchers(request, updated, user.id, f"{user.username} changed {'; '.join(changes)}.", skip=told)
    if updated["status"] == CLOSED and item["status"] != CLOSED:
        upcoming = store.create_next_occurrence(task_id, date.today(), user.username)
        if upcoming:
            _notify_watchers(request, upcoming, user.id,
                             f"Repeats {upcoming['due_repeat']}: next due {upcoming['due_date']}.",
                             title=f"Next occurrence: {_label(upcoming)}")
    return updated


@router.get("/{task_id}/project")
def task_project(task_id: int, request: Request, record: SessionRecord = Depends(_current_session)) -> Dict[str, str]:
    """The project a task is in, to open it from an alert raised while in another project."""

    _, _, user = record
    item = _store(request).get(task_id)
    if item is None:
        raise HTTPException(status_code=404, detail="That task no longer exists.")
    require(request, user, "tasks.read", item["project_id"])
    row = request.app.state.entropy_context.database_manager.connection.fetchone(
        "SELECT key FROM projects WHERE id = ?", (item["project_id"],)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="That task no longer exists.")
    return {"project": row["key"]}


@router.delete("/{task_id}", status_code=204, dependencies=[Depends(verify_csrf)])
def delete_task(task_id: int, request: Request, record: SessionRecord = Depends(_current_session)) -> Response:
    _, _, user = record
    item = _task(request, user, task_id, "tasks.manage")
    root = _attachment_root(request, item["project_id"])
    # Before it goes: who watches it is kept with the task. There is no task left to link to.
    _notify_watchers(request, item, user.id, f"{user.username} deleted this task.",
                     title=f"Task deleted: {_label(item)}", source="tasks")
    for attachment in _store(request).delete(task_id):
        if attachment.get("storage_name"):
            target = (root / attachment["storage_name"]).resolve()
            if root.resolve() in target.parents:
                target.unlink(missing_ok=True)
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
    item = store.get(task_id) or {}
    mentioned = _notify_mentions(request, item, user, body)
    _notify_watchers(request, item, user.id, f"{user.username} commented: {body[:200]}", skip=mentioned)
    return store.get(task_id) or {}


@router.put("/{task_id}/follow", dependencies=[Depends(verify_csrf)])
def follow_task(task_id: int, payload: FollowUpdate, request: Request, record: SessionRecord = Depends(_current_session)) -> Dict[str, bool]:
    _, _, user = record
    _task(request, user, task_id, "tasks.follow")
    assert user.id is not None
    _store(request).follow(task_id, user.id, payload.following)
    return {"following": payload.following}


# ----------------------------------------------------------------------
# Attachments
# ----------------------------------------------------------------------


@router.post("/{task_id}/attachments", status_code=201, dependencies=[Depends(verify_csrf)])
async def upload_attachments(task_id: int, request: Request, files: List[UploadFile] = File(...),
                             record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    item = _task(request, user, task_id, "tasks.comment")
    store = _store(request)
    root = _attachment_root(request, item["project_id"])
    root.mkdir(parents=True, exist_ok=True)
    for upload in files[:20]:
        name = Path((upload.filename or "").replace("\\", "/")).name.strip()[:255]
        if not name or name in {".", ".."}:
            raise HTTPException(status_code=400, detail="Choose files with valid names.")
        storage_name = f"{task_id}-{uuid.uuid4().hex}{''.join(Path(name).suffixes)[-32:]}"
        temporary = root / f".{storage_name}.part"
        size = 0
        try:
            with temporary.open("xb") as output:
                while chunk := await upload.read(CHUNK_BYTES):
                    size += len(chunk)
                    if size > MAX_ATTACHMENT_BYTES:
                        raise HTTPException(status_code=413, detail=f"'{name}' is larger than 50 MiB.")
                    output.write(chunk)
            if size == 0:
                raise HTTPException(status_code=400, detail=f"'{name}' is empty.")
            os.replace(temporary, root / storage_name)
            store.add_attachment(task_id, name, upload.content_type, size, user.username, storage_name=storage_name)
        finally:
            temporary.unlink(missing_ok=True)
            await upload.close()
    assert user.id is not None
    names = ", ".join(Path((upload.filename or "").replace("\\", "/")).name for upload in files[:20])
    _notify_watchers(request, item, user.id, f"{user.username} attached {names}.")
    return store.get(task_id) or {}


def _attachment(request: Request, user: User, task_id: int, attachment_id: int, permission: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    item = _task(request, user, task_id, permission)
    attachment = _store(request).get_attachment(attachment_id)
    if attachment is None or attachment["task_id"] != task_id:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    return item, attachment


@router.get("/{task_id}/attachments/{attachment_id}")
def download_attachment(task_id: int, attachment_id: int, request: Request,
                        record: SessionRecord = Depends(_current_session)) -> Response:
    _, _, user = record
    item, attachment = _attachment(request, user, task_id, attachment_id, "tasks.read")
    if not attachment.get("storage_name"):
        raise HTTPException(status_code=404, detail="This attachment is a link to Jira; open it there.")
    root = _attachment_root(request, item["project_id"])
    target = (root / attachment["storage_name"]).resolve()
    if root.resolve() not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="The attachment file is missing.")
    return FileResponse(target, filename=attachment["filename"],
                        media_type=attachment.get("content_type") or "application/octet-stream")


@router.patch("/{task_id}/attachments/{attachment_id}", dependencies=[Depends(verify_csrf)])
def rename_attachment(task_id: int, attachment_id: int, payload: AttachmentRename, request: Request,
                      record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    item, attachment = _attachment(request, user, task_id, attachment_id, "tasks.read")
    # Same rule as removing: the uploader, or someone who manages tasks.
    if attachment["uploaded_by"].lower() != user.username.lower():
        require(request, user, "tasks.manage", item["project_id"])
    name = Path(payload.filename.replace("\\", "/")).name.strip()[:255]
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=422, detail="Choose a valid file name.")
    store = _store(request)
    store.rename_attachment(attachment_id, name)
    if name != attachment["filename"]:
        _notify_watchers(request, item, user.id,
                         f"{user.username} renamed attachment {attachment['filename']} to {name}.")
    return store.get(task_id) or {}


@router.delete("/{task_id}/attachments/{attachment_id}", status_code=204, dependencies=[Depends(verify_csrf)])
def delete_attachment(task_id: int, attachment_id: int, request: Request,
                      record: SessionRecord = Depends(_current_session)) -> Response:
    _, _, user = record
    item, attachment = _attachment(request, user, task_id, attachment_id, "tasks.read")
    # The uploader removes their own files; others need tasks.manage.
    if attachment["uploaded_by"].lower() != user.username.lower():
        require(request, user, "tasks.manage", item["project_id"])
    if attachment.get("storage_name"):
        root = _attachment_root(request, item["project_id"])
        target = (root / attachment["storage_name"]).resolve()
        if root.resolve() in target.parents:
            target.unlink(missing_ok=True)
    _store(request).delete_attachment(attachment_id)
    _notify_watchers(request, item, user.id, f"{user.username} removed attachment {attachment['filename']}.")
    return Response(status_code=204)


# ----------------------------------------------------------------------
# Settings and groups
# ----------------------------------------------------------------------


@router.put("/settings", dependencies=[Depends(verify_csrf)])
def update_settings(payload: SettingsUpdate, request: Request, record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project_id = _project_id(request, user, "tasks.manage")
    prefix = payload.prefix.strip().upper() if payload.prefix is not None else None
    if prefix is not None and not PREFIX.match(prefix):
        raise HTTPException(status_code=422, detail="The prefix is 2 to 10 capital letters or digits, starting with a letter (like ENTASK).")
    types = None
    if payload.types is not None:
        types = [name.strip().lower() for name in payload.types if name.strip()]
        bad = [name for name in types if not TYPE_NAME.match(name)]
        if bad:
            raise HTTPException(status_code=422, detail=f"Type names are lower case letters, digits, '_' or '-': {', '.join(bad)}.")
    return _store(request).update_settings(project_id, prefix, types)


@router.post("/groups", status_code=201, dependencies=[Depends(verify_csrf)])
def create_group(payload: GroupCreate, request: Request, record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project_id = _project_id(request, user, "tasks.create")
    store = _store(request)
    name = payload.name.strip()
    if payload.kind not in GROUP_KINDS:
        raise HTTPException(status_code=422, detail="Choose a valid group kind.")
    if not name:
        raise HTTPException(status_code=422, detail="Group name cannot be blank.")
    if store.group_by_name(project_id, name):
        raise HTTPException(status_code=409, detail=f"A group named '{name}' already exists.")
    group = store.create_group(project_id, name, payload.kind, payload.description,
                               (payload.external_ref or "").strip() or None, user.username)
    _add_tasks(store, project_id, group["id"], payload.task_ids)
    _notify_grouped(request, user, store, group, payload.task_ids, "added it to")
    return group


def _notify_grouped(request: Request, user: User, store: TaskStore, group: Dict[str, Any],
                    task_ids: List[int], verb: str) -> None:
    for task_id in dict.fromkeys(task_ids):
        task = store.get(task_id)
        if task:
            _notify_watchers(request, task, user.id, f"{user.username} {verb} group {group['name']}.")


def _add_tasks(store: TaskStore, project_id: int, group_id: int, task_ids: List[int]) -> None:
    for task_id in task_ids:
        task = store.get(task_id)
        if task is None or task["project_id"] != project_id:
            raise HTTPException(status_code=422, detail="Choose tasks of the current project.")
    store.add_to_group(group_id, task_ids)


def _group(request: Request, user: User, group_id: int, permission: str) -> Tuple[int, Dict[str, Any]]:
    project_id = _project_id(request, user, permission)
    group = _store(request).get_group(group_id)
    if group is None or group["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Group not found in the current project.")
    return project_id, group


@router.patch("/groups/{group_id}", dependencies=[Depends(verify_csrf)])
def update_group(group_id: int, payload: GroupUpdate, request: Request, record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project_id, group = _group(request, user, group_id, "tasks.manage")
    store = _store(request)
    data = payload.model_dump(exclude_unset=True, exclude={"add_task_ids"})
    if "kind" in data and data["kind"] not in GROUP_KINDS:
        raise HTTPException(status_code=422, detail="Choose a valid group kind.")
    if data.get("name"):
        data["name"] = data["name"].strip()
        other = store.group_by_name(project_id, data["name"])
        if other and other["id"] != group_id:
            raise HTTPException(status_code=409, detail=f"A group named '{data['name']}' already exists.")
    # Only those not in the group yet have changed.
    members = set(store.group_task_ids(group_id))
    added = [task_id for task_id in payload.add_task_ids if task_id not in members]
    _add_tasks(store, project_id, group_id, payload.add_task_ids)
    _notify_grouped(request, user, store, group, added, "added it to")
    return store.update_group(group_id, data)


@router.delete("/groups/{group_id}", status_code=204, dependencies=[Depends(verify_csrf)])
def delete_group(group_id: int, request: Request, record: SessionRecord = Depends(_current_session)) -> Response:
    """Removes the group; its tasks are kept."""

    _, _, user = record
    _, group = _group(request, user, group_id, "tasks.manage")
    store = _store(request)
    members = store.group_task_ids(group_id)
    store.delete_group(group_id)
    _notify_grouped(request, user, store, group, members, "deleted its")
    return Response(status_code=204)


# ----------------------------------------------------------------------
# Jira import
# ----------------------------------------------------------------------


@router.post("/import", dependencies=[Depends(verify_csrf)])
async def import_jira(request: Request, file: UploadFile = File(...), group: str = Form(""),
                      update_existing: bool = Form(True),
                      record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    from lib.tasks.jira import JiraImportError, import_issues, parse

    _, _, user = record
    project_id = _project_id(request, user, "tasks.create")
    data = await file.read(MAX_IMPORT_BYTES + 1)
    await file.close()
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="Import files are limited to 50 MiB.")
    try:
        issues = parse(data, file.filename or "")
    except JiraImportError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    return import_issues(_store(request), project_id, issues, _members(request, project_id), user.username,
                         group=group.strip() or None, update_existing=update_existing)
