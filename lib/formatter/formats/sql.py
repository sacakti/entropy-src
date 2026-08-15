"""
SQL formatter.
"""

from __future__ import annotations

try:

    import sqlparse

except ImportError:  # pragma: no cover

    sqlparse = None


from lib.formatter.base import BaseFormatter
from lib.formatter.exceptions import (
    FormatterDependencyError,
    FormatterFormatError,
)


class SqlFormatter(
    BaseFormatter,
):
    """
    Format SQL documents.
    """

    @property
    def name(
        self,
    ) -> str:
        return "sql"

    def format(
        self,
        content: str,
    ) -> str:
        """
        Format SQL.
        """

        if sqlparse is None:

            raise FormatterDependencyError(
                "SQL formatting requires the 'sqlparse' package.",
            )

        if not content.strip():

            return ""

        try:

            return sqlparse.format(
                content,
                reindent=True,
                keyword_case="upper",
                strip_comments=False,
            ).rstrip() + "\n"

        except Exception as exc:

            raise FormatterFormatError(
                f"Unable to format SQL: {exc}",
            ) from exc
