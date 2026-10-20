"""
Start, stop and reconcile workflow and plugin runs on behalf of users.

Runs started from the web or by a schedule execute as the requesting
user: a short-lived session is issued for them and handed to the worker
process, which revokes it when the run ends.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lib.auth.manager import SESSION_TOKEN_ENV
from lib.models.workflow import WorkflowExecutionOptions

from .nodes import NodeStore, agent_up
from .store import LOCAL_NODE, RunStore

# Delegated sessions outlive any reasonable run; the worker revokes early.
RUN_SESSION_HOURS = 72

# A job whose worker never attached is considered lost after this long.
QUEUED_GRACE = timedelta(minutes=2)

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

    def __init__(self, context: Any) -> None:
        assert context.database_manager is not None
        self._context = context
        connection = context.database_manager.connection
        self.store = RunStore(connection)
        self.nodes = NodeStore(connection)

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    def _executable_node(self, name: str) -> Dict[str, Any]:
        node = self.nodes.get(name or "local")

        if node is None:
            raise RunError(f"Node '{name}' does not exist.", 404)

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
                environment={SESSION_TOKEN_ENV: session.token},
            )
        except Exception:
            sessions.revoke(session.token)
            raise

    def start_workflow(
        self,
        user: Any,
        name: str,
        *,
        node: str = "local",
        variables: Optional[Dict[str, Any]] = None,
        trigger: str = "manual",
        schedule_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        target = self._executable_node(node)

        try:
            if target["kind"] == "local":
                job_id = self._start(user, name=name, variables=variables).require_id()
            else:
                manager = self._context.workflow_manager
                workflow = manager.get(name)
                job_id = self._dispatch(
                    user,
                    target,
                    name=workflow.name,
                    definition=manager.serialize(workflow, "json"),
                    steps=[step.plugin for step in workflow.steps if step.enabled],
                    variables=variables,
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
        )
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
    ) -> Dict[str, Any]:
        """Run one installed plugin as a single-step workflow."""

        if not _QUALIFIED_PLUGIN.match(qualified_name or ""):
            raise RunError("Plugin name must be namespace.name.")

        plugins = self._context.plugin_manager
        if plugins is None:
            raise RunError("Plugin service unavailable.", 503)

        if not plugins.exists(qualified_name):
            raise RunError(f"Plugin '{qualified_name}' is not installed.", 404)

        target = self._executable_node(node)

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

        if run["state"] not in ("queued", "starting", "running", "paused"):
            raise RunError(f"Run #{job_id} is not running.", 409)

        jobs = self._context.workflow_job_manager

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
        root = Path(self._context.bootstrap.project_root)
        return root / "tmp" / f"workflow-worker-{job_id}.log"

    def log(self, job_id: int, offset: int = 0, limit: int = 256_000) -> Dict[str, Any]:
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
