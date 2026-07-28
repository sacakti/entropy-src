"""
Base repository.
"""

from sqlite3 import Connection


class Repository:

    def __init__(
        self,
        connection: Connection,
    ):

        self._connection = connection

    @property
    def connection(self):

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

    def commit(self):

        self._connection.commit()