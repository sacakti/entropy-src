"""Pull and push between Entropy's copy of a repository and its remote, and Git credentials."""

from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path

import pytest

from lib.database.connection import DatabaseConnection
from lib.git_repositories.remote import (
    GitCredentialStore,
    GitRemoteError,
    branch_status,
    normalize_host,
    pull,
    push,
    record_tracking,
    remote_environment,
    remote_host,
)

IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def _run(*arguments: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **IDENTITY},
    ).stdout.strip()


def _commit(git_dir: Path, branch: str, name: str, work: Path) -> None:
    """Add a commit to *branch* of the bare repository *git_dir*."""
    if not work.exists():
        _run("clone", "--quiet", str(git_dir), str(work))
    _run("fetch", "--quiet", "origin", cwd=work)
    remote_branches = _run("branch", "-r", cwd=work)
    if f"origin/{branch}" in remote_branches:
        _run("checkout", "--quiet", "-B", branch, f"origin/{branch}", cwd=work)
    else:
        _run("checkout", "--quiet", "--orphan", branch, cwd=work)
    (work / name).write_text(name)
    _run("add", name, cwd=work)
    _run("commit", "--quiet", "-m", name, cwd=work)
    _run("push", "--quiet", "origin", f"HEAD:refs/heads/{branch}", cwd=work)


@pytest.fixture
def repos(tmp_path):
    """A remote with a commit on main, and Entropy's mirror of it."""
    remote = tmp_path / "remote.git"
    _run("init", "--quiet", "--bare", "-b", "main", str(remote))
    _commit(remote, "main", "one.txt", tmp_path / "upstream")
    mirror = tmp_path / "mirror.git"
    _run("clone", "--quiet", "--mirror", str(remote), str(mirror))
    record_tracking(str(mirror))
    return remote, mirror, tmp_path


def _head(git_dir: Path, ref: str) -> str:
    return _run("--git-dir", str(git_dir), "rev-parse", ref)


def test_pull_fast_forwards_and_creates_branches(repos) -> None:
    remote, mirror, tmp = repos
    _commit(remote, "main", "two.txt", tmp / "upstream")
    _commit(remote, "feature", "f.txt", tmp / "upstream")

    summary = pull(str(mirror), str(remote))

    assert summary["updated"] == ["main"] and summary["created"] == ["feature"]
    assert _head(mirror, "refs/heads/main") == _head(remote, "refs/heads/main")
    assert branch_status(str(mirror), "main") == {"tracking": True, "ahead": 0, "behind": 0}


def test_pull_keeps_local_commits_and_push_sends_them(repos) -> None:
    remote, mirror, tmp = repos
    _commit(mirror, "main", "local.txt", tmp / "entropy")
    local = _head(mirror, "refs/heads/main")

    assert pull(str(mirror), str(remote))["ahead"] == ["main"]
    assert _head(mirror, "refs/heads/main") == local
    assert branch_status(str(mirror), "main")["ahead"] == 1

    push(str(mirror), str(remote), "main")
    assert _head(remote, "refs/heads/main") == local
    assert branch_status(str(mirror), "main") == {"tracking": True, "ahead": 0, "behind": 0}


def test_diverged_branch_is_reported_and_push_is_rejected(repos) -> None:
    remote, mirror, tmp = repos
    _commit(mirror, "main", "local.txt", tmp / "entropy")
    _commit(remote, "main", "upstream.txt", tmp / "upstream")
    local = _head(mirror, "refs/heads/main")

    assert pull(str(mirror), str(remote))["diverged"] == ["main"]
    assert _head(mirror, "refs/heads/main") == local
    with pytest.raises(GitRemoteError, match="Pull the latest changes"):
        push(str(mirror), str(remote), "main")


def test_new_branch_is_pushed(repos) -> None:
    remote, mirror, _ = repos
    _run("--git-dir", str(mirror), "branch", "topic", "main")
    assert branch_status(str(mirror), "topic")["tracking"] is False

    push(str(mirror), str(remote), "topic")
    assert _head(remote, "refs/heads/topic") == _head(mirror, "refs/heads/topic")


def test_hosts() -> None:
    assert remote_host("git@github.com:org/repo.git") == "github.com"
    assert remote_host("https://GitHub.com/org/repo.git") == "github.com"
    assert remote_host("https://git.example.com:8443/r.git") == "git.example.com:8443"
    assert normalize_host("https://github.com/") == "github.com"
    with pytest.raises(GitRemoteError):
        normalize_host("not a host")


def test_token_reaches_git_only_through_the_environment() -> None:
    environment = remote_environment("https://github.com/org/repo.git", ("ana", "s3cret"))
    assert environment["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraHeader"
    expected = base64.b64encode(b"ana:s3cret").decode()
    assert environment["GIT_CONFIG_VALUE_0"] == f"Authorization: Basic {expected}"
    assert "GIT_CONFIG_COUNT" not in remote_environment("git@github.com:org/repo.git", ("ana", "x"))


def test_credentials_are_encrypted_and_per_user(tmp_path) -> None:
    db = DatabaseConnection(tmp_path / "entropy.db")
    db.open()
    try:
        store = GitCredentialStore(db, os.urandom(32))
        store.set_identity(1, "Ana Lee", "ana@example.com")
        store.set_credential(1, "https://GitHub.com", "ana", "ghp_token")

        assert store.identity(1) == {"name": "Ana Lee", "email": "ana@example.com"}
        assert store.identity(2) is None
        assert [item["host"] for item in store.credentials(1)] == ["github.com"]
        assert "token" not in store.credentials(1)[0] and "secret" not in store.credentials(1)[0]
        assert store.credential(1, "github.com") == ("ana", "ghp_token")
        assert store.credential(2, "github.com") is None
        stored = db.fetchone("SELECT secret FROM entropy_git_credentials")["secret"]
        assert "ghp_token" not in stored

        with pytest.raises(GitRemoteError, match="email"):
            store.set_identity(1, "Ana", "not-an-email")
        store.delete_credential(1, "github.com")
        assert store.credentials(1) == []
    finally:
        db.close()
