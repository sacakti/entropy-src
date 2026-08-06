"""
Workflow execution context.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from core.models.runtime import RuntimeNodeType
from core.observability.emitter import Emitter

from .execution import WorkflowExecution
from .activity import Activity
from .stage import Stage
from .step import StepScope
from .tree import RuntimeTree
from .workflow import WorkflowScope

if TYPE_CHECKING:
    from core.context import EntropyContext
    from core.observability.logging.manager import ExecutionLogManager

    from .node import RuntimeNode


class ExecutionContext:
    """
    Runtime context passed to every plugin.

    Owns all execution state while exposing application
    services from the Entropy context.
    """

    def __init__(
        self,
        entropy: EntropyContext,
        workspace: Path,
    ) -> None:

        #
        # Application
        #

        self._entropy = entropy

        #
        # Execution
        #

        self._workspace = workspace

        self._tree = RuntimeTree()

        self._execution: WorkflowExecution | None = None

        #
        # Runtime State
        #

        self.variables: dict[str, Any] = {}

        self.arguments: dict[str, Any] = {}

        self.outputs: dict[str, Any] = {}

        self.artifacts: dict[str, Path] = {}

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    @property
    def execution(self) -> WorkflowExecution:

        assert self._execution is not None

        return self._execution

    def start(
        self,
        workflow,
    ) -> None:
        """
        Initialize a workflow execution.
        """

        self._execution = WorkflowExecution(
            id=uuid4().hex,
            workflow=workflow,
            context=self,
        )

        self.set_variables(
            workflow.variables,
        )

        self.arguments.clear()

        self.outputs.clear()

        self.artifacts.clear()

    @property
    def workspace(self) -> Path:

        return self._workspace

    @property
    def tree(self) -> RuntimeTree:

        return self._tree

    @property
    def node(self) -> RuntimeNode | None:

        return self._tree.current

    # ------------------------------------------------------------------
    # Runtime State
    # ------------------------------------------------------------------

    def set_variables(
        self,
        variables: dict[str, Any],
    ) -> None:
        """
        Replace runtime variables.
        """

        self.variables.clear()

        self.variables.update(
            variables,
        )

    def set_arguments(
        self,
        arguments: dict[str, Any],
    ) -> None:
        """
        Replace step arguments.
        """

        self.arguments.clear()

        self.arguments.update(
            arguments,
        )

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    # @property
    # def logger(self) -> ExecutionLogManager:

    #     assert self._entropy.logger is not None

    #     return self._entropy.logger

    def emitter(
        self,
        source: str,
    ) -> Emitter:

        assert self._entropy.observability is not None

        return self._entropy.observability.emitter(
            source,
        )

    # ------------------------------------------------------------------
    # Runtime Scopes
    # ------------------------------------------------------------------

    def workflow(
        self,
        name: str,
    ) -> WorkflowScope:
        """
        Create a workflow scope.
        """

        return WorkflowScope(
            context=self,
            name=name,
        )

    def step(
        self,
        name: str,
        *,
        index: int,
        total: int,
    ) -> StepScope:
        """
        Create a workflow step scope.
        """

        return StepScope(
            context=self,
            name=name,
            metadata={
                "index": index,
                "total": total,
            },
        )

    def stage(
        self,
        *,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> Stage:
        """
        Create a stage scope.
        """

        return Stage(
            context=self,
            name=name,
            metadata=metadata,
        )

    def activity(
        self,
        *,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> Activity:
        """
        Create an activity scope.
        """

        return Activity(
            context=self,
            name=name,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Application Services
    # ------------------------------------------------------------------

    @property
    def configuration(self):

        return self._entropy.configuration

    @property
    def executor(self):

        return self._entropy.executor

    @property
    def template(self):

        return self._entropy.template

    @property
    def database(self):

        return self._entropy.database_manager

    @property
    def ui(self):

        assert self._entropy.ui is not None

        return self._entropy.ui

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    @property
    def user(self):

        assert self._entropy.session_manager is not None

        return self._entropy.session_manager.require().username

    #
    #
    #

    def enter(
        self,
        *,
        type: RuntimeNodeType,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeNode:
        """
        Enter a runtime node.
        """

        return self._tree.enter(
            type=type,
            name=name,
            metadata=metadata,
        )


    def leave(
        self,
    ) -> None:
        """
        Leave the current runtime node.
        """

        self._tree.leave()
