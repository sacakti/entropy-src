"""
Base plugin.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Sequence

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
    def repositories(self):
        """Git repositories assigned to this workflow/plugin execution."""
        return self._context.repositories

    @property
    def workspace(
        self,
    ):
        """
        Workflow workspace.
        """

        return self._context.workspace

    def git_repository(
        self,
        name: str,
    ):
        """
        Check out a repository from Tools -> Git repositories (by name or
        id) into the run's workspace and return its path. Pushes from it go
        back to the managed repository.
        """

        return self._context.git_repository(
            name,
        )

    def vault(
        self,
        reference: str,
    ) -> Any:
        """
        Read a vault value ("namespace/key") with the run user's vault
        access, for example SFTP credentials stored as a JSON object:
        `sftp = self.vault("prod/sftp")` gives {"host": ..., "port": ...}.
        Prefer taking it as an argument (`${entv:prod/sftp}`) so the
        workflow decides which entry is used.
        """

        return self._context.vault(
            reference,
        )

    def ask(
        self,
        label: str,
        *,
        name: Optional[str] = None,
        secret: bool = False,
        default: Optional[str] = None,
        description: str = "",
        choices: Optional[Sequence[str]] = None,
    ) -> str:
        """
        Ask the user for a value at run time (interactive runs), for
        example a one-time code or a confirmation. `secret` hides what is
        typed and keeps it out of logs. Automated runs get `default`, or
        fail when there is none.
        """

        return self._context.ask(
            label,
            name=name,
            secret=secret,
            default=default,
            description=description,
            choices=choices,
        )

    @property
    def data_directory(self) -> Path:
        """
        The plugin's own folder, kept between runs and upgrades (one per
        project); the run workspace is temporary.
        """

        return self._context.data_directory

    @property
    def can_ask(self) -> bool:
        """
        True when ask() reaches a person (`ent` in a terminal, or an
        interactive run); otherwise ask() returns its default.
        """

        return self._context.can_ask

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

    @property
    def normalizer(self):
        return self._context.normalizer

    @property
    def structures(self):
        return self._context.structures

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

    # ------------------------------------------------------------------
    # Lifecycle: validate -> prepare -> execute -> cleanup
    #
    # Entropy checks the arguments against plugin.json before validate();
    # cleanup() runs whether execute() succeeded or not. Only execute() is
    # required.
    # ------------------------------------------------------------------

    def validate(
        self,
    ) -> None:
        """
        Check the arguments beyond their declared types (e.g. one of two
        given); raise PluginValueError to stop before anything happens.
        """

    def prepare(
        self,
    ) -> None:
        """
        Set up what execute() needs (connections, working folders).
        """

    @abstractmethod
    def execute(
        self,
    ) -> PluginResult:
        """
        Execute the plugin and return its result.
        """

        raise NotImplementedError()

    def cleanup(
        self,
    ) -> None:
        """
        Release what prepare() and execute() set up; always runs.
        """
