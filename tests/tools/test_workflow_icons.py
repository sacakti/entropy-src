"""Workflow icons: per project, follow the workflow, and only ever a well-formed id."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.web.routes import workflows as routes
from core.web.transfer import ProjectTransfer
from lib.authorization.projects import workflow_key
from lib.database.connection import DatabaseConnection
from lib.database.objects.events import WorkflowEventsTable
from lib.database.objects.jobs import WorkflowJobsTable
from lib.plugins.icons import PluginIconError
from lib.workflow.exceptions import WorkflowNotFoundError
from lib.workflow.icons import WorkflowIconStore

Migration = importlib.import_module(
    "lib.migrations.scripts.031_workflow_icons"
).WorkflowIconsMigration


@pytest.fixture
def connection(tmp_path: Path, monkeypatch) -> DatabaseConnection:
    # Permission seeding needs the authorization tables; not under test here.
    monkeypatch.setattr(
        "lib.authorization.initializer.AuthorizationInitializer.reconcile",
        lambda self: None,
    )
    connection = DatabaseConnection(tmp_path / "entropy.db")
    WorkflowJobsTable().create(connection)
    WorkflowEventsTable().create(connection)
    return connection


def test_the_same_name_in_two_projects_has_its_own_icon(connection) -> None:
    store = WorkflowIconStore(connection)

    store.set(workflow_key(1, "deploy"), "rocket", "me")
    store.set(workflow_key(2, "deploy"), "database", "me")

    assert store.all() == {"1/deploy": "rocket", "2/deploy": "database"}


def test_choosing_again_replaces_and_none_goes_back_to_the_default(connection) -> None:
    store = WorkflowIconStore(connection)
    store.set("1/deploy", "rocket", "me")

    store.set("1/deploy", "database", "me")
    assert store.all() == {"1/deploy": "database"}

    store.set("1/deploy", None, "me")
    assert store.all() == {}


@pytest.mark.parametrize("icon", ["", "Rocket", "../x", "a b", "<svg>", "x" * 61])
def test_a_badly_formed_icon_is_refused(connection, icon) -> None:
    with pytest.raises(PluginIconError):
        WorkflowIconStore(connection).set("1/deploy", icon, "me")


def test_the_migration_creates_the_table_and_can_run_twice(connection) -> None:
    with connection.transaction():
        Migration().upgrade(connection)
        Migration().upgrade(connection)

    assert connection.fetchone(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'workflow_icons'"
    )


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------


@pytest.fixture
def world(connection, monkeypatch) -> SimpleNamespace:
    entries = {"deploy": SimpleNamespace(name="deploy")}

    def get(name, project_id):
        if name not in entries:
            raise WorkflowNotFoundError(name)
        return entries[name]

    denied = set()
    context = SimpleNamespace(
        database_manager=SimpleNamespace(connection=connection),
        workflow_manager=SimpleNamespace(get=get),
        authorization=SimpleNamespace(
            has_permission=lambda user, permission, project=None: permission not in denied
        ),
    )
    monkeypatch.setattr(routes, "current_project", lambda request, user: {"id": 7})
    return SimpleNamespace(
        request=SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(entropy_context=context))
        ),
        record=("session", "token", SimpleNamespace(id=1, username="me")),
        denied=denied,
        connection=connection,
    )


def _put(world, name="deploy", icon="rocket"):
    payload = routes.WorkflowIconRequest(icon=icon)
    return routes.set_workflow_icon(name, payload, world.request, world.record)


def test_the_icon_is_saved_for_the_current_project(world) -> None:
    assert _put(world) == {"name": "deploy", "icon": "rocket"}
    assert WorkflowIconStore(world.connection).all() == {"7/deploy": "rocket"}


def test_changing_an_icon_needs_write_access(world) -> None:
    world.denied.add("workflows.write")

    with pytest.raises(routes.HTTPException) as caught:
        _put(world)

    assert caught.value.status_code == 403
    assert WorkflowIconStore(world.connection).all() == {}


def test_an_unknown_workflow_is_not_found(world) -> None:
    with pytest.raises(routes.HTTPException) as caught:
        _put(world, name="missing")

    assert caught.value.status_code == 404


def test_a_badly_formed_icon_is_unprocessable(world) -> None:
    with pytest.raises(routes.HTTPException) as caught:
        _put(world, icon="Not Valid")

    assert caught.value.status_code == 422


# ----------------------------------------------------------------------
# Move and copy between projects
# ----------------------------------------------------------------------


class _Workflows:
    """Just enough of the workflow manager: names per project."""

    def __init__(self, *owned) -> None:
        self.owned = set(owned)

    def exists(self, name, project_id):
        return (project_id, name) in self.owned

    def get(self, name, project_id):
        return name

    def serialize(self, workflow, format_name):
        return json.dumps({"name": workflow})

    def add(self, path, project_id):
        name = json.loads(Path(path).read_text())["name"]
        self.owned.add((project_id, name))
        return SimpleNamespace(name=name)

    def move(self, name, source_project_id, target_project_id):
        self.owned.discard((source_project_id, name))
        self.owned.add((target_project_id, name))


def _send(connection, mode, *owned):
    transfer = ProjectTransfer(
        SimpleNamespace(
            database_manager=SimpleNamespace(connection=connection),
            workflow_manager=_Workflows(*owned),
        )
    )
    return transfer.transfer(
        1,
        2,
        workflows=["deploy"],
        schedule_ids=[],
        mode=mode,
        with_schedules=False,
        user=SimpleNamespace(id=1, username="me"),
    )


def test_a_moved_workflow_keeps_its_icon(connection) -> None:
    store = WorkflowIconStore(connection)
    store.set("1/deploy", "rocket", "me")

    result = _send(connection, "move", (1, "deploy"))

    assert result["errors"] == []
    assert store.all() == {"2/deploy": "rocket"}


def test_a_copy_has_the_same_icon_under_its_own_name(connection) -> None:
    store = WorkflowIconStore(connection)
    store.set("1/deploy", "rocket", "me")

    result = _send(connection, "copy", (1, "deploy"), (2, "deploy"))

    assert result["workflows"] == [{"name": "deploy", "as": "deploy-2"}]
    assert store.all() == {"1/deploy": "rocket", "2/deploy-2": "rocket"}


def test_copying_a_workflow_without_an_icon_adds_none(connection) -> None:
    store = WorkflowIconStore(connection)

    assert _send(connection, "copy", (1, "deploy"))["errors"] == []
    assert store.all() == {}
