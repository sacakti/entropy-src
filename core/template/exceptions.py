"""
Template exceptions.
"""

from core.exceptions import EntropyException


class TemplateError(EntropyException):
    """
    Base template exception.
    """


class TemplateNotFoundError(TemplateError):
    """
    Raised when a template cannot be found.
    """
