"""
Configuration resolver.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


class ConfigurationResolver:
    """
    Resolves configuration values.

    Currently performs an identity transformation.

    Future support:

    - ${ENV}
    - ${HOME}
    - ${secret:name}
    - ${variable:name}
    """

    def resolve(
        self,
        configuration: dict[str, Any],
    ) -> dict[str, Any]:

        #
        # Placeholder for future variable resolution.
        #

        return deepcopy(
            configuration,
        )
