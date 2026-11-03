"""Deleting releases and promotions from Release Manager."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Dict
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from core.web.routes import releases as routes
from core.web.routes.releases import ArchiveSelection, delete_selected
from lib.artifacts.store import ensure_artifacts_schema
from lib.authorization.projects import BUILTIN_ROLES, PROJECT_PERMISSIONS, role_scope
from lib.database.connection import DatabaseConnection
from lib.releases.store import ReleaseStore, ensure_releases_schema
from lib.tasks.store import TaskStore, ensure_tasks_schema

PROJECT, OTHER = 1, 2


@pytest.fixture()
def connection(tmp_path: Path) -> DatabaseConnection:
    connection = DatabaseConnection(tmp_path / "entropy.db")
    ensure_tasks_schema(connection)
    ensure_artifacts_schema(connection)
    ensure_releases_schema(connection)
    return connection


@pytest.fixture()
def store(connection) -> ReleaseStore:
    return ReleaseStore(connection)


def _release(store: ReleaseStore, name: str = "R", project: int = PROJECT) -> int:
    return store.create(project, name, "1", "SIT", "", "deploy", "owner")["id"]


def _promotion(store: ReleaseStore, *release_ids: int, project: int = PROJECT) -> int:
    return store.create_promotion(project, list(release_ids), "UAT", "promote", "owner")


def _count(connection, table: str) -> int:
    return connection.fetchone(f"SELECT COUNT(*) AS n FROM {table}")["n"]


# ----------------------------------------------------------------------
# Store
# ----------------------------------------------------------------------


def test_deleting_a_release_removes_its_links_but_not_tasks(connection, store) -> None:
    release = _release(store)
    kept = _release(store, "Kept")
    tasks = TaskStore(connection)
    task = tasks.create(PROJECT, "T", "", "", None, None, "owner")["id"]
    store.link_task(release, task)
    store.link_task(kept, task)

    result = store.delete_records(PROJECT, [release], [])

    assert result == {"deleted_releases": 1, "deleted_promotions": 0}
    assert store.get(release) is None
    assert [item["id"] for item in store.get(kept)["tasks"]] == [task]
    assert connection.fetchone("SELECT id FROM tasks WHERE id = ?", (task,)) is not None


def test_a_promotion_left_empty_goes_with_its_release(connection, store) -> None:
    release = _release(store)
    _promotion(store, release)

    result = store.delete_records(PROJECT, [release], [])

    assert result == {"deleted_releases": 1, "deleted_promotions": 1}
    assert _count(connection, "release_promotions") == 0
    assert _count(connection, "release_promotion_items") == 0


def test_a_promotion_with_other_releases_stays_without_the_deleted_one(store) -> None:
    gone, stays = _release(store, "Gone"), _release(store, "Stays")
    promotion = _promotion(store, gone, stays)

    result = store.delete_records(PROJECT, [gone], [])

    assert result == {"deleted_releases": 1, "deleted_promotions": 0}
    [kept] = store.promotions(PROJECT, True)
    assert kept["id"] == promotion
    assert [item["name"] for item in kept["releases"]] == ["Stays"]


def test_deleting_a_promotion_keeps_its_releases(connection, store) -> None:
    release = _release(store)
    promotion = _promotion(store, release)

    result = store.delete_records(PROJECT, [], [promotion])

    assert result == {"deleted_releases": 0, "deleted_promotions": 1}
    assert store.get(release) is not None
    assert _count(connection, "release_promotion_items") == 0


def test_a_deleted_promotion_frees_its_number(store) -> None:
    release = _release(store)
    promotion = store.create_promotion(PROJECT, [release], "UAT", "w", "owner", "NUM-1")

    store.delete_records(PROJECT, [], [promotion])

    assert store.create_promotion(PROJECT, [release], "UAT", "w", "owner", "NUM-1")


def test_archived_records_can_be_deleted(connection, store) -> None:
    release = _release(store)
    with connection.transaction():
        connection.execute(
            "UPDATE releases SET archived_at = datetime('now') WHERE id = ?", (release,)
        )

    assert store.delete_records(PROJECT, [release], [])["deleted_releases"] == 1


def test_another_projects_records_are_left_alone(store) -> None:
    release = _release(store, project=OTHER)
    promotion = _promotion(store, release, project=OTHER)

    result = store.delete_records(PROJECT, [release], [promotion])

    assert result == {"deleted_releases": 0, "deleted_promotions": 0}
    assert store.get(release) is not None
    assert store.promotions(OTHER, True)


def test_deleting_both_at_once_counts_each_promotion_once(store) -> None:
    release = _release(store)
    promotion = _promotion(store, release)

    result = store.delete_records(PROJECT, [release], [promotion])

    assert result == {"deleted_releases": 1, "deleted_promotions": 1}


# ----------------------------------------------------------------------
# Route
# ----------------------------------------------------------------------


@pytest.fixture()
def call(monkeypatch, store):
    """Calls the route; `runs` maps a job id to its state."""

    runs: Dict[int, str] = {}
    checked = []

    def project(request, user, permission):
        checked.append(permission)
        return {"id": PROJECT}

    monkeypatch.setattr(routes, "_project", project)
    monkeypatch.setattr(routes, "_store", lambda request: store)
    monkeypatch.setattr(
        routes,
        "RunService",
        lambda context: SimpleNamespace(
            store=SimpleNamespace(
                get=lambda job: {"state": runs[job]} if job in runs else None,
            )
        ),
    )

    def run(release_ids=(), promotion_ids=()):
        payload = ArchiveSelection(release_ids=list(release_ids), promotion_ids=list(promotion_ids))
        return delete_selected(payload, MagicMock(), ("token", MagicMock(), MagicMock()))

    return SimpleNamespace(run=run, runs=runs, checked=checked)


def test_route_needs_the_delete_permission_and_a_selection(call) -> None:
    with pytest.raises(HTTPException) as caught:
        call.run()

    assert call.checked == ["releases.delete"]
    assert caught.value.status_code == 422


def test_route_deletes(call, store) -> None:
    release = _release(store)

    assert call.run([release])["deleted_releases"] == 1


@pytest.mark.parametrize("state", ["queued", "starting", "running", "paused"])
def test_a_running_release_stops_the_whole_delete(call, store, state) -> None:
    busy, idle = _release(store, "Busy"), _release(store, "Idle")
    store.set_run(busy, 9)
    call.runs[9] = state

    with pytest.raises(HTTPException) as caught:
        call.run([busy, idle])

    assert caught.value.status_code == 409 and "release Busy" in caught.value.detail
    assert store.get(busy) is not None and store.get(idle) is not None


@pytest.mark.parametrize("state", ["completed", "failed", "cancelled"])
def test_a_finished_run_does_not_stop_a_delete(call, store, state) -> None:
    release = _release(store)
    store.set_run(release, 9)
    call.runs[9] = state

    assert call.run([release])["deleted_releases"] == 1


def test_a_run_that_no_longer_exists_does_not_stop_a_delete(call, store) -> None:
    release = _release(store)
    store.set_run(release, 404)

    assert call.run([release])["deleted_releases"] == 1


def test_a_running_promotion_stops_deleting_it_or_its_releases(call, store) -> None:
    release = _release(store)
    promotion = _promotion(store, release)
    store.set_promotion_run(promotion, 9)
    call.runs[9] = "running"

    for selection in ({"promotion_ids": [promotion]}, {"release_ids": [release]}):
        with pytest.raises(HTTPException) as caught:
            call.run(**selection)
        assert caught.value.status_code == 409 and "promotion" in caught.value.detail

    assert store.get(release) is not None and store.promotions(PROJECT, True)


# ----------------------------------------------------------------------
# Permission
# ----------------------------------------------------------------------


def test_delete_is_a_project_permission_for_maintainers_only() -> None:
    assert "releases.delete" in PROJECT_PERMISSIONS
    assert role_scope(["releases.delete"]) == "project"
    holders = {
        name
        for name, (_, _, _, permissions) in BUILTIN_ROLES.items()
        if permissions is not None and "releases.delete" in permissions
    }
    assert holders and all("maintainer" in name.lower() for name in holders)


def test_a_whole_list_can_be_deleted_in_one_request(call, store) -> None:
    ids = [_release(store, f"R{number}") for number in range(600)]

    assert call.run(ids)["deleted_releases"] == 600
