"""
JSON formatter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lib.formatter.base import BaseFormatter
from lib.formatter.exceptions import FormatterFormatError

if TYPE_CHECKING:

    from lib.executor import LinuxExecutor


class JsonFormatter(
    BaseFormatter,
):
    """
    Format JSON documents using Entropy's executor APIs.
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

        return "json"

    # ------------------------------------------------------------------
    # Parse
    # ------------------------------------------------------------------

    def parse(
        self,
        content: str,
    ) -> Any:
        """
        Parse JSON content.
        """

        if not content.strip():

            raise FormatterFormatError(
                "Invalid JSON: document is empty.",
            )

        try:

            return self._executor.parse_json(
                content,
            )

        except Exception as exc:

            raise FormatterFormatError(
                f"Invalid JSON: {exc}",
            ) from exc

    # ------------------------------------------------------------------
    # Serialize
    # ------------------------------------------------------------------

    def serialize(
        self,
        value: Any,
    ) -> str:
        """
        Serialize a Python value as JSON.
        """

        try:

            formatted = self._executor.serialize_json(
                value,
                indent=4,
                sort_keys=False,
            )

        except Exception as exc:

            raise FormatterFormatError(
                f"Unable to serialize JSON: {exc}",
            ) from exc

        return formatted.rstrip() + "\n"

    # ------------------------------------------------------------------
    # Format
    # ------------------------------------------------------------------

    def format(
        self,
        content: str,
    ) -> str:
        """
        Parse and serialize JSON.
        """

        return self.serialize(
            self.parse(
                content,
            ),
        )
