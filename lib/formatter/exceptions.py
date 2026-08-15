"""
Formatter exceptions.
"""

from __future__ import annotations

from core.exceptions import EntropyException


class FormatterError(EntropyException):
    """
    Base exception for formatter failures.
    """


class FormatterFormatError(FormatterError):
    """
    Raised when a format is unsupported or invalid.
    """


class FormatterFileError(FormatterError):
    """
    Raised when a formatter cannot read or write a file.
    """


class FormatterDependencyError(FormatterError):
    """
    Raised when a formatter requires an unavailable dependency.
    """
