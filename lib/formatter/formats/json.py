"""
JSON formatter.
"""

from __future__ import annotations

import json

from lib.formatter.base import BaseFormatter
from lib.formatter.exceptions import FormatterFormatError


class JsonFormatter(
    BaseFormatter,
):
    """
    Format JSON documents.
    """

    @property
    def name(
        self,
    ) -> str:
        return "json"

    def format(
        self,
        content: str,
    ) -> str:
        """
        Parse and format JSON.
        """

        try:

            document = json.loads(
                content,
            )

        except json.JSONDecodeError as exc:

            raise FormatterFormatError(
                f"Invalid JSON: {exc.msg} "
                f"at line {exc.lineno}, column {exc.colno}.",
            ) from exc

        return json.dumps(
            document,
            indent=4,
            ensure_ascii=False,
        ) + "\n"
