"""
Workflow CLI assignment parsing.
"""

from __future__ import annotations

import json
from typing import Any

from core.constants import DEFAULT_SEPARATOR
from lib.workflow.exceptions import WorkflowArgumentError


class WorkflowAssignments:
    """
    Parse CLI assignment expressions.

    Default syntax:

        key=value;key2=value2

    A custom separator may be supplied.

    Values may be quoted with single or double quotes.
    Separators inside quoted values are preserved.
    """

    DEFAULT_SEPARATOR = DEFAULT_SEPARATOR

    SUPPORTED_TYPES = {
        "auto",
        "string",
        "integer",
        "float",
        "boolean",
        "json",
        "list",
        "dict",
    }

    def parse(
        self,
        values: list[str] | None,
        *,
        separator: str = DEFAULT_SEPARATOR,
    ) -> dict[str, Any]:
        """
        Parse assignment expressions.

        Multiple expressions may be supplied and are merged.

        Later assignments override earlier assignments.
        """

        if not values:
            return {}

        if not separator:
            raise WorkflowArgumentError(
                "Assignment separator must not be empty.",
            )

        result: dict[str, Any] = {}

        for expression in values:

            for assignment in self._split(
                expression,
                separator,
            ):

                key, value = self._assignment(
                    assignment,
                )

                result[key] = value

        return result

    def parse_typed(
        self,
        values: list[str] | None,
        *,
        separator: str = DEFAULT_SEPARATOR,
        value_type: str = "string",
    ) -> dict[str, Any]:
        """
        Parse assignment expressions and convert values.

        Type conversion is applied only to the assignment values.

        Supported types:

            auto
            string
            integer
            float
            boolean
            json
            list
            dict
        """

        if value_type not in self.SUPPORTED_TYPES:

            raise WorkflowArgumentError(
                f"Unsupported assignment type '{value_type}'. "
                f"Supported types: "
                f"{', '.join(sorted(self.SUPPORTED_TYPES))}.",
            )

        assignments = self.parse(
            values,
            separator=separator,
        )

        return {
            key: self._convert(
                value,
                value_type,
            )
            for key, value in assignments.items()
        }

    @classmethod
    def _convert(
        cls,
        value: str,
        value_type: str,
    ) -> Any:
        """
        Convert an assignment value to the requested type.
        """

        if value_type == "auto":
            return cls._parse_auto(value)

        if value_type == "string":

            return value

        if value_type == "integer":

            try:

                return int(value)

            except ValueError as exc:

                raise WorkflowArgumentError(
                    f"Invalid integer value '{value}'.",
                ) from exc

        if value_type == "float":

            try:

                return float(value)

            except ValueError as exc:

                raise WorkflowArgumentError(
                    f"Invalid float value '{value}'.",
                ) from exc

        if value_type == "boolean":

            normalized = value.strip().lower()

            if normalized == "true":

                return True

            if normalized == "false":

                return False

            raise WorkflowArgumentError(
                f"Invalid boolean value '{value}'. " "Expected true or false.",
            )

        if value_type == "json":

            return cls._parse_json(
                value,
            )

        if value_type == "list":

            result = cls._parse_json(
                value,
            )

            if not isinstance(
                result,
                list,
            ):

                raise WorkflowArgumentError(
                    f"Invalid list value '{value}'. " "Expected a JSON array.",
                )

            return result

        if value_type == "dict":

            result = cls._parse_json(
                value,
            )

            if not isinstance(
                result,
                dict,
            ):

                raise WorkflowArgumentError(
                    f"Invalid dict value '{value}'. " "Expected a JSON object.",
                )

            return result

        # This should be unreachable because parse_typed()
        # validates the type before conversion.
        raise WorkflowArgumentError(
            f"Unsupported assignment type '{value_type}'.",
        )

    @staticmethod
    def _parse_auto(
        value: str,
    ) -> Any:
        """
        Automatically parse a CLI value.

        JSON-compatible values are converted to their
        corresponding Python types. Values that are not
        valid JSON remain strings.
        """

        try:

            return json.loads(
                value,
            )

        except json.JSONDecodeError:

            return value

    @staticmethod
    def _parse_json(
        value: str,
    ) -> Any:
        """
        Parse a JSON assignment value.
        """

        try:

            return json.loads(
                value,
            )

        except json.JSONDecodeError as exc:

            raise WorkflowArgumentError(
                f"Invalid JSON value '{value}': {exc.msg}.",
            ) from exc

    def _split(
        self,
        expression: str,
        separator: str,
    ) -> list[str]:
        """
        Split assignments while respecting quotes.
        """

        parts: list[str] = []
        current: list[str] = []

        quote: str | None = None
        escaped = False

        index = 0

        while index < len(expression):

            char = expression[index]

            if escaped:

                current.append(char)
                escaped = False
                index += 1
                continue

            if char == "\\":

                current.append(char)
                escaped = True
                index += 1
                continue

            if quote is not None:

                current.append(char)

                if char == quote:
                    quote = None

                index += 1
                continue

            if char in {"'", '"'}:

                quote = char
                current.append(char)
                index += 1
                continue

            if expression.startswith(
                separator,
                index,
            ):

                value = "".join(current).strip()

                if not value:

                    raise WorkflowArgumentError(
                        "Empty workflow assignment.",
                    )

                parts.append(value)
                current = []

                index += len(separator)
                continue

            current.append(char)
            index += 1

        if quote is not None:

            raise WorkflowArgumentError(
                "Unterminated quote in workflow assignment.",
            )

        value = "".join(current).strip()

        if not value:

            raise WorkflowArgumentError(
                "Empty workflow assignment.",
            )

        parts.append(value)

        return parts

    @staticmethod
    def _assignment(
        value: str,
    ) -> tuple[str, str]:
        """
        Parse one key=value assignment.
        """

        if "=" not in value:

            raise WorkflowArgumentError(
                f"Invalid assignment '{value}'. " "Expected KEY=VALUE.",
            )

        key, item = value.split(
            "=",
            1,
        )

        key = key.strip()
        item = item.strip()

        if not key:

            raise WorkflowArgumentError(
                f"Invalid assignment '{value}'. " "Assignment key must not be empty.",
            )

        return (
            key,
            WorkflowAssignments._unquote(item),
        )

    @staticmethod
    def _unquote(
        value: str,
    ) -> str:
        """
        Remove matching surrounding quotes.
        """

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:

            return value[1:-1]

        return value
