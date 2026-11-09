"""
Per-user Git identity and credentials, and pull/push between Entropy's copy of a
remote repository and the remote itself.

Entropy keeps a bare copy (``bare_path``) of each imported remote. Pull fetches the
remote's branches into ``refs/remotes/origin/*`` and fast-forwards local branches;
branches with commits that are not on the remote are never overwritten. Push sends
one branch without forcing. HTTPS tokens are stored encrypted with the vault key and
reach git only through the environment, never the command line or the remote URL.
"""

from __future__ import annotations

import base64
import os
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from lib.database.connection import DatabaseConnection

TRACKING_PREFIX = "refs/remotes/origin/"
_SCP_URL = re.compile(r"[A-Za-z0-9._-]+@([A-Za-z0-9.-]+):[^\s]+")
_EMAIL = re.compile(r"[^@\s<>]+@[^@\s<>]+")


class GitRemoteError(RuntimeError):
    """A pull, push or credential operation that cannot be done; the message says why."""


# ----------------------------------------------------------------------
# Schema
# ----------------------------------------------------------------------


def ensure_git_credentials_schema(connection: DatabaseConnection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS entropy_git_identities ("
        "user_id INTEGER PRIMARY KEY, author_name TEXT NOT NULL, author_email TEXT NOT NULL,"
        "updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ")"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS entropy_git_credentials ("
        "user_id INTEGER NOT NULL, host TEXT NOT NULL, username TEXT NOT NULL,"
        "secret TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
        "PRIMARY KEY(user_id, host)"
        ")"
    )


# ----------------------------------------------------------------------
# Remote URLs
# ----------------------------------------------------------------------


def remote_host(url: str) -> str:
    """The host (with a non-default port) a remote URL points at, lower case."""

    value = (url or "").strip()
    match = _SCP_URL.fullmatch(value)
    if match:
        return match.group(1).lower()
    parsed = urlsplit(value)
    if not parsed.hostname:
        raise GitRemoteError("This repository has no valid remote URL.")
    host = parsed.hostname.lower()
    return f"{host}:{parsed.port}" if parsed.port else host


def is_https(url: str) -> bool:
    return urlsplit((url or "").strip()).scheme == "https"


def normalize_host(value: str) -> str:
    """A host as entered by a person (``github.com`` or ``https://github.com/``)."""

    text = (value or "").strip().lower()
    if "://" in text:
        text = urlsplit(text).netloc.rsplit("@", 1)[-1]
    text = text.strip("/")
    if not text or not re.fullmatch(r"[a-z0-9.-]+(:[0-9]{1,5})?", text):
        raise GitRemoteError("Enter a host name such as github.com.")
    return text


# ----------------------------------------------------------------------
# Identity and credentials
# ----------------------------------------------------------------------


