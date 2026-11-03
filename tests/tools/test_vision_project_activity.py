"""A project chooses whether Vision shows its members each other's runs."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from core.web.routes import projects as project_routes
from core.web.routes import vision as routes
from lib.authorization.projects import Projects, ensure_projects_schema
from lib.database.connection import DatabaseConnection
from lib.system.settings import SystemSettings

RECORD = ("token", MagicMock(), SimpleNamespace(username="admin", id=1))


@pytest.fixture()
def connection(tmp_path: Path) -> DatabaseConnection:
    return DatabaseConnection(tmp_path / "entropy.db")


@pytest.fixture()
def store(connection) -> Projects:
    return Projects(connection)


def _request(connection) -> SimpleNamespace:
    context = SimpleNamespace(database_manager=SimpleNamespace(connection=connection))
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(entropy_context=context)))


def test_a_project_shares_its_activity_by_default(store) -> None:
    assert store.create("app1", "App 1", "", "admin")["vision_activity"] is True


def test_it_can_be_turned_off_and_on(store) -> None:
    store.create("app1", "App 1", "", "admin")

    assert store.update("app1", "App 1", "", False)["vision_activity"] is False
    assert store.get("app1")["vision_activity"] is False
    assert store.update("app1", "App 1", "", True)["vision_activity"] is True


def test_editing_other_fields_leaves_it_alone(store) -> None:
    store.create("app1", "App 1", "", "admin")
    store.update("app1", "App 1", "", False)

    updated = store.update("app1", "New name", "Text")

    assert updated["name"] == "New name" and updated["vision_activity"] is False


def test_each_project_has_its_own_setting(store) -> None:
    store.create("one", "One", "", "admin")
    store.create("two", "Two", "", "admin")

    store.update("one", "One", "", False)

    assert store.get("one")["vision_activity"] is False
    assert store.get("two")["vision_activity"] is True


def test_an_existing_database_gets_the_column_with_sharing_on(connection) -> None:
    with connection.transaction():
        connection.execute(
            "CREATE TABLE projects (id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL UNIQUE,"
            " name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', created_by TEXT,"
            " created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO projects (key, name, created_at, updated_at)"
            " VALUES ('old', 'Old', 'x', 'x')"
        )

    ensure_projects_schema(connection)

    assert Projects(connection).get("old")["vision_activity"] is True


def test_the_status_reports_the_current_projects_setting(connection, store, monkeypatch) -> None:
    store.create("app1", "App 1", "", "admin")
    store.update("app1", "App 1", "", False)
    store.create("app2", "App 2", "", "admin")
    current = {"key": "app1"}
    monkeypatch.setattr(routes, "current_project", lambda r, u: store.get(current["key"]))

    request = _request(connection)
    assert routes.vision_status(request, MagicMock(), RECORD)["project_activity"] is False

    current["key"] = "app2"
    assert routes.vision_status(request, MagicMock(), RECORD)["project_activity"] is True


def test_no_access_to_the_project_shows_nothing_of_it(connection, store, monkeypatch) -> None:
    def refuse(request, user):
        raise HTTPException(status_code=403, detail="Not a member")

    monkeypatch.setattr(routes, "current_project", refuse)

    status = routes.vision_status(_request(connection), MagicMock(), RECORD)

    assert status["enabled"] is True and status["project_activity"] is False


def test_turned_off_for_everyone_it_reports_no_activity(connection, store) -> None:
    SystemSettings(connection).update("vision", {"enabled": False})

    status = routes.vision_status(_request(connection), MagicMock(), RECORD)

    assert status == {"enabled": False, "broadcasts": [], "project_activity": False}


def test_changing_it_needs_the_manage_permission(connection, store, monkeypatch) -> None:
    store.create("app1", "App 1", "", "admin")
    asked = []
    monkeypatch.setattr(project_routes, "require", lambda r, u, name: asked.append(name))
    monkeypatch.setattr(project_routes, "projects", lambda request: store)

    result = project_routes.update_project(
        "app1",
        project_routes.ProjectUpdate(name="App 1", vision_activity=False),
        MagicMock(),
        RECORD,
    )

    assert asked == ["projects.manage"] and result["vision_activity"] is False


def test_the_route_leaves_it_alone_when_not_sent(connection, store, monkeypatch) -> None:
    store.create("app1", "App 1", "", "admin")
    store.update("app1", "App 1", "", False)
    monkeypatch.setattr(project_routes, "require", lambda *arguments: None)
    monkeypatch.setattr(project_routes, "projects", lambda request: store)

    result = project_routes.update_project(
        "app1", project_routes.ProjectUpdate(name="Renamed"), MagicMock(), RECORD
    )

    assert result["vision_activity"] is False
