"""Workflow names are unique per project, not across Entropy."""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.authorization.projects import Projects, default_project_id, workflow_key
from lib.database.connection import DatabaseConnection
from lib.database.objects.workflow_registry import WorkflowRegistryTable
from lib.database.repositories.workflow_registry import WorkflowRegistryRepository
from lib.runs.alerts import RunAlerts
from lib.workflow.drafts import WorkflowDrafts

NOW = "2026-01-01T00:00:00+00:00"


def _migration():
    import importlib

    module = importlib.import_module("lib.migrations.scripts.025_project_scoped_workflows")
    return module.ProjectScopedWorkflowsMigration()


def _connection(tmp_path: Path) -> DatabaseConnection:
    return DatabaseConnection(tmp_path / "entropy.db")


def _projects(connection: DatabaseConnection) -> tuple[int, int, int]:
    projects = Projects(connection)
    default_id = default_project_id(connection)
    one = projects.create("project-1", "Project 1", "", "alice")["id"]
    two = projects.create("project-2", "Project 2", "", "alice")["id"]
    return default_id, one, two


def _create(registry: WorkflowRegistryRepository, project_id: int, name: str, body: str = "{}"):
    return registry.create(
        project_id=project_id,
        name=name,
        version="1.0.0",
        description=None,
        definition=body,
        created_at=NOW,
        updated_at=NOW,
    )


# ----------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------


def test_the_same_name_exists_in_two_projects(tmp_path: Path) -> None:
    connection = _connection(tmp_path)
    WorkflowRegistryTable().create(connection)
    _, one, two = _projects(connection)
    registry = WorkflowRegistryRepository(connection)

    _create(registry, one, "CopyFiles", '{"in": 1}')
    _create(registry, two, "CopyFiles", '{"in": 2}')

    assert registry.get_by_name(one, "CopyFiles").definition == '{"in": 1}'
    assert registry.get_by_name(two, "CopyFiles").definition == '{"in": 2}'
    assert [entry.name for entry in registry.list(one)] == ["CopyFiles"]
    assert len(registry.list()) == 2

    registry.delete(one, "CopyFiles")
    assert not registry.exists(one, "CopyFiles")
    assert registry.exists(two, "CopyFiles")


def test_a_name_is_still_unique_within_a_project(tmp_path: Path) -> None:
    connection = _connection(tmp_path)
    WorkflowRegistryTable().create(connection)
    _, one, _ = _projects(connection)
    registry = WorkflowRegistryRepository(connection)
    _create(registry, one, "CopyFiles")

    with pytest.raises(Exception, match="UNIQUE"):
        _create(registry, one, "CopyFiles")


def test_update_and_move_touch_only_that_project(tmp_path: Path) -> None:
    connection = _connection(tmp_path)
    WorkflowRegistryTable().create(connection)
    _, one, two = _projects(connection)
    registry = WorkflowRegistryRepository(connection)
    _create(registry, one, "CopyFiles", "{}")
    _create(registry, two, "Other", "{}")

    registry.update(
        project_id=one,
        name="CopyFiles",
        version="1.0.1",
        description=None,
        definition='{"changed": true}',
        updated_at=NOW,
    )
    registry.move("CopyFiles", one, two)

    assert not registry.exists(one, "CopyFiles")
    assert registry.get_by_name(two, "CopyFiles").version == "1.0.1"
    assert Projects(connection).usage(two)["workflows"] == 2
    assert Projects(connection).usage(one)["workflows"] == 0


# ----------------------------------------------------------------------
# Migration 025
# ----------------------------------------------------------------------


