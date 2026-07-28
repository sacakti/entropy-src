"""
Entropy configuration manager.
"""

from pathlib import Path

from core.constants import CONFIG_FILE

from .loader import ConfigurationLoader
from lib.models.configuration import ConfigurationModel
from .validator import ConfigurationValidator


class ConfigurationManager:
    """
    Configuration manager.
    """

    def __init__(self):

        self._loader = ConfigurationLoader()

        self._validator = ConfigurationValidator()

        self._configuration = None

    def load(
        self,
        config_file: Path = CONFIG_FILE,
    ) -> None:
        """
        Load configuration.
        """

        configuration = self._loader.load(
            config_file
        )

        self._validator.validate(
            configuration
        )

        self._configuration = ConfigurationModel(
            configuration
        )

    def get(
        self,
        path: str,
        default=None,
    ):
        """
        Get a configuration value.
        """

        if self._configuration is None:

            raise RuntimeError(
                "Configuration has not been loaded."
            )

        return self._configuration.get(
            path,
            default,
        )