"""
Workflow execution manager.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from core.context import EntropyContext
from lib.workflow.workspace import WorkspaceTemplateResolver

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
        self._workspace_resolver = WorkspaceTemplateResolver()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def create(
        self,
        workflow: Any,
        *,
        variables: dict[str, Any] | None = None,
    ) -> WorkflowExecution:
        """
        Create a new workflow execution.
        """

        execution_id = self._execution_id(
            workflow,
        )

        workspace_name = self._workspace_name(
            workflow,
            execution_id,
            variables or {},
        )

        workspace = self._workspace(
            workspace_name,
        )

        self._prepare(
            workspace,
        )

        assert self._context.session_manager is not None

        session = self._context.session_manager.require()

        runtime = ExecutionContext(
            entropy=self._context,
            workspace=workspace,
            user=session.username,
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
        workspace_name: str,
    ) -> Path:

        assert self._context.paths is not None

        return self._context.paths.workspace.executions / workspace_name

    def _workspace_name(
        self,
        workflow: Any,
        execution_id: str,
        variables: dict[str, Any],
    ) -> str:
        """
        Resolve the physical workspace directory name.
        """

        workspace = getattr(
            workflow,
            "workspace",
            None,
        )

        if workspace is None or not workspace.add_text:
            return execution_id

        if workspace.name is None:
            return execution_id

        if workspace.type == "custom":
            text = workspace.name
        else:
            text = self._workspace_resolver.resolve(
                workspace.name,
                variables,
            )

        if workspace.position == "before":
            return f"{text}_{execution_id}"

        return f"{execution_id}_{text}"

    def _prepare(
        self,
        workspace: Path,
    ) -> None:

        assert self._context.executor is not None

        self._context.executor.mkdir(
            workspace,
        )

    def create_plugin(
        self,
        *,
        arguments: dict[str, Any] | None = None,
        variables: dict[str, Any] | None = None,
    ) -> ExecutionContext:
        """
        Create a runtime context for standalone plugin execution.
        """

        execution_id = f"plugin_{uuid4().hex[:8]}"

        workspace = self._workspace(
            execution_id,
        )

        self._prepare(
            workspace,
        )

        assert self._context.session_manager is not None

        session = self._context.session_manager.require()

        runtime = ExecutionContext(
            entropy=self._context,
            workspace=workspace,
            user=session.username,
        )

        runtime.start_plugin(
            arguments=arguments,
            variables=variables,
            execution_id=execution_id,
        )

        return runtime

    def _plugin_execution_id(
        self,
    ) -> str:
        """
        Generate a unique standalone plugin execution ID.
        """

        return f"plugin_{uuid4().hex[:8]}"

    def _plugin_workspace(
        self,
        execution_id: str,
    ) -> Path:
        """
        Return the workspace for standalone plugin execution.
        """

        assert self._context.paths is not None

        return self._context.paths.workspace.executions / execution_id
