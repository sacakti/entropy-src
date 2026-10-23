"""
Start, stop and reconcile workflow and plugin runs on behalf of users.

Runs started from the web or by a schedule execute as the requesting
user: a short-lived session is issued for them and handed to the worker
process, which revokes it when the run ends.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lib.auth.manager import SESSION_TOKEN_ENV
from lib.models.workflow import WorkflowExecutionOptions
from lib.system.install import scratch_directory

from .nodes import NodeStore, agent_up
from .plan import PlanError, RunPlan, build_plan
from .store import LOCAL_NODE, RunStore

# Delegated sessions outlive any reasonable run; the worker revokes early.
RUN_SESSION_HOURS = 72

# A job whose worker never attached is considered lost after this long.
QUEUED_GRACE = timedelta(minutes=2)

# A coordinated (multi-node) run whose main node stopped following it.
HEARTBEAT_GRACE = timedelta(seconds=60)

ACTIVE_STATES = ("queued", "starting", "running", "paused")

# Plugin bundle digests, memoised per directory (see plugin_digest).
_DIGESTS: Dict[str, Tuple[float, str]] = {}

_QUALIFIED_PLUGIN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


class RunError(Exception):
    """A run could not be started or changed; `status` maps to HTTP."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def _pid_alive(pid: Optional[int]) -> bool:
    if not pid or pid <= 0:
        return False

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

    # A finished child of this process stays a zombie until reaped.
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as handle:
            state = handle.read().rsplit(")", 1)[1].split()[0]
        return state not in ("Z", "X")
    except (OSError, IndexError):
        return True


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class RunService:
    """Starts runs as a given user and keeps job state honest."""

    # The project of the run being started; workers get it in their
    # environment so they read only that project's vault namespaces.
    _project_id: Optional[int] = None

    def __init__(self, context: Any) -> None:
        assert context.database_manager is not None
        self._context = context
        connection = context.database_manager.connection
        self.store = RunStore(connection)
        self.nodes = NodeStore(connection)

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    def _executable_node(self, name: str, project_id: Optional[int] = None) -> Dict[str, Any]:
        node = self.nodes.get(name or "local")

        if node is None:
            raise RunError(f"Node '{name}' does not exist.", 404)

        if project_id is not None:
            from lib.authorization.projects import Projects

            if not Projects(self.store.connection).node_available(node["name"], project_id):
                raise RunError(
                    f"Node '{node['name']}' is not available to this project.", 403
                )

        if not node["enabled"]:
            raise RunError(f"Node '{node['name']}' is disabled.", 409)

        if node["kind"] != "local" and not agent_up(node):
            raise RunError(
                f"Node '{node['name']}' is unreachable: its agent has not reported recently.",
                409,
            )

        return node

    def _dispatch(
        self,
        user: Any,
        node: Dict[str, Any],
        *,
        name: str,
        definition: str,
        steps: List[Any],
        variables: Optional[Dict[str, Any]],
    ) -> int:
        """Queue a run for a remote node's agent; returns the job id."""

        from lib.nodes.dispatch import NodeDispatcher
        from lib.nodes.packaging import plugin_digest

        plugins = self._context.plugin_manager
        required = sorted({step for step in steps if step})
        bundles = []
        for qualified_name in required:
            if not plugins.exists(qualified_name):
                raise RunError(f"Plugin '{qualified_name}' is not installed on the main node.", 409)
            path = Path(plugins.get(qualified_name).path)
            bundles.append(
                {"qualified_name": qualified_name, "digest": plugin_digest(path, _DIGESTS)}
            )

        slug = re.sub(r"[^a-z0-9_.-]+", "_", name.lower()).strip("_") or "workflow"
        job = self._context.workflow_job_manager.create(
            execution_id=f"{slug}_{uuid.uuid4().hex[:8]}",
            workflow=name,
            workspace=Path(f"node:{node['name']}"),
            pid=0,
            user_id=user.id,
            username=user.username,
            full_name=getattr(user, "full_name", None),
        )
        job_id = job.require_id()

        NodeDispatcher(self._context).enqueue(
            job_id,
            node["name"],
            {
                "job_id": job_id,
                "execution_id": job.execution_id,
                "definition": definition,
                "variables": dict(variables or {}),
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "full_name": getattr(user, "full_name", None),
                },
                "plugins": bundles,
            },
        )
        return job_id

    def _start(
        self,
        user: Any,
        *,
        name: Optional[str] = None,
        file: Optional[Path] = None,
        variables: Optional[Dict[str, Any]] = None,
    ):
        sessions = self._context.session_manager
        workflows = self._context.workflow_manager

        if sessions is None or workflows is None:
            raise RunError("Workflow service unavailable.", 503)

        session = sessions.issue(
            user.id,
            user.username,
            getattr(user, "full_name", None),
            hours=RUN_SESSION_HOURS,
        )

        try:
            return workflows.start(
                name,
                file=file,
                options=WorkflowExecutionOptions(variables=dict(variables or {})),
                session=session,
                environment=self._worker_environment(session.token),
            )
        except Exception:
            sessions.revoke(session.token)
            raise

    def _worker_environment(self, token: str) -> Dict[str, str]:
        from lib.vault.projects import PROJECT_ENV

        environment = {SESSION_TOKEN_ENV: token}
        if self._project_id is not None:
            environment[PROJECT_ENV] = str(self._project_id)
        return environment

    def launch(
        self,
        user: Any,
        node: Dict[str, Any],
        workflow: Any,
        variables: Optional[Dict[str, Any]],
        *,
        registered: bool = False,
    ) -> int:
        """
        Start `workflow` on `node`; returns the job id. A registered workflow
        runs by name; a trimmed one (a plan's segment) from a definition file.
        """

        manager = self._context.workflow_manager

        if node["kind"] != "local":
            return self._dispatch(
                user,
                node,
                name=workflow.name,
                definition=manager.serialize(workflow, "json"),
                steps=[step.plugin for step in workflow.steps if step.enabled],
                variables=variables,
            )

        if registered:
            return self._start(user, name=workflow.name, variables=variables).require_id()

        directory = scratch_directory(self._context.bootstrap.project_root) / "run-definitions"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{uuid.uuid4().hex}.json"
        path.write_text(manager.serialize(workflow, "json"), encoding="utf-8")
        return self._start(user, file=path, variables=variables).require_id()

    def plan(
        self,
        name: str,
        *,
        node: str = "local",
        steps: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        step_nodes: Optional[Dict[str, str]] = None,
    ) -> Tuple[Any, RunPlan]:
        """The workflow and the plan a run with these options would follow."""

        try:
            workflow = self._context.workflow_manager.get(name)
        except Exception as exc:
            raise RunError(str(exc) or f"Workflow '{name}' does not exist.", 404) from exc

        try:
            plan = build_plan(
                workflow,
                default_node=node or "local",
                steps=steps,
                tags=tags,
                step_nodes=step_nodes,
            )
        except PlanError as exc:
            raise RunError(str(exc), 422) from exc
        return workflow, plan

    def start_workflow(
        self,
        user: Any,
        name: str,
        *,
        node: str = "local",
        variables: Optional[Dict[str, Any]] = None,
        steps: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        step_nodes: Optional[Dict[str, str]] = None,
        trigger: str = "manual",
        schedule_id: Optional[int] = None,
        project_id: Optional[int] = None,
        workflow_definition: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._project_id = project_id
        if workflow_definition is None:
            workflow, plan = self.plan(name, node=node, steps=steps, tags=tags, step_nodes=step_nodes)
        else:
            try:
                workflow = self._context.workflow_manager.deserialize(workflow_definition)
                if workflow.name != name:
                    raise RunError("Saved workflow definition does not match this run.", 409)
                self._context.workflow_manager._validator.validate(workflow)
                plan = build_plan(
                    workflow,
                    default_node=node or "local",
                    steps=steps,
                    tags=tags,
                    step_nodes=step_nodes,
                )
            except RunError:
                raise
            except PlanError as exc:
                raise RunError(str(exc), 422) from exc
            except Exception as exc:
                raise RunError(str(exc) or "Saved workflow configuration is invalid.", 422) from exc
        nodes = {item: self._executable_node(item, project_id) for item in plan.nodes}
        segments = plan.segments
        options = plan.snapshot(variables)
        rerun_config = {
            "definition": self._context.workflow_manager.serialize(workflow, "json"),
            "variables": dict(variables or {}),
            "node": node or "local",
            "steps": list(steps) if steps is not None else None,
            "tags": list(tags or []),
            "step_nodes": dict(step_nodes or {}),
        }

        if len(segments) > 1:
            from .coordinator import Coordinator

            run = Coordinator.begin(
                self,
                user,
                workflow,
                plan,
                variables,
                trigger=trigger,
                schedule_id=schedule_id,
                rerun_config=rerun_config,
            )
            if run.get("id") is not None:
                self.store.set_project(run["id"], project_id)
                run["project_id"] = project_id
            return run

        target = nodes[segments[0]["node"]]
        try:
            if plan.trivial and workflow_definition is None:
                job_id = self.launch(user, target, workflow, variables, registered=True)
            else:
                from .plan import segment_workflow

                job_id = self.launch(
                    user, target, segment_workflow(workflow, segments[0]["steps"]), variables
                )
        except RunError:
            raise
        except Exception as exc:
            raise RunError(str(exc) or exc.__class__.__name__) from exc

        self.store.record(
            job_id,
            node=target["name"],
            kind="workflow",
            target=name,
            trigger=trigger,
            schedule_id=schedule_id,
            options=options,
            rerun_config=rerun_config,
        )
        self.store.set_project(job_id, project_id)
        return self.store.get(job_id) or {}

    def start_plugin(
        self,
        user: Any,
        qualified_name: str,
        *,
        node: str = "local",
        arguments: Optional[Dict[str, Any]] = None,
        trigger: str = "manual",
        schedule_id: Optional[int] = None,
        project_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Run one installed plugin as a single-step workflow."""

        self._project_id = project_id
        if not _QUALIFIED_PLUGIN.match(qualified_name or ""):
            raise RunError("Plugin name must be namespace.name.")

        plugins = self._context.plugin_manager
        if plugins is None:
            raise RunError("Plugin service unavailable.", 503)

        if not plugins.exists(qualified_name):
            raise RunError(f"Plugin '{qualified_name}' is not installed.", 404)

        target = self._executable_node(node, project_id)

        definition = {
            "name": f"plugin.{qualified_name}",
            "version": "1.0.0",
            "description": f"Run of plugin {qualified_name}.",
            "variables": {},
            "steps": [
                {
                    "name": qualified_name,
                    "plugin": qualified_name,
                    "arguments": dict(arguments or {}),
                    "enabled": True,
                    "on_failure": "abort",
                    "suppress_result": False,
                    "tags": [],
                }
            ],
        }

        if target["kind"] != "local":
            try:
                job_id = self._dispatch(
                    user,
                    target,
                    name=str(definition["name"]),
                    definition=json.dumps(definition, indent=2),
                    steps=[qualified_name],
                    variables=None,
                )
            except RunError:
                raise
            except Exception as exc:
                raise RunError(str(exc) or exc.__class__.__name__) from exc
        else:
            directory = self.plugin_run_directory()
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{uuid.uuid4().hex}.json"
            path.write_text(json.dumps(definition, indent=2), encoding="utf-8")

            try:
                job_id = self._start(user, file=path).require_id()
            except RunError:
                path.unlink()
                raise
            except Exception as exc:
                path.unlink()
                raise RunError(str(exc) or exc.__class__.__name__) from exc

        self.store.record(
            job_id,
            node=target["name"],
            kind="plugin",
            target=qualified_name,
            trigger=trigger,
            schedule_id=schedule_id,
        )
        self.store.set_project(job_id, project_id)
        return self.store.get(job_id) or {}

    def plugin_run_directory(self) -> Path:
        return Path(self._context.bootstrap.home) / "runs" / "plugins"

    # ------------------------------------------------------------------
    # Stop
    # ------------------------------------------------------------------

    def stop(self, job_id: int) -> Dict[str, Any]:
        run = self.store.get(job_id)

        if run is None:
            raise RunError(f"Run #{job_id} does not exist.", 404)

        if run["state"] not in ACTIVE_STATES:
            raise RunError(f"Run #{job_id} is not running.", 409)

        jobs = self._context.workflow_job_manager

        if run["coordinated"]:
            # Cancelling the run stops its coordinator from starting more
            # segments; the segment running now is stopped like any run.
            jobs.cancel(job_id)
            for child in self.store.children(job_id):
                if child["state"] in ACTIVE_STATES:
                    with contextlib.suppress(RunError):
                        self.stop(child["id"])
            return self.store.get(job_id) or run

        if run["node"] != LOCAL_NODE:
            from lib.nodes.dispatch import NodeDispatcher

            # The node's agent stops it on its next heartbeat.
            if not NodeDispatcher(self._context).request_stop(job_id):
                jobs.cancel(job_id)
        elif _pid_alive(run["pid"]):
            # SIGINT: the worker records the cancellation itself.
            jobs.stop(run["pid"])
        else:
            jobs.cancel(job_id)

        return self.store.get(job_id) or run

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------

    def log_path(self, job_id: int) -> Path:
        root = scratch_directory(self._context.bootstrap.project_root)
        return root / f"workflow-worker-{job_id}.log"

    def log(self, job_id: int, offset: int = 0, limit: int = 256_000) -> Dict[str, Any]:
        children = self.store.children(job_id)
        if children:
            return self._combined_log(children, offset, limit)

        path = self.log_path(job_id)

        if not path.exists():
            return {"offset": 0, "size": 0, "text": ""}

        size = path.stat().st_size
        offset = max(0, min(offset, size))

        with path.open("rb") as handle:
            handle.seek(offset)
            data = handle.read(limit)

        return {
            "offset": offset + len(data),
            "size": size,
            "text": data.decode("utf-8", errors="replace"),
        }

    def _combined_log(
        self, children: List[Dict[str, Any]], offset: int, limit: int
    ) -> Dict[str, Any]:
        """A coordinated run's output: its segments' logs one after another."""

        parts: List[bytes] = []
        for index, child in enumerate(children, start=1):
            parts.append(
                f"\n=== Segment {index} on {child['node']} (job #{child['id']}) ===\n".encode()
            )
            path = self.log_path(child["id"])
            if path.exists():
                parts.append(path.read_bytes())
        data = b"".join(parts)
        offset = max(0, min(offset, len(data)))
        chunk = data[offset : offset + limit]
        return {
            "offset": offset + len(chunk),
            "size": len(data),
            "text": chunk.decode("utf-8", errors="replace"),
        }

    # ------------------------------------------------------------------
    # Reconcile
    # ------------------------------------------------------------------

    def reconcile(self) -> int:
        """
        Fail active jobs whose worker is gone (crashed, killed, rebooted).

        Returns the number of jobs that were corrected.
        """

        jobs = self._context.workflow_job_manager
        now = datetime.now(timezone.utc)
        fixed = 0

        for run in self.store.active():
            if run["coordinated"]:
                if self._coordinator_lost(run):
                    fixed += 1
                continue

            # Remote runs are reconciled against their node's heartbeat.
            if run["node"] != LOCAL_NODE or _pid_alive(run["pid"]):
                continue

            if not run["pid"]:
                created = _parse(run["created_at"])
                if created is not None and now - created < QUEUED_GRACE:
                    continue

            # The worker may have recorded its final state meanwhile.
            current = self.store.get(run["id"])
            if current is None or current["state"] not in (
                "queued",
                "starting",
                "running",
                "paused",
            ):
                continue

            try:
                jobs.event(
                    job_id=run["id"],
                    execution_id=run["execution_id"],
                    event_type="message",
                    source="entropy.runs",
                    level="error",
                    message="Worker process exited unexpectedly.",
                )
                jobs.fail(run["id"], 1)
                fixed += 1
            except Exception:  # noqa: BLE001 - keep reconciling the rest
                continue

        return fixed

    def _coordinator_lost(self, run: Dict[str, Any]) -> bool:
        """Fail a multi-node run whose main node stopped following it."""

        beat = _parse(self.store.heartbeat_at(run["id"]))
        if beat is not None and datetime.now(timezone.utc) - beat < HEARTBEAT_GRACE:
            return False

        jobs = self._context.workflow_job_manager
        try:
            jobs.event(
                job_id=run["id"],
                execution_id=run["execution_id"],
                event_type="message",
                source="entropy.runs",
                level="error",
                message="The main node stopped coordinating this run (it restarted?).",
            )
            jobs.fail(run["id"], 1)
        except Exception:  # noqa: BLE001 - keep reconciling the rest
            return False

        for child in self.store.children(run["id"]):
            if child["state"] in ACTIVE_STATES:
                with contextlib.suppress(RunError):
                    self.stop(child["id"])
        return True
