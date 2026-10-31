"""
Workflow variables entered when a run starts.

A variable whose value is exactly ``${ask}`` (or ``${ask:secret}`` for hidden
input) is asked for when the workflow runs, unless the run was started with a
value for it. The runner asks; dry runs treat the value as a placeholder.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

ASK = "${ask}"
ASK_SECRET = "${ask:secret}"

# Stands in for a value entered at run time during dry runs.
DRY_RUN_PLACEHOLDER = "<entered at run time>"


def ask_marker(value: Any) -> Optional[bool]:
    """
    None when the value is not an ask marker, else whether it is secret.
    """

    if not isinstance(value, str):
        return None

    marker = value.strip()

    if marker == ASK:
        return False

    if marker == ASK_SECRET:
        return True

    return None


def asked_variables(variables: Dict[str, Any]) -> Dict[str, bool]:
    """
    The variables to ask for, each mapped to whether its input is secret.
    """

    asked: Dict[str, bool] = {}

    for name, value in variables.items():
        secret = ask_marker(value)

        if secret is not None:
            asked[name] = secret

    return asked
