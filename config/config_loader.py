"""
Entropy Configuration Manager
"""

import json
from pathlib import Path

from core.constants import CONFIG_FILE
from core.exceptions import ConfigurationException


class Configuration:

    def __init__(self):

        self._config = {}

    def load(self, config_file: Path = CONFIG_FILE):

        if not config_file.exists():
            raise ConfigurationException(
                f"Configuration file not found: {config_file}"
            )

        with open(config_file, "r", encoding="utf-8") as fp:
            self._config = json.load(fp)

        self.validate()

    def validate(self):

        required = [
            "application",
            "logging",
            "database",
            "runtime",
            "workflow",
        ]

        for key in required:

            if key not in self._config:
                raise ConfigurationException(
                    f"Missing configuration section '{key}'"
                )

    def get(self, path, default=None):

        current = self._config

        for item in path.split("."):

            if not isinstance(current, dict):
                return default

            current = current.get(item)

            if current is None:
                return default

        return current


config = Configuration()