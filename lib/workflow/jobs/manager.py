"""
Workflow job manager.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.context import EntropyContext
from lib.workflow.exceptions import WorkflowJobNotFoundError

from .events import (
    WorkflowEvent,
    WorkflowEventRepository,
)
from .model import WorkflowJob
from .repository import WorkflowJobRepository
from .state import JobState


class WorkflowJobManager:
    """
    Manages persistent workflow jobs.

    Responsible for workflow job lifecycle and event
    persistence.

    Process management is intentionally handled separately.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        assert context.database_manager is not None

        connection = (
            context.database_manager.connection
        )

        self._repository = WorkflowJobRepository(
            connection,
        )

        self._events = WorkflowEventRepository(
            connection,
        )

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(
        self,
        execution_id: str,
        workflow: str,
        workspace: Path,
        pid: int,
    ) -> WorkflowJob:
        """
        Create a queued workflow job.
        """

        job = WorkflowJob(
            id=None,
            execution_id=execution_id,
            workflow=workflow,
            state=JobState.QUEUED,
            pid=pid,
            workspace=workspace,
            created_at=datetime.now(
                timezone.utc,
            ),
        )

        return self._repository.create(
            job,
        )

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get(
        self,
        job_id: int,
    ) -> WorkflowJob:
        """
        Return a workflow job.
        """

        return self._repository.get(
            job_id,
        )

    def get_by_execution_id(
        self,
        execution_id: str,
    ) -> WorkflowJob:
        """
        Return a workflow job by execution ID.
        """

        return self._repository.get_by_execution_id(
            execution_id,
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(
        self,
    ) -> list[WorkflowJob]:
        """
        Return all workflow jobs.
        """

        return self._repository.list()

    def active(
        self,
    ) -> list[WorkflowJob]:
        """
        Return active workflow jobs.
        """

        return self._repository.list_active()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(
        self,
        job_id: int,
        pid: int | None = None,
    ) -> WorkflowJob:
        """
        Mark a job as starting and optionally assign its PID.
        """

        job = self.get(
            job_id,
        )

        self._ensure_transition(
            job,
            JobState.STARTING,
        )

        job.state = JobState.STARTING
        job.started_at = datetime.now(
            timezone.utc,
        )

        if pid is not None:

            job.pid = pid

        return self._repository.update(
            job,
        )

    def running(
        self,
        job_id: int,
    ) -> WorkflowJob:
        """
        Mark a job as running.
        """

        job = self.get(
            job_id,
        )

        self._ensure_transition(
            job,
            JobState.RUNNING,
        )

        job.state = JobState.RUNNING

        return self._repository.update(
            job,
        )

    def set_pid(
        self,
        job_id: int,
        pid: int,
    ) -> WorkflowJob:
        """
        Assign the operating-system process ID.
        """

        if pid <= 0:

            raise ValueError(
                "Process ID must be greater than zero.",
            )

        return self._repository.set_pid(
            job_id,
            pid,
        )

    def pause(
        self,
        job_id: int,
    ) -> WorkflowJob:
        """
        Mark a running job as paused.

        Actual process suspension will be implemented by
        the process manager.
        """

        job = self.get(
            job_id,
        )

        if job.state is not JobState.RUNNING:

            raise ValueError(
                f"Job '{job_id}' is not running.",
            )

        return self._repository.set_state(
            job_id,
            JobState.PAUSED,
        )

    def resume(
        self,
        job_id: int,
    ) -> WorkflowJob:
        """
        Mark a paused job as running.

        Actual process resumption will be implemented by
        the process manager.
        """

        job = self.get(
            job_id,
        )

        if job.state is not JobState.PAUSED:

            raise ValueError(
                f"Job '{job_id}' is not paused.",
            )

        return self._repository.set_state(
            job_id,
            JobState.RUNNING,
        )

    def complete(
        self,
        job_id: int,
        exit_code: int = 0,
    ) -> WorkflowJob:
        """
        Mark a job as successfully completed.
        """

        return self._repository.complete(
            job_id,
            JobState.COMPLETED,
            exit_code,
        )

    def fail(
        self,
        job_id: int,
        exit_code: int | None = None,
    ) -> WorkflowJob:
        """
        Mark a job as failed.
        """

        return self._repository.complete(
            job_id,
            JobState.FAILED,
            exit_code,
        )

    def cancel(
        self,
        job_id: int,
        exit_code: int = 130,
    ) -> WorkflowJob:
        """
        Mark a job as cancelled.
        """

        return self._repository.complete(
            job_id,
            JobState.CANCELLED,
            exit_code,
        )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def event(
        self,
        *,
        job_id: int,
        execution_id: str,
        event_type: str,
        source: str | None = None,
        level: str | None = None,
        message: str | None = None,
        node_type: str | None = None,
        node_id: str | None = None,
        node_name: str | None = None,
        payload: dict | None = None,
    ) -> WorkflowEvent:
        """
        Persist a workflow execution event.
        """

        event = WorkflowEvent(
            id=None,
            job_id=job_id,
            execution_id=execution_id,
            event_type=event_type,
            source=source,
            level=level,
            message=message,
            node_type=node_type,
            node_id=node_id,
            node_name=node_name,
            payload=payload,
        )

        return self._events.create(
            event,
        )

    def events(
        self,
        job_id: int,
        *,
        after: int | None = None,
        limit: int = 500,
    ) -> list[WorkflowEvent]:
        """
        Return persisted events for a job.

        ``after`` is the event cursor used by follow mode.
        """

        return self._events.list(
            job_id,
            after=after,
            limit=limit,
        )

    def get_by_pid(
        self,
        pid: int,
    ) -> WorkflowJob:
        """
        Return a workflow job by process ID.
        """

        try:

            return self._repository.get_by_pid(
                pid,
            )

        except KeyError as exc:

            raise WorkflowJobNotFoundError(
                pid,
            ) from exc

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_transition(
        job: WorkflowJob,
        target: JobState,
    ) -> None:
        """
        Validate a job state transition.
        """

        allowed = {
            JobState.QUEUED: {
                JobState.STARTING,
                JobState.CANCELLED,
            },
            JobState.STARTING: {
                JobState.RUNNING,
                JobState.FAILED,
                JobState.CANCELLED,
            },
            JobState.RUNNING: {
                JobState.PAUSED,
                JobState.COMPLETED,
                JobState.FAILED,
                JobState.CANCELLED,
            },
            JobState.PAUSED: {
                JobState.RUNNING,
                JobState.CANCELLED,
            },
            JobState.COMPLETED: set(),
            JobState.FAILED: set(),
            JobState.CANCELLED: set(),
        }

        if target not in allowed[job.state]:

            raise ValueError(
                f"Invalid workflow job transition: "
                f"'{job.state.value}' -> '{target.value}'.",
            )

    # ------------------------------------------------------------------
    # Background process
    # ------------------------------------------------------------------

    def attach(
        self,
        job_id: int,
    ) -> WorkflowJob:
        """
        Attach to an existing workflow job.

        Used by a background worker process after the parent
        process has created the persistent job.
        """

        try:

            job = self.get(
                job_id,
            )

        except KeyError as exc:

            raise WorkflowJobNotFoundError(
                job_id,
            ) from exc

        if job.state is not JobState.QUEUED:

            raise ValueError(
                f"Workflow job '{job_id}' is not queued.",
            )

        return job
