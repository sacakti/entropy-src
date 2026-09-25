"""
Workflow workspace template resolver.
"""

from __future__ import annotations

import re
from typing import Any

from .exceptions import WorkspaceVariableNotFoundError


class WorkspaceTemplateResolver:
    """
    Resolves workflow workspace templates.

    Workspace variables use the following syntax:

        %variable%

    Examples:

        %tag%
        %tag%_%environment%
        release-%tag%

    Workspace templates intentionally use a separate syntax from
    workflow argument variables, which use ${...}.
    """

    _REFERENCE_PATTERN = re.compile(
        r"%([^%]+)%",
    )

    def resolve(
        self,
        template: str,
        variables: dict[str, Any],
    ) -> str:
        """
        Resolve workspace variable references.
        """

        def replace(
            match: re.Match[str],
        ) -> str:

            name = match.group(1).strip()

            if name not in variables:
                raise WorkspaceVariableNotFoundError(
                    f"Workspace variable '{name}' does not exist.",
                )

            value = variables[name]

            if isinstance(
                value,
                (dict, list, tuple, set),
            ):
                raise WorkspaceVariableNotFoundError(
                    f"Workspace variable '{name}' "
                    "must resolve to a scalar value.",
                )

            return str(value)

        return self._REFERENCE_PATTERN.sub(
            replace,
            template,
        )
