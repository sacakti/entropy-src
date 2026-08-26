"""
Vault models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class VaultValueType(str, Enum):
    """
    Supported Vault value types.
    """

    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    JSON = "json"


@dataclass
class VaultEntry:
    """
    Represents a Vault key/value entry.
    """

    key: str

    value: Any

    type: VaultValueType

    sensitive: bool

    namespace_id: Optional[int] = None

    id: Optional[int] = None

    created_at: Optional[datetime] = None

    updated_at: Optional[datetime] = None
