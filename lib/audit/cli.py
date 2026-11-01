"""
Audit of commands run with the server-side command line (`entropy.py` / `ent`
on the Entropy host).

These commands work on the database directly, not through the web API, so
the web layer never sees them. The command manager records them here, in
the same audit log: who (the signed-in Entropy user and the operating system
account), what (`workflow.edit`, `user.role.add`, ...), on what, and whether
it worked. Reads (list, get, ...) are not recorded, as in the web API.
"""

from __future__ import annotations

import getpass
import logging
import socket
from argparse import Namespace
from typing import Any, List, Optional

LOGGER = logging.getLogger("entropy.audit")

# Commands that only show something.
QUIET_COMMANDS = {"help", "man", "version", "format", "web"}
# Verbs that only read; everything else is a change worth recording.
READ_VERBS = {
    "list",
    "get",
    "show",
    "describe",
    "jobs",
    "follow",
    "validate",
    "status",
    "whoami",
    "info",
    "search",
    "logs",
    "log",
    "current",
    "tree",
    "view",
    "check",
    "permissions",
}
# Subcommand destinations, outermost first (e.g. user -> role -> add).
ACTION_FIELDS = (
    "action",
    "generator",
    "user_action",
    "role_action",
    "namespace_action",
    "permission_action",
)
# Arguments that name what a command acts on (never values such as passwords).
TARGET_FIELDS = (
    "name",
    "username",
    "workflow",
    "plugin",
    "key",
    "namespace",
    "group",
    "role",
    "project",
    "job_id",
    "id",
    "target",
)


def verbs(resource: str, args: Namespace) -> List[str]:
    """The command's verbs, canonical (aliases resolved), outermost first."""

    from lib.remote_cli.contract import canonical_verb

    words: List[str] = []
    for field in ACTION_FIELDS:
        value = getattr(args, field, None)
        if isinstance(value, str) and value:
            words.append(canonical_verb(resource, value) if not words else value)
    return words


def should_record(resource: str, words: List[str]) -> bool:
    if resource in QUIET_COMMANDS:
        return False
    return not words or words[-1] not in READ_VERBS


def target_of(args: Namespace) -> Optional[str]:
    for field in TARGET_FIELDS:
        value = getattr(args, field, None)
        if isinstance(value, (str, int)) and not isinstance(value, bool) and str(value).strip():
            return str(value).strip()[:200]
    return None


def record_command(
    context: Any,
    resource: str,
    args: Namespace,
    *,
    outcome: str,
    duration_ms: int,
    error: Optional[str] = None,
) -> None:
    """Write the command to the audit log; a failure is logged and never fails the command."""

    words = verbs(resource, args)
    if not should_record(resource, words):
        return
    manager = getattr(context, "database_manager", None)
    if manager is None:
        return
    try:
        session = None
        sessions = getattr(context, "session_manager", None)
        if sessions is not None:
            session = sessions.current()
        details: dict = {
            "command": " ".join(["ent", resource, *words]),
            "os_user": _os_user(),
            "host": socket.gethostname(),
        }
        if error:
            details["error"] = error[:500]
        from lib.audit.store import AuditStore

        AuditStore(manager.connection).record(
            category=resource,
            action=".".join([resource, *words]) if words else resource,
            outcome=outcome,
            username=session.username if session else None,
            user_id=session.user_id if session else None,
            target=target_of(args),
            address="localhost",
            source="server-cli",
            project=_project(context, session),
            duration_ms=duration_ms,
            details=details,
        )
    except Exception as failure:  # noqa: BLE001 - auditing must not break the command
        LOGGER.warning("Unable to write the audit entry for '%s': %s", resource, failure)


def _project(context: Any, session: Any) -> Optional[str]:
    """The signed-in user's current CLI project (`ent project use`)."""

    if session is None:
        return None
    try:
        from core.commands.project_context import ProjectContext

        return str(ProjectContext(context).current(session)["key"])
    except Exception:  # noqa: BLE001 - the entry is still useful without a project
        return None


def _os_user() -> str:
    try:
        return getpass.getuser()
    except (KeyError, OSError):
        return ""
