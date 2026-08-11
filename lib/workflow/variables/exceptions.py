"""
Workflow variable resolution exceptions.
"""

from __future__ import annotations


class VariableResolutionError(ValueError):
    """
    Raised when a workflow variable cannot be resolved.
    """


class VariableNotFoundError(VariableResolutionError):
    """
    Raised when a referenced variable does not exist.
    """


class VariableCircularReferenceError(VariableResolutionError):
    """
    Raised when workflow variables contain a circular reference.
    """
