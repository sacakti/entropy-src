"""
Post-deployment SQLPlus validation orchestration.
"""

from __future__ import annotations

from pathlib import Path

from .model import ValidationResult
from .parser import PostValidationLogParser
from .reconciler import PostValidationReconciler
from .report import PostValidationReportBuilder


class PostValidationValidator:
    """
    Coordinate SQLPlus log parsing, reconciliation, and reporting.
    """

    def __init__(
        self,
        *,
        parser: PostValidationLogParser | None = None,
        reconciler: PostValidationReconciler | None = None,
        report_builder: PostValidationReportBuilder | None = None,
    ) -> None:
        self._parser = (
            parser
            or PostValidationLogParser()
        )

        self._reconciler = (
            reconciler
            or PostValidationReconciler()
        )

        self._report_builder = (
            report_builder
            or PostValidationReportBuilder()
        )

    def validate(
        self,
        *,
        json_path: Path,
        log_path: Path,
    ) -> ValidationResult:
        """
        Parse and reconcile a deployment log.
        """

        self._validate_input(
            json_path,
            "pre-validation JSON",
        )

        self._validate_input(
            log_path,
            "deployment log",
        )

        parsed_log = self._parser.parse(
            log_path,
        )

        return self._reconciler.reconcile(
            json_path=json_path,
            log_path=log_path,
            parsed_log=parsed_log,
        )

    def build_dashboard(
        self,
        *,
        result: ValidationResult,
        output: Path,
        embed_log: bool = True,
    ) -> Path:
        """
        Build the HTML dashboard for a validation result.
        """

        return self._report_builder.build(
            result=result,
            output=output,
            embed_log=embed_log,
        )

    @staticmethod
    def _validate_input(
        path: Path,
        description: str,
    ) -> None:
        if not path.exists():
            raise FileNotFoundError(
                f"{description.capitalize()} "
                f"does not exist: {path}",
            )

        if not path.is_file():
            raise ValueError(
                f"{description.capitalize()} "
                f"is not a file: {path}",
            )
