"""Vault namespaces belong to projects; runs read only their project's secrets."""

from __future__ import annotations

import pytest

# Import the vault package first: importing lib.database.repositories.vault
# on its own is a circular import (as before this change).
from lib.vault import (
    VaultKeyProvider,
    VaultManager,
    VaultRepository,
    VaultSerializer,
)  # isort: skip
from lib.authorization.projects import Projects, default_project_id
from lib.database.connection import DatabaseConnection
from lib.database.objects.vault import VaultEntriesTable
from lib.database.objects.vault_namespaces import VaultNamespacesTable
from lib.database.repositories.vault_namespaces import VaultNamespaceRepository
from lib.executor import LinuxExecutor
from lib.models.vault import VaultValueType
from lib.vault.exceptions import (
    VaultAccessDeniedError,
    VaultNamespaceExistsError,
    VaultNamespaceNotFoundError,
)
from lib.vault.namespace_manager import VaultNamespaceManager
from lib.vault.projects import PROJECT_ENV


class FakeAuthorization:
    """Grants as (user_id, permission, project_id) triples."""

    def __init__(self, *grants: tuple) -> None:
        self.grants = set(grants)

    def has_permission(self, user_id: int, permission: str, project_id=None) -> bool:
        return (user_id, permission, project_id) in self.grants


@pytest.fixture
def connection(tmp_path):
    connection = DatabaseConnection(tmp_path / "entropy.db")
    connection.open()
    VaultNamespacesTable().create(connection)
    VaultEntriesTable().create(connection)
    connection.commit()
    yield connection
    connection.close()


@pytest.fixture
def projects(connection):
    return {
        "default": default_project_id(connection),
        "alpha": Projects(connection).create("alpha", "Alpha", "", "admin")["id"],
    }


@pytest.fixture
def namespaces(connection):
    return VaultNamespaceManager(VaultNamespaceRepository(connection))


def _vault(connection, namespaces, tmp_path, authorization) -> VaultManager:
    return VaultManager(
        repository=VaultRepository(connection),
        serializer=VaultSerializer(),
        key_provider=VaultKeyProvider(LinuxExecutor(), tmp_path / "vault" / "master.key"),
        namespace_manager=namespaces,
        authorization=authorization,
    )


# ----------------------------------------------------------------------
# Names per project
# ----------------------------------------------------------------------


def test_the_same_name_may_exist_in_each_project(namespaces, projects) -> None:
    default = namespaces.create("app", projects["default"], owner_user_id=1)
    alpha = namespaces.create("app", projects["alpha"], owner_user_id=1)

    assert default.id != alpha.id
    assert namespaces.get("app", projects["alpha"]).id == alpha.id
    assert [item.name for item in namespaces.list(projects["alpha"])] == ["app"]

    with pytest.raises(VaultNamespaceExistsError):
        namespaces.create("app", projects["alpha"])


def test_a_namespace_of_another_project_is_not_found(namespaces, projects) -> None:
    namespaces.create("only-default", projects["default"])

    with pytest.raises(VaultNamespaceNotFoundError):
        namespaces.get("only-default", projects["alpha"])


def test_rename_checks_names_in_its_project_only(namespaces, projects) -> None:
    namespaces.create("taken", projects["default"])
    alpha = namespaces.create("mine", projects["alpha"])

    assert namespaces.modify(alpha, name="taken").name == "taken"

    other = namespaces.create("other", projects["alpha"])
    with pytest.raises(VaultNamespaceExistsError):
        namespaces.modify(other, name="taken")


# ----------------------------------------------------------------------
# Runs
# ----------------------------------------------------------------------


@pytest.fixture
def secrets(connection, namespaces, projects, tmp_path):
    """'app/url' in both projects with different values; 'shared/x' in Default only."""

    vault = _vault(connection, namespaces, tmp_path, None)
    for project, value in (("default", "https://default"), ("alpha", "https://alpha")):
        namespace = namespaces.create("app", projects[project])
        vault.add(namespace.id, "url", value, VaultValueType.STRING, sensitive=True)
    shared = namespaces.create("shared", projects["default"])
    vault.add(shared.id, "x", "secret", VaultValueType.STRING)
    return projects


def test_a_run_resolves_in_its_own_project(
    connection, namespaces, secrets, tmp_path, monkeypatch
) -> None:
    alpha = secrets["alpha"]
    vault = _vault(
        connection, namespaces, tmp_path, FakeAuthorization((7, "workflows.execute", alpha))
    )
    monkeypatch.setenv(PROJECT_ENV, str(alpha))

    assert vault.resolve("app", "url", 7) == "https://alpha"
    # The matched prefix is dropped from the keys (existing behaviour).
    assert vault.resolve_matching("app", "u*", 7) == {"rl": "https://alpha"}

    # Another project's namespace is not visible to the run.
    with pytest.raises(VaultNamespaceNotFoundError):
        vault.resolve("shared", "x", 7)


def test_plugin_runners_may_read_too(connection, namespaces, secrets, tmp_path, monkeypatch):
    alpha = secrets["alpha"]
    vault = _vault(
        connection, namespaces, tmp_path, FakeAuthorization((7, "plugins.execute", alpha))
    )
    monkeypatch.setenv(PROJECT_ENV, str(alpha))

    assert vault.resolve("app", "url", 7) == "https://alpha"


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        FakeAuthorization(),
        # Revealing in the UI is not the same as running: runs need run rights.
        FakeAuthorization((7, "vault.read", "ALPHA")),
    ],
)
def test_a_run_whose_starter_may_not_run_there_is_denied(
    connection, namespaces, secrets, tmp_path, monkeypatch, authorization
) -> None:
    alpha = secrets["alpha"]
    if isinstance(authorization, FakeAuthorization):
        authorization.grants = {
            (user, permission, alpha if project == "ALPHA" else project)
            for user, permission, project in authorization.grants
        }
    vault = _vault(connection, namespaces, tmp_path, authorization)
    monkeypatch.setenv(PROJECT_ENV, str(alpha))

    with pytest.raises(VaultAccessDeniedError):
        vault.resolve("app", "url", 7)


def test_without_a_run_project_the_default_project_is_used(
    connection, namespaces, secrets, tmp_path, monkeypatch
) -> None:
    vault = _vault(
        connection,
        namespaces,
        tmp_path,
        FakeAuthorization((7, "workflows.execute", secrets["default"])),
    )
    monkeypatch.delenv(PROJECT_ENV, raising=False)

    assert vault.resolve("app", "url", 7) == "https://default"
