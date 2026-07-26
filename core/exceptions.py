"""
Application exceptions.
"""


class EntropyException(Exception):
    """Base exception."""


class ConfigurationException(EntropyException):
    """Configuration errors."""


class DatabaseException(EntropyException):
    """SQLite errors."""


class WorkflowException(EntropyException):
    """Workflow errors."""


class PluginException(EntropyException):
    """Plugin errors."""


class ExecutionException(EntropyException):
    """Execution errors."""


class ValidationException(EntropyException):
    """Validation errors."""