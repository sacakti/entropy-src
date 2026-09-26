"""
Models for SQLPlus post-deployment validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ValidationError:
    """
    A hard deployment error found in the SQLPlus log.
    """

    file: str
    line: int
    message: str


@dataclass(frozen=True)
class ValidationNote:
    """
    An advisory message found in the SQLPlus log.

    Notes do not cause validation failure.
    """

    file: str
    line: int
    message: str


@dataclass(frozen=True)
class OperationCount:
    """
    Expected and actual count for one operation.
    """

    operation: str
    expected: int
    actual: int

    @property
    def delta(self) -> int:
        """
        Difference between actual and expected counts.
        """

        return self.actual - self.expected


@dataclass(frozen=True)
class ValidationFileResult:
    """
    Validation result for one deployment script.
    """

    folder: str
    file: str

    jira: str = "—"
    schema: str = "—"

    dml: tuple[OperationCount, ...] = ()
    ddl: tuple[OperationCount, ...] = ()

    block_operations: tuple[str, ...] = ()

    blocks_expected: int = 0
    blocks_completed: int = 0
    blocks_clean: int = 0

    success_markers: int = 0

    errors: tuple[ValidationError, ...] = ()
    notes: tuple[ValidationNote, ...] = ()

    status: str = "notrun"

    @property
    def mismatches(self) -> tuple[OperationCount, ...]:
        """
        Return genuine expected > actual mismatches.
        """

        return tuple(
            operation
            for operation in (*self.dml, *self.ddl)
            if operation.expected > operation.actual
        )

    @property
    def error_count(self) -> int:
        """
        Number of hard errors.
        """

        return len(self.errors)

    @property
    def note_count(self) -> int:
        """
        Number of advisory notes.
        """

        return len(self.notes)

    @property
    def not_run(self) -> bool:
        """
        Whether this file was not present in the deployment log.
        """

        return self.status == "notrun"


@dataclass(frozen=True)
class ValidationAssociateResult:
    """
    Validation result for one associate.
    """

    name: str
    status: str

    dml: tuple[OperationCount, ...] = ()
    ddl: tuple[OperationCount, ...] = ()

    errors: tuple[ValidationError, ...] = ()
    notes: tuple[ValidationNote, ...] = ()

    mismatches: tuple[OperationCount, ...] = ()

    blocks_expected: int = 0
    blocks_completed: int = 0

    success_markers: int = 0

    not_run_files: int = 0

    files: tuple[ValidationFileResult, ...] = ()


@dataclass(frozen=True)
class ValidationResult:
    """
    Complete post-deployment validation result.
    """

    release: str
    json_path: Path
    log_path: Path

    associates: tuple[ValidationAssociateResult, ...] = ()

    @property
    def passed(self) -> int:
        """
        Number of associates that passed.
        """

        return sum(
            result.status == "pass"
            for result in self.associates
        )

    @property
    def failed(self) -> int:
        """
        Number of associates that failed.
        """

        return sum(
            result.status == "fail"
            for result in self.associates
        )

    @property
    def partial(self) -> int:
        """
        Number of partially validated associates.
        """

        return sum(
            result.status == "partial"
            for result in self.associates
        )

    @property
    def notrun(self) -> int:
        """
        Number of associates that did not run.
        """

        return sum(
            result.status == "notrun"
            for result in self.associates
        )

    @property
    def error_lines(self) -> int:
        """
        Total hard error lines.
        """

        return sum(
            len(result.errors)
            for result in self.associates
        )

    @property
    def count_mismatches(self) -> int:
        """
        Total genuine count mismatches.
        """

        return sum(
            len(result.mismatches)
            for result in self.associates
        )

    @property
    def success(self) -> bool:
        """
        Whether all associates passed validation.
        """

        return self.failed == 0
