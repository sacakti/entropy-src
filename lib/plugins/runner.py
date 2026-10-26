"""
Plugin runner.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from lib.models.plugin import PluginResult
from lib.plugins.contract import (
    ContractError,
    check_arguments,
    check_outputs,
    declared,
    read_manifest,
)
from lib.plugins.exceptions import (
    PluginDisabledError,
    PluginExecutionError,
    PluginValueError,
)

from .context import PluginContext
from .loader import PluginLoader
from .mode import PluginMode

if TYPE_CHECKING:
    from core.runtime.context import ExecutionContext
    from lib.plugins.base import BasePlugin


class PluginRunner:
    """
    Loads and executes plugins.
    """

    def __init__(
        self,
        loader: PluginLoader,
    ) -> None:

        self._loader = loader

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        context: ExecutionContext,
        qualified_name: str,
        mode: PluginMode = PluginMode.WORKFLOW,
    ) -> PluginResult:
        """
        Load and execute a plugin.
        """

        plugin = self._create_plugin(
            context=context,
            qualified_name=qualified_name,
            mode=mode,
        )

        if mode is PluginMode.CLI:

            context.start_plugin_scope(
                qualified_name,
            )

        try:

            from lib.git_repositories.store import checkout_assigned_repositories

            context.repositories.update(
                checkout_assigned_repositories(context, qualified_name)
            )

            result = self._lifecycle(
                plugin,
                qualified_name,
            )

            self._capture_artifacts(context, plugin, qualified_name)

        except Exception:

            if mode is PluginMode.CLI:

                context.finish_plugin_scope(
                    success=False,
                )

            raise

        else:

            if mode is PluginMode.CLI:

                context.finish_plugin_scope(
                    success=True,
                )

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _lifecycle(
        plugin: BasePlugin,
        name: str,
    ) -> PluginResult:
        """
        validate -> prepare -> execute -> cleanup (always), then check the
        result and that its outputs are declared.
        """

        contract = getattr(
            plugin,
            "_entropy_contract",
            None,
        )

        try:

            plugin.validate()

            plugin.prepare()

            result = plugin.execute()

        finally:

            plugin.cleanup()

        if not isinstance(
            result,
            PluginResult,
        ):

            raise PluginExecutionError(
                f"Plugin '{name}' returned "
                f"'{type(result).__name__}', "
                "expected PluginResult.",
            )

        if contract is not None:

            problems = check_outputs(
                contract,
                dict(result.outputs or {}),
            )

            if problems:

                raise PluginExecutionError(
                    f"Plugin '{name}': " + "; ".join(problems) + ".",
                )

        return result

    @staticmethod
    def _contract_arguments(
        context: ExecutionContext,
        directory: Path,
        name: str,
    ) -> tuple:
        """
        (contract, checked arguments) when the plugin declares a contract;
        (None, None) for plugins that predate contracts.
        """

        try:

            contract = declared(
                read_manifest(
                    directory,
                ),
            )

        except ContractError as exc:

            raise PluginExecutionError(
                f"Plugin '{name}' has an invalid contract in plugin.json: {exc}",
            ) from None

        if contract is None:

            return None, None

        try:

            arguments = check_arguments(
                contract,
                dict(context.arguments or {}),
            )

        except ContractError as exc:

            raise PluginValueError(
                f"Plugin '{name}': {exc}.",
            ) from None

        return contract, arguments

    def _create_context(
        self,
        context: ExecutionContext,
        mode: PluginMode,
        arguments: dict | None = None,
    ) -> PluginContext:
        """
        Create the public plugin context.
        """

        return PluginContext(
            context=context,
            mode=mode,
            arguments=arguments,
        )

    def _instantiate(
        self,
        plugin_class: type,
        context: ExecutionContext,
        mode: PluginMode,
        directory: Path,
        name: str,
    ) -> BasePlugin:
        """A plugin instance with its arguments checked against its contract."""

        contract, arguments = self._contract_arguments(
            context,
            directory,
            name,
        )

        plugin = plugin_class(
            self._create_context(
                context=context,
                mode=mode,
                arguments=arguments,
            ),
        )

        plugin._entropy_contract = contract

        return plugin

    def _create_plugin(
        self,
        context: ExecutionContext,
        qualified_name: str,
        mode: PluginMode,
    ) -> BasePlugin:
        """
        Load and instantiate a plugin.
        """

        plugin = self._loader.get(
            qualified_name,
        )

        if not plugin.enabled:

            raise PluginDisabledError(
                qualified_name,
            )

        plugin_class = self._loader.load(
            qualified_name,
        )

        return self._instantiate(
            plugin_class,
            context,
            mode,
            plugin.path,
            qualified_name,
        )

    def execute_local(
        self,
        context: ExecutionContext,
        directory: Path,
        mode: PluginMode = PluginMode.CLI,
    ) -> PluginResult:
        """
        Load and execute a plugin from a local directory.
        """

        plugin_class = self._loader.load_local(
            directory,
        )

        plugin = self._instantiate(
            plugin_class,
            context,
            mode,
            directory,
            str(directory),
        )

        identifier = str(
            directory,
        )

        if mode is PluginMode.CLI:

            context.start_plugin_scope(
                identifier,
            )

        try:

            from lib.git_repositories.store import checkout_assigned_repositories

            context.repositories.update(
                checkout_assigned_repositories(context, identifier)
            )

            result = self._lifecycle(
                plugin,
                str(directory),
            )

            self._capture_artifacts(context, plugin, identifier)

        except Exception:

            if mode is PluginMode.CLI:

                context.finish_plugin_scope(
                    success=False,
                )

            raise

        else:

            if mode is PluginMode.CLI:

                context.finish_plugin_scope(
                    success=True,
                )

        return result

    @staticmethod
    def _capture_artifacts(context: ExecutionContext, plugin: BasePlugin, origin: str) -> None:
        """Expose plugin artifacts to the runtime and register existing files."""
        produced = dict(plugin.artifacts)
        context.artifacts.update(produced)
        if not produced:
            return

        # Artifact inventory is an optional integration: a bad/missing output
        # should be visible in the run log without turning a successful plugin
        # execution into a failure.
        try:
            from lib.artifacts.store import ArtifactStore, ensure_artifacts_schema
            from lib.authorization.projects import default_project_id
            from lib.vault.projects import run_project
            import hashlib
            import json

            connection = context.database.connection
            ensure_artifacts_schema(connection)
            project_id = run_project() or default_project_id(connection)
            store = ArtifactStore(connection)
            run_id = context.execution.id
            run_tag = "run:" + hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:16]
            for name, raw_path in produced.items():
                path = Path(raw_path).expanduser()
                if not path.is_absolute():
                    path = context.workspace / path
                path = path.resolve(strict=True)
                if not path.is_file():
                    continue
                store.create(
                    project_id,
                    path.name or str(name),
                    "server_path",
                    path.stat().st_size,
                    context.user,
                    server_path=str(path),
                    tags=json.dumps([run_tag]),
                    classification="generated",
                    origin=origin,
                    run_id=run_id,
                )
        except Exception as error:
            context.logger.warning("plugin", f"Unable to register generated artifacts: {error}")
