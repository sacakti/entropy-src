"""
Plugin discovery.
"""

from __future__ import annotations

from core.context import EntropyContext

from .registry import PluginRegistry
from .validators.manifest import ManifestValidator


class PluginDiscovery:
    """
    Discovers plugins on disk.
    """

    def __init__(
        self,
        context: EntropyContext,
        registry: PluginRegistry,
    ) -> None:

        self._context = context

        self._registry = registry

        self._validator = ManifestValidator()

    # ------------------------------------------------------------------

    def discover(
        self,
    ) -> None:

        assert self._context.bootstrap is not None

        root = self._context.bootstrap.resources.plugins

        if not root.exists():

            return

        for namespace in root.iterdir():

            if not namespace.is_dir():

                continue

            for directory in namespace.iterdir():

                if not directory.is_dir():

                    continue

                metadata = self._validator.validate(
                    namespace.name,
                    directory,
                )

                self._registry.register(
                    metadata,
                )
