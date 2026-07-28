"""
Entropy configuration loader.
"""

import json
from pathlib import Path

from core.exceptions import ConfigurationException


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

            raise ConfigurationException(
                f"Configuration file not found: {config_file}"
            )

        try:

            with config_file.open(
                "r",
                encoding="utf-8",
            ) as fp:

                return json.load(fp)

        except json.JSONDecodeError as exc:

            raise ConfigurationException(
                f"Invalid configuration: {exc}"
            ) from exc