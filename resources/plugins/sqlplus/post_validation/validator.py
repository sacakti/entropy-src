"""
Post-deployment SQLPlus validation orchestration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(
        self,
        *,
        json_path: Path,
        log_path: Path,
    ) -> ValidationResult:
        """
        Parse and reconcile a deployment log against pre-validation
        expectations.
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

    # ------------------------------------------------------------------
    # Log-only analysis
    # ------------------------------------------------------------------

    def analyze(
        self,
        *,
        log_path: Path,
    ) -> dict[str, Any]:
        """
        Parse a deployment log without pre-validation expectations.

        This mode intentionally performs no expected-versus-actual
        reconciliation. The returned structure is the parser's
        application/file analysis and is consumed by the log-only
        report builder.
        """

        self._validate_input(
            log_path,
            "deployment log",
        )

        return self._parser.parse(
            log_path,
        )

    # ------------------------------------------------------------------
    # Validation report
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------

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

    def build_log_analysis(
        self,
        *,
        log_path: Path,
        analysis: dict[str, Any],
        output: Path,
        release: str,
        embed_log: bool = True,
    ) -> Path:
        """
        Build an HTML report for log-only analysis.
        """

        return self._report_builder.build_log_analysis(
            log_path=log_path,
            analysis=analysis,
            output=output,
            release=release,
            embed_log=embed_log,
        )
