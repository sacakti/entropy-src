"""
SQL formatter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lib.formatter.base import BaseFormatter
from lib.formatter.exceptions import FormatterFormatError

if TYPE_CHECKING:

    from lib.executor import LinuxExecutor


class SqlFormatter(
    BaseFormatter,
):
    """
    Format SQL documents using Entropy's executor APIs.
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

        return "sql"

    # ------------------------------------------------------------------
    # Parse
    # ------------------------------------------------------------------

    def parse(
        self,
        content: str,
    ) -> Any:
        """
        Validate SQL content.

        SQL does not have a structured parse API in the current
        formatter contract, so the source text itself is returned.
        """

        if not content.strip():

            return ""

        return content

    # ------------------------------------------------------------------
    # Serialize
    # ------------------------------------------------------------------

    def serialize(
        self,
        value: Any,
    ) -> str:
        """
        Format SQL text using the executor.
        """

        if not isinstance(
            value,
            str,
        ):

            raise FormatterFormatError(
                "SQL serialization requires a string value.",
            )

        if not value.strip():

            return ""

        try:

            return self._executor.format_sql(
                value,
            )

        except Exception as exc:

            raise FormatterFormatError(
                f"Unable to format SQL: {exc}",
            ) from exc

    # ------------------------------------------------------------------
    # Format
    # ------------------------------------------------------------------

    def format(
        self,
        content: str,
    ) -> str:
        """
        Format SQL.
        """

        return self.serialize(
            self.parse(
                content,
            ),
        )
