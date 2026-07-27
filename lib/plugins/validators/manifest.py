"""
Plugin manifest validator.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from lib.models.plugin import Plugin

from .base import BaseValidator


class ManifestValidator(BaseValidator):
    """
    Validates plugin manifests.
    """

    VERSION_PATTERN = re.compile(
        r"^\d+\.\d+\.\d+$"
    )

    REQUIRED_FIELDS = (
        "name",
        "version",
        "description",
        "author",
        "license",
    )

    REQUIRED_FILES = (
        "__init__.py",
        "plugin.py",
        "plugin.json",
    )

    def validate(
        self,
        namespace: str,
        directory: Path,
    ) -> Plugin:
        """
        Validate a plugin directory.
        """

        self._errors = []

        manifest = directory / "plugin.json"

        if not manifest.exists():

            self._add_error(
                "Missing plugin.json."
            )

            self._raise(directory)

        try:

            with manifest.open(
                "r",
                encoding="utf-8",
            ) as fp:

                data = json.load(fp)

        except json.JSONDecodeError as exc:

            self._add_error(
                f"Invalid JSON: {exc.msg}"
            )

            self._raise(directory)

        self._validate_fields(data)
        self._validate_version(data)
        self._validate_directory(directory, data)
        self._validate_files(directory)

        self._raise(directory)

        return Plugin(
            name=data["name"],
            namespace=namespace,
            version=data["version"],
            description=data["description"],
            author=data["author"],
            license=data["license"],
            path=directory,
            manifest=manifest,
        )

    def _validate_fields(
        self,
        data: dict,
    ) -> None:

        for field in self.REQUIRED_FIELDS:

            if field not in data:

                self._add_error(
                    f"Missing required field '{field}'."
                )

    def _validate_version(
        self,
        data: dict,
    ) -> None:

        version = data.get("version")

        if version is None:
            return

        if not self.VERSION_PATTERN.fullmatch(version):

            self._add_error(
                f"Invalid version '{version}'."
            )

    def _validate_directory(
        self,
        directory: Path,
        data: dict,
    ) -> None:

        name = data.get("name")

        if name is None:
            return

        if directory.name != name:

            self._add_error(
                "Directory name "
                f"'{directory.name}' "
                "does not match "
                f"manifest name '{name}'."
            )

    def _validate_files(
        self,
        directory: Path,
    ) -> None:

        for filename in self.REQUIRED_FILES:

            if not (directory / filename).exists():

                self._add_error(
                    f"Missing required file '{filename}'."
                )

    def _add_error(
        self,
        message: str,
    ) -> None:

        self._errors.append(message)

    def _raise(
        self,
        directory: Path,
    ) -> None:

        if not self._errors:
            return

        message = (
            f"Invalid plugin '{directory.name}':\n\n"
            + "\n".join(
                f"  • {error}"
                for error in self._errors
            )
        )

        raise ValueError(message)