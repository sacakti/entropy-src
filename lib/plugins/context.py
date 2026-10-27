"""
Plugin execution context.

Provides the public SDK exposed to plugins.

This class wraps the internal ExecutionContext and exposes only
stable, supported APIs for plugin authors.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Sequence

from lib.plugins.arguments import PluginArguments
from lib.plugins.message import PluginMessage
from lib.plugins.mode import PluginMode
from lib.plugins.ui import PluginUI

if TYPE_CHECKING:
    from core.observability.emitter import Emitter
    from core.observability.logging import ExecutionLogger
    from core.runtime.context import ExecutionContext
    from lib.executor import LinuxExecutor


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
        arguments: dict[str, Any] | None = None,
        name: str | None = None,
    ) -> None:

        self._runtime = context

        self._mode = mode

        # Qualified name of the plugin (namespace.name), for its data folder.
        self._name = name

        self._outputs: dict[str, Any] = {}
        self._artifacts: dict[str, Path] = {}

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

        # Checked against the plugin's contract (defaults filled in) when it has one.
        self._arguments = PluginArguments(
            context.arguments if arguments is None else arguments,
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
        Outputs produced by the current plugin.
        """

        return self._outputs

    @property
    def artifacts(
        self,
    ) -> dict[str, Path]:
        """
        Artifacts produced by the current plugin.
        """

        return self._artifacts

    @property
    def repositories(self) -> dict[str, Path]:
        """Git repositories assigned to this workflow/plugin execution."""
        return self._runtime.repositories

    @property
    def workspace(
        self,
    ) -> Path:
        """
        Workflow workspace.
        """

        return self._runtime.workspace

    @property
    def data_directory(self) -> Path:
        """
        A folder of the plugin's own that is kept between runs and plugin
        upgrades (the run workspace is not): one per plugin and project,
        under <workspace>/plugin-data/<plugin>/project-<id>.
        """

        from lib.authorization.projects import default_project_id
        from lib.plugins.exceptions import PluginValueError
        from lib.vault.projects import run_project

        if not self._name:
            raise PluginValueError(
                "This plugin has no data folder (it was not started by Entropy)."
            )
        # Plugins run from a folder (`ent plugin run <dir>`) are named by it.
        name = self._name
        if "/" in name or "\\" in name:
            name = f"local.{Path(name).name}"
        root = Path(self._runtime._entropy.paths.workspace.root)
        project = run_project() or default_project_id(self._runtime.database.connection)
        path = root / "plugin-data" / name / f"project-{project}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ------------------------------------------------------------------
    # Git repositories
    # ------------------------------------------------------------------

    def git_repository(
        self,
        name: str,
    ) -> Path:
        """
        A working copy, in the run's workspace, of a repository from
        Tools -> Git repositories (by name or id) that the run's user may
        use: their own, or the project's. Its origin is that repository,
        so pushes go back to it.
        """

        from lib.git_repositories.store import checkout_repository
        from lib.plugins.exceptions import PluginValueError

        try:
            return checkout_repository(self._runtime, name)
        except RuntimeError as exc:
            raise PluginValueError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Vault
    # ------------------------------------------------------------------

    def vault(
        self,
        reference: str,
    ) -> Any:
        """
        A vault value, read with the access of the user the run belongs to:
        "namespace/key", "${environment}/key" style references are not
        resolved here (pass them as arguments instead). JSON objects stored
        in the vault arrive as dictionaries; "namespace/prefix*" returns
        every matching entry.
        """

        from lib.plugins.exceptions import PluginValueError
        from lib.workflow.exceptions import VariableNotFoundError
        from lib.workflow.variables.resolver import WorkflowVariableResolver

        text = str(reference or "").strip()
        if text.startswith("${entv:") and text.endswith("}"):
            text = text[len("${entv:") : -1]
        if "${" in text:
            raise PluginValueError(
                f"Vault reference '{reference}' must be 'namespace/key'.",
            )

        entropy = self._runtime._entropy
        if entropy.vault_manager is None or entropy.session_manager is None:
            raise PluginValueError("The vault is not available to this run.")
        session = entropy.session_manager.require()
        resolver = WorkflowVariableResolver(
            entropy.vault_manager,
            session.user_id,
            getattr(self._runtime, "secrets", None),
        )
        try:
            return resolver.resolve("${entv:" + text + "}", {})
        except VariableNotFoundError as exc:
            raise PluginValueError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

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
        Ask the user for a value while the plugin runs.

        Interactive runs show the question on the run screen and wait for
        the answer; `ent` asks in the terminal. Automated runs get
        `default`, or fail when there is none.
        """

        from lib.plugins.exceptions import PluginValueError
        from lib.runs.prompts import RUN_MODE_ENV, PromptError, prompts_for

        if self._mode is PluginMode.CLI and sys.stdin.isatty():
            hint = f" [{default}]" if default and not secret else ""
            if secret:
                import getpass

                answer = getpass.getpass(f"{label}: ")
            else:
                answer = input(f"{label}{hint}: ")
            return answer or default or ""

        if os.environ.get(RUN_MODE_ENV) != "interactive":
            if default is not None:
                return default
            raise PluginValueError(
                f"'{label}' needs an answer, but this run is automated. "
                "Start it in interactive mode, or give the value as an argument."
            )

        node = self._runtime.node
        store = prompts_for(self._runtime._entropy)
        prompt = store.ask(
            self._runtime.job_id,
            name=name or label,
            label=label,
            step=getattr(node, "name", None),
            description=description,
            secret=secret,
            default=default,
            choices=choices,
        )
        self._message.info(f"Waiting for an answer: {label}")
        try:
            answer = store.wait(prompt)
        except PromptError as exc:
            raise PluginValueError(f"'{label}': {exc}") from exc
        # A secret is never echoed.
        self._message.info(f"Answered: {label}" + ("" if secret else f" = {answer}"))
        return answer or (default or "")

    # ------------------------------------------------------------------
    # Infrastructure
    # ------------------------------------------------------------------

    @property
    def path(
        self,
    ) -> LinuxExecutor:
        """ """

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

    @property
    def can_ask(self) -> bool:
        """
        True when ask() reaches a person: `ent` in a terminal, or a run
        started in interactive mode. Otherwise ask() returns its default.
        """

        from lib.runs.prompts import RUN_MODE_ENV

        if self._mode is PluginMode.CLI and sys.stdin.isatty():
            return True
        return os.environ.get(RUN_MODE_ENV) == "interactive"

    @property
    def session_directory(self) -> Path:
        """
        Entropy session directory.
        """

        return self._runtime.session_directory

    @property
    def formatter(self):
        """
        Document formatting service.
        """

        return self._runtime.formatter

    @property
    def structures(self):
        """
        Entropy application resources.
        """

        return self._runtime.structures

    @property
    def normalizer(self):
        """
        Entropy application resources.
        """

        return self._runtime.normalizer
