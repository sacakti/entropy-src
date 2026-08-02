"""
Log levels.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class LogLevel(str, Enum):

    DEBUG = "debug"

    INFO = "info"

    SUCCESS = "success"

    WARNING = "warning"

    ERROR = "error"

    CRITICAL = "critical"


@dataclass(frozen=True)
class LogEntry:

    level: LogLevel

    source: str

    message: str

    timestamp: datetime
