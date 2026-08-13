"""
Workflow argument overrides.
"""

from __future__ import annotations

from typing import Any

from lib.workflow.exceptions import WorkflowArgumentError


class WorkflowArgumentOverrides:
    """
    Apply externally supplied argument overrides to a workflow step.

    Overrides are applied after normal workflow argument resolution.
    """

    def apply(
        self,
        arguments: dict[str, Any],
        overrides: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Return arguments with external overrides applied.

        Existing argument names may be overridden.
        Unknown argument names are rejected.
        """

        result = dict(arguments)

        for key, value in overrides.items():

            if key not in result:

                raise WorkflowArgumentError(
                    f"Override argument '{key}' "
                    "does not exist in the workflow step.",
                )

            result[key] = value

        return result
