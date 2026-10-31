"""
Who may do what with a Vault namespace.

Vault namespaces belong to a project. Access comes only from roles: a project
role in the namespace's project, or a global role (the Administrator role has
every permission). There are no per-namespace user grants.

Permissions:

    vault.namespace.read     see the project's namespaces and entry names
    vault.read               reveal values
    vault.add / vault.modify add and change entries
    vault.delete             delete entries
    vault.namespace.create   create namespaces in the project
    vault.namespace.modify   rename namespaces
    vault.namespace.delete   delete namespaces

Runs do not need `vault.read`: a run in project P resolves `${entv:...}` from
P's namespaces when its starter may run workflows (or plugins) there.
"""

from __future__ import annotations

from typing import Any, Optional

from lib.vault.exceptions import VaultAccessDeniedError

# A run may read its project's secrets if its starter may start runs there.
RUN_PERMISSIONS = (
    "workflows.execute",
    "plugins.execute",
)


def can(
    authorization: Any,
    user_id: Optional[int],
    permission: str,
    project_id: int,
) -> bool:
    """Whether the user holds the Vault permission in the project."""

    return (
        user_id is not None
        and authorization is not None
        and bool(authorization.has_permission(user_id, permission, project_id))
    )


def require(
    authorization: Any,
    user_id: Optional[int],
    permission: str,
    project_id: int,
) -> None:
    """Raise VaultAccessDeniedError unless the user holds the permission."""

    if not can(authorization, user_id, permission, project_id):
        raise VaultAccessDeniedError(
            "You do not have permission for this Vault namespace "
            f"({permission} in its project).",
        )


def require_run(
    authorization: Any,
    user_id: Optional[int],
    project_id: int,
) -> None:
    """A run's starter must be allowed to start runs in the project."""

    if not any(
        can(authorization, user_id, permission, project_id) for permission in RUN_PERMISSIONS
    ):
        raise VaultAccessDeniedError(
            "Permission denied: this run may not read the project's Vault "
            "(its starter cannot run workflows or plugins in the project).",
        )
