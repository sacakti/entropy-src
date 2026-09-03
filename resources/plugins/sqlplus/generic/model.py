"""
SQLPlus plugin models.
"""

from __future__ import annotations
from typing import Any
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
    executed_script: Path
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    duration: float
    spool: dict[str, Any] | None = None
    error_type: str | None = None
    error_message: str | None = None

"""
SQLPlus spool models.
"""
@dataclass(frozen=True)
class SpoolSettings:
    """
    SQLPlus spool configuration.
    """

    enabled: bool = False

    create_if_not_exists: bool = True

    name_placeholder: str = (
        "%execution_path/%release_%schema_%date.log"
    )

    infile_replace: bool = False

    override: bool = False

    wrappers_before: tuple[str, ...] = ()

    wrappers_after: tuple[str, ...] = ()
