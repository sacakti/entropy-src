"""
Workflow event follower.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from lib.workflow.exceptions import WorkflowError
from lib.workflow.jobs.events import WorkflowEvent
from lib.workflow.jobs.manager import WorkflowJobManager

from .renderer import WorkflowEventRenderer

if TYPE_CHECKING:
    from lib.workflow.jobs.model import WorkflowJob


class WorkflowFollower:
    """
    Follows a workflow execution through its persisted event stream.

    The follower is intentionally concerned only with event-stream
    consumption. Presentation is delegated to
    WorkflowEventRenderer.
    """

    def __init__(
        self,
        jobs: WorkflowJobManager,
        renderer: WorkflowEventRenderer,
    ) -> None:

        self._jobs = jobs
        self._renderer = renderer

    # ------------------------------------------------------------------
    # Follow
    # ------------------------------------------------------------------

    def follow(
        self,
        job: WorkflowJob,
        *,
        interval: float = 0.25,
    ) -> None:
        """
        Replay persisted events and follow new events until completion.
        """

        if job.id is None:

            raise WorkflowError(
                "Cannot follow a workflow job without an id.",
            )

        cursor: int | None = None

        while True:

            cursor = self._drain(
                job.id,
                cursor,
            )

            current = self._jobs.get(
                job.id,
            )

            if current.finished:

                #
                # The terminal state may have been committed before
                # the final event became visible to this reader.
                #
                # Drain once more before returning.
                #

                self._drain(
                    job.id,
                    cursor,
                )

                return

            time.sleep(
                interval,
            )

    # ------------------------------------------------------------------
    # Drain
    # ------------------------------------------------------------------

    def _drain(
        self,
        job_id: int,
        cursor: int | None,
    ) -> int | None:
        """
        Render all currently persisted events after the cursor.

        Returns the ID of the last rendered event.
        """

        events = self._jobs.events(
            job_id,
            after=cursor,
        )

        for event in events:

            self._render(
                event,
            )

            cursor = event.id

        return cursor

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def _render(
        self,
        event: WorkflowEvent,
    ) -> None:
        """
        Render one persisted workflow event.
        """

        self._renderer.render(
            event,
        )
