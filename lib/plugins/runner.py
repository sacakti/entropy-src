"""
Plugin runner.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from lib.models.plugin import PluginResult
from lib.plugins.exceptions import PluginDisabledError, PluginExecutionError

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

            result = plugin.execute()

            if not isinstance(
                result,
                PluginResult,
            ):
                raise PluginExecutionError(
                    f"Plugin '{qualified_name}' returned "
                    f"'{type(result).__name__}', "
                    "expected PluginResult.",
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

    def _create_context(
        self,
        context: ExecutionContext,
        mode: PluginMode,
    ) -> PluginContext:
        """
        Create the public plugin context.
        """

        return PluginContext(
            context=context,
            mode=mode,
        )

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

        return plugin_class(
            self._create_context(
                context=context,
                mode=mode,
            ),
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

        plugin = plugin_class(
            self._create_context(
                context=context,
                mode=mode,
            ),
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

            result = plugin.execute()

            if not isinstance(
                result,
                PluginResult,
            ):

                raise PluginExecutionError(
                    f"Local plugin '{directory}' returned "
                    f"'{type(result).__name__}', "
                    "expected PluginResult.",
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
