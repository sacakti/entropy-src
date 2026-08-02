"""
Migration exceptions.
"""

from core.exceptions import EntropyException


class MigrationException(EntropyException):
    """
    Base migration exception.
    """


class MigrationNotFoundError(MigrationException):
    """
    Raised when a migration cannot be found.
    """


class MigrationAlreadyRegisteredError(MigrationException):
    """
    Raised when a migration version is already registered.
    """


class MigrationExecutionError(MigrationException):
    """
    Raised when a migration fails.
    """
