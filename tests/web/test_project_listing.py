"""The project list works even when the browser names a project the user cannot see."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from core.web.projects import current_project
from core.web.routes import projects as project_routes
from lib.authorization.projects import Projects
from lib.database.connection import DatabaseConnection

USER = SimpleNamespace(username="pravin", id=7)
RECORD = ("token", MagicMock(), USER)


@pytest.fixture()
def store(tmp_path: Path) -> Projects:
    return Projects(DatabaseConnection(tmp_path / "entropy.db"))


def _request(store: Projects, visible: set, header: str = "") -> SimpleNamespace:
    service = MagicMock()
    service.member_projects.return_value = visible
    service.has_permission.return_value = False
    context = SimpleNamespace(
        database_manager=SimpleNamespace(connection=store.connection),
        authorization=service,
    )
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(entropy_context=context)),
        headers={"x-entropy-project": header} if header else {},
        query_params={},
    )


def test_a_project_left_by_another_user_still_lists_this_users_projects(store, monkeypatch) -> None:
    monkeypatch.setattr(store, "memberships", lambda user_id: [])
    monkeypatch.setattr(project_routes, "projects", lambda request: store)
    store.create("admin-only", "Admin only", "", "admin")
    app1 = store.create("app1", "App 1", "", "admin")
    request = _request(store, {app1["id"]}, header="admin-only")

    result = project_routes.list_projects(request, MagicMock(headers={}), RECORD)

    assert [item["key"] for item in result["items"]] == ["app1"]
    assert result["current"] == "app1"


def test_other_routes_still_refuse_a_project_the_user_is_not_in(store) -> None:
    store.create("admin-only", "Admin only", "", "admin")
    app1 = store.create("app1", "App 1", "", "admin")

    with pytest.raises(HTTPException) as refused:
        current_project(_request(store, {app1["id"]}, header="admin-only"), USER)

    assert refused.value.status_code == 403
