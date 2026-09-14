"""
Normalization structure loader.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from lib.formatter.exceptions import (
    FormatterFileError,
    FormatterFormatError,
)

if TYPE_CHECKING:

    from lib.executor import LinuxExecutor


class StructureLoader:
    """
    Load YAML normalization structures using Entropy's
    executor APIs.
    """

    def __init__(
        self,
        executor: LinuxExecutor,
    ) -> None:

        self._executor = executor

    def load(
        self,
        path: Path,
    ) -> dict[str, Any]:
        """
        Load a normalization structure from YAML.
        """

        path = Path(
            path,
        )

        if not path.exists():

            raise FormatterFileError(
                f"Structure file '{path}' does not exist.",
            )

        if not path.is_file():

            raise FormatterFileError(
                f"Structure path '{path}' is not a file.",
            )

        try:

            content = path.read_text(
                encoding="utf-8",
            )

        except OSError as exc:

            raise FormatterFileError(
                f"Unable to read structure file '{path}': {exc}",
            ) from exc

        if not content.strip():

            return {}

        try:

            structure = self._executor.parse_yaml(
                content,
            )

        except Exception as exc:

            raise FormatterFormatError(
                f"Invalid structure YAML '{path}': {exc}",
            ) from exc

        if structure is None:

            return {}

        if not isinstance(
            structure,
            dict,
        ):

            raise FormatterFormatError(
                f"Structure file '{path}' must contain " "a YAML mapping.",
            )

        return dict(
            structure,
        )
