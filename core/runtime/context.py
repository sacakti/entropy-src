"""
Workflow execution context.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.context import EntropyContext
from core.observability.emitter import Emitter

from .tree import RuntimeTree

if TYPE_CHECKING:
    from core.observability.logging.manager import ExecutionLogManager

    from .activity import Activity
    from .execution import WorkflowExecution
    from .node import RuntimeNode
    from .stage import Stage


class ExecutionContext:
    """
    Runtime context passed to every plugin.

    Exposes runtime services but contains no business logic.
    """

    def __init__(
        self,
        entropy: EntropyContext,
        workspace: Path,
    ) -> None:

        self._entropy = entropy

        self._workspace = workspace

        self._tree = RuntimeTree()

        self._execution: WorkflowExecution | None = None

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------

    @property
    def execution(self) -> WorkflowExecution:

        assert self._execution is not None

        return self._execution

    @execution.setter
    def execution(
        self,
        execution: WorkflowExecution,
    ) -> None:

        self._execution = execution

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
    # Observability
    # ------------------------------------------------------------------

    @property
    def logger(self) -> ExecutionLogManager:

        assert self._entropy.logger is not None

        return self._entropy.logger

    def emitter(
        self,
        source: str,
    ) -> Emitter:

        assert self._entropy.observability is not None

        return self._entropy.observability.emitter(source)

    # ------------------------------------------------------------------
    # Runtime Scopes
    # ------------------------------------------------------------------

    def stage(
        self,
        *,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> Stage:

        from .stage import Stage

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

        from .activity import Activity

        return Activity(
            context=self,
            name=name,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Runtime Services
    # ------------------------------------------------------------------

    @property
    def configuration(self):

        return self._entropy.configuration

    @property
    def variables(self):

        return self._entropy.variable_manager

    @property
    def secrets(self):

        return self._entropy.secret_manager

    @property
    def executor(self):

        return self._entropy.executor

    @property
    def template(self):

        return self._entropy.template

    @property
    def database(self):

        return self._entropy.database_manager

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    @property
    def user(self):

        assert self._entropy.session_manager is not None

        return self._entropy.session_manager.require().username
