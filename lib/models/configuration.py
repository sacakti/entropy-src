"""
Configuration model.
"""

from typing import Any


class ConfigurationModel:
    """
    Configuration model.
    """

    def __init__(
        self,
        configuration: dict[str, Any],
    ):

        self._configuration = configuration

    def get(
        self,
        path: str,
        default: Any = None,
    ) -> Any:
        """
        Get a configuration value.
        """

        current: Any = self._configuration

        for key in path.split("."):

            if not isinstance(
                current,
                dict,
            ):
                return default

            current = current.get(key)

            if current is None:
                return default

        return current

    def exists(
        self,
        path: str,
    ) -> bool:

        return (
            self.get(
                path,
                default=object(),
            )
            is not object()
        )

    def all(self) -> dict[str, Any]:
        return self._configuration.copy()
