"""
Workflow execution manager.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

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

        runtime.start(
            workflow,
            execution_id=execution_id,
        )

        execution = runtime.execution

        execution.id = execution_id

        return execution

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _execution_id(
        self,
        workflow: Any,
    ) -> str:
        """
        Generate a unique workflow execution ID.

        Example

            deploy_database_20260809_153723_a81f4c2e
        """

        name = getattr(
            workflow,
            "name",
            "workflow",
        )

        name = (
            str(
                name,
            )
            .strip()
            .lower()
            .replace(
                " ",
                "_",
            )
        )

        suffix = uuid4().hex[:8]

        return f"{name}_{suffix}"

    def _workspace(
        self,
        execution_id: str,
    ) -> Path:

        assert self._context.paths is not None

        return self._context.paths.workspace.executions / execution_id

    def _prepare(
        self,
        workspace: Path,
    ) -> None:

        assert self._context.executor is not None

        self._context.executor.mkdir(
            workspace,
        )
