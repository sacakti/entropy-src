"""
Workflow job repository.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List

from lib.database.connection import DatabaseConnection
from lib.database.repository import Repository
from lib.workflow.exceptions import WorkflowInvalidTerminalError, WorkflowJobIDRequiredError
from lib.workflow.jobs.model import WorkflowJob
from lib.workflow.jobs.state import JobState


class WorkflowJobRepository(Repository):
    """
    Persists workflow jobs.
    """

    def __init__(
        self,
        connection: DatabaseConnection,
    ) -> None:

        super().__init__(
            connection,
        )

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(
        self,
        job: WorkflowJob,
    ) -> WorkflowJob:
        """
        Create a workflow job.
        """

        with self.connection.transaction():

            cursor = self.execute(
                """
                INSERT INTO workflow_jobs
                (
                    execution_id,
                    workflow,
                    state,
                    pid,
                    workspace,
                    created_at,
                    started_at,
                    finished_at,
                    exit_code
                )
                VALUES
                (
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?
                )
                """,
                (
                    job.execution_id,
                    job.workflow,
                    job.state.value,
                    job.pid,
                    str(job.workspace),
                    self._datetime(
                        job.created_at,
                    ),
                    self._datetime(
                        job.started_at,
                    ),
                    self._datetime(
                        job.finished_at,
                    ),
                    job.exit_code,
                ),
            )

            job.id = cursor.lastrowid

        assert job.id is not None

        return self.get(
            job.id,
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

        row = self.connection.fetchone(
            """
            SELECT *
            FROM workflow_jobs
            WHERE id = ?
            """,
            (job_id,),
        )

        if row is None:

            raise KeyError(
                f"Workflow job '{job_id}' was not found.",
            )

        return self._from_row(
            row,
        )

    def get_by_execution_id(
        self,
        execution_id: str,
    ) -> WorkflowJob:
        """
        Return a workflow job by execution identifier.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM workflow_jobs
            WHERE execution_id = ?
            """,
            (execution_id,),
        )

        if row is None:

            raise KeyError(
                f"Workflow execution '{execution_id}' was not found.",
            )

        return self._from_row(
            row,
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

        rows = self.connection.fetchall(
            """
            SELECT *
            FROM workflow_jobs
            ORDER BY id DESC
            """
        )

        return [
            self._from_row(
                row,
            )
            for row in rows
        ]

    def list_active(
        self,
    ) -> List[WorkflowJob]:
        """
        Return active workflow jobs.
        """

        rows = self.connection.fetchall(
            """
            SELECT *
            FROM workflow_jobs
            WHERE state IN (?, ?, ?)
            ORDER BY id
            """,
            (
                JobState.STARTING.value,
                JobState.RUNNING.value,
                JobState.PAUSED.value,
            ),
        )

        return [
            self._from_row(
                row,
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self,
        job: WorkflowJob,
    ) -> WorkflowJob:
        """
        Update a workflow job.
        """

        if job.id is None:

            raise WorkflowJobIDRequiredError()

        with self.connection.transaction():

            self.execute(
                """
                UPDATE workflow_jobs
                SET
                    execution_id = ?,
                    workflow = ?,
                    state = ?,
                    pid = ?,
                    workspace = ?,
                    started_at = ?,
                    finished_at = ?,
                    exit_code = ?
                WHERE id = ?
                """,
                (
                    job.execution_id,
                    job.workflow,
                    job.state.value,
                    job.pid,
                    str(job.workspace),
                    self._datetime(
                        job.started_at,
                    ),
                    self._datetime(
                        job.finished_at,
                    ),
                    job.exit_code,
                    job.id,
                ),
            )

        return self.get(
            job.id,
        )

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def set_state(
        self,
        job_id: int,
        state: JobState,
    ) -> WorkflowJob:
        """
        Update the state of a workflow job.
        """

        with self.connection.transaction():

            self.execute(
                """
                UPDATE workflow_jobs
                SET state = ?
                WHERE id = ?
                """,
                (
                    state.value,
                    job_id,
                ),
            )

        return self.get(
            job_id,
        )

    def set_pid(
        self,
        job_id: int,
        pid: int,
    ) -> WorkflowJob:
        """
        Assign the operating-system process ID.
        """

        with self.connection.transaction():

            self.execute(
                """
                UPDATE workflow_jobs
                SET pid = ?
                WHERE id = ?
                """,
                (
                    pid,
                    job_id,
                ),
            )

        return self.get(
            job_id,
        )

    def complete(
        self,
        job_id: int,
        state: JobState,
        exit_code: int | None = None,
    ) -> WorkflowJob:
        """
        Mark a job as finished.
        """

        if state not in (
            JobState.COMPLETED,
            JobState.FAILED,
            JobState.CANCELLED,
        ):

            raise WorkflowInvalidTerminalError(
                state.value,
            )

        finished_at = datetime.now(
            timezone.utc,
        )

        with self.connection.transaction():

            self.execute(
                """
                UPDATE workflow_jobs
                SET
                    state = ?,
                    finished_at = ?,
                    exit_code = ?
                WHERE id = ?
                """,
                (
                    state.value,
                    self._datetime(
                        finished_at,
                    ),
                    exit_code,
                    job_id,
                ),
            )

        return self.get(
            job_id,
        )

    # ------------------------------------------------------------------
    # Mapper
    # ------------------------------------------------------------------

    @staticmethod
    def _datetime(
        value: datetime | None,
    ) -> str | None:

        if value is None:

            return None

        return value.isoformat()

    @classmethod
    def _from_row(
        cls,
        row,
    ) -> WorkflowJob:
        """
        Convert a database row into a workflow job.
        """

        return WorkflowJob(
            id=row["id"],
            execution_id=row["execution_id"],
            workflow=row["workflow"],
            state=JobState(
                row["state"],
            ),
            pid=row["pid"],
            workspace=Path(
                row["workspace"],
            ),
            created_at=cls._parse_datetime(
                row["created_at"],
            ),
            started_at=cls._parse_datetime(
                row["started_at"],
            ),
            finished_at=cls._parse_datetime(
                row["finished_at"],
            ),
            exit_code=row["exit_code"],
        )

    @staticmethod
    def _parse_datetime(
        value: str | None,
    ) -> datetime | None:

        if not value:
            return None

        parsed = datetime.fromisoformat(
            value,
        )

        if parsed.tzinfo is None:

            return parsed.replace(
                tzinfo=timezone.utc,
            )

        return parsed.astimezone(
            timezone.utc,
        )

    def get_by_pid(
        self,
        pid: int,
    ) -> WorkflowJob:
        """
        Return a workflow job by process ID.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM workflow_jobs
            WHERE pid = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (pid,),
        )

        if row is None:

            raise KeyError(
                f"Workflow process '{pid}' was not found.",
            )

        return self._from_row(
            row,
        )
