"""
Entropy configuration loader.
"""

from pathlib import Path
from typing import Any

from lib.configuration.exceptions import ConfigurationFileNotFoundError


class ConfigurationLoader:
    """
    Loads configuration from disk.
    """

    def __init__(self, context):
        self.context = context

    def load(
        self,
        config_file: Path,
    ) -> Any:
        """
        Load configuration.
        """

        if not config_file.exists():
            raise ConfigurationFileNotFoundError(config_file)

        return self.context.executor.read_json(config_file)
