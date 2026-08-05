"""
Plugin runner.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .loader import PluginLoader

if TYPE_CHECKING:
    from core.runtime.context import ExecutionContext


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
    ) -> None:
        """
        Load and execute a plugin.
        """

        plugin_class = self._loader.load(
            qualified_name,
        )

        plugin = plugin_class(
            context,
        )

        plugin.execute()
