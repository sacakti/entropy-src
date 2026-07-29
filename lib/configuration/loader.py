"""
Entropy configuration loader.
"""

import json
from pathlib import Path

from lib.configuration.exceptions import ConfigurationFileNotFoundError, InvalidConfigurationError


class ConfigurationLoader:
    """
    Loads configuration from disk.
    """

    def load(
        self,
        config_file: Path,
    ) -> dict:
        """
        Load configuration.
        """

        if not config_file.exists():

            raise ConfigurationFileNotFoundError(
                config_file
            )

        try:

            with config_file.open(
                "r",
                encoding="utf-8",
            ) as fp:

                return json.load(fp)

        except json.JSONDecodeError as exc:

            raise InvalidConfigurationError(
                exc
            ) from exc