"""
Configuration loader.
"""

from __future__ import annotations

from pathlib import Path

from lib.executor import LinuxExecutor

from .exceptions import ConfigurationFileNotFoundError


class ConfigurationLoader:
    """
    Loads configuration documents from disk.
    """

    def __init__(
        self,
        executor: LinuxExecutor,
    ) -> None:

        self._executor = executor

    def load(
        self,
        file: Path,
    ) -> str:
        """
        Load configuration file contents.
        """

        if not self._executor.exists(file):

            raise ConfigurationFileNotFoundError(
                file,
            )

        return self._executor.read_text(
            file,
        )
