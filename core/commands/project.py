"""Choose the project used by CLI commands."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace

from core.commands.base import BaseCommand, CommandMetadata
from core.commands.output_mode import add_output_argument, emit
from core.commands.project_context import ProjectContext
from lib.remote_cli.contract import canonical_verb, resource


class ProjectCommand(BaseCommand):
    metadata = CommandMetadata(
        name="project",
        description="Select the current project.",
        aliases=("projects", "proj"),
    )

    def configure(self, parser: ArgumentParser) -> None:
        item = resource("project")
        assert item is not None
        actions = parser.add_subparsers(dest="action", required=True)
        verbs = {
            verb.name: actions.add_parser(verb.name, aliases=list(verb.aliases), help=verb.help)
            for verb in item.verbs
        }
        verbs["set"].add_argument("project", help="Project key.")
        add_output_argument(verbs["list"])

    def execute(self, args: Namespace) -> None:
        session = self._require_authentication()
        projects = ProjectContext(self.context)
        action = canonical_verb("project", args.action)
        if action == "set":
            project = projects.set(session, args.project)
            self.context.ui.success(
                f"Current project set to '{project['key']}' ({project['name']})."
            )
        elif action == "remove":
            projects.remove(session)
            current = projects.current(session)
            self.context.ui.success(f"Project selection cleared. Using '{current['key']}'.")
        elif action == "current":
            project = projects.current(session)
            self.context.ui.info(f"{project['key']} — {project['name']}")
        else:
            accessible = projects.accessible_ids(session)
            available = projects.projects.list(accessible)
            current_id = projects.current(session)["id"]
            emit(
                self.context,
                args,
                title="Available Projects",
                columns=[
                    ("current", lambda p: "*" if p["id"] == current_id else "", False),
                    ("key", lambda p: p["key"], False),
                    ("name", lambda p: p["name"], False),
                    ("description", lambda p: p.get("description"), True),
                ],
                items=available,
                kind="project",
                name=lambda p: p["key"],
            )
