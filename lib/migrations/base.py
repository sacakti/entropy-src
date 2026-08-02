"""
Base migration.
"""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod

from lib.database.connection import DatabaseConnection


class BaseMigration(ABC):
    """
    Base migration.
    """

    VERSION: int

    DESCRIPTION: str

    def validate(self) -> None:
        """
        Validate the migration.
        """

    @abstractmethod
    def upgrade(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """
        Upgrade the schema.
        """