class GitCredentialStore:
    """A user's commit identity and HTTPS tokens per Git host."""

    def __init__(self, connection: DatabaseConnection, key: Optional[bytes] = None) -> None:
        ensure_git_credentials_schema(connection)
        self.connection = connection
        self._key = key

    def _cipher(self) -> Any:
        if self._key is None:
            raise GitRemoteError("The vault key is unavailable, so Git tokens cannot be used.")
        from lib.vault.cipher import VaultCipher

        return VaultCipher(self._key)

    def identity(self, user_id: int) -> Optional[Dict[str, str]]:
        row = self.connection.fetchone(
            "SELECT author_name, author_email FROM entropy_git_identities WHERE user_id = ?",
            (user_id,),
        )
        return {"name": row["author_name"], "email": row["author_email"]} if row else None

    def set_identity(self, user_id: int, name: str, email: str) -> Dict[str, str]:
        name, email = name.strip(), email.strip()
        if not name or any(character in name for character in "<>\n\r\0"):
            raise GitRemoteError("Enter the name to show on your commits.")
        if not _EMAIL.fullmatch(email):
            raise GitRemoteError("Enter a valid email address for your commits.")
        self.connection.execute(
            "INSERT INTO entropy_git_identities (user_id, author_name, author_email, updated_at) "
            "VALUES (?, ?, ?, datetime('now')) ON CONFLICT(user_id) DO UPDATE SET "
            "author_name = excluded.author_name, author_email = excluded.author_email, "
            "updated_at = datetime('now')",
            (user_id, name, email),
        )
        return {"name": name, "email": email}

    def credentials(self, user_id: int) -> List[Dict[str, str]]:
        """Saved hosts and usernames; tokens are never returned."""

        return [
            {"host": row["host"], "username": row["username"], "updated_at": row["updated_at"]}
            for row in self.connection.fetchall(
                "SELECT host, username, updated_at FROM entropy_git_credentials "
                "WHERE user_id = ? ORDER BY host",
                (user_id,),
            )
        ]

    def set_credential(self, user_id: int, host: str, username: str, token: str) -> None:
        host = normalize_host(host)
        username, token = username.strip(), token.strip()
        if not username or ":" in username or any(c.isspace() for c in username):
            raise GitRemoteError("Enter the Git account username for this host.")
        if not token or any(character.isspace() for character in token):
            raise GitRemoteError("Enter a personal access token for this host.")
        sealed = base64.b64encode(self._cipher().encrypt(token.encode("utf-8"))).decode("ascii")
        self.connection.execute(
            "INSERT INTO entropy_git_credentials (user_id, host, username, secret, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now')) ON CONFLICT(user_id, host) DO UPDATE SET "
            "username = excluded.username, secret = excluded.secret, updated_at = datetime('now')",
            (user_id, host, username, sealed),
        )

    def delete_credential(self, user_id: int, host: str) -> None:
        self.connection.execute(
            "DELETE FROM entropy_git_credentials WHERE user_id = ? AND host = ?",
            (user_id, normalize_host(host)),
        )

    def has_credential(self, user_id: int, host: str) -> bool:
        return (
            self.connection.fetchone(
                "SELECT 1 FROM entropy_git_credentials WHERE user_id = ? AND host = ?",
                (user_id, host),
            )
            is not None
        )

    def credential(self, user_id: int, host: str) -> Optional[Tuple[str, str]]:
        """(username, token) saved by the user for *host*."""

        row = self.connection.fetchone(
            "SELECT username, secret FROM entropy_git_credentials WHERE user_id = ? AND host = ?",
            (user_id, host),
        )
        if row is None:
            return None
        token = self._cipher().decrypt(base64.b64decode(row["secret"])).decode("utf-8")
        return row["username"], token


# ----------------------------------------------------------------------
# Git environment
# ----------------------------------------------------------------------


def remote_environment(url: str, credential: Optional[Tuple[str, str]] = None) -> Dict[str, str]:
    """
    Environment for a git command that talks to *url*.

    A saved HTTPS token is sent as an Authorization header scoped to the remote's
    host, through ``GIT_CONFIG_*`` variables so it never appears in a process list.
    SSH remotes use the Entropy server's SSH keys.
    """

    environment = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_PAGER": "cat",
        "GIT_SSH_COMMAND": "ssh -o BatchMode=yes",
    }
    for name in [key for key in environment if key.startswith("GIT_CONFIG_")]:
        environment.pop(name)
    if credential is not None and is_https(url):
        username, token = credential
        basic = base64.b64encode(f"{username}:{token}".encode()).decode("ascii")
        environment["GIT_CONFIG_COUNT"] = "1"
        environment["GIT_CONFIG_KEY_0"] = f"http.https://{remote_host(url)}/.extraHeader"
        environment["GIT_CONFIG_VALUE_0"] = f"Authorization: Basic {basic}"
    return environment


def _git(
    git_dir: str,
    arguments: List[str],
    environment: Optional[Dict[str, str]] = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "--git-dir", git_dir, *arguments],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=environment or {**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )


def _secret_free(text: str, credential: Optional[Tuple[str, str]]) -> str:
    if credential is not None and credential[1]:
        text = text.replace(credential[1], "****")
    return text.strip()


