"""Vault namespaces belong to projects."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lib.authorization.projects import Projects, default_project_id
from lib.database.connection import DatabaseConnection
from lib.vault import projects as vault_projects
from lib.vault.exceptions import VaultAccessDeniedError
from lib.vault.manager import VaultManager


@pytest.fixture
def connection(tmp_path):
    connection = DatabaseConnection(tmp_path / "entropy.db")
    connection.open()
    connection.execute("CREATE TABLE vault_namespaces (id INTEGER PRIMARY KEY, name TEXT)")
    for number, name in ((1, "old"), (2, "alpha-ns")):
        connection.execute("INSERT INTO vault_namespaces (id, name) VALUES (?, ?)", (number, name))
    connection.commit()
    yield connection
    connection.close()


def test_namespaces_default_to_the_default_project(connection, monkeypatch) -> None:
    alpha = Projects(connection).create("alpha", "Alpha", "", "admin")["id"]
    default = default_project_id(connection)
    vault_projects.set_namespace_project(connection, 2, alpha)

    assert vault_projects.namespace_project(connection, 1) == default
    assert vault_projects.namespaces_in(connection, default) == {1}
    assert vault_projects.namespaces_in(connection, alpha) == {2}


def test_a_run_reads_only_its_own_project(connection, monkeypatch) -> None:
    alpha = Projects(connection).create("alpha", "Alpha", "", "admin")["id"]
    vault_projects.set_namespace_project(connection, 2, alpha)
    manager = VaultManager(
        repository=SimpleNamespace(connection=connection),
        serializer=None,
        key_provider=None,
        namespace_manager=None,
    )

    monkeypatch.setenv(vault_projects.PROJECT_ENV, str(alpha))
    manager._require_run_project(SimpleNamespace(id=2, name="alpha-ns"))
    with pytest.raises(VaultAccessDeniedError, match="another project"):
        manager._require_run_project(SimpleNamespace(id=1, name="old"))

    # Outside a run worker (web, CLI) the project check does not apply.
    monkeypatch.delenv(vault_projects.PROJECT_ENV)
    manager._require_run_project(SimpleNamespace(id=1, name="old"))
