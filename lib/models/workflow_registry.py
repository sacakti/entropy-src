"""
Registered workflow model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class WorkflowRegistryEntry:
    """
    Persisted workflow definition metadata.
    """

    id: int

    name: str

    version: str

    description: str | None

    definition: str

    created_at: datetime

    updated_at: datetime
