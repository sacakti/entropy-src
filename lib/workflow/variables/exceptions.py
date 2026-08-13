"""
Workflow variable resolution exceptions.
"""

from __future__ import annotations

from core.exceptions import EntropyException


class VariableResolutionError(EntropyException):
    """
    Raised when a workflow variable cannot be resolved.
    """
    def __init__(self,message):
        print(message)


class VariableNotFoundError(VariableResolutionError):
    """
    Raised when a referenced variable does not exist.
    """


class VariableCircularReferenceError(VariableResolutionError):
    """
    Raised when workflow variables contain a circular reference.
    """
