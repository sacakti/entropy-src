"""
Diagnostic log entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from core.models.logger import LogLevel


@dataclass(frozen=True)
class LogEntry:
    """
    Immutable diagnostic log entry.
    """

    level: LogLevel

    source: str

    message: str

    timestamp: datetime = field(
        default_factory=datetime.utcnow,
    )
