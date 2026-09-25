"""
Invalid objects report models.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InvalidObject:
    """
    One invalid Oracle object.
    """

    name: str
    object_type: str
    status: str
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class SchemaReport:
    """
    Invalid-object inspection result for one schema.
    """

    schema: str
    status: str
    invalid_objects: tuple[InvalidObject, ...] = ()
    error_type: str | None = None
    error_message: str | None = None
    stderr: str | None = None
