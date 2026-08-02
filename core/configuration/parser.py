"""
Configuration document parser.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lib.executor import LinuxExecutor

from .exceptions import (
    InvalidConfigurationError,
    UnsupportedConfigurationFormatError,
)


class ConfigurationParser:
    """
    Parses configuration documents.

    Delegates document parsing to the Executor.
    """

    def __init__(
        self,
        executor: LinuxExecutor,
    ) -> None:

        self._executor = executor

    # ------------------------------------------------------------------

    def read(
        self,
        file: Path,
    ) -> dict[str, Any]:
        """
        Parse a configuration document.
        """

        suffix = file.suffix.lower()

        try:

            if suffix == ".json":

                return self._executor.read_json(file)

            if suffix in (
                ".yaml",
                ".yml",
            ):

                return self._executor.read_yaml(file)

        except Exception as exc:

            raise InvalidConfigurationError(
                str(exc),
            ) from exc

        raise UnsupportedConfigurationFormatError(
            suffix,
        )

    # ------------------------------------------------------------------

    def write(
        self,
        file: Path,
        configuration: dict[str, Any],
    ) -> Path:
        """
        Write a configuration document.
        """

        suffix = file.suffix.lower()

        try:

            if suffix == ".json":

                return self._executor.write_json(
                    file,
                    configuration,
                )

            if suffix in (
                ".yaml",
                ".yml",
            ):

                return self._executor.write_yaml(
                    file,
                    configuration,
                )

        except Exception as exc:

            raise InvalidConfigurationError(
                str(exc),
            ) from exc

        raise UnsupportedConfigurationFormatError(
            suffix,
        )
