"""
Workflow loader.
"""

from __future__ import annotations

from pathlib import Path

from core.context import EntropyContext
from lib.models.workflow import (
    Workflow,
    WorkflowStep,
)

from .exceptions import (
    InvalidWorkflowError,
    WorkflowNotFoundError,
)


class WorkflowLoader:
    """
    Loads workflow definitions.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        assert context.executor is not None

        self._executor = context.executor

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def load(
        self,
        workflow: Path,
    ) -> Workflow:
        """
        Load a workflow.
        """

        if not self._executor.exists(
            workflow,
        ):

            raise WorkflowNotFoundError(
                workflow,
            )

        data = self._executor.read_json(
            workflow,
        )

        return self._model(
            data,
        )

    # ------------------------------------------------------------------
    # Mapper
    # ------------------------------------------------------------------

    def _model(
        self,
        data: dict,
    ) -> Workflow:
        """
        Convert JSON into a workflow model.
        """

        try:

            return Workflow(
                name=data["name"],
                version=data["version"],
                description=data.get(
                    "description",
                ),
                variables=data.get(
                    "variables",
                    {},
                ),
                steps=[
                    self._step(
                        item,
                    )
                    for item in data.get(
                        "steps",
                        [],
                    )
                ],
            )

        except KeyError as exc:

            raise InvalidWorkflowError(
                f"Missing required field '{exc.args[0]}'.",
            ) from exc

    def _step(
        self,
        data: dict,
    ) -> WorkflowStep:
        """
        Convert JSON into a workflow step.
        """

        return WorkflowStep(
            name=data["name"],
            plugin=data["plugin"],
            arguments=data.get(
                "arguments",
                {},
            ),
            enabled=data.get(
                "enabled",
                True,
            ),
            continue_on_error=data.get(
                "continue_on_error",
                False,
            ),
        )
