"""Tasks created and linked from Release Manager."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.web.routes.releases import ReleaseTaskCreate, ReleaseTasksImport, TaskIds
from core.web.routes.tasks import TaskCreate
from lib.database.connection import DatabaseConnection
from lib.tasks.store import TaskStore, ensure_tasks_schema


@pytest.fixture()
def store(tmp_path: Path) -> TaskStore:
    connection = DatabaseConnection(tmp_path / "entropy.db")
    ensure_tasks_schema(connection)
    return TaskStore(connection)


def test_release_task_has_the_create_task_contract() -> None:
    assert set(ReleaseTaskCreate.model_fields) == set(TaskCreate.model_fields)
    task = ReleaseTaskCreate(
        title="Deploy", type="task", severity="high", group_ids=[3], due_date="2026-12-31"
    )
    assert (task.type, task.severity, task.group_ids, task.status) == ("task", "high", [3], "todo")


def test_old_task_json_imports_still_validate() -> None:
    payload = ReleaseTasksImport(tasks=[{"title": "A", "description": "d", "assignee": None}])
    assert payload.tasks[0].type == "issue" and payload.tasks[0].severity == "medium"


def test_link_accepts_groups_or_tasks() -> None:
    assert TaskIds(group_ids=[1]).task_ids == []
    assert TaskIds(task_ids=[2]).group_ids == []


def test_group_task_ids(store: TaskStore) -> None:
    group = store.create_group(1, "release1", "release", "", None, "admin")
    other = store.create_group(1, "sprint", "sprint", "", None, "admin")
    first = store.create(1, "One", "", "", None, None, "admin", group_ids=[group["id"]])
    store.create(1, "Two", "", "", None, None, "admin", group_ids=[other["id"]])
    third = store.create(
        1, "Three", "", "", None, None, "admin", group_ids=[group["id"], other["id"]]
    )

    assert store.group_task_ids(group["id"]) == [first["id"], third["id"]]
    assert store.group_task_ids(999) == []


def test_release_context_exposes_artifact_paths(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from core.web.routes.releases import _release_context
    from lib.artifacts.store import ArtifactStore, ensure_artifacts_schema

    connection = DatabaseConnection(tmp_path / "entropy.db")
    ensure_artifacts_schema(connection)
    artifacts = ArtifactStore(connection)
    package = artifacts.create(
        4, "payments-2.8.zip", "upload", 10, "admin", storage_name="ab12.zip"
    )
    local = artifacts.create(
        4, "values.yaml", "server_path", 5, "admin", server_path="/srv/values.yaml"
    )
    foreign = artifacts.create(5, "other.zip", "upload", 1, "admin", storage_name="zz.zip")
    context = SimpleNamespace(
        database_manager=SimpleNamespace(connection=connection),
        bootstrap=SimpleNamespace(home=str(tmp_path)),
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(entropy_context=context)))
    release = {
        "id": 7,
        "project_id": 4,
        "name": "Payments",
        "version": "2.8",
        "environment": "SIT",
        "description": "",
        "tags": ["urgent"],
        "artifacts": [{"id": package["id"]}, {"id": local["id"]}, {"id": foreign["id"]}],
    }

    result = _release_context(request, release)  # type: ignore[arg-type]

    package_path = str(tmp_path / "artifacts" / "4" / "ab12.zip")
    assert result["artifact"]["path"] == package_path
    assert [item["name"] for item in result["artifacts"]] == ["payments-2.8.zip", "values.yaml"]
    assert result["artifact_paths"] == {
        "payments-2.8.zip": package_path,
        "values.yaml": "/srv/values.yaml",
    }
    assert "artifact" not in _release_context(request, {**release, "artifacts": []})  # type: ignore[arg-type]
