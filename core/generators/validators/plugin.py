import re
from pathlib import Path

from core.generators.exceptions import (
    InvalidPluginNameError,
    PluginAlreadyExistsError,
)


class PluginValidator:

    NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

    @classmethod
    def validate(
        cls,
        name: str,
        plugin_root: Path,
    ) -> None:

        cls.validate_name(name)
        cls.validate_exists(name, plugin_root)

    @classmethod
    def validate_name(
        cls,
        name: str,
    ) -> None:

        if not name:
            raise InvalidPluginNameError("Plugin name is required.")

        if not cls.NAME_PATTERN.fullmatch(name):
            raise InvalidPluginNameError(
                "Plugin name must start with a lowercase letter and contain only "
                "lowercase letters, digits and underscores."
            )

    @classmethod
    def validate_exists(
        cls,
        name: str,
        plugin_root: Path,
    ) -> None:

        plugin = plugin_root / name

        if plugin.exists():
            raise PluginAlreadyExistsError(
                f"Plugin '{name}' already exists."
            )
