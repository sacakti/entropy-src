"""
Plugin execution context.

Provides the public SDK exposed to plugins.

This class wraps the internal ExecutionContext and exposes only
stable, supported APIs for plugin authors.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from lib.plugins.message import PluginMessage
from lib.plugins.ui import PluginUI
from lib.plugins.arguments import PluginArguments

if TYPE_CHECKING:
    from core.observability.emitter import Emitter
    from core.observability.logging import ExecutionLogger
    from core.runtime.context import ExecutionContext
    from lib.executor import LinuxExecutor
    from lib.plugins.mode import PluginMode

class PluginLog:
    """
    Workflow logger exposed to plugins.

    Plugin log messages are written directly to the
    current workflow execution log.
    """

    def __init__(
        self,
        logger: ExecutionLogger,
        module: str = "plugin",
    ) -> None:

        self._logger = logger
        self._module = module

    def debug(
        self,
        message: str,
    ) -> None:

        self._logger.debug(
            self._module,
            message,
        )

    def info(
        self,
        message: str,
    ) -> None:

        self._logger.info(
            self._module,
            message,
        )

    def warning(
        self,
        message: str,
    ) -> None:

        self._logger.warning(
            self._module,
            message,
        )

    def error(
        self,
        message: str,
    ) -> None:

        self._logger.error(
            self._module,
            message,
        )

    def critical(
        self,
        message: str,
    ) -> None:

        self._logger.critical(
            self._module,
            message,
        )

class PluginContext:
    """
    Public execution context available to plugins.

    This class intentionally hides runtime implementation details
    such as runtime scopes, execution tree, observability internals
    and workflow lifecycle management.
    """

    def __init__(
        self,
        context: ExecutionContext,
        mode: PluginMode,
    ) -> None:

        self._runtime = context

        self._mode = mode

        self._emitter: Emitter = context.emitter(
            "plugin",
        )

        self._ui = PluginUI(
            ui=context.ui,
        )

        self._message = PluginMessage(
            runtime=context,
            emitter=self._emitter,
        )

        self._arguments = PluginArguments(
            context.arguments,
        )

    # ------------------------------------------------------------------
    # Runtime State
    # ------------------------------------------------------------------

    @property
    def variables(
        self,
    ) -> dict[str, Any]:
        """
        Workflow variables.
        """

        return self._runtime.variables

    @property
    def arguments(
        self,
    ) -> PluginArguments:
        """
        Typed workflow arguments.
        """

        return self._arguments

    @property
    def outputs(
        self,
    ) -> dict[str, Any]:
        """
        Workflow outputs.
        """

        return self._runtime.outputs

    @property
    def artifacts(
        self,
    ) -> dict[str, Path]:
        """
        Workflow artifacts.
        """

        return self._runtime.artifacts

    @property
    def workspace(
        self,
    ) -> Path:
        """
        Workflow workspace.
        """

        return self._runtime.workspace

    # ------------------------------------------------------------------
    # Infrastructure
    # ------------------------------------------------------------------

    @property
    def path(
        self,
    ) -> LinuxExecutor:
        """
        """

        return self._runtime.executor

    @property
    def filesystem(
        self,
    ) -> LinuxExecutor:
        """
        Filesystem operations.
        """

        return self._runtime.executor

    @property
    def shell(
        self,
    ) -> LinuxExecutor:
        """
        Process execution.
        """

        return self._runtime.executor

    @property
    def archive(
        self,
    ) -> LinuxExecutor:
        """
        Archive operations.
        """

        return self._runtime.executor

    @property
    def environment(
        self,
    ) -> LinuxExecutor:
        """
        Environment operations.
        """

        return self._runtime.executor

    @property
    def information(
        self,
    ) -> LinuxExecutor:
        """
        File information utilities.
        """

        return self._runtime.executor

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    @property
    def log(
        self,
    ) -> PluginLog:
        """
        Workflow execution logger exposed to plugins.

        Plugin log messages are written to workflow.log
        and are not rendered in the workflow execution UI.
        """

        return PluginLog(
            logger=self._runtime.logger,
            module="plugin",
        )

    @property
    def message(
        self,
    ) -> PluginMessage:
        """
        Runtime message API.
        """

        return self._message

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------

    @property
    def ui(
        self,
    ) -> PluginUI:
        """
        User interface.
        """

        return self._ui

    @property
    def configuration(
        self,
    ):
        """
        Configuration manager.
        """

        return self._runtime.configuration

    @property
    def database(
        self,
    ):
        """
        Database manager.
        """

        return self._runtime.database

    @property
    def template(
        self,
    ):
        """
        Template engine.
        """

        return self._runtime.template

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def user(
        self,
    ) -> str:
        """
        Current authenticated user.
        """

        return self._runtime.user

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------

    def activity(
        self,
        name: str,
        metadata: dict[str, Any] | None = None,
    ):
        """
        Create a plugin activity.

        Activities are rendered in the workflow UI and
        recorded in the execution log.
        """

        return self._runtime.activity(
            name=name,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Execution Mode
    # ------------------------------------------------------------------

    @property
    def mode(
        self,
    ) -> PluginMode:
        """
        Current execution mode.
        """

        return self._mode

    @property
    def interactive(
        self,
    ) -> bool:
        """
        True when running interactively.
        """

        return self._mode is PluginMode.CLI

    @property
    def automated(
        self,
    ) -> bool:
        """
        True when running from a workflow.
        """

        return self._mode is PluginMode.WORKFLOW
