"""
Base database object.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from lib.database.connection import DatabaseConnection


class DatabaseObject(ABC):
    """
    Base class for all database objects.

    A database object represents a table, index,
    view or trigger that forms part of the schema.
    """

    NAME: str

    @abstractmethod
    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """
        Create the database object.
        """

    def drop(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """
        Drop the database object.
        """

        connection.execute(f"DROP TABLE IF EXISTS {self.NAME}")
