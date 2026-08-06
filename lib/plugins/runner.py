"""
Plugin runner.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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
    ) -> None:
        """
        Load and execute a plugin.
        """

        plugin = self._create_plugin(
            context=context,
            qualified_name=qualified_name,
            mode=mode,
        )

        plugin.execute()

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

        plugin_class = self._loader.load(
            qualified_name,
        )

        return plugin_class(
            self._create_context(
                context=context,
                mode=mode,
            ),
        )
