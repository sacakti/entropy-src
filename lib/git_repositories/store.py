"""Persistence and runtime checkout support for managed Git repositories."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lib.database.connection import DatabaseConnection


def ensure_git_repositories_schema(connection: DatabaseConnection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS entropy_git_repositories ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, repo_key TEXT NOT NULL UNIQUE,"
        "name TEXT NOT NULL, scope TEXT NOT NULL CHECK(scope IN ('user','project')),"
        "owner_user_id INTEGER, project_id INTEGER, bare_path TEXT NOT NULL,"
        "source_type TEXT NOT NULL DEFAULT 'managed', source_location TEXT,"
        "created_by TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ")"
    )
    columns = {row["name"] for row in connection.fetchall("PRAGMA table_info(entropy_git_repositories)")}
    if "source_type" not in columns:
        connection.execute("ALTER TABLE entropy_git_repositories ADD COLUMN source_type TEXT NOT NULL DEFAULT 'managed'")
    if "source_location" not in columns:
        connection.execute("ALTER TABLE entropy_git_repositories ADD COLUMN source_location TEXT")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS entropy_git_repository_assignments ("
        "repository_id INTEGER NOT NULL REFERENCES entropy_git_repositories(id) ON DELETE CASCADE,"
        "project_id INTEGER NOT NULL, target_type TEXT NOT NULL CHECK(target_type IN ('workflow','plugin')) ,"
        "target_key TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')),"
        "PRIMARY KEY(repository_id, project_id, target_type, target_key)"
        ")"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS entropy_git_repositories_owner "
        "ON entropy_git_repositories(owner_user_id, project_id)"
    )


class GitRepositoryStore:
    def __init__(self, connection: DatabaseConnection) -> None:
        self.connection = connection

    def get(self, repository_id: int) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone(
            "SELECT * FROM entropy_git_repositories WHERE id = ?", (repository_id,)
        )
        return dict(row) if row else None

    def visible(self, project_id: int, user_id: int, include_project: bool) -> List[Dict[str, Any]]:
        if include_project:
            rows = self.connection.fetchall(
                "SELECT * FROM entropy_git_repositories WHERE owner_user_id = ? "
                "OR (scope = 'project' AND project_id = ?) ORDER BY name COLLATE NOCASE, id",
                (user_id, project_id),
            )
        else:
            rows = self.connection.fetchall(
                "SELECT * FROM entropy_git_repositories WHERE owner_user_id = ? "
                "ORDER BY name COLLATE NOCASE, id", (user_id,)
            )
        return [dict(row) for row in rows]

    def assignments(self, repository_id: int, project_id: int) -> List[Dict[str, str]]:
        return [dict(row) for row in self.connection.fetchall(
            "SELECT target_type, target_key FROM entropy_git_repository_assignments "
            "WHERE repository_id = ? AND project_id = ? ORDER BY target_type, target_key",
            (repository_id, project_id),
        )]

    def replace_assignments(self, repository_id: int, project_id: int,
                            assignments: List[Dict[str, str]]) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "DELETE FROM entropy_git_repository_assignments WHERE repository_id = ? AND project_id = ?",
                (repository_id, project_id),
            )
            for item in assignments:
                self.connection.execute(
                    "INSERT INTO entropy_git_repository_assignments(repository_id, project_id, target_type, target_key) "
                    "VALUES (?, ?, ?, ?)",
                    (repository_id, project_id, item["target_type"], item["target_key"]),
                )

    def delete(self, repository_id: int) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "DELETE FROM entropy_git_repository_assignments WHERE repository_id = ?", (repository_id,)
            )
            self.connection.execute("DELETE FROM entropy_git_repositories WHERE id = ?", (repository_id,))


def safe_checkout_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    return safe[:80] or "repository"


def _run_identity(context: Any) -> Tuple[int, int]:
    """(project id, user id) of the run, for which repositories it may use."""
    from lib.authorization.projects import default_project_id
    from lib.vault.projects import run_project

    connection = context.database.connection
    ensure_git_repositories_schema(connection)
    project_id = run_project() or default_project_id(connection)
    user_row = connection.fetchone("SELECT id FROM users WHERE username = ?", (context.user,))
    user_id = int(user_row["id"]) if user_row else -1
    return project_id, user_id


def _checkout(context: Any, repo: Dict[str, Any]) -> Path:
    """A working copy of a managed repository in the run's workspace (origin: the repository)."""
    checkout_root = context.workspace / ".entropy-repositories"
    checkout_root.mkdir(parents=True, exist_ok=True)
    destination = checkout_root / f"{repo['id']}-{safe_checkout_name(repo['name'])}"
    if not (destination / ".git").is_dir():
        completed = subprocess.run(
            ["git", "clone", "--quiet", "--", repo["bare_path"], str(destination)],
            cwd=context.workspace,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if completed.returncode:
            detail = (completed.stderr or completed.stdout or "Git clone failed.").strip()
            raise RuntimeError(f"Unable to prepare repository '{repo['name']}': {detail}")
        # Commits made in the run are by its user, as in the repository browser.
        user = str(context.user or "entropy")
        for key, value in (("user.name", user), ("user.email", f"{user}@entropy.local")):
            subprocess.run(
                ["git", "-C", str(destination), "config", key, value],
                capture_output=True,
                timeout=30,
                check=False,
            )
    return destination


def checkout_assigned_repositories(context: Any, plugin_name: str) -> Dict[str, Path]:
    """Clone repositories assigned to the active workflow and plugin into its workspace."""
    connection = context.database.connection
    project_id, user_id = _run_identity(context)
    workflow = getattr(context.execution, "workflow", None)
    workflow_name = getattr(workflow, "name", None) if workflow is not None else None
    rows = connection.fetchall(
        "SELECT DISTINCT r.* FROM entropy_git_repositories r "
        "JOIN entropy_git_repository_assignments a ON a.repository_id = r.id "
        "WHERE a.project_id = ? AND ((a.target_type = 'plugin' AND a.target_key = ?) "
        "OR (a.target_type = 'workflow' AND a.target_key = ?)) "
        "AND (r.scope = 'project' OR r.owner_user_id = ?) ORDER BY r.name COLLATE NOCASE",
        (project_id, plugin_name, workflow_name or "", user_id),
    )
    if not rows:
        return {}

    result: Dict[str, Path] = {}
    for row in rows:
        repo = dict(row)
        if repo["name"] in result:
            raise RuntimeError(
                f"More than one assigned Git repository is named '{repo['name']}'. "
                "Use distinct repository names for assigned repositories."
            )
        result[repo["name"]] = _checkout(context, repo)
    return result


def find_repository(
    connection: DatabaseConnection, project_id: int, user_id: int, reference: str
) -> Dict[str, Any]:
    """
    A repository from Tools -> Git repositories by name (or id) that the user may
    use in the project: their own, or the project's.
    """
    ensure_git_repositories_schema(connection)
    text = str(reference or "").strip()
    if not text:
        raise RuntimeError("Name a repository from Tools -> Git repositories.")
    rows = [
        dict(row)
        for row in connection.fetchall(
            "SELECT * FROM entropy_git_repositories WHERE "
            "((scope = 'project' AND project_id = ?) OR owner_user_id = ?) "
            "AND (name = ? COLLATE NOCASE OR CAST(id AS TEXT) = ?) ORDER BY id",
            (project_id, user_id, text, text),
        )
    ]
    if not rows:
        raise RuntimeError(
            f"No Git repository '{text}' is available to you in this project "
            "(Tools -> Git repositories)."
        )
    if len(rows) > 1:
        ids = ", ".join(str(row["id"]) for row in rows)
        raise RuntimeError(
            f"More than one Git repository is named '{text}' (ids {ids}); use the id instead."
        )
    return rows[0]


def repository_info(context: Any, reference: str) -> Dict[str, Any]:
    """
    A repository from Tools -> Git repositories that the run may use, without
    checking it out: its name, how it was created and Entropy's copy (`path`).
    `source_location` is the server folder for repositories created from one
    (source_type 'local'); remote URLs are not passed on.
    """
    project_id, user_id = _run_identity(context)
    repo = find_repository(context.database.connection, project_id, user_id, reference)
    source_type = repo.get("source_type") or "managed"
    return {
        "id": repo["id"],
        "name": repo["name"],
        "source_type": source_type,
        "source_location": repo.get("source_location") if source_type == "local" else None,
        "path": repo["bare_path"],
    }


def checkout_repository(context: Any, reference: str) -> Path:
    """Check out a repository from Tools -> Git repositories (by name or id) for this run."""
    project_id, user_id = _run_identity(context)
    repo = find_repository(context.database.connection, project_id, user_id, reference)
    return _checkout(context, repo)
