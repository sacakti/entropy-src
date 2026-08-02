
"""
Base repository.
"""

from __future__ import annotations

from lib.database.connection import DatabaseConnection


class Repository:
    """
    Base repository.
    """

    def __init__(
        self,
        connection: DatabaseConnection,
    ) -> None:

        self._connection = connection

    @property
    def connection(
        self,
    ) -> DatabaseConnection:

        return self._connection

    def execute(
        self,
        sql,
        parameters=(),
    ):

        return self._connection.execute(
            sql,
            parameters,
        )

    def fetchone(
        self,
        sql,
        parameters=(),
    ):

        return self._connection.fetchone(
            sql,
            parameters,
        )

    def fetchall(
        self,
        sql,
        parameters=(),
    ):

        return self._connection.fetchall(
            sql,
            parameters,
        )
