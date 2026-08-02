"""
Migration registry.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

from .base import BaseMigration
from .exceptions import (
    MigrationAlreadyRegisteredError,
)


class MigrationRegistry:
    """
    Discovers and registers database migrations.
    """

    def __init__(
        self,
        package: str,
    ) -> None:

        self._package = package

        self._migrations: dict[int, BaseMigration] = {}

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> None:
        """
        Discover migration classes.
        """

        package = importlib.import_module(
            self._package,
        )

        for _, module_name, _ in pkgutil.iter_modules(
            package.__path__,
        ):

            module = importlib.import_module(
                f"{self._package}.{module_name}",
            )

            for _, cls in inspect.getmembers(
                module,
                inspect.isclass,
            ):

                if (
                    issubclass(
                        cls,
                        BaseMigration,
                    )
                    and cls is not BaseMigration
                ):

                    self.register(
                        cls(),
                    )

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        migration: BaseMigration,
    ) -> None:
        """
        Register a migration.
        """

        version = migration.VERSION

        if version in self._migrations:

            raise MigrationAlreadyRegisteredError(
                f"Migration {version} is already registered."
            )

        self._migrations[version] = migration

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(
        self,
        version: int,
    ) -> BaseMigration | None:
        """
        Return a migration.
        """

        return self._migrations.get(
            version,
        )

    def has(
        self,
        version: int,
    ) -> bool:
        """
        Return True if a migration exists.
        """

        return version in self._migrations

    def list(
        self,
    ) -> list[BaseMigration]:
        """
        Return migrations ordered by version.
        """

        return [
            self._migrations[version]
            for version in sorted(
                self._migrations
            )
        ]

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def clear(
        self,
    ) -> None:
        """
        Remove all registered migrations.
        """

        self._migrations.clear()
