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


def _commit(work, user, files) -> None:
    for path, text in files.items():
        target = work / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    subprocess.run(["git", "-C", str(work), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(work),
            "-c",
            f"user.name={user}",
            "-c",
            f"user.email={user}@x",
            "commit",
            "--quiet",
            "-m",
            "change",
        ],
        check=True,
    )


def test_browser_lists_one_folder_at_a_time_without_a_file_cap(tmp_path) -> None:
    from core.web.routes.git_repositories import _directory_entries

    work = tmp_path / "work"
    subprocess.run(["git", "init", "--quiet", "-b", "main", str(work)], check=True)
    _commit(work, "ana", {f"many/file{i}.txt": "x" for i in range(1200)})
    _commit(work, "ana", {"src/app.py": "print(1)\n", "README.md": "hi"})
    _commit(work, "bo", {"src/app.py": "print(2)\n"})
    bare = tmp_path / "repo.git"
    subprocess.run(["git", "clone", "--quiet", "--mirror", str(work), str(bare)], check=True)

    root = _directory_entries(str(bare), "refs/heads/main", "")
    assert [(e["name"], e["type"]) for e in root["entries"]] == [
        ("many", "dir"),
        ("src", "dir"),
        ("README.md", "file"),
    ]
    src = next(e for e in root["entries"] if e["name"] == "src")
    assert (src["created_by"], src["modified_by"], src["size"]) == ("ana", "bo", None)

    nested = _directory_entries(str(bare), "refs/heads/main", "src")
    assert nested["entries"][0]["path"] == "src/app.py"
    assert nested["entries"][0]["size"] == len("print(2)\n")
    assert len(_directory_entries(str(bare), "refs/heads/main", "many")["entries"]) == 1200
