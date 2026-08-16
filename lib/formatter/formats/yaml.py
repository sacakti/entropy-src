"""
YAML formatter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lib.formatter.base import BaseFormatter
from lib.formatter.exceptions import FormatterFormatError

if TYPE_CHECKING:

    from lib.executor import LinuxExecutor


class YamlFormatter(
    BaseFormatter,
):
    """
    Format YAML documents using Entropy's executor YAML APIs.
    """

    def __init__(
        self,
        executor: LinuxExecutor,
    ) -> None:

        self._executor = executor

    @property
    def name(
        self,
    ) -> str:

        return "yaml"

    @property
    def aliases(
        self,
    ) -> tuple[str, ...]:

        return (
            "yml",
        )

    # ------------------------------------------------------------------
    # Parse
    # ------------------------------------------------------------------

    def parse(
        self,
        content: str,
    ) -> Any:
        """
        Parse YAML content.
        """

        if not content.strip():

            raise FormatterFormatError(
                "Invalid YAML: document is empty.",
            )

        try:

            document = self._executor.parse_yaml(
                content,
            )

        except Exception as exc:

            raise FormatterFormatError(
                f"Invalid YAML: {exc}",
            ) from exc

        if document is None:

            raise FormatterFormatError(
                "Invalid YAML: document does not contain "
                "a YAML value.",
            )

        return document

    # ------------------------------------------------------------------
    # Serialize
    # ------------------------------------------------------------------

    def serialize(
        self,
        value: Any,
    ) -> str:
        """
        Serialize a Python value as YAML.
        """

        try:

            formatted = self._executor.serialize_yaml(
                value,
            )

        except Exception as exc:

            raise FormatterFormatError(
                f"Unable to serialize YAML: {exc}",
            ) from exc

        if not formatted.strip():

            raise FormatterFormatError(
                "Unable to serialize YAML: formatter produced "
                "an empty document.",
            )

        return formatted

    # ------------------------------------------------------------------
    # Format
    # ------------------------------------------------------------------

    def format(
        self,
        content: str,
    ) -> str:
        """
        Parse and serialize YAML.
        """

        document = self.parse(
            content,
        )

        return self.serialize(
            document,
        )
