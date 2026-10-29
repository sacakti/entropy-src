"""
Runs (jobs) of the current project: the same verbs as the ent client and
the browser shell (`ent job list|get|logs|stop|wait`).
"""

from __future__ import annotations

import time
from argparse import ArgumentParser, Namespace
from typing import Any, Dict, Optional

from core.commands.base import BaseCommand, CommandMetadata
from core.commands.exceptions import CommandError
from core.commands.output_mode import add_output_argument, emit, output_mode
from core.commands.project_context import ProjectContext
from lib.authorization.exceptions import AuthorizationRequiredError
from lib.authorization.projects import DEFAULT_PROJECT
from lib.remote_cli.contract import canonical_verb, resource
from lib.remote_cli.output import when
from lib.runs.service import RunError, RunService
from lib.runs.store import ACTIVE_STATES

POLL_SECONDS = 1.0


def _nodes(run: Dict[str, Any]) -> str:
    return ",".join((run.get("options") or {}).get("nodes") or [run["node"]])


class JobCommand(BaseCommand):
    """
    List, inspect, follow and stop runs.
    """

    metadata = CommandMetadata(
        name="job",
        description="Runs of the current project.",
        aliases=(
            "jobs",
            "run",
            "runs",
        ),
    )

    # ------------------------------------------------------------------
    # Configure
    # ------------------------------------------------------------------

    def configure(
        self,
        parser: ArgumentParser,
    ) -> None:

        item = resource("job")
        assert item is not None

        actions = parser.add_subparsers(
            dest="action",
            required=True,
        )

        verbs = {
            verb.name: actions.add_parser(
                verb.name,
                aliases=list(verb.aliases),
                help=verb.help,
            )
            for verb in item.verbs
            if verb.local
        }

        verbs["list"].add_argument(
            "--state",
            choices=("active", "completed", "failed", "cancelled", "all"),
            default="all",
        )

        verbs["list"].add_argument(
            "--workflow",
            help="Only runs of this workflow or plugin.",
        )

        verbs["list"].add_argument(
            "--limit",
            type=int,
            default=20,
        )

        for name in ("get", "logs", "stop", "wait"):

            verbs[name].add_argument(
                "id",
                type=int,
                help="Run ID.",
            )

        for name in ("list", "get"):

            add_output_argument(
                verbs[name],
            )

        verbs["logs"].add_argument(
            "-f",
            "--follow",
            action="store_true",
            help="Keep printing until it ends.",
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        args: Namespace,
    ) -> None:

        {
            "list": self._list,
            "get": self._get,
            "logs": self._logs,
            "stop": self._stop,
            "wait": self._wait,
        }[canonical_verb("job", args.action)](
            args,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _service(self) -> RunService:
        return RunService(self.context)

    def _run(self, job_id: int, permission: str) -> Dict[str, Any]:
        """
        A run, after checking `permission` in its project.
        """

        session = self._require_authentication()
        service = self._service()
        run = service.store.get(job_id)

        if run is None:
            raise CommandError(f"Run #{job_id} does not exist.")

        project_id = run.get("project_id")
        if project_id is None:
            default = ProjectContext(self.context).projects.get(DEFAULT_PROJECT)
            project_id = default["id"] if default else None

        assert self.context.authorization is not None
        if not self.context.authorization.has_permission(session.user_id, permission, project_id):
            raise AuthorizationRequiredError(permission)

        return run

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _list(
        self,
        args: Namespace,
    ) -> None:

        session = self._require_authentication()
        project = ProjectContext(self.context).current(session)

        assert self.context.authorization is not None
        if not self.context.authorization.has_permission(
            session.user_id, "workflows.read", project["id"]
        ):
            raise AuthorizationRequiredError("workflows.read")

        items, _ = self._service().store.list(
            tab=args.state,
            search=args.workflow or "",
            limit=args.limit,
            project_id=project["id"],
        )

        emit(
            self.context,
            args,
            title=f"Runs in {project['key']}",
            columns=[
                ("id", lambda r: r["id"], False),
                ("target", lambda r: r.get("target") or r.get("workflow"), False),
                ("state", lambda r: r["state"], False),
                ("node", _nodes, False),
                ("by", lambda r: r.get("username"), True),
                ("started", lambda r: when(r.get("started_at") or r.get("created_at")), False),
                ("finished", lambda r: when(r.get("finished_at")), True),
                ("trigger", lambda r: r.get("trigger"), True),
            ],
            items=items,
            kind="job",
            name=lambda r: r["id"],
        )

    def _get(
        self,
        args: Namespace,
    ) -> None:

        run = self._run(args.id, "workflows.read")
        steps = self._service().store.steps(args.id)

        if output_mode(self.context, args) != "detailed":
            emit(
                self.context,
                args,
                title="Run",
                columns=[
                    ("id", lambda r: r["id"], False),
                    ("target", lambda r: r.get("target") or r.get("workflow"), False),
                    ("state", lambda r: r["state"], False),
                    ("node", _nodes, False),
                    ("by", lambda r: r.get("username"), True),
                    ("started", lambda r: when(r.get("started_at")), False),
                    ("finished", lambda r: when(r.get("finished_at")), True),
                ],
                items=[run],
                kind="job",
                name=lambda r: r["id"],
                data={"run": run, "steps": steps},
            )
            return

        self.context.ui.table(
            title=f"Run #{run['id']}",
            columns=["Property", "Value"],
            rows=[
                ["Target", str(run.get("target") or run.get("workflow"))],
                ["State", str(run["state"])],
                ["Node", _nodes(run)],
                ["Trigger", str(run.get("trigger") or "")],
                ["By", str(run.get("username") or "")],
                ["Started", when(run.get("started_at"))],
                ["Finished", when(run.get("finished_at"))],
            ],
        )

        if steps:
            emit(
                self.context,
                args,
                title="Steps",
                columns=[
                    ("step", lambda s: s.get("name"), False),
                    ("status", lambda s: s.get("status"), False),
                    ("started", lambda s: when(s.get("started_at")), False),
                    ("finished", lambda s: when(s.get("finished_at")), False),
                ],
                items=steps,
                kind="step",
            )

    def _logs(
        self,
        args: Namespace,
    ) -> None:

        self._run(args.id, "workflows.read")
        service = self._service()
        offset = 0
        pending = ""

        while True:
            chunk = service.log(args.id, offset=offset)
            offset = chunk["offset"]
            text = pending + chunk["text"]
            # Whole lines only: the console adds its own line ends.
            complete, _, pending = text.rpartition("\n")
            if complete:
                self.context.ui.text(complete)
            if not args.follow:
                break
            run = service.store.get(args.id)
            if (run is None or run["state"] not in ACTIVE_STATES) and not chunk["text"]:
                break
            time.sleep(POLL_SECONDS)

        if pending:
            self.context.ui.text(pending)

    def _stop(
        self,
        args: Namespace,
    ) -> None:

        self._run(args.id, "workflows.execute")

        try:
            run = self._service().stop(args.id)
        except RunError as exc:
            raise CommandError(str(exc)) from exc

        self.context.ui.success(f"Run #{run['id']}: {run['state']}.")

    def _wait(
        self,
        args: Namespace,
    ) -> None:

        run: Optional[Dict[str, Any]] = self._run(args.id, "workflows.read")
        store = self._service().store

        while run is not None and run["state"] in ACTIVE_STATES:
            time.sleep(POLL_SECONDS)
            run = store.get(args.id)

        state = run["state"] if run else "unknown"
        if state != "completed":
            raise CommandError(f"Run #{args.id} {state}.")

        self.context.ui.success(f"Run #{args.id} completed.")
