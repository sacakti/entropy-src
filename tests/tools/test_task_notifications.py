"""Who hears what when a task changes, and who can be assigned or mentioned."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from fastapi import BackgroundTasks, HTTPException

from core.web.routes import tasks as routes
from lib.database.connection import DatabaseConnection
from lib.tasks.store import TaskStore, ensure_tasks_schema

PROJECT = 2
ARAVINTHAN, PRAVIN, FOLLOWER, STRANGER, DISABLED = 1, 2, 3, 4, 5
NAMES = {ARAVINTHAN: "aravinthan", PRAVIN: "pravin", FOLLOWER: "fatima", STRANGER: "sam"}


def _user(user_id: int) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, username=NAMES[user_id])


def _record(user_id: int) -> tuple:
    return ("token", MagicMock(), _user(user_id))


@pytest.fixture()
def connection(tmp_path: Path) -> DatabaseConnection:
    connection = DatabaseConnection(tmp_path / "entropy.db")
    ensure_tasks_schema(connection)
    with connection.transaction():
        connection.execute(
            "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT,"
            " full_name TEXT, email TEXT, is_active INTEGER NOT NULL DEFAULT 1)"
        )
        connection.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY, key TEXT)")
        connection.execute("INSERT INTO projects VALUES (?, 'app1')", (PROJECT,))
        for user_id, name in NAMES.items():
            connection.execute("INSERT INTO users (id, username) VALUES (?, ?)", (user_id, name))
        connection.execute(
            "INSERT INTO users (id, username, is_active) VALUES (?, 'gone', 0)", (DISABLED,)
        )
    return connection


@pytest.fixture()
def world(connection, monkeypatch) -> SimpleNamespace:
    """The routes over a real store; aravinthan holds a global role, pravin is a member."""

    sent: List[Dict[str, Any]] = []
    readers = {ARAVINTHAN, PRAVIN, FOLLOWER, DISABLED}
    context = SimpleNamespace(
        database_manager=SimpleNamespace(connection=connection),
        authorization=SimpleNamespace(
            has_permission=lambda user_id, name, project: user_id in readers
        ),
        bootstrap=SimpleNamespace(home="/nonexistent"),
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(entropy_context=context)))

    def notify(context, user_id, title, message="", level="info", source=None):
        sent.append({"user": user_id, "title": title, "message": message, "source": source})

    monkeypatch.setattr("lib.database.repositories.notifications.notify_user", notify)
    monkeypatch.setattr(routes, "current_project", lambda request, user: {"id": PROJECT})
    monkeypatch.setattr(routes, "require", lambda *arguments: None)
    store = TaskStore(connection)
    return SimpleNamespace(request=request, store=store, sent=sent)


def _create(world, actor: int = ARAVINTHAN, **values: Any) -> Dict[str, Any]:
    payload = routes.TaskCreate(title=values.pop("title", "Fix it"), **values)
    return routes.create_task(payload, world.request, _record(actor))


def _update(world, task: Dict[str, Any], actor: int = ARAVINTHAN, **values: Any) -> Dict[str, Any]:
    return routes.update_task(
        task["id"], routes.TaskUpdate(**values), world.request, BackgroundTasks(), _record(actor)
    )


def _to(world, user_id: int) -> List[Dict[str, Any]]:
    return [item for item in world.sent if item["user"] == user_id]


# ----------------------------------------------------------------------
# Assigning
# ----------------------------------------------------------------------


def test_creating_a_task_tells_its_assignee_with_a_link_to_it(world) -> None:
    task = _create(world, assignee="pravin")

    [alert] = world.sent
    assert alert["user"] == PRAVIN and alert["title"].startswith("Assigned to you:")
    assert alert["source"] == f"task:{task['id']}"
    assert "aravinthan" in alert["message"]


def test_assigning_yourself_tells_nobody(world) -> None:
    _create(world, assignee="aravinthan")

    assert world.sent == []


def test_reassigning_tells_both_people(world) -> None:
    task = _create(world, assignee="pravin")
    world.sent.clear()

    _update(world, task, assignee="fatima")

    assert _to(world, FOLLOWER)[0]["title"].startswith("Assigned to you:")
    [replaced] = _to(world, PRAVIN)
    assert replaced["title"].startswith("No longer assigned:") and "fatima" in replaced["message"]


def test_a_new_assignee_mentioned_in_the_description_hears_once(world) -> None:
    _create(world, assignee="pravin", description="please look @pravin")

    assert len(_to(world, PRAVIN)) == 1


# ----------------------------------------------------------------------
# Who can be assigned or mentioned
# ----------------------------------------------------------------------


def test_someone_with_a_global_role_can_be_mentioned_and_assigned(world) -> None:
    # Aravinthan is an administrator, not a project member.
    members = [item["username"] for item in routes._members(world.request, PROJECT)]
    assert "aravinthan" in members and "pravin" in members

    task = _create(world, actor=PRAVIN, assignee="aravinthan")
    assert _to(world, ARAVINTHAN)[0]["title"].startswith("Assigned to you:")

    world.sent.clear()
    routes.comment_task(
        task["id"],
        routes.CommentCreate(body="@aravinthan see this"),
        world.request,
        _record(PRAVIN),
    )
    [alert] = _to(world, ARAVINTHAN)
    assert alert["title"].startswith("pravin mentioned you")


def test_those_who_cannot_read_the_project_are_not_offered(world) -> None:
    members = [item["username"] for item in routes._members(world.request, PROJECT)]

    assert "sam" not in members
    with pytest.raises(HTTPException) as caught:
        routes._validate_assignee(world.request, _user(ARAVINTHAN), PROJECT, "sam")
    assert caught.value.status_code == 422


def test_disabled_users_are_not_offered(world) -> None:
    assert "gone" not in [item["username"] for item in routes._members(world.request, PROJECT)]


# ----------------------------------------------------------------------
# Followers hear about everything
# ----------------------------------------------------------------------


@pytest.fixture()
def followed(world) -> Dict[str, Any]:
    task = _create(world, assignee="pravin", description="Old")
    world.store.follow(task["id"], FOLLOWER, True)
    world.sent.clear()
    return task


@pytest.mark.parametrize(
    ("values", "words"),
    [
        ({"title": "New title"}, "title from Fix it to New title"),
        ({"severity": "high"}, "severity from medium to high"),
        ({"description": "New"}, "the description"),
        ({"remarks": "Note"}, "the remarks"),
        ({"due_date": "2030-01-01"}, "due date from none to 2030-01-01"),
        ({"external_ref": "JIRA-1"}, "external reference from none to JIRA-1"),
        ({"reminder_at": "2030-01-01T10:00"}, "reminder from none"),
    ],
)
def test_every_field_change_reaches_followers_and_assignee(world, followed, values, words) -> None:
    _update(world, followed, **values)

    for user_id in (FOLLOWER, PRAVIN):
        [alert] = _to(world, user_id)
        assert words in alert["message"] and alert["source"] == f"task:{followed['id']}"
    assert _to(world, ARAVINTHAN) == []


def test_saving_without_a_change_tells_nobody(world, followed) -> None:
    _update(world, followed, title="Fix it", severity="medium")

    assert world.sent == []


def test_a_status_change_reaches_followers_and_assignee(world, followed) -> None:
    _update(world, followed, status="in_progress")

    for user_id in (FOLLOWER, PRAVIN):
        [alert] = _to(world, user_id)
        assert "aravinthan moved" in alert["message"]


def test_a_status_and_field_change_are_told_together(world, followed) -> None:
    _update(world, followed, status="in_progress", severity="high")

    [alert] = _to(world, FOLLOWER)
    assert "moved" in alert["message"] and "severity from medium to high" in alert["message"]


def test_the_one_who_changes_it_is_not_told(world, followed) -> None:
    _update(world, followed, actor=FOLLOWER, severity="high")

    assert _to(world, FOLLOWER) == []
    assert len(_to(world, PRAVIN)) == 1


def test_an_unfollowed_task_stops_reaching_that_person(world, followed) -> None:
    world.store.follow(followed["id"], FOLLOWER, False)

    _update(world, followed, severity="high")

    assert _to(world, FOLLOWER) == []


def test_a_comment_reaches_followers_and_assignee_with_its_text(world, followed) -> None:
    routes.comment_task(
        followed["id"], routes.CommentCreate(body="Almost done"), world.request, _record(ARAVINTHAN)
    )

    for user_id in (FOLLOWER, PRAVIN):
        [alert] = _to(world, user_id)
        assert "Almost done" in alert["message"]


def test_someone_mentioned_in_a_comment_hears_once(world, followed) -> None:
    routes.comment_task(
        followed["id"],
        routes.CommentCreate(body="@fatima look"),
        world.request,
        _record(ARAVINTHAN),
    )

    [alert] = _to(world, FOLLOWER)
    assert "mentioned you" in alert["title"]


def test_only_new_mentions_in_a_description_alert(world, followed) -> None:
    _update(world, followed, description="@fatima first")
    world.sent.clear()

    _update(world, followed, description="@fatima first, now longer")

    assert not [item for item in _to(world, FOLLOWER) if "mentioned" in item["title"]]


def test_renaming_and_removing_an_attachment_are_told(world, followed) -> None:
    attachment = world.store.add_attachment(followed["id"], "a.txt", "text/plain", 1, "aravinthan")
    attachment_id = attachment["id"] if isinstance(attachment, dict) else attachment

    routes.rename_attachment(
        followed["id"],
        attachment_id,
        routes.AttachmentRename(filename="b.txt"),
        world.request,
        _record(ARAVINTHAN),
    )
    routes.delete_attachment(followed["id"], attachment_id, world.request, _record(ARAVINTHAN))

    messages = [item["message"] for item in _to(world, FOLLOWER)]
    assert any("renamed attachment a.txt to b.txt" in item for item in messages)
    assert any("removed attachment b.txt" in item for item in messages)


def test_adding_to_a_group_reaches_watchers_of_new_members_only(world, followed) -> None:
    group = world.store.create_group(PROJECT, "R1", "release", "", None, "aravinthan")

    routes.update_group(
        group["id"],
        routes.GroupUpdate(add_task_ids=[followed["id"]]),
        world.request,
        _record(ARAVINTHAN),
    )
    assert "group R1" in _to(world, FOLLOWER)[0]["message"]

    world.sent.clear()
    routes.update_group(
        group["id"],
        routes.GroupUpdate(add_task_ids=[followed["id"]]),
        world.request,
        _record(ARAVINTHAN),
    )
    assert world.sent == []


def test_deleting_a_task_tells_watchers_without_a_dead_link(world, followed) -> None:
    routes.delete_task(followed["id"], world.request, _record(ARAVINTHAN))

    for user_id in (FOLLOWER, PRAVIN):
        [alert] = _to(world, user_id)
        assert alert["title"].startswith("Task deleted:")
        assert alert["source"] == "tasks"


# ----------------------------------------------------------------------
# Opening a task from an alert
# ----------------------------------------------------------------------


def test_the_project_of_a_task_is_found_for_its_alert_link(world, followed) -> None:
    assert routes.task_project(followed["id"], world.request, _record(PRAVIN)) == {
        "project": "app1"
    }


def test_finding_a_task_needs_permission_there(world, followed, monkeypatch) -> None:
    def refuse(*arguments):
        raise HTTPException(status_code=403, detail="Forbidden")

    monkeypatch.setattr(routes, "require", refuse)

    with pytest.raises(HTTPException) as caught:
        routes.task_project(followed["id"], world.request, _record(STRANGER))

    assert caught.value.status_code == 403


def test_a_deleted_task_is_not_found(world) -> None:
    with pytest.raises(HTTPException) as caught:
        routes.task_project(999, world.request, _record(PRAVIN))

    assert caught.value.status_code == 404
