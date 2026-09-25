"""
Workflow execution context.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from core.models.runtime import RuntimeNodeType
from core.observability.emitter import Emitter
from core.runtime.ui import ExecutionUI
from lib.models.plugin import PluginResult

from .activity import Activity
from .execution import WorkflowExecution
from .stage import Stage
from .step import StepScope
from .tree import RuntimeTree
from .workflow import WorkflowScope

if TYPE_CHECKING:

    from core.configuration.manager import ConfigurationManager
    from core.context import EntropyContext
    from core.observability.logging import ExecutionLogger
    from core.runtime.node import RuntimeNode
    from core.template.engine import TemplateEngine
    from lib.database.manager import DatabaseManager
    from lib.executor import LinuxExecutor


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
        user: str,
    ) -> None:

        #
        # Application
        #

        self._entropy = entropy

        self._user = user

        #
        # Execution
        #

        self._workspace = workspace

        self._tree = RuntimeTree()

        self._execution: WorkflowExecution | None = None

        self.job_id: int | None = None

        #
        # Runtime State
        #

        self.variables: dict[str, Any] = {}

        self.arguments: dict[str, Any] = {}

        self.outputs: dict[str, Any] = {}

        self.artifacts: dict[str, Path] = {}

        self._step_results: dict[str, PluginResult] = {}

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
        *,
        execution_id: str | None = None,
    ) -> None:
        """
        Initialize a workflow execution.
        """

        self._execution = WorkflowExecution(
            id=execution_id or uuid4().hex,
            workflow=workflow,
            context=self,
        )

        self.set_variables(
            workflow.variables,
        )

        self.arguments.clear()

        self.outputs.clear()

        self.artifacts.clear()

        self._step_results.clear()

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
        plugin: str | None = None,
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
                "plugin": plugin,
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
    def logger(
        self,
    ) -> ExecutionLogger:
        """
        Return the logger for the current workflow execution.
        """

        assert self._entropy.logging is not None

        return self._entropy.logging.logger(
            self._workspace / "workflow.log",
        )

    @property
    def configuration(self) -> ConfigurationManager:

        assert self._entropy.configuration is not None

        return self._entropy.configuration

    @property
    def executor(self) -> LinuxExecutor:

        assert self._entropy.executor is not None

        return self._entropy.executor

    @property
    def template(self) -> TemplateEngine:

        assert self._entropy.template is not None

        return self._entropy.template

    @property
    def database(self) -> DatabaseManager:

        assert self._entropy.database_manager is not None

        return self._entropy.database_manager

    @property
    def ui(self) -> ExecutionUI:
        """
        Workflow execution UI.
        """

        assert self._entropy.ui is not None

        return ExecutionUI(
            ui=self._entropy.ui,
            context=self,
        )

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    @property
    def user(self) -> str:
        """
        Return the user who initiated this execution.
        """

        return self._user

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

    def set_step_result(
        self,
        step_name: str,
        result: PluginResult,
    ) -> None:
        """
        Store the result produced by a workflow step.
        """

        self.step_results[step_name] = result

    def get_step_result(
        self,
        step_name: str,
    ) -> PluginResult | None:
        """
        Return a previously stored step result.
        """

        return self.step_results.get(
            step_name,
        )

    @property
    def step_results(
        self,
    ) -> dict[str, PluginResult]:
        """
        Return results produced by workflow steps.
        """

        return self._step_results

    # Standalone plugin run
    def start_plugin(
        self,
        *,
        execution_id: str,
        arguments: dict[str, Any] | None = None,
        variables: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize runtime state for standalone plugin execution.
        """

        self._execution = WorkflowExecution(
            id=execution_id,
            workflow=None,
            context=self,
        )

        self.job_id = None

        self.set_variables(
            variables or {},
        )

        self.set_arguments(
            arguments or {},
        )

        self.outputs.clear()

        self.artifacts.clear()

        self._step_results.clear()

        self.execution.start()

    def start_plugin_scope(
        self,
        name: str,
    ) -> None:
        """
        Enter the runtime root for standalone plugin execution.
        """

        self.enter(
            type=RuntimeNodeType.WORKFLOW,
            name=name,
            metadata={
                "mode": "plugin",
            },
        )

        assert self.node is not None

        self.node.start()

    def finish_plugin_scope(
        self,
        *,
        success: bool,
    ) -> None:
        """
        Finish the runtime root for standalone plugin execution.
        """

        node = self.node

        assert node is not None

        if success:
            node.complete()
        else:
            node.fail()

        self.leave()

    @property
    def session_directory(self) -> Path:
        """
        Return the Entropy session directory.
        """

        return self._entropy.paths.session.directory

    @property
    def formatter(self):
        """
        Document formatting service.
        """

        assert self._entropy.formatter is not None

        return self._entropy.formatter

    @property
    def structures(self):

        return self._entropy.bootstrap.resources.structures

    @property
    def normalizer(self):

        assert self._entropy.normalizer is not None

        return self._entropy.normalizer
