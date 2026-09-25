"""
Workflow validator.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lib.models.workflow import (
    Workflow,
    WorkflowStep,
)

if TYPE_CHECKING:
    from lib.plugins.manager import PluginManager

from .exceptions import (
    InvalidWorkflowError,
)


class WorkflowValidator:
    """
    Validates workflow definitions.
    """

    def __init__(
        self,
        plugins: PluginManager,
    ) -> None:

        self._plugins = plugins

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def validate(
        self,
        workflow: Workflow,
    ) -> None:
        """
        Validate a workflow.
        """

        self._workflow(
            workflow,
        )

        self._workspace(
            workflow,
        )

        self._steps(
            workflow,
        )

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------

    def _workflow(
        self,
        workflow: Workflow,
    ) -> None:
        """
        Validate workflow metadata.
        """

        if not workflow.name:

            raise InvalidWorkflowError(
                "Workflow name is required.",
            )

        if not workflow.steps:

            raise InvalidWorkflowError(
                "Workflow contains no steps.",
            )

    def _workspace(
        self,
        workflow: Workflow,
    ) -> None:
        """
        Validate workflow workspace configuration.
        """

        workspace = workflow.workspace

        if workspace is None:
            return

        if workspace.position not in {
            "before",
            "after",
        }:

            raise InvalidWorkflowError(
                f"Unsupported workspace position "
                f"'{workspace.position}'. "
                "Supported values: before, after.",
            )

        if workspace.type not in {
            "variable",
            "custom",
        }:

            raise InvalidWorkflowError(
                f"Unsupported workspace type "
                f"'{workspace.type}'. "
                "Supported values: variable, custom.",
            )

        if workspace.add_text and not workspace.name:

            raise InvalidWorkflowError(
                "Workspace 'name' is required when "
                "'add_text' is enabled.",
            )

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def _steps(
        self,
        workflow: Workflow,
    ) -> None:
        """
        Validate workflow steps.
        """

        names: set[str] = set()

        for step in workflow.steps:

            self._step(
                step,
            )

            if step.name in names:

                raise InvalidWorkflowError(
                    f"Duplicate step '{step.name}'.",
                )

            names.add(
                step.name,
            )

    # ------------------------------------------------------------------
    # Step
    # ------------------------------------------------------------------

    def _step(
        self,
        step: WorkflowStep,
    ) -> None:
        """
        Validate a workflow step.
        """

        if not step.name:

            raise InvalidWorkflowError(
                "Workflow step name is required.",
            )

        if not step.plugin:

            raise InvalidWorkflowError(
                f"Step '{step.name}' has no plugin.",
            )

        if not self._plugins.exists(
            step.plugin,
        ):

            raise InvalidWorkflowError(
                f"Plugin '{step.plugin}' is not installed.",
            )
