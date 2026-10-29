"""Manage Entropy's local Git repositories and resource assignments."""

from __future__ import annotations

import shutil
import subprocess
import uuid
import re
import os
import tempfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Dict, List, Literal, Optional, Tuple
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from core.web.projects import current_project, require
from core.web.routes.auth import _current_session, verify_csrf
from lib.git_repositories.store import GitRepositoryStore, ensure_git_repositories_schema
from lib.models.session import Session
from lib.models.users import User

router = APIRouter(prefix="/api/git-repositories", tags=["git-repositories"])
SessionRecord = Tuple[Session, str, User]


class RepositoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    scope: Literal["user", "project"] = "project"
    source_type: Literal["managed", "local", "remote"] = "managed"
    source_location: Optional[str] = Field(default=None, max_length=2048)


class Assignment(BaseModel):
    target_type: Literal["workflow", "plugin"]
    target_key: str = Field(min_length=1, max_length=255)


class AssignmentUpdate(BaseModel):
    assignments: List[Assignment] = Field(default_factory=list, max_length=500)


class FileWrite(BaseModel):
    branch: str = Field(min_length=1, max_length=255)
    path: str = Field(min_length=1, max_length=2048)
    content: str


class BranchCreate(BaseModel):
    branch: str = Field(min_length=1, max_length=255)
    base_branch: str = Field(min_length=1, max_length=255)


def _store(request: Request) -> GitRepositoryStore:
    connection = request.app.state.entropy_context.database_manager.connection
    ensure_git_repositories_schema(connection)
    return GitRepositoryStore(connection)


def _repo_root(request: Request) -> Path:
    return Path(request.app.state.entropy_context.bootstrap.home) / "git-repositories"


def _remote_source(value: str) -> str:
    value = value.strip()
    if not value or any(character.isspace() for character in value):
        raise HTTPException(status_code=422, detail="Enter a valid HTTPS or SSH Git remote URL.")
    if re.fullmatch(r"[A-Za-z0-9._-]+@[A-Za-z0-9.-]+:[^\s]+", value):
        return value
    parsed = urlsplit(value)
    if parsed.scheme not in {"https", "ssh"} or not parsed.hostname or parsed.query or parsed.fragment:
        raise HTTPException(status_code=422, detail="Remote repositories must use an HTTPS or SSH URL without query parameters.")
    if parsed.password or (parsed.scheme == "https" and parsed.username):
        raise HTTPException(status_code=422, detail="Do not put credentials in the remote URL. Configure a Git credential helper or SSH key on the Entropy server.")
    return value


def _remote_display(source_type: str, source_location: Optional[str]) -> str:
    if source_type == "managed":
        return "Entropy managed"
    if source_type == "local":
        return "Imported server path"
    value = source_location or ""
    parsed = urlsplit(value if "://" in value else "ssh://" + value.replace(":", "/", 1))
    return parsed.hostname or "External Git remote"


def _require_workflow_write(request: Request, user: User, project_id: int) -> None:
    require(request, user, "workflows.write", project_id)


def _can_manage(request: Request, user: User, repository: Dict[str, Any], project_id: int) -> bool:
    if repository["scope"] == "user":
        return repository["owner_user_id"] == user.id
    return repository["project_id"] == project_id and user.id is not None and request.app.state.entropy_context.authorization.has_permission(
        user.id, "workflows.write", project_id
    )


