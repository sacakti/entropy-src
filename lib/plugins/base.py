"""
Base plugin.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lib.models.plugin import PluginResult
from lib.plugins.arguments import PluginArguments

if TYPE_CHECKING:
    from .context import PluginContext


class BasePlugin(ABC):
    """
    Base class for all Entropy plugins.

    A plugin implements one unit of executable workflow behaviour.

    Plugins interact only with the public Plugin SDK.
    Runtime internals remain hidden.
    """

    def __init__(
        self,
        context: PluginContext,
    ) -> None:

        self._context = context

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------

    @property
    def context(
        self,
    ) -> PluginContext:
        """
        Public plugin context.
        """

        return self._context

    # ------------------------------------------------------------------
    # Execution Mode
    # ------------------------------------------------------------------

    @property
    def mode(
        self,
    ):
        """
        Current execution mode.
        """

        return self._context.mode

    @property
    def interactive(
        self,
    ) -> bool:
        """
        True when running interactively.
        """

        return self._context.interactive

    @property
    def automated(
        self,
    ) -> bool:
        """
        True when running from a workflow.
        """

        return self._context.automated

    # ------------------------------------------------------------------
    # Runtime State
    # ------------------------------------------------------------------

    @property
    def variables(
        self,
    ):
        """
        Workflow variables.
        """

        return self._context.variables

    @property
    def arguments(
        self,
    ) -> PluginArguments:
        """
        Typed step arguments.
        """

        return self._context.arguments

    @property
    def outputs(
        self,
    ):
        """
        Workflow outputs.
        """

        return self._context.outputs

    @property
    def artifacts(
        self,
    ):
        """
        Workflow artifacts.
        """

        return self._context.artifacts

    @property
    def workspace(
        self,
    ):
        """
        Workflow workspace.
        """

        return self._context.workspace

    # ------------------------------------------------------------------
    # Infrastructure
    # ------------------------------------------------------------------
    @property
    def path(
        self,
    ):
        """
        Return Path.
        """

        return self._context.path

    @property
    def filesystem(
        self,
    ):
        """
        Filesystem operations.
        """

        return self._context.filesystem

    @property
    def shell(
        self,
    ):
        """
        Process execution.
        """

        return self._context.shell

    @property
    def archive(
        self,
    ):
        """
        Archive operations.
        """

        return self._context.archive

    @property
    def environment(
        self,
    ):
        """
        Environment operations.
        """

        return self._context.environment

    @property
    def information(
        self,
    ):
        """
        File information utilities.
        """

        return self._context.information

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    @property
    def log(
        self,
    ):
        """
        Application logger.
        """

        return self._context.log

    @property
    def message(
        self,
    ):
        """
        Runtime messages.
        """

        return self._context.message

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------

    @property
    def ui(
        self,
    ):
        """
        User interface.
        """

        return self._context.ui

    @property
    def configuration(
        self,
    ):
        """
        Application configuration.
        """

        return self._context.configuration

    @property
    def template(
        self,
    ):
        """
        Template engine.
        """

        return self._context.template

    @property
    def database(
        self,
    ):
        """
        Database manager.
        """

        return self._context.database

    @property
    def user(
        self,
    ):
        """
        Current authenticated user.
        """

        return self._context.user

    @property
    def session_directory(self) -> Path:
        """
        Entropy session directory.
        """

        return self._context.session_directory

    @property
    def formatter(self):
        """
        Document formatting service.
        """

        return self._context.formatter

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------

    def activity(
        self,
        name: str,
        metadata: dict[str, Any] | None = None,
    ):
        """
        Create a workflow activity.
        """

        return self._context.activity(
            name=name,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    @abstractmethod
    def execute(
        self,
    ) -> PluginResult:
        """
        Execute the plugin and return its result.
        """

        raise NotImplementedError()
