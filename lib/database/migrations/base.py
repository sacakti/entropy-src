"""
Base migration.
"""

from abc import ABC, abstractmethod


class BaseMigration(ABC):

    VERSION = None

    DESCRIPTION = ""

    @abstractmethod
    def validate(self):

        pass

    def upgrade(
        self,
        connection,
    ):

        raise NotImplementedError()

    @abstractmethod
    def dispose(self):

        pass
