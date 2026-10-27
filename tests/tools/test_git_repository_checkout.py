"""Plugins use repositories from Tools -> Git repositories by name."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from lib.database.connection import DatabaseConnection
from lib.git_repositories.store import (
    checkout_repository,
    ensure_git_repositories_schema,
    find_repository,
)


@pytest.fixture
def connection(tmp_path):
    db = DatabaseConnection(tmp_path / "entropy.db")
    db.open()
    ensure_git_repositories_schema(db)
    db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)")
    db.execute("INSERT INTO users (id, username) VALUES (1, 'ana'), (2, 'bo')")
    yield db
    db.close()


def _repo(connection, tmp_path, name, scope, owner, project=1):
    bare = tmp_path / f"{name}-{owner}.git"
    subprocess.run(["git", "init", "--quiet", "--bare", "-b", "main", str(bare)], check=True)
    connection.execute(
        "INSERT INTO entropy_git_repositories "
        "(repo_key, name, scope, owner_user_id, project_id, bare_path, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, 'test')",
        (f"{name}-{owner}-{scope}", name, scope, owner, project, str(bare)),
    )
    return bare


def test_find_by_name_or_id_within_the_users_reach(connection, tmp_path) -> None:
    _repo(connection, tmp_path, "notes", "project", 2)
    _repo(connection, tmp_path, "private", "user", 2)
    _repo(connection, tmp_path, "elsewhere", "project", 2, project=9)

    assert find_repository(connection, 1, 1, "NOTES")["name"] == "notes"
    assert find_repository(connection, 1, 1, "1")["name"] == "notes"
    for hidden in ("private", "elsewhere", "missing"):
        with pytest.raises(RuntimeError, match="No Git repository"):
            find_repository(connection, 1, 1, hidden)

    _repo(connection, tmp_path, "notes", "user", 1)
    with pytest.raises(RuntimeError, match="use the id"):
        find_repository(connection, 1, 1, "notes")


def test_checkout_clones_with_the_run_users_identity(connection, tmp_path, monkeypatch) -> None:
    import lib.vault.projects as projects

    monkeypatch.setattr(projects, "run_project", lambda: 1)
    _repo(connection, tmp_path, "notes", "project", 2)
    workspace = tmp_path / "run"
    workspace.mkdir()
    context = SimpleNamespace(
        database=SimpleNamespace(connection=connection), user="ana", workspace=workspace
    )
    path = checkout_repository(context, "notes")
    assert (path / ".git").is_dir() and path.parent == workspace / ".entropy-repositories"
    email = subprocess.run(
        ["git", "-C", str(path), "config", "user.email"], capture_output=True, text=True
    )
    assert email.stdout.strip() == "ana@entropy.local"
    assert checkout_repository(context, "notes") == path  # reused within the run
