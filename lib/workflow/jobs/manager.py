"""
Workflow job manager.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List

from core.context import EntropyContext
from lib.database.repositories.workflow_jobs import WorkflowJobRepository
from lib.workflow.exceptions import (
    WorkflowInvalidTransitionError,
    WorkflowJobIsNotPausedError,
    WorkflowJobNotFoundError,
    WorkflowJobNotRunningError,
    WorkflowNotQueuedError,
    WorkflowProcessIDError,
)
from lib.workflow.process import WorkflowProcess

from .events import (
    WorkflowEvent,
    WorkflowEventRepository,
)
from lib.models.workflow_jobs import WorkflowJob
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

        connection = context.database_manager.connection

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
        user_id: int,
        username: str,
        full_name: str | None,
    ) -> WorkflowJob:
        """
        Create a queued workflow job.
        """

        job = WorkflowJob(
            id=None,
            execution_id=execution_id,
            workflow=workflow,
            user_id=user_id,
            username=username,
            full_name=full_name,
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
    ) -> List[WorkflowJob]:
        """
        Return all workflow jobs.
        """

        return self._repository.list()

    def active(
        self,
    ) -> List[WorkflowJob]:
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

            raise WorkflowProcessIDError

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

            raise WorkflowJobNotRunningError(
                job_id,
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

            raise WorkflowJobIsNotPausedError(
                job_id,
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

    def stop(
        self,
        pid: int,
    ) -> WorkflowJob:
        """
        Request graceful cancellation of a workflow process.
        """

        job = self.get_by_pid(
            pid,
        )

        if not job.running:

            raise WorkflowJobNotRunningError(
                job.id,
            )

        WorkflowProcess.stop(
            pid,
        )

        return job

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
        limit: int | None = 500,
    ) -> List[WorkflowEvent]:
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

            raise WorkflowInvalidTransitionError(
                job.state.value,
                target.value,
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

            raise WorkflowNotQueuedError(
                job_id,
            )

        return job
