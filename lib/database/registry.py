"""
Migration registry.
"""

import importlib
import inspect
import pkgutil

from core.constants import DATABASE_MIGRATION_PACKAGE

from .migrations.base import BaseMigration


class MigrationRegistry:

    def __init__(self):

        self._migrations = {}

    def discover(self):

        package = importlib.import_module(
            DATABASE_MIGRATION_PACKAGE
        )

        for _, module_name, _ in pkgutil.iter_modules(
            package.__path__
        ):

            if module_name == "base":
                continue

            module = importlib.import_module(
                f"{DATABASE_MIGRATION_PACKAGE}.{module_name}"
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

                    migration = cls()

                    self.register(
                        migration
                    )

    def register(
        self,
        migration,
    ):

        self._migrations[
            migration.VERSION
        ] = migration

    def get(
        self,
        version,
    ):

        return self._migrations.get(
            version
        )

    def list(self):

        return [
            self._migrations[k]
            for k in sorted(
                self._migrations
            )
        ]

    def all(self):

        return tuple(
            self._migrations[k]
            for k in sorted(self._migrations)
        )

    def clear(self):

        self._migrations.clear()