"""
Configuration model.
"""


class ConfigurationModel:
    """
    Configuration model.
    """

    def __init__(
        self,
        configuration: dict,
    ):

        self._configuration = configuration

    def get(
        self,
        path: str,
        default=None,
    ):
        """
        Get a configuration value.
        """

        current = self._configuration

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

    def all(self) -> dict:

        return self._configuration.copy()
