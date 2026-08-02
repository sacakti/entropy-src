"""
Configuration validator.
"""

from __future__ import annotations

from typing import Any

from .exceptions import InvalidConfigurationError


class ConfigurationValidator:
    """
    Validates configuration documents.
    """

    REQUIRED_SECTIONS = (
        "application",
        "console",
        "logging",
        "database",
        "runtime",
        "session",
        "python",
        "workflow",
        "git",
        "plugins",
    )

    def validate(
        self,
        configuration: dict[str, Any],
    ) -> None:
        """
        Validate configuration.
        """

        missing = [section for section in self.REQUIRED_SECTIONS if section not in configuration]

        if not missing:

            return

        message = "\n".join(f"Missing section: {section}" for section in missing)

        raise InvalidConfigurationError(
            message,
        )
