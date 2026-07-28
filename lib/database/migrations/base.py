"""
Base migration.
"""

from abc import ABC


class BaseMigration(ABC):

    VERSION = None

    DESCRIPTION = ""

    def validate(self):

        pass

    def upgrade(
        self,
        connection,
    ):

        raise NotImplementedError()

    def dispose(self):

        pass