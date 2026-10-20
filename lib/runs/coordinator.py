"""
Runs whose steps go to several nodes.

The run itself is a job on the main node with no process of its own. A
thread here starts its segments one after another (each an ordinary job
on its node, see lib.runs.plan), waits for each to finish, and hands the
outputs of finished steps to the next segment. It writes a heartbeat so
reconcile can tell when the main node stopped following the run.
"""

from __future__ import annotations

import contextlib
import logging
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from .plan import RunPlan, segment_workflow

LOGGER = logging.getLogger("entropy.runs")

POLL_SECONDS = 1.0
HEARTBEAT_SECONDS = 5.0
# How long a segment may take to stop after its run was cancelled.
STOP_WAIT_SECONDS = 60.0

ACTIVE = ("queued", "starting", "running", "paused")


class Coordinator:
    """Follows one multi-node run until it ends."""

    def __init__(
        self,
        service: Any,
        user: Any,
        workflow: Any,
        plan: RunPlan,
        variables: Optional[Dict[str, Any]],
        job_id: int,
        execution_id: str,
    ) -> None:
        self.service = service
        self.user = user
        self.workflow = workflow
        self.plan = plan
        self.variables = dict(variables or {})
        self.job_id = job_id
        self.execution_id = execution_id
        self._jobs = service._context.workflow_job_manager
        self._beat = 0.0

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    @classmethod
    def begin(
        cls,
        service: Any,
        user: Any,
        workflow: Any,
        plan: RunPlan,
        variables: Optional[Dict[str, Any]],
        *,
        trigger: str,
        schedule_id: Optional[int],
    ) -> Dict[str, Any]:
        """Record the run and start following it; returns the run."""

        slug = re.sub(r"[^a-z0-9_.-]+", "_", workflow.name.lower()).strip("_") or "workflow"
        job = service._context.workflow_job_manager.create(
            execution_id=f"{slug}_{uuid.uuid4().hex[:8]}",
            workflow=workflow.name,
            workspace=Path("nodes:" + ",".join(plan.nodes)),
            pid=0,
            user_id=user.id,
            username=user.username,
            full_name=getattr(user, "full_name", None),
        )
        job_id = job.require_id()
        service.store.record(
            job_id,
            node=plan.default_node,
            kind="workflow",
            target=workflow.name,
            trigger=trigger,
            schedule_id=schedule_id,
            options=plan.snapshot(variables),
            coordinated=True,
        )

        coordinator = cls(service, user, workflow, plan, variables, job_id, job.execution_id)
        threading.Thread(target=coordinator.run, name=f"entropy-run-{job_id}", daemon=True).start()
        return service.store.get(job_id) or {}

    # ------------------------------------------------------------------
    # Follow
    # ------------------------------------------------------------------

    def _say(self, message: str, level: str = "info", **payload: Any) -> None:
        self._jobs.event(
            job_id=self.job_id,
            execution_id=self.execution_id,
            event_type="message",
            source="entropy.runs",
            level=level,
            message=message,
            payload=payload or None,
        )

    def _state(self, job_id: int) -> Optional[str]:
        run = self.service.store.get(job_id)
        return run["state"] if run else None

    def _heartbeat(self, force: bool = False) -> None:
        now = time.monotonic()
        if force or now - self._beat >= HEARTBEAT_SECONDS:
            self.service.store.heartbeat(self.job_id)
            self._beat = now

    def run(self) -> None:
        try:
            self._run()
        except Exception as exc:  # noqa: BLE001 - the run must end either way
            LOGGER.exception("Coordinated run #%s failed.", self.job_id)
            if self._state(self.job_id) in ACTIVE:
                self._say(f"The run failed: {exc}", "error")
                self._jobs.fail(self.job_id, 1)

    def _run(self) -> None:
        self._heartbeat(force=True)
        self._jobs.start(self.job_id)
        self._jobs.running(self.job_id)

        segments = self.plan.segments
        self._say(
            f"Running {len(self.plan.selected)} step(s) in {len(segments)} segments on "
            + ", ".join(self.plan.nodes)
            + "."
        )

        outputs: Dict[str, Dict[str, Any]] = {}
        for index, segment in enumerate(segments, start=1):
            if self._state(self.job_id) not in ACTIVE:
                return  # cancelled

            label = f"Segment {index}/{len(segments)} on {segment['node']}"
            try:
                workflow = segment_workflow(self.workflow, segment["steps"], outputs)
                node = self.service._executable_node(segment["node"])
                child = self.service.launch(self.user, node, workflow, self.variables)
            except Exception as exc:  # noqa: BLE001 - reported on the run
                self._say(f"{label} could not start: {exc}", "error")
                self._jobs.fail(self.job_id, 1)
                return

            self.service.store.record(
                child,
                node=segment["node"],
                kind="workflow",
                target=self.workflow.name,
                trigger="manual",
                options={"segment": index, "steps": segment["steps"]},
                parent_job_id=self.job_id,
            )
            self._say(
                f"{label}: {', '.join(segment['steps'])} (job #{child}).",
                segment=index,
                node=segment["node"],
                job_id=child,
                steps=segment["steps"],
            )

            state = self._wait(child)
            if state != "completed":
                if self._state(self.job_id) in ACTIVE:
                    self._say(f"{label} ended {state}; the run stops here.", "error")
                    if state == "cancelled":
                        self._jobs.cancel(self.job_id)
                    else:
                        self._jobs.fail(self.job_id, 1)
                return

            outputs.update(self.service.store.step_outputs(child))

        if self._state(self.job_id) in ACTIVE:
            self._say("All segments completed.")
            self._jobs.complete(self.job_id)

    def _wait(self, child: int) -> Optional[str]:
        """Wait for a segment to end; stop it if the run was cancelled."""

        stop_sent: Optional[float] = None
        while True:
            self._heartbeat()
            state = self._state(child)
            if state not in ACTIVE:
                return state

            if self._state(self.job_id) not in ACTIVE:
                if stop_sent is None:
                    stop_sent = time.monotonic()
                    # The segment may have just ended on its own.
                    with contextlib.suppress(Exception):
                        self.service.stop(child)
                elif time.monotonic() - stop_sent > STOP_WAIT_SECONDS:
                    return "cancelled"

            time.sleep(POLL_SECONDS)
