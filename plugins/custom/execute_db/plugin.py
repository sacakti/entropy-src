"""
execute_db plugin.
"""

from lib.plugins.base import BasePlugin


class Plugin(BasePlugin):
    """
    execute_db plugin implementation.
    """

    def validate(
        self,
        config: dict,
    ) -> None:
        """
        Validate plugin configuration.
        """

        super().validate(config)

    def execute(
        self,
        config: dict,
    ) -> None:
        """
        Execute the plugin.
        """

        raise NotImplementedError(
            "Plugin execution has not been implemented."
        )


PLUGIN_CLASS = "Plugin"
