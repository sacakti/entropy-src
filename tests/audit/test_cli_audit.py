"""Server-side commands (`ent ...` on the Entropy host) are audited too."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.commands.manager import CommandManager
from lib.audit.cli import should_record, target_of, verbs
from lib.audit.store import AuditStore
from lib.auth.exceptions import AuthenticationRequiredError
from lib.database.connection import DatabaseConnection


class FakeCommand:
    def __init__(self, name: str, run) -> None:
        self.metadata = SimpleNamespace(name=name, authentication_required=False)
        self._run = run

    def execute(self, args: Namespace) -> None:
        self._run(args)


@pytest.fixture
def connection(tmp_path: Path) -> DatabaseConnection:
    return DatabaseConnection(tmp_path / "entropy.db")


@pytest.fixture
def manager(connection) -> CommandManager:
    session = SimpleNamespace(username="alice", user_id=3)
    context = SimpleNamespace(
        observability=MagicMock(),
        database_manager=SimpleNamespace(connection=connection),
        session_manager=SimpleNamespace(current=lambda: session, require=lambda: session),
        authorization=None,  # no project lookup: entries without a project
        bootstrap=None,
    )
    return CommandManager(context)


def _run(manager: CommandManager, command: str, run, **args) -> None:
    manager._commands[command] = FakeCommand(command, run)
    manager.execute(command, Namespace(command=command, **args))


def test_workflow_edit_is_recorded(manager, connection) -> None:
    _run(manager, "workflow", lambda args: None, action="edit", name="deploy")

    [entry] = AuditStore(connection).search()[0]
    assert (entry["action"], entry["target"], entry["outcome"]) == (
        "workflow.edit",
        "deploy",
        "success",
    )
    assert entry["username"] == "alice" and entry["source"] == "server-cli"
    assert entry["details"]["command"] == "ent workflow edit"
    assert entry["details"]["os_user"]


def test_reads_are_not_recorded_and_aliases_are_resolved(manager, connection) -> None:
    _run(manager, "workflow", lambda args: None, action="list")
    _run(manager, "help", lambda args: None)
    assert AuditStore(connection).search()[1] == 0
    assert verbs("workflow", Namespace(action="ls")) in (
        ["list"],
        ["ls"],
    )  # alias known to the contract


def test_refusals_and_failures_are_recorded(manager, connection) -> None:
    def refuse(args: Namespace) -> None:
        raise AuthenticationRequiredError()

    def fail(args: Namespace) -> None:
        raise ValueError("Workflow 'x' does not exist.")

    with pytest.raises(SystemExit):
        _run(manager, "workflow", refuse, action="delete", name="prod")
    with pytest.raises(SystemExit):
        _run(manager, "user", fail, action="disable", username="bob", role_action=None)

    failed, denied = AuditStore(connection).search()[0]
    assert (denied["action"], denied["outcome"]) == ("workflow.delete", "denied")
    assert (failed["action"], failed["target"], failed["outcome"]) == (
        "user.disable",
        "bob",
        "failure",
    )
    assert failed["details"]["error"] == "Workflow 'x' does not exist."


def test_nested_verbs_and_targets() -> None:
    args = Namespace(action="role", role_action="add", username="bob", password="secret")
    assert verbs("user", args) == ["role", "add"]
    assert target_of(args) == "bob"
    assert should_record("user", ["role", "add"])
    assert not should_record("user", ["list"])
    assert not should_record("version", [])
