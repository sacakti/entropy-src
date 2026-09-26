"""
SQL script analysis models.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AnalysePolicy:
    """
    SQL analysis policy.
    """

    warning: tuple[str, ...] = ()

    error: tuple[str, ...] = ()

    stop: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnalyseFinding:
    """
    One SQL analysis finding.
    """

    rule: str

    severity: str

    message: str

    file: Path

    line: int

    column: int | None = None


@dataclass(frozen=True)
class AnalyseObject:
    """
    One database object operation discovered in a SQL script.
    """

    name: str

    object_type: str

    operation: str

    category: str

    file: Path

    line: int

    column: int | None = None


@dataclass(frozen=True)
class AnalyseFileResult:
    """
    Analysis result for one SQL file.
    """

    file: Path

    objects: tuple[AnalyseObject, ...] = ()

    findings: tuple[AnalyseFinding, ...] = ()


@dataclass(frozen=True)
class AnalyseResult:
    """
    Overall SQL analysis result.
    """

    files_scanned: int

    objects: tuple[AnalyseObject, ...]

    findings: tuple[AnalyseFinding, ...]

    stopped: bool


@dataclass(frozen=True)
class AnalyseToken:
    """
    Token extracted from a SQL script.
    """

    value: str

    token_type: str

    line: int

    column: int


@dataclass(frozen=True)
class AnalyseStatement:
    """
    Parsed SQL statement.
    """

    file: Path

    text: str

    line: int

    column: int

    tokens: tuple[AnalyseToken, ...]
