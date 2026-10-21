"""
Vault namespaces belong to a project, like workflows and schedules.

A namespace without a row belongs to the Default project (namespaces made
before projects existed). The web UI shows and opens only the current
project's namespaces, and a run may read only its own project's secrets.
"""

from __future__ import annotations

import os
from typing import Any, Optional, Set

# Set for workflow workers: the project of the run they execute.
PROJECT_ENV = "ENTROPY_PROJECT_ID"


def ensure_schema(connection: Any) -> None:
    if getattr(connection, "_entropy_vault_projects_ready", False):
        return
    with connection.transaction():
        connection.execute("""
            CREATE TABLE IF NOT EXISTS vault_namespace_projects
            (
                namespace_id INTEGER PRIMARY KEY
                    REFERENCES vault_namespaces (id) ON DELETE CASCADE,
                project_id   INTEGER NOT NULL
            )
            """)
    connection._entropy_vault_projects_ready = True


def _default(connection: Any) -> int:
    from lib.authorization.projects import default_project_id

    return default_project_id(connection)


def namespace_project(connection: Any, namespace_id: int) -> int:
    ensure_schema(connection)
    row = connection.fetchone(
        "SELECT project_id FROM vault_namespace_projects WHERE namespace_id = ?",
        (namespace_id,),
    )
    return int(row["project_id"]) if row else _default(connection)


def set_namespace_project(connection: Any, namespace_id: int, project_id: int) -> None:
    ensure_schema(connection)
    with connection.transaction():
        connection.execute(
            "INSERT INTO vault_namespace_projects (namespace_id, project_id) VALUES (?, ?)"
            " ON CONFLICT (namespace_id) DO UPDATE SET project_id = excluded.project_id",
            (namespace_id, project_id),
        )


def namespaces_in(connection: Any, project_id: int) -> Set[int]:
    """Ids of the project's namespaces."""

    ensure_schema(connection)
    rows = connection.fetchall("SELECT id FROM vault_namespaces")
    assigned = {
        int(row["namespace_id"]): int(row["project_id"])
        for row in connection.fetchall(
            "SELECT namespace_id, project_id FROM vault_namespace_projects"
        )
    }
    default = _default(connection)
    return {
        int(row["id"]) for row in rows if assigned.get(int(row["id"]), default) == project_id
    }


def run_project() -> Optional[int]:
    """The project of the run this process executes, if it is a run worker."""

    value = os.environ.get(PROJECT_ENV, "").strip()
    try:
        return int(value) if value else None
    except ValueError:
        return None
