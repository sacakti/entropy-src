"""Resolve and persist the current CLI project."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib.authorization.projects import DEFAULT_PROJECT, Projects
from lib.models.session import Session


class ProjectContext:
    """Per-user project selection for CLI commands."""

    def __init__(self, context: Any) -> None:
        self.context = context
        assert context.database_manager is not None
        assert context.bootstrap is not None
        self.projects = Projects(context.database_manager.connection)
        self.path = context.bootstrap.home / "config" / "cli-projects.json"

    def accessible_ids(self, session: Session) -> set[int] | None:
        assert self.context.authorization is not None
        return self.context.authorization.member_projects(session.user_id)

    def _selections(self) -> dict[str, str]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def current(self, session: Session) -> dict[str, Any]:
        selections = self._selections()
        key = selections.get(str(session.user_id))
        accessible = self.accessible_ids(session)
        if key:
            selected = self.projects.get(key)
            if selected is not None and (accessible is None or selected["id"] in accessible):
                return selected
        default = self.projects.get(DEFAULT_PROJECT)
        if default is not None and (accessible is None or default["id"] in accessible):
            return default
        projects = self.projects.list(accessible)
        if projects:
            return projects[0]
        if default is None:
            raise ValueError("No projects are configured.")
        return default

    def set(self, session: Session, key: str) -> dict[str, Any]:
        project = self.projects.get(key)
        if project is None:
            raise ValueError(f"Project '{key}' was not found.")
        accessible = self.accessible_ids(session)
        if accessible is not None and project["id"] not in accessible:
            raise ValueError(f"You do not have access to project '{project['key']}'.")
        selections = self._selections()
        selections[str(session.user_id)] = project["key"]
        self._write(selections)
        return project

    def remove(self, session: Session) -> None:
        selections = self._selections()
        selections.pop(str(session.user_id), None)
        self._write(selections)

    def _write(self, selections: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(selections, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
