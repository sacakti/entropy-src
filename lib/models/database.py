"""
Database models.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Optional


class MigrationMode(Enum):

    SILENT = auto()

    NORMAL = auto()

    VERBOSE = auto()


@dataclass
class Setting:

    key: str

    value: str

    updated_at: Optional[datetime] = None


@dataclass
class License:

    key: str

    edition: str

    customer: str

    email: str

    issued_at: datetime

    expires_at: Optional[datetime]

    activated_at: Optional[datetime]

    status: str

    signature: str


@dataclass
class Plugin:

    name: str

    namespace: str

    version: str

    enabled: bool

    installed_at: Optional[datetime]


@dataclass
class Deployment:

    workflow: str

    started_at: datetime

    finished_at: Optional[datetime]

    duration_ms: Optional[int]

    status: str
