"""
Workflow manager.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from lib.workflow.loader import WorkflowLoader
from lib.workflow.validator import WorkflowValidator
from lib.models.workflow import WorkflowDefinition
from lib.workflow.execution import WorkflowExecutor

if TYPE_CHECKING:
    from core.context import EntropyContext


class WorkflowManager:
    """
    Loads and validates workflow definitions.
    """

    def __init__(
        self,
        context: "EntropyContext",
    ) -> None:

        self._context = context

        self._loader = WorkflowLoader()

        self._validator = WorkflowValidator()

        self._executor = WorkflowExecutor(
            context,
        )

        self._workflow: WorkflowDefinition | None = None

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def load(
        self,
        workflow: Path,
    ) -> WorkflowDefinition:
        """
        Load a workflow definition.
        """

        assert self._context.executor is not None
        assert self._context.paths is not None

        #
        # Resolve workflow name.
        #
        if workflow.suffix == "":

            directory = self._context.paths.workflow.directory

            candidates = [
                directory / (workflow.name + ".json"),
                directory / (workflow.name + ".yaml"),
                directory / (workflow.name + ".yml"),
            ]

            workflow_file = None

            for candidate in candidates:

                if self._context.executor.exists(candidate):

                    workflow_file = candidate
                    break

            if workflow_file is None:

                raise FileNotFoundError(
                    "Workflow '{0}' does not exist.".format(
                        workflow.name,
                    )
                )

        else:

            workflow_file = workflow

        #
        # Read document.
        #
        suffix = workflow_file.suffix.lower()

        if suffix in {".yaml", ".yml"}:

            document = self._context.executor.read_yaml(
                workflow_file,
            )

        elif suffix == ".json":

            document = self._context.executor.read_json(
                workflow_file,
            )

        else:

            raise ValueError(
                "Unsupported workflow format '{0}'.".format(
                    suffix,
                )
            )

        workflow = self._loader.load(
            document,
        )

        self._validator.validate(
            workflow,
        )

        self._workflow = workflow

        return workflow

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
    ) -> None:
        """
        Execute the loaded workflow.
        """

        if self._workflow is None:

            raise RuntimeError(
                "No workflow has been loaded."
            )

        self._executor.execute(
            self._workflow,
        )
