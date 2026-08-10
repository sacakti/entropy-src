"""
Immutable application configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Configuration:
    """
    Immutable application configuration.
    """

    _data: dict[str, Any]

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    @property
    def application(self) -> dict[str, Any]:

        return self._section("application")

    @property
    def console(self) -> dict[str, Any]:

        return self._section("console")

    @property
    def logging(self) -> dict[str, Any]:

        return self._section("logging")

    @property
    def database(self) -> dict[str, Any]:

        return self._section("database")

    @property
    def runtime(self) -> dict[str, Any]:

        return self._section("runtime")

    @property
    def session(self) -> dict[str, Any]:

        return self._section("session")

    @property
    def python(self) -> dict[str, Any]:

        return self._section("python")

    @property
    def workflow(self) -> dict[str, Any]:

        return self._section("workflow")

    @property
    def git(self) -> dict[str, Any]:

        return self._section("git")

    @property
    def plugins(self) -> dict[str, Any]:

        return self._section("plugins")

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(
        self,
        path: str,
        default: Any = None,
    ) -> Any:
        """
        Retrieve a configuration value using dot notation.

        Example:

            logging.level
            database.path
        """

        value: Any = self._data

        for part in path.split("."):

            if not isinstance(
                value,
                dict,
            ):

                return default

            if part not in value:

                return default

            value = value[part]

        return value

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _section(
        self,
        name: str,
    ) -> dict[str, Any]:

        value = self._data.get(
            name,
            {},
        )

        if not isinstance(value, dict):
            return {}

        return value

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    @property
    def runtime_directory(self) -> Path:

        return Path(
            self.runtime["directory"],
        )

    @property
    def logging_directory(self) -> Path:

        return Path(
            self.logging["directory"],
        )

    @property
    def database_path(self) -> Path:

        return Path(
            self.database["path"],
        )

    @property
    def plugins_directory(self) -> Path:

        return Path(
            self.plugins["directory"],
        )

    @property
    def workflow_default(self) -> Path:

        return Path(
            self.workflow["default"],
        )

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __contains__(
        self,
        key: str,
    ) -> bool:

        return key in self._data

    def __getitem__(
        self,
        key: str,
    ) -> Any:

        return self._data[key]

    def __len__(
        self,
    ) -> int:

        return len(self._data)

    def __iter__(
        self,
    ):

        return iter(
            self._data,
        )