def _ref(git_dir: str, ref: str) -> Optional[str]:
    completed = _git(git_dir, ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"])
    return completed.stdout.strip() if completed.returncode == 0 else None


def _is_ancestor(git_dir: str, ancestor: str, descendant: str) -> bool:
    return _git(git_dir, ["merge-base", "--is-ancestor", ancestor, descendant]).returncode == 0


# ----------------------------------------------------------------------
# Pull, push, status
# ----------------------------------------------------------------------


def pull(git_dir: str, url: str, credential: Optional[Tuple[str, str]] = None) -> Dict[str, Any]:
    """
    Fetch the remote's branches and fast-forward local ones.

    Local branches the remote does not have are kept; branches with local commits
    are reported as ahead (push them) or diverged (both sides changed).
    """

    fetched = _git(
        git_dir,
        [
            "fetch",
            "--quiet",
            "--prune",
            "--no-tags",
            "--",
            url,
            f"+refs/heads/*:{TRACKING_PREFIX}*",
        ],
        remote_environment(url, credential),
        timeout=300,
    )
    if fetched.returncode:
        raise GitRemoteError(
            _secret_free(fetched.stderr or "Git could not fetch from the remote.", credential)
        )
    listed = _git(git_dir, ["for-each-ref", "--format=%(refname)", TRACKING_PREFIX])
    summary: Dict[str, List[str]] = {
        "created": [],
        "updated": [],
        "up_to_date": [],
        "ahead": [],
        "diverged": [],
    }
    for ref in sorted(line for line in listed.stdout.splitlines() if line):
        branch = ref[len(TRACKING_PREFIX) :]
        if branch == "HEAD":
            continue
        remote = _ref(git_dir, ref)
        local = _ref(git_dir, f"refs/heads/{branch}")
        if remote is None:
            continue
        if local is None:
            outcome = "created"
        elif local == remote:
            summary["up_to_date"].append(branch)
            continue
        elif _is_ancestor(git_dir, local, remote):
            outcome = "updated"
        elif _is_ancestor(git_dir, remote, local):
            summary["ahead"].append(branch)
            continue
        else:
            summary["diverged"].append(branch)
            continue
        # The old value guards against a commit saved while the fetch ran.
        moved = _git(git_dir, ["update-ref", f"refs/heads/{branch}", remote, local or ""])
        summary["diverged" if moved.returncode else outcome].append(branch)
    return summary


def push(
    git_dir: str, url: str, branch: str, credential: Optional[Tuple[str, str]] = None
) -> Dict[str, Any]:
    """Push one branch to the remote without forcing."""

    local = _ref(git_dir, f"refs/heads/{branch}")
    if local is None:
        raise GitRemoteError(f"Branch '{branch}' has no commits to push.")
    pushed = _git(
        git_dir,
        ["push", "--porcelain", "--", url, f"refs/heads/{branch}:refs/heads/{branch}"],
        remote_environment(url, credential),
        timeout=300,
    )
    if pushed.returncode:
        detail = _secret_free(pushed.stderr or pushed.stdout or "Git could not push.", credential)
        if "[rejected]" in pushed.stdout or "non-fast-forward" in detail or "fetch first" in detail:
            raise GitRemoteError(
                f"The remote '{branch}' has commits that are not here. Pull the latest changes "
                "first; if both sides changed, save your work to a new branch and push that."
            )
        raise GitRemoteError(detail)
    _git(git_dir, ["update-ref", f"{TRACKING_PREFIX}{branch}", local])
    return {"branch": branch, "commit": local}


def branch_status(git_dir: str, branch: str) -> Dict[str, Any]:
    """Commits on *branch* not on the remote (ahead) and the other way (behind), as last pulled."""

    local = _ref(git_dir, f"refs/heads/{branch}")
    remote = _ref(git_dir, f"{TRACKING_PREFIX}{branch}")
    if remote is None:
        return {"tracking": False, "ahead": None, "behind": None}
    if local is None:
        return {"tracking": True, "ahead": 0, "behind": None}
    counted = _git(git_dir, ["rev-list", "--left-right", "--count", f"{local}...{remote}"])
    try:
        ahead, behind = (int(value) for value in counted.stdout.split())
    except ValueError:
        return {"tracking": True, "ahead": None, "behind": None}
    return {"tracking": True, "ahead": ahead, "behind": behind}


def record_tracking(git_dir: str) -> None:
    """After a fresh clone of the remote, remember each branch as last seen there."""

    listed = _git(
        git_dir, ["for-each-ref", "--format=%(refname:lstrip=2) %(objectname)", "refs/heads"]
    )
    for line in listed.stdout.splitlines():
        branch, _, commit = line.rpartition(" ")
        if branch and commit:
            _git(git_dir, ["update-ref", f"{TRACKING_PREFIX}{branch}", commit])
