"""
Normalization structure loader.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from lib.formatter.exceptions import (
    FormatterFileError,
    FormatterFormatError,
)


class StructureLoader:
    """
    Load YAML normalization structures.
    """

    def __init__(self) -> None:

        self._yaml = YAML(
            typ="safe",
        )

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

        try:

            structure = self._yaml.load(
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
                f"Structure file '{path}' must contain "
                "a YAML mapping.",
            )

        return dict(
            structure,
        )
