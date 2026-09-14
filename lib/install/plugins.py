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
        Install all built-in plugins shipped with Entropy.
        """

        root = self._bootstrap.resources.plugins / "builtin"

        if not root.is_dir():

            raise RuntimeError(
                f"Built-in plugin directory not found: {root}",
            )

        plugins = sorted(
            path for path in root.iterdir() if path.is_dir() and not path.name.startswith(".")
        )

        for source in plugins:

            self._plugins.install(
                source,
            )
