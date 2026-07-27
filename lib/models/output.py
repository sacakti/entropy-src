"""
Output Models
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class LogRecord:

    timestamp: datetime = field(default_factory=datetime.now)

    level: str = "INFO"

    category: str = "system"

    message: str = ""

    release_id: Optional[str] = None

    workflow: Optional[str] = None

    target: Optional[str] = None

    plugin: Optional[str] = None

    step: Optional[int] = None

    pid: Optional[int] = None

    file: Optional[str] = None

    