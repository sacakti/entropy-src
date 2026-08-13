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
