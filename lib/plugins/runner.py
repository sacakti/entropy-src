"""
Plugin runner.
"""

from __future__ import annotations

from .loader import PluginLoader


class PluginRunner:
    """
    Executes loaded plugins.
    """

    def __init__(
        self,
        loader: PluginLoader,
    ) -> None:

        self._loader = loader

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def run(
        self,
        qualified_name: str,
        arguments: dict[str, object],
    ) -> None:
        """
        Execute a plugin.
        """

        plugin = self._loader.load(
            qualified_name,
        )

        plugin.execute(
            **arguments,
        )
