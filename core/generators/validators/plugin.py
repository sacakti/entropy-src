"""
Plugin generator validator.
"""

from __future__ import annotations

import re
from pathlib import Path

from core.generators.exceptions import (
    GeneratorAlreadyExistsError,
    InvalidGeneratorNameError,
)


class PluginValidator:
    """
    Validates plugin generation requests.
    """

    NAME_PATTERN = re.compile(
        r"^[a-z][a-z0-9_]*$",
    )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    @classmethod
    def validate(
        cls,
        *,
        namespace: str,
        name: str,
        root: Path,
    ) -> None:
        """
        Validate a plugin request.
        """

        cls.validate_namespace(
            namespace,
        )

        cls.validate_name(
            name,
        )

        cls.validate_exists(
            namespace,
            name,
            root,
        )

    # ------------------------------------------------------------------
    # Namespace
    # ------------------------------------------------------------------

    @classmethod
    def validate_namespace(
        cls,
        namespace: str,
    ) -> None:
        """
        Validate plugin namespace.
        """

        if not namespace:

            raise InvalidGeneratorNameError(
                "Plugin namespace is required.",
            )

        if not cls.NAME_PATTERN.fullmatch(
            namespace,
        ):

            raise InvalidGeneratorNameError(
                "Invalid plugin namespace.",
            )

    # ------------------------------------------------------------------
    # Name
    # ------------------------------------------------------------------

    @classmethod
    def validate_name(
        cls,
        name: str,
    ) -> None:
        """
        Validate plugin name.
        """

        if not name:

            raise InvalidGeneratorNameError(
                "Plugin name is required.",
            )

        if not cls.NAME_PATTERN.fullmatch(
            name,
        ):

            raise InvalidGeneratorNameError(
                "Invalid plugin name.",
            )

    # ------------------------------------------------------------------
    # Exists
    # ------------------------------------------------------------------

    @classmethod
    def validate_exists(
        cls,
        namespace: str,
        name: str,
        root: Path,
    ) -> None:
        """
        Ensure the plugin does not already exist.
        """

        plugin = cls.directory(
            root=root,
            namespace=namespace,
            name=name,
        )

        if plugin.exists():

            raise GeneratorAlreadyExistsError(
                f"Plugin '{namespace}.{name}' already exists.",
            )

    @classmethod
    def directory(
        cls,
        *,
        root: Path,
        namespace: str,
        name: str,
    ) -> Path:
        """
        Return the plugin directory.
        """

        return (
            root /
            namespace /
            name
        )