def _legacy_database(tmp_path: Path):
    """A database from before project scoped names, with alerts and history."""

    connection = _connection(tmp_path)
    connection.execute(
        """
        CREATE TABLE workflow_registry
        (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            version TEXT NOT NULL,
            description TEXT,
            definition TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    default_id, one, two = _projects(connection)
    for name in ("CopyFiles", "Legacy"):
        connection.execute(
            "INSERT INTO workflow_registry (name, version, description, definition,"
            " created_at, updated_at) VALUES (?, '1.0.0', NULL, '{}', ?, ?)",
            (name, NOW, NOW),
        )
    # CopyFiles was project-1's; Legacy had no project row (Default).
    connection.execute(
        "INSERT INTO workflow_projects (workflow, project_id) VALUES ('CopyFiles', ?)", (one,)
    )
    RunAlerts(connection).set(
        "workflow",
        "CopyFiles",
        emails=["ops@example.com"],
        on_success=True,
        on_failure=True,
        on_cancel=False,
        user="alice",
    )
    from lib.history import DefinitionHistory

    DefinitionHistory(connection, "workflow").record("Legacy", "0.9.0", {"name": "Legacy"})
    return connection, default_id, one, two


def test_migration_keeps_each_workflow_in_its_project(tmp_path: Path) -> None:
    connection, default_id, one, two = _legacy_database(tmp_path)

    _migration().upgrade(connection)

    registry = WorkflowRegistryRepository(connection)
    assert registry.exists(one, "CopyFiles")
    assert registry.exists(default_id, "Legacy")
    # Now project-2 may have its own CopyFiles.
    _create(registry, two, "CopyFiles")
    assert registry.exists(two, "CopyFiles")

    assert RunAlerts(connection).get("workflow", workflow_key(one, "CopyFiles"))["emails"] == [
        "ops@example.com"
    ]
    from lib.history import DefinitionHistory

    kept = DefinitionHistory(connection, "workflow").list(workflow_key(default_id, "Legacy"))
    assert [item["version"] for item in kept] == ["0.9.0"]


def test_migration_runs_once(tmp_path: Path) -> None:
    connection, _, one, _ = _legacy_database(tmp_path)

    _migration().upgrade(connection)
    _migration().upgrade(connection)

    assert WorkflowRegistryRepository(connection).exists(one, "CopyFiles")


def test_migration_skips_a_new_install(tmp_path: Path) -> None:
    connection = _connection(tmp_path)
    WorkflowRegistryTable().create(connection)

    _migration().upgrade(connection)

    columns = {row["name"] for row in connection.fetchall("PRAGMA table_info(workflow_registry)")}
    assert "project_id" in columns


# ----------------------------------------------------------------------
# Per-project companions
# ----------------------------------------------------------------------


def test_drafts_of_the_same_name_are_kept_per_project(tmp_path: Path) -> None:
    connection = _connection(tmp_path)
    _, one, two = _projects(connection)
    drafts = WorkflowDrafts(connection)

    for project_id in (one, two):
        drafts.save(
            draft_id=None,
            workflow="CopyFiles",
            title="CopyFiles",
            format="json",
            definition=f'{{"project": {project_id}}}',
            errors=[],
            user="alice",
            project_id=project_id,
        )

    assert drafts.for_workflow("CopyFiles", one)["project_id"] == one
    assert drafts.for_workflow("CopyFiles", two)["project_id"] == two

    drafts.delete_for_workflow("CopyFiles", one)
    assert drafts.for_workflow("CopyFiles", one) is None
    assert drafts.for_workflow("CopyFiles", two) is not None


def test_run_alerts_follow_the_runs_project(tmp_path: Path) -> None:
    connection = _connection(tmp_path)
    _, one, two = _projects(connection)
    alerts = RunAlerts(connection)
    alerts.set(
        "workflow",
        workflow_key(one, "CopyFiles"),
        emails=["one@example.com"],
        on_success=True,
        on_failure=True,
        on_cancel=False,
        user="alice",
    )

    finished = {"kind": "workflow", "target": "CopyFiles", "state": "completed"}

    assert alerts.recipients({**finished, "project_id": one}) == ["one@example.com"]
    assert alerts.recipients({**finished, "project_id": two}) == []


# ----------------------------------------------------------------------
# WorkflowManager
# ----------------------------------------------------------------------


def _manager(tmp_path: Path, connection: DatabaseConnection):
    """A WorkflowManager over a real registry and codecs (plugins not checked)."""

    from types import SimpleNamespace
    from unittest.mock import Mock

    from lib.executor.linux import LinuxExecutor
    from lib.workflow.codec.json import JsonWorkflowCodec
    from lib.workflow.codec.registry import WorkflowCodecRegistry
    from lib.workflow.manager import WorkflowManager

    codecs = WorkflowCodecRegistry([JsonWorkflowCodec(LinuxExecutor())])
    manager = WorkflowManager.__new__(WorkflowManager)
    manager._context = SimpleNamespace(
        database_manager=SimpleNamespace(connection=connection),
        workflow_codecs=codecs,
        paths=SimpleNamespace(workspace=SimpleNamespace(workflows=tmp_path / "workflows")),
    )
    manager._registry = WorkflowRegistryRepository(connection)
    manager._validator = Mock()
    manager._loader = SimpleNamespace(load=lambda path: codecs.get("json").decode(path.read_text()))
    return manager


def _definition(tmp_path: Path, name: str, message: str) -> Path:
    import json

    path = tmp_path / f"{name}-{message}.json"
    path.write_text(
        json.dumps(
            {
                "name": name,
                "version": "1.0.0",
                "steps": [
                    {"name": "say", "plugin": "builtin.hello", "arguments": {"text": message}}
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_manager_keeps_same_named_workflows_apart(tmp_path: Path, monkeypatch) -> None:
    from lib.vault.projects import PROJECT_ENV
    from lib.workflow.exceptions import WorkflowAlreadyExistsError, WorkflowNotFoundError

    monkeypatch.delenv(PROJECT_ENV, raising=False)
    connection = _connection(tmp_path)
    WorkflowRegistryTable().create(connection)
    default_id, one, two = _projects(connection)
    manager = _manager(tmp_path, connection)

    manager.add(_definition(tmp_path, "CopyFiles", "one"), project_id=one)
    manager.add(_definition(tmp_path, "CopyFiles", "two"), project_id=two)
    with pytest.raises(WorkflowAlreadyExistsError):
        manager.add(_definition(tmp_path, "CopyFiles", "again"), project_id=one)

    def text(project_id):
        return manager.get("CopyFiles", project_id=project_id).steps[0].arguments["text"]

    assert (text(one), text(two)) == ("one", "two")
    assert [entry.name for entry in manager.list(project_id=two)] == ["CopyFiles"]
    assert len(manager.list_all()) == 2

    manager.replace("CopyFiles", _definition(tmp_path, "CopyFiles", "one-b"), project_id=one)
    assert (text(one), text(two)) == ("one-b", "two")

    # Without a project: the run worker's project, else Default.
    with pytest.raises(WorkflowNotFoundError):
        manager.get("CopyFiles")
    monkeypatch.setenv(PROJECT_ENV, str(two))
    assert text(None) == "two"
    monkeypatch.delenv(PROJECT_ENV)

    # A run's definition file is per project, so two runs cannot overwrite each other.
    first = manager._materialize(manager.get("CopyFiles", project_id=one), one)
    second = manager._materialize(manager.get("CopyFiles", project_id=two), two)
    assert first != second and first.name == second.name == "CopyFiles.json"

    with pytest.raises(WorkflowAlreadyExistsError):
        manager.move("CopyFiles", source_project_id=one, target_project_id=two)
    manager.remove("CopyFiles", project_id=one)
    assert not manager.exists("CopyFiles", project_id=one)
    assert manager.exists("CopyFiles", project_id=two)
    manager.move("CopyFiles", source_project_id=two, target_project_id=default_id)
    assert text(None) == "two"
