"""
Log levels.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum


class LogLevel(IntEnum):

    DEBUG = 10
    INFO = 20
    SUCCESS = 25
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


@dataclass(frozen=True)
class LogEntry:

    level: LogLevel

    source: str

    message: str

    timestamp: datetime
