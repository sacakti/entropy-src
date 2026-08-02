"""
Workflow execution manager.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from core.context import EntropyContext

from .context import ExecutionContext
from .execution import WorkflowExecution


class ExecutionManager:
    """
    Creates workflow execution environments.

    This class does not execute workflows.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        self._context = context

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def create(
        self,
        workflow: Any,
    ) -> WorkflowExecution:
        """
        Create a new workflow execution.
        """

        execution_id = self._execution_id(
            workflow,
        )

        workspace = self._workspace(
            execution_id,
        )

        self._prepare(
            workspace,
        )

        runtime = ExecutionContext(
            entropy=self._context,
            workspace=workspace,
        )

        execution = WorkflowExecution(
            id=execution_id,
            workflow=workflow,
            context=runtime,
        )

        runtime.execution = execution

        return execution

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _execution_id(
        self,
        workflow: Any,
    ) -> str:
        """
        Generate a workflow execution id.

        Example

            deploy_database_20260802_143215
        """

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        name = getattr(
            workflow,
            "name",
            "workflow",
        )

        name = str(name).strip().lower().replace(" ", "_")

        return f"{name}_{timestamp}"

    def _workspace(
        self,
        execution_id: str,
    ) -> Path:

        assert self._context.paths is not None

        return self._context.paths.logs.workflows / execution_id

    def _prepare(
        self,
        workspace: Path,
    ) -> None:

        assert self._context.executor is not None

        self._context.executor.mkdir(
            workspace,
        )
