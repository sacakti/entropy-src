"""Kept versions of workflows and plugins."""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.database.connection import DatabaseConnection
from lib.history import KEEP, DefinitionHistory


@pytest.fixture
def connection(tmp_path: Path) -> DatabaseConnection:
    return DatabaseConnection(tmp_path / "entropy.db")


def test_keeps_the_last_five_versions_per_item(connection) -> None:
    workflows = DefinitionHistory(connection, "workflow")
    for index in range(KEEP + 3):
        workflows.record("deploy", f"1.0.{index}", {"steps": index}, user="admin")
    workflows.record("other", "2.0.0", "{}")

    items = workflows.list("deploy")
    assert [item["version"] for item in items] == [f"1.0.{i}" for i in range(KEEP + 2, 2, -1)]
    assert len(workflows.list("other")) == 1

    newest = workflows.get("deploy", items[0]["id"])
    assert newest["content"] == {"steps": KEEP + 2} and newest["created_by"] == "admin"


def test_kinds_are_separate_and_forget_drops_history(connection) -> None:
    workflows = DefinitionHistory(connection, "workflow")
    plugins = DefinitionHistory(connection, "plugin")
    workflows.record("x", "1", "a")
    plugins.record("x", "1", {"plugin.json": "{}"})

    assert plugins.get("x", workflows.list("x")[0]["id"]) is None
    workflows.forget("x")
    assert workflows.list("x") == [] and len(plugins.list("x")) == 1

    with pytest.raises(ValueError):
        DefinitionHistory(connection, "vault")