def _visible_repo(request: Request, user: User, repository_id: int, project_id: int) -> Dict[str, Any]:
    item = _store(request).get(repository_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Repository not found.")
    if item["scope"] == "user":
        if item["owner_user_id"] != user.id:
            raise HTTPException(status_code=404, detail="Repository not found.")
    elif item["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Repository not found.")
    return item


def _readable_repo(request: Request, user: User, repository_id: int, project_id: int) -> Dict[str, Any]:
    item = _visible_repo(request, user, repository_id, project_id)
    if item["scope"] == "project":
        require(request, user, "workflows.read", project_id)
    return item


def _git_output(arguments: List[str], *, timeout: int = 20, max_bytes: int = 4 * 1024 * 1024) -> bytes:
    completed = subprocess.run(
        ["git", *arguments], capture_output=True, timeout=timeout, check=False,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat"},
    )
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise HTTPException(status_code=422, detail=detail or "Git could not read this repository reference.")
    if len(completed.stdout) > max_bytes:
        raise HTTPException(status_code=413, detail="The requested Git data is too large to display in the browser.")
    return completed.stdout


def _branch_name(repository: Dict[str, Any], branch: str) -> str:
    if not branch or len(branch) > 255:
        raise HTTPException(status_code=422, detail="Choose a valid branch.")
    completed = subprocess.run(
        ["git", "--git-dir", repository["bare_path"], "check-ref-format", "--branch", branch],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if completed.returncode:
        raise HTTPException(status_code=422, detail="Choose a valid branch.")
    return branch


def _commit_hash(value: str) -> str:
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", value):
        raise HTTPException(status_code=422, detail="Choose a valid commit.")
    return value


def _require_branch(repository: Dict[str, Any], branch: str) -> str:
    branch = _branch_name(repository, branch)
    _git_output(["--git-dir", repository["bare_path"], "rev-parse", "--verify", f"{branch}^{{commit}}"], max_bytes=1024)
    return branch


def _branch_has_commit(repository: Dict[str, Any], branch: str) -> bool:
    completed = subprocess.run(
        ["git", "--git-dir", repository["bare_path"], "rev-parse", "--verify", f"refs/heads/{branch}^{{commit}}"],
        capture_output=True, timeout=10, check=False,
    )
    return completed.returncode == 0


def _safe_file_path(path: str) -> str:
    candidate = PurePosixPath(path)
    if path.startswith("/") or "\\" in path or "\0" in path or any(part in {"", ".", ".."} for part in path.split("/")):
        raise HTTPException(status_code=422, detail="Choose a valid relative file path.")
    if len(path) > 2048 or not candidate.parts:
        raise HTTPException(status_code=422, detail="Choose a valid relative file path.")
    return path


def _commit_file(repository: Dict[str, Any], branch: str, path: str, data: bytes, username: str) -> None:
    branch = _branch_name(repository, branch)
    path = _safe_file_path(path)
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Files larger than 20 MiB cannot be added to this repository.")
    environment = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_AUTHOR_NAME": username,
        "GIT_AUTHOR_EMAIL": f"{username}@entropy.local",
        "GIT_COMMITTER_NAME": username,
        "GIT_COMMITTER_EMAIL": f"{username}@entropy.local",
    }
    with tempfile.TemporaryDirectory(prefix="entropy-git-browser-") as directory:
        checkout = Path(directory) / "checkout"
        clone = subprocess.run(["git", "clone", "--no-checkout", repository["bare_path"], str(checkout)], capture_output=True, text=True, timeout=30, check=False, env=environment)
        if clone.returncode:
            raise HTTPException(status_code=422, detail=(clone.stderr or "Unable to prepare a repository checkout.").strip())
        exists = subprocess.run(["git", "-C", str(checkout), "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], timeout=10, check=False, env=environment)
        if exists.returncode == 0:
            action = ["checkout", branch]
        else:
            action = ["checkout", "--orphan", branch]
        checked_out = subprocess.run(["git", "-C", str(checkout), *action], capture_output=True, text=True, timeout=15, check=False, env=environment)
        if checked_out.returncode:
            raise HTTPException(status_code=422, detail=(checked_out.stderr or "Unable to select the repository branch.").strip())
        target = checkout.joinpath(*PurePosixPath(path).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        added = subprocess.run(["git", "-C", str(checkout), "add", "--", path], capture_output=True, text=True, timeout=15, check=False, env=environment)
        if added.returncode:
            raise HTTPException(status_code=422, detail=(added.stderr or "Unable to stage the repository file.").strip())
        committed = subprocess.run(["git", "-C", str(checkout), "commit", "-m", f"Update {PurePosixPath(path).name}"], capture_output=True, text=True, timeout=30, check=False, env=environment)
        if committed.returncode:
            raise HTTPException(status_code=422, detail=(committed.stderr or "Unable to create a commit.").strip())
        pushed = subprocess.run(["git", "-C", str(checkout), "push", "origin", f"HEAD:refs/heads/{branch}"], capture_output=True, text=True, timeout=30, check=False, env=environment)
        if pushed.returncode:
            raise HTTPException(status_code=422, detail=(pushed.stderr or "Unable to save the file to the repository.").strip())


@router.get("/{repository_id}/browser/branches")
def browser_branches(repository_id: int, request: Request,
                     record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project = current_project(request, user)
    repository = _readable_repo(request, user, repository_id, project["id"])
    output = _git_output(["--git-dir", repository["bare_path"], "for-each-ref", "--format=%(refname:short)", "refs/heads"], max_bytes=256 * 1024)
    branches = [line for line in output.decode("utf-8", errors="replace").splitlines() if line]
    if not branches:
        head_ref = subprocess.run(["git", "--git-dir", repository["bare_path"], "symbolic-ref", "--quiet", "HEAD"], capture_output=True, text=True, timeout=10, check=False)
        unborn = head_ref.stdout.strip().removeprefix("refs/heads/") if head_ref.returncode == 0 else "main"
        return {"branches": [unborn or "main"], "committed_branches": [], "default_branch": unborn or "main"}
    default = None
    if branches:
        head = subprocess.run(["git", "--git-dir", repository["bare_path"], "symbolic-ref", "--quiet", "--short", "HEAD"], capture_output=True, text=True, timeout=10, check=False)
        candidate = head.stdout.strip() if head.returncode == 0 else ""
        default = candidate if candidate in branches else branches[0]
    committed = [name for name in branches if _branch_has_commit(repository, name)]
    return {"branches": branches, "committed_branches": committed, "default_branch": default}


@router.post("/{repository_id}/browser/branches", status_code=201, dependencies=[Depends(verify_csrf)])
def browser_create_branch(repository_id: int, payload: BranchCreate, request: Request,
                          record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project = current_project(request, user)
    repository = _visible_repo(request, user, repository_id, project["id"])
    if not _can_manage(request, user, repository, project["id"]):
        raise HTTPException(status_code=403, detail="You cannot create branches in this repository.")
    branch = _branch_name(repository, payload.branch.strip())
    base_branch = _require_branch(repository, payload.base_branch)
    exists = subprocess.run(
        ["git", "--git-dir", repository["bare_path"], "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        timeout=10, check=False,
    )
    if exists.returncode == 0:
        raise HTTPException(status_code=409, detail=f"Branch '{branch}' already exists.")
    created = subprocess.run(
        ["git", "--git-dir", repository["bare_path"], "branch", branch, base_branch],
        capture_output=True, text=True, timeout=15, check=False,
    )
    if created.returncode:
        raise HTTPException(status_code=422, detail=(created.stderr or "Git could not create this branch.").strip())
    return {"branch": branch, "base_branch": base_branch}


@router.get("/{repository_id}/browser/commits")
def browser_commits(repository_id: int, request: Request, branch: str = Query(..., min_length=1, max_length=255),
                    limit: int = Query(50, ge=1, le=100),
                    record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project = current_project(request, user)
    repository = _readable_repo(request, user, repository_id, project["id"])
    branch = _branch_name(repository, branch)
    if not _branch_has_commit(repository, branch):
        return {"commits": []}
    output = _git_output(["--git-dir", repository["bare_path"], "log", branch, "-n", str(limit), "--format=%H%x00%h%x00%s%x00%an%x00%aI"], max_bytes=1024 * 1024)
    commits = []
    for line in output.decode("utf-8", errors="replace").splitlines():
        parts = line.split("\x00", 4)
        if len(parts) == 5:
            commits.append({"sha": parts[0], "short_sha": parts[1], "subject": parts[2], "author": parts[3], "date": parts[4]})
    return {"commits": commits}


_HISTORY_COMMIT_LIMIT = 2000
_ENTRY_TYPES = {"040000": "dir", "160000": "submodule", "120000": "symlink"}


def _directory_history(git_dir: str, branch: str, directory: str) -> Tuple[Dict[str, List[str]], Dict[str, List[str]], bool]:
    """Return latest and earliest (date, author) per direct child of *directory* in one git log pass."""
    prefix = f"{directory}/" if directory else ""
    try:
        completed = subprocess.run(
            ["git", "-c", "core.quotePath=false", "--git-dir", git_dir, "log", "-n", str(_HISTORY_COMMIT_LIMIT),
             "--no-renames", "--name-only", "--format=%x01%aI%x02%an", branch, "--", directory or "."],
            capture_output=True, timeout=20, check=False,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat"},
        )
    except subprocess.TimeoutExpired:
        return {}, {}, True
    if completed.returncode:
        return {}, {}, True
    latest: Dict[str, List[str]] = {}
    earliest: Dict[str, List[str]] = {}
    commits = 0
    current = ["", ""]
    for line in completed.stdout.decode("utf-8", errors="replace").splitlines():
        if line.startswith("\x01"):
            commits += 1
            current = line[1:].split("\x02", 1) + [""]
            continue
        if not line or not line.startswith(prefix):
            continue
        child = line[len(prefix):].split("/", 1)[0]
        latest.setdefault(child, current[:2])
        earliest[child] = current[:2]
    return latest, earliest, commits >= _HISTORY_COMMIT_LIMIT


def _directory_entries(git_dir: str, branch: str, directory: str) -> Dict[str, Any]:
    """List the direct children of one folder of *branch* with their latest commit details."""
    listed = subprocess.run(
        ["git", "--git-dir", git_dir, "ls-tree", "-z", "--long", f"{branch}:{directory}"],
        capture_output=True, timeout=20, check=False,
    )
    if listed.returncode:
        raise HTTPException(status_code=404, detail="Folder not found in this branch.")
    if len(listed.stdout) > 4 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="This folder has too many entries to display in the browser.")
    latest, earliest, history_limited = _directory_history(git_dir, branch, directory)
    entries = []
    for record in listed.stdout.split(b"\0"):
        if b"\t" not in record:
            continue
        meta, raw_name = record.split(b"\t", 1)
        mode, _, _, size = meta.decode().split(None, 3)
        name = raw_name.decode("utf-8", errors="replace")
        modified = latest.get(name, ["", ""])
        # Without the full history the earliest commit seen is not the creating commit.
        created = ["", ""] if history_limited else earliest.get(name, ["", ""])
        entries.append({
            "name": name, "path": f"{directory}/{name}" if directory else name,
            "type": _ENTRY_TYPES.get(mode, "file"), "size": int(size) if size.strip().isdigit() else None,
            "created_at": created[0], "created_by": created[1],
            "modified_at": modified[0], "modified_by": modified[1],
        })
    entries.sort(key=lambda item: (item["type"] != "dir", item["name"].casefold()))
    return {"path": directory, "entries": entries, "history_limited": history_limited}


@router.get("/{repository_id}/browser/files")
def browser_files(repository_id: int, request: Request, branch: str = Query(..., min_length=1, max_length=255),
                  path: str = Query("", max_length=2048),
                  record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project = current_project(request, user)
    repository = _readable_repo(request, user, repository_id, project["id"])
    branch = _branch_name(repository, branch)
    directory = _safe_file_path(path.strip("/")) if path.strip("/") else ""
    if not _branch_has_commit(repository, branch):
        return {"path": directory, "entries": [], "history_limited": False}
    return _directory_entries(repository["bare_path"], f"refs/heads/{branch}", directory)


@router.get("/{repository_id}/browser/file")
def browser_file(repository_id: int, request: Request, branch: str = Query(..., min_length=1, max_length=255),
                 path: str = Query(..., min_length=1, max_length=2048),
                 record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project = current_project(request, user)
    repository = _readable_repo(request, user, repository_id, project["id"])
    branch = _branch_name(repository, branch)
    path = _safe_file_path(path)
    if not _branch_has_commit(repository, branch):
        raise HTTPException(status_code=404, detail="File not found in this branch.")
    exists = subprocess.run(["git", "--git-dir", repository["bare_path"], "cat-file", "-e", f"{branch}:{path}"], capture_output=True, timeout=15, check=False)
    if exists.returncode:
        raise HTTPException(status_code=404, detail="File not found in this branch.")
    size_text = _git_output(["--git-dir", repository["bare_path"], "cat-file", "-s", f"{branch}:{path}"], max_bytes=1024).decode().strip()
    try:
        size = int(size_text)
    except ValueError:
        raise HTTPException(status_code=422, detail="Git returned an invalid file size.")
    if size > 1024 * 1024:
        raise HTTPException(status_code=413, detail="Files larger than 1 MiB are not shown in the browser.")
    content = _git_output(["--git-dir", repository["bare_path"], "show", f"{branch}:{path}"], max_bytes=1024 * 1024)
    try:
        decoded = content.decode("utf-8")
        binary = "\0" in decoded
    except UnicodeDecodeError:
        decoded, binary = "", True
    return {"path": path, "content": "" if binary else decoded, "binary": binary, "size": size}


@router.put("/{repository_id}/browser/file", dependencies=[Depends(verify_csrf)])
def browser_save_file(repository_id: int, payload: FileWrite, request: Request,
                      record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project = current_project(request, user)
    repository = _visible_repo(request, user, repository_id, project["id"])
    if not _can_manage(request, user, repository, project["id"]):
        raise HTTPException(status_code=403, detail="You cannot modify this repository.")
    _commit_file(repository, payload.branch, payload.path, payload.content.encode("utf-8"), user.username)
    return {"message": "File saved as a new commit."}


@router.post("/{repository_id}/browser/files", status_code=201, dependencies=[Depends(verify_csrf)])
async def browser_upload_file(repository_id: int, request: Request, branch: str = Form("main"), path: str = Form(""),
                              file: UploadFile = File(...), record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project = current_project(request, user)
    repository = _visible_repo(request, user, repository_id, project["id"])
    if not _can_manage(request, user, repository, project["id"]):
        raise HTTPException(status_code=403, detail="You cannot modify this repository.")
    path = _safe_file_path(path or file.filename or "")
    data = await file.read(20 * 1024 * 1024 + 1)
    _commit_file(repository, branch, path, data, user.username)
    return {"message": f"{path} added as a new commit."}


@router.get("/{repository_id}/browser/commits/{commit}/diff")
def browser_commit_diff(repository_id: int, commit: str, request: Request,
                        record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project = current_project(request, user)
    repository = _readable_repo(request, user, repository_id, project["id"])
    commit = _commit_hash(commit)
    _git_output(["--git-dir", repository["bare_path"], "cat-file", "-e", f"{commit}^{{commit}}"], max_bytes=1024)
    parent = subprocess.run(["git", "--git-dir", repository["bare_path"], "rev-parse", "--verify", f"{commit}^"], capture_output=True, text=True, timeout=10, check=False)
    parent_commit = parent.stdout.strip() if parent.returncode == 0 else None
    compare_args = ["--root", commit] if parent_commit is None else [parent_commit, commit]
    raw_paths = _git_output(["--git-dir", repository["bare_path"], "diff-tree", "--no-commit-id", "--name-status", "-r", "-z", "--no-renames", *compare_args], max_bytes=2 * 1024 * 1024)
    fields = raw_paths.decode("utf-8", errors="replace").split("\0")
    fields = [field for field in fields if field]
    if len(fields) % 2:
        raise HTTPException(status_code=422, detail="Git returned an invalid commit file list.")
    if len(fields) // 2 > 100:
        raise HTTPException(status_code=413, detail="This commit changes more than 100 files; use Git locally to inspect it.")
    changes = []
    total_bytes = 0
    for status, path in zip(fields[0::2], fields[1::2]):
        path = _safe_file_path(path)
        old_content = b""
        new_content = b""
        too_large = False
        if status != "A" and parent_commit:
            old_size = int(_git_output(["--git-dir", repository["bare_path"], "cat-file", "-s", f"{parent_commit}:{path}"], max_bytes=1024).decode().strip())
            too_large = old_size > 512 * 1024
        if status != "D":
            new_size = int(_git_output(["--git-dir", repository["bare_path"], "cat-file", "-s", f"{commit}:{path}"], max_bytes=1024).decode().strip())
            too_large = too_large or new_size > 512 * 1024
        if not too_large:
            if status != "A" and parent_commit:
                old_content = _git_output(["--git-dir", repository["bare_path"], "show", f"{parent_commit}:{path}"], max_bytes=512 * 1024)
            if status != "D":
                new_content = _git_output(["--git-dir", repository["bare_path"], "show", f"{commit}:{path}"], max_bytes=512 * 1024)
        total_bytes += len(old_content) + len(new_content)
        if total_bytes > 4 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="The selected commit diff is too large to display.")
        try:
            original = old_content.decode("utf-8")
            modified = new_content.decode("utf-8")
            binary = too_large or b"\0" in old_content or b"\0" in new_content
        except UnicodeDecodeError:
            original, modified, binary = "", "", True
        changes.append({"path": path, "status": status, "original": "" if binary else original,
                        "modified": "" if binary else modified, "binary": binary})
    return {"changes": changes}


def _serialize(repository: Dict[str, Any], assignments: List[Dict[str, str]], can_manage: bool) -> Dict[str, Any]:
    return {
        "id": repository["id"], "name": repository["name"], "scope": repository["scope"],
        "project_id": repository["project_id"], "created_by": repository["created_by"],
        "created_at": repository["created_at"], "assignments": assignments,
        "can_manage": can_manage, "clone_path": repository["bare_path"],
        "source_type": repository.get("source_type", "managed"),
        "source_display": _remote_display(repository.get("source_type", "managed"), repository.get("source_location")),
    }


@router.get("")
def list_repositories(request: Request, record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project = current_project(request, user)
    assert user.id is not None
    auth = request.app.state.entropy_context.authorization
    can_read_project = auth.has_permission(user.id, "workflows.read", project["id"])
    can_write_project = auth.has_permission(user.id, "workflows.write", project["id"])
    store = _store(request)
    rows = store.visible(project["id"], user.id, can_read_project)
    items = [_serialize(row, store.assignments(row["id"], project["id"]), _can_manage(request, user, row, project["id"])) for row in rows]
    return {
        "items": items,
        "project": {"id": project["id"], "key": project["key"], "name": project["name"]},
        "permissions": {"project_write": can_write_project},
    }


@router.get("/targets")
def list_targets(request: Request, record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project = current_project(request, user)
    _require_workflow_write(request, user, project["id"])
    context = request.app.state.entropy_context
    workflows = [
        {"key": item.name, "name": item.name}
        for item in context.workflow_manager.list(project_id=project["id"])
    ]
    plugins = [
        {"key": item.qualified_name, "name": item.qualified_name}
        for item in context.plugin_manager.list() if item.enabled
    ]
    return {"workflows": workflows, "plugins": plugins}


@router.get("/sources/local/directories")
def browse_local_repository_directories(
    request: Request,
    path: str = Query("/", min_length=1, max_length=4096),
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """List directories on the Entropy host for the authenticated repository picker."""
    _, _, user = record
    current_project(request, user)
    try:
        directory = Path(path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        raise HTTPException(status_code=422, detail="That server directory does not exist or cannot be accessed.") from None
    if not directory.is_dir():
        raise HTTPException(status_code=422, detail="Choose a server directory.")

    git = shutil.which("git")
    is_repository = False
    if git is not None:
        checked = subprocess.run(
            [git, "-C", str(directory), "rev-parse", "--git-dir"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        is_repository = checked.returncode == 0

    directories = []
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        directories.append({"name": entry.name, "path": str(directory / entry.name)})
                except OSError:
                    continue
    except OSError:
        raise HTTPException(status_code=422, detail="This server directory cannot be listed.") from None
    directories.sort(key=lambda item: item["name"].casefold())
    return {
        "path": str(directory),
        "parent_path": str(directory.parent) if directory.parent != directory else None,
        "is_git_repository": is_repository,
        "directories": directories[:500],
        "truncated": len(directories) > 500,
    }


@router.post("", status_code=201, dependencies=[Depends(verify_csrf)])
def create_repository(payload: RepositoryCreate, request: Request,
                      record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project = current_project(request, user)
    if payload.scope == "project":
        _require_workflow_write(request, user, project["id"])
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Repository name cannot be blank.")
    git = shutil.which("git")
    if git is None:
        raise HTTPException(status_code=503, detail="Git is not installed on the Entropy server.")
    connection = request.app.state.entropy_context.database_manager.connection
    ensure_git_repositories_schema(connection)
    if payload.scope == "project" or request.app.state.entropy_context.authorization.has_permission(
        user.id, "workflows.read", project["id"]
    ):
        duplicate = connection.fetchone(
            "SELECT 1 FROM entropy_git_repositories WHERE lower(name) = lower(?) "
            "AND (owner_user_id = ? OR (scope = 'project' AND project_id = ?)) LIMIT 1",
            (name, user.id, project["id"]),
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="A repository with that name already exists in this project or your personal scope.")
    else:
        duplicate = connection.fetchone(
            "SELECT 1 FROM entropy_git_repositories WHERE lower(name) = lower(?) "
            "AND owner_user_id = ? LIMIT 1", (name, user.id),
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="A personal repository with that name already exists.")
    repo_key = uuid.uuid4().hex
    root = _repo_root(request)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    bare_path = root / f"{repo_key}.git"
    source_location = None
    if payload.source_type == "local":
        if not payload.source_location or not payload.source_location.strip():
            raise HTTPException(status_code=422, detail="Enter the server path to an existing Git repository.")
        try:
            source_path = Path(payload.source_location).expanduser().resolve(strict=True)
        except (OSError, RuntimeError):
            raise HTTPException(status_code=422, detail="The server path does not exist or cannot be accessed.") from None
        if not source_path.is_dir():
            raise HTTPException(status_code=422, detail="The server path must point to a Git repository directory.")
        valid_repo = subprocess.run([git, "-C", str(source_path), "rev-parse", "--git-dir"], capture_output=True, text=True, timeout=15, check=False)
        if valid_repo.returncode:
            raise HTTPException(status_code=422, detail="The selected server path is not an existing Git repository.")
        source_location = str(source_path)
    elif payload.source_type == "remote":
        if not payload.source_location:
            raise HTTPException(status_code=422, detail="Enter an HTTPS or SSH URL for the remote Git repository.")
        source_location = _remote_source(payload.source_location)
    elif payload.source_location:
        raise HTTPException(status_code=422, detail="A source path or URL is only used for imported repositories.")

    git_environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat"}
    if payload.source_type == "remote":
        git_environment["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"
        initialized = subprocess.run([git, "clone", "--quiet", "--mirror", "--", source_location or "", str(bare_path)], capture_output=True, text=True, timeout=300, check=False, env=git_environment)
    elif payload.source_type == "local":
        initialized = subprocess.run([git, "clone", "--quiet", "--mirror", "--", source_location or "", str(bare_path)], capture_output=True, text=True, timeout=300, check=False, env=git_environment)
    else:
        initialized = subprocess.run([git, "init", "--bare", "--initial-branch=main", str(bare_path)], capture_output=True, text=True, timeout=30, check=False, env=git_environment)
    if initialized.returncode:
        shutil.rmtree(bare_path, ignore_errors=True)
        message = (initialized.stderr or initialized.stdout or "Git could not initialize the repository.").strip()
        if payload.source_type == "remote":
            message += " Check the URL and make sure the Entropy server has network access and SSH key or Git credential-helper access."
        raise HTTPException(status_code=422 if payload.source_type != "managed" else 500, detail=message)
    try:
        with connection.transaction():
            cursor = connection.execute(
                "INSERT INTO entropy_git_repositories(repo_key,name,scope,owner_user_id,project_id,bare_path,created_by,source_type,source_location) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (repo_key, name, payload.scope, user.id if payload.scope == "user" else None,
                 project["id"] if payload.scope == "project" else None, str(bare_path), user.username,
                 payload.source_type, source_location),
            )
    except Exception:
        shutil.rmtree(bare_path, ignore_errors=True)
        raise
    item = GitRepositoryStore(connection).get(cursor.lastrowid)
    assert item is not None
    return _serialize(item, [], True)


@router.put("/{repository_id}/assignments", dependencies=[Depends(verify_csrf)])
def update_assignments(repository_id: int, payload: AssignmentUpdate, request: Request,
                       record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project = current_project(request, user)
    _require_workflow_write(request, user, project["id"])
    item = _visible_repo(request, user, repository_id, project["id"])
    if not _can_manage(request, user, item, project["id"]):
        raise HTTPException(status_code=403, detail="You cannot change this repository's assignments.")
    context = request.app.state.entropy_context
    workflow_names = {
        workflow.name for workflow in context.workflow_manager.list(project_id=project["id"])
    }
    plugin_names = {plugin.qualified_name for plugin in context.plugin_manager.list() if plugin.enabled}
    assignments = []
    seen = set()
    for assignment in payload.assignments:
        choices = workflow_names if assignment.target_type == "workflow" else plugin_names
        if assignment.target_key not in choices:
            raise HTTPException(status_code=422, detail=f"Unknown {assignment.target_type} '{assignment.target_key}' in this project.")
        pair = (assignment.target_type, assignment.target_key)
        if pair not in seen:
            assignments.append({"target_type": pair[0], "target_key": pair[1]})
            seen.add(pair)
    store = _store(request)
    store.replace_assignments(repository_id, project["id"], assignments)
    return _serialize(item, store.assignments(repository_id, project["id"]), True)


@router.delete("/{repository_id}", status_code=204, dependencies=[Depends(verify_csrf)])
def delete_repository(repository_id: int, request: Request,
                      record: SessionRecord = Depends(_current_session)) -> None:
    _, _, user = record
    project = current_project(request, user)
    item = _visible_repo(request, user, repository_id, project["id"])
    if not _can_manage(request, user, item, project["id"]):
        raise HTTPException(status_code=403, detail="You cannot delete this repository.")
    root = _repo_root(request).resolve()
    path = Path(item["bare_path"]).resolve()
    if root not in path.parents:
        raise HTTPException(status_code=409, detail="Repository path is outside Entropy's managed storage.")
    shutil.rmtree(path, ignore_errors=False)
    _store(request).delete(repository_id)
