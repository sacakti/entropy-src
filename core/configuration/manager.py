"""
Configuration manager.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

# from core.context import EntropyContext
from .configuration import Configuration
from .exceptions import ConfigurationNotLoadedError
from .loader import ConfigurationLoader
from .parser import ConfigurationParser
from .resolver import ConfigurationResolver
from .validator import ConfigurationValidator

if TYPE_CHECKING:
    from core.context import EntropyContext


class ConfigurationManager:
    """
    Application configuration manager.

    Responsible for the complete configuration lifecycle.

        Load
            ↓
        Parse
            ↓
        Resolve
            ↓
        Validate
            ↓
        Configuration
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        self._context = context

        assert context.executor is not None

        self._loader = ConfigurationLoader(
            context.executor,
        )

        self._parser = ConfigurationParser(
            context.executor,
        )

        self._resolver = ConfigurationResolver()

        self._validator = ConfigurationValidator()

        self._configuration: Configuration | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def file(self) -> Path:

        assert self._context.bootstrap is not None

        return self._context.bootstrap.configuration.file

    @property
    def loaded(self) -> bool:

        return self._configuration is not None

    @property
    def configuration(self) -> Configuration:

        if self._configuration is None:

            raise ConfigurationNotLoadedError()

        return self._configuration

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def load(self) -> Configuration:
        """
        Load application configuration.
        """

        data = self._parser.read(
            self.file,
        )

        data = self._resolver.resolve(
            data,
        )

        self._validator.validate(
            data,
        )

        self._configuration = Configuration(
            data,
        )

        return self._configuration

    def reload(self) -> Configuration:
        """
        Reload configuration from disk.
        """

        self._configuration = None

        return self.load()

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(
        self,
        path: str,
        default=None,
    ):

        return self.configuration.get(
            path,
            default,
        )
