"""
The project a run works in.

Vault namespaces (like workflows and schedules) belong to a project: see
`VaultNamespace.project_id` and `lib.vault.access`. A run worker gets its
project in ENTROPY_PROJECT_ID; a run reads only that project's secrets.
"""

from __future__ import annotations

import os
from typing import Any, Optional

# Set for run workers (and `ent` runs): the project of the run they execute.
PROJECT_ENV = "ENTROPY_PROJECT_ID"


def run_project() -> Optional[int]:
    """The project of the run this process executes, if it is a run worker."""

    value = os.environ.get(PROJECT_ENV, "").strip()
    try:
        return int(value) if value else None
    except ValueError:
        return None


def current_run_project(connection: Any) -> int:
    """The run's project, else the Default project."""

    from lib.authorization.projects import default_project_id

    return run_project() or default_project_id(connection)
