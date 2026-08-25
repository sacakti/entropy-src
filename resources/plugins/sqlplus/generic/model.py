"""
SQLPlus plugin models.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SqlPlusExecution:
    """
    One SQLPlus database execution.
    """

    ip: str
    port: int
    sid: str
    schema: str
    username: str
    password: str
    script: Path


@dataclass(frozen=True)
class SqlPlusExecutionResult:
    """
    Result of one SQLPlus database execution.
    """

    schema: str
    script: Path
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    duration: float
