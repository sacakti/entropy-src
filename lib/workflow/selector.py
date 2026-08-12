"""
Workflow step selector.
"""

from __future__ import annotations

from dataclasses import dataclass

from lib.models.workflow import WorkflowStep

from .exceptions import (
    WorkflowStepNotFoundError,
    WorkflowStepRangeError,
)


@dataclass(frozen=True)
class WorkflowSelection:
    """
    Result of workflow step selection.
    """

    steps: list[WorkflowStep]


class WorkflowStepSelector:
    """
    Select workflow steps for execution.

    Selection is performed in workflow order.

    The selection pipeline is:

        from-step / to-step
                ↓
              tags
                ↓
        selected steps
    """

    def select(
        self,
        steps: list[WorkflowStep],
        *,
        tags: tuple[str, ...] = (),
        from_step: str | None = None,
        to_step: str | None = None,
    ) -> WorkflowSelection:
        """
        Select workflow steps.

        Parameters
        ----------
        steps:
            Workflow steps in their declared order.

        tags:
            Select steps containing at least one of these tags.

        from_step:
            First step to include.

        to_step:
            Last step to include.
        """

        start = self._find_index(
            steps,
            from_step,
        )

        end = self._find_index(
            steps,
            to_step,
        )

        if start is None:
            start = 0

        if end is None:
            end = len(steps) - 1

        if start > end:

            raise WorkflowStepRangeError(
                from_step=from_step,
                to_step=to_step,
            )

        selected = steps[
            start : end + 1
        ]

        #
        # Apply tag filtering only when tags
        # were actually supplied.
        #
        if tags:

            selected = [
                step
                for step in selected
                if any(
                    tag in step.tags
                    for tag in tags
                )
            ]

        return WorkflowSelection(
            steps=selected,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_index(
        steps: list[WorkflowStep],
        name: str | None,
    ) -> int | None:
        """
        Return the index of a named workflow step.
        """

        if name is None:
            return None

        for index, step in enumerate(steps):

            if step.name == name:

                return index

        raise WorkflowStepNotFoundError(
            name,
        )
