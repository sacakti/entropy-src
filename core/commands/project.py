"""Choose the project used by CLI commands."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace

from core.commands.base import BaseCommand, CommandMetadata
from core.commands.project_context import ProjectContext


class ProjectCommand(BaseCommand):
    metadata = CommandMetadata(name="project", description="Select the current project.")

    def configure(self, parser: ArgumentParser) -> None:
        actions = parser.add_subparsers(dest="action", required=True)
        actions.add_parser("current", help="Show the current project.")
        actions.add_parser("list", help="List projects available to you.")
        set_parser = actions.add_parser("set", help="Set the current project.")
        set_parser.add_argument("project", help="Project key.")
        actions.add_parser("remove", help="Clear the selection and use the default project.")

    def execute(self, args: Namespace) -> None:
        session = self._require_authentication()
        projects = ProjectContext(self.context)
        if args.action == "set":
            project = projects.set(session, args.project)
            self.context.ui.success(f"Current project set to '{project['key']}' ({project['name']}).")
        elif args.action == "remove":
            projects.remove(session)
            current = projects.current(session)
            self.context.ui.success(f"Project selection cleared. Using '{current['key']}'.")
        elif args.action == "current":
            project = projects.current(session)
            self.context.ui.info(f"{project['key']} — {project['name']}")
        else:
            accessible = projects.accessible_ids(session)
            available = projects.projects.list(accessible)
            current_id = projects.current(session)["id"]
            self.context.ui.table(
                title="Available Projects",
                columns=["Key", "Name", "Current"],
                rows=[
                    [
                        project["key"],
                        project["name"],
                        "Yes" if project["id"] == current_id else "",
                    ]
                    for project in available
                ],
            )
