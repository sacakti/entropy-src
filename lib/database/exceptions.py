"""
Authorization exceptions.
"""

from __future__ import annotations

from core.exceptions import EntropyException


class DatabaseException(EntropyException):
    """
    Base class for authorization failures.
    """
