"""
Default plugin installation.
"""

from __future__ import annotations

from core.context import EntropyContext


class DefaultPluginInstaller:
    """
    Installs plugins shipped with Entropy.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        assert context.bootstrap is not None
        assert context.plugin_manager is not None

        self._context = context
        self._bootstrap = context.bootstrap
        self._plugins = context.plugin_manager

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def install(self) -> None:
        """
        Install Entropy's default plugins.
        """

        plugins = (
            "hello",
            "shell",
        )

        for name in plugins:

            source = self._bootstrap.resources.plugins / "builtin" / name

            self._plugins.install(
                source,
            )
