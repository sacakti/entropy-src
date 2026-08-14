"""
Workflow argument resolution.
"""

from __future__ import annotations

import re
from typing import Any

from lib.models.plugin import PluginResult
from lib.workflow.exceptions import WorkflowArgumentError


class WorkflowArgumentResolver:
    """
    Resolves workflow and step argument references.
    """

    _REFERENCE = re.compile(
        r"^\$\{([^}]+)\}$",
    )

    def resolve(
        self,
        arguments: dict[str, Any],
        *,
        variables: dict[str, Any],
        step_results: dict[str, PluginResult],
    ) -> dict[str, Any]:
        """
        Resolve all arguments.
        """

        return {
            key: self._resolve_value(
                value,
                variables=variables,
                step_results=step_results,
            )
            for key, value in arguments.items()
        }

    def _resolve_value(
        self,
        value: Any,
        *,
        variables: dict[str, Any],
        step_results: dict[str, PluginResult],
    ) -> Any:

        if isinstance(value, str):

            match = self._REFERENCE.fullmatch(
                value,
            )

            if match:

                return self._resolve_reference(
                    match.group(1),
                    variables=variables,
                    step_results=step_results,
                )

            return value

        if isinstance(value, list):

            return [
                self._resolve_value(
                    item,
                    variables=variables,
                    step_results=step_results,
                )
                for item in value
            ]

        if isinstance(value, dict):

            return {
                key: self._resolve_value(
                    item,
                    variables=variables,
                    step_results=step_results,
                )
                for key, item in value.items()
            }

        return value

    def _resolve_reference(
        self,
        reference: str,
        *,
        variables: dict[str, Any],
        step_results: dict[str, PluginResult],
    ) -> Any:

        parts = reference.split(".")

        if not parts:

            raise WorkflowArgumentError(
                f"Invalid reference '{reference}'.",
            )

        if parts[0] == "variables":

            if len(parts) < 2:

                raise WorkflowArgumentError(
                    f"Variable reference '{reference}' " "must specify a variable name.",
                )

            return self._lookup(
                variables,
                parts[1:],
                reference,
            )

        if parts[0] == "steps":

            if len(parts) < 4 or parts[2] != "outputs":

                raise WorkflowArgumentError(
                    f"Invalid step output reference "
                    f"'{reference}'. Expected "
                    "'steps.<step>.outputs.<key>'.",
                )

            step_name = parts[1]

            result = step_results.get(
                step_name,
            )

            if result is None:

                raise WorkflowArgumentError(
                    f"Step '{step_name}' has not produced " f"a result.",
                )

            return self._lookup(
                result.outputs,
                parts[3:],
                reference,
            )

        raise WorkflowArgumentError(
            f"Unsupported workflow reference " f"'{reference}'.",
        )

    @staticmethod
    def _lookup(
        value: Any,
        path: list[str],
        reference: str,
    ) -> Any:

        current = value

        for key in path:

            if (
                isinstance(
                    current,
                    dict,
                )
                and key in current
            ):

                current = current[key]

                continue

            raise WorkflowArgumentError(
                f"Unable to resolve reference " f"'{reference}'.",
            )

        return current
