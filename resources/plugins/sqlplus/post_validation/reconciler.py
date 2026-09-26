"""
Reconcile pre-validation expectations with SQLPlus log results.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .model import (
    OperationCount,
    ValidationAssociateResult,
    ValidationError,
    ValidationFileResult,
    ValidationNote,
    ValidationResult,
)


class PostValidationReconciler:
    """
    Reconcile pre-validation expectations against parsed SQLPlus output.

    The reconciliation rules intentionally mirror the original
    post_validation_tool implementation:

    * Direct operations use SQLPlus feedback directly.
    * Block-wrapped operations receive proportional credit based on
      cleanly completed PL/SQL blocks.
    * Expected > actual is a mismatch.
    * Actual > expected is tolerated.
    * Hard errors fail the file/associate.
    * A file absent from the deployment log is ``notrun``.
    """

    def reconcile(
        self,
        *,
        json_path: Path,
        log_path: Path,
        parsed_log: dict[str, Any],
    ) -> ValidationResult:
        payload = self._load_pre_validation(json_path)

        release = str(
            payload.get(
                "release",
                json_path.parent.name,
            ),
        )

        sections_map = parsed_log.get(
            "sections_map",
            {},
        )

        associates: list[
            ValidationAssociateResult
        ] = []

        for _, expected in payload.get(
            "associates",
            {},
        ).items():

            display = str(
                expected["display"],
            )

            section = sections_map.get(
                display.strip().casefold(),
            )

            associates.append(
                self._reconcile_associate(
                    display=display,
                    expected=expected,
                    section=section,
                ),
            )

        return ValidationResult(
            release=release,
            json_path=json_path,
            log_path=log_path,
            associates=tuple(associates),
        )

    # ------------------------------------------------------------------
    # Associate
    # ------------------------------------------------------------------

    def _reconcile_associate(
        self,
        *,
        display: str,
        expected: dict[str, Any],
        section: dict[str, Any] | None,
    ) -> ValidationAssociateResult:
        file_rows = tuple(
            self._reconcile_file(
                expected_file=file_data,
                parsed_file=(
                    self._match_per_file(
                        section,
                        str(
                            file_data["path"],
                        ),
                    )
                    if section
                    else None
                ),
            )
            for file_data in expected.get(
                "files",
                [],
            )
        )

        statuses = [
            row.status
            for row in file_rows
        ]

        notrun_files = sum(
            status == "notrun"
            for status in statuses
        )

        section_errors = tuple(
            section.get(
                "errors",
                (),
            )
            if section
            else ()
        )

        if (
            section is None
            or (
                statuses
                and all(
                    status == "notrun"
                    for status in statuses
                )
            )
        ):
            status = "notrun"

        elif any(
            status == "fail"
            for status in statuses
        ) or section_errors:
            status = "fail"

        elif notrun_files:
            status = "partial"

        else:
            status = "pass"

        dml = self._aggregate(
            row.dml
            for row in file_rows
        )

        ddl = self._aggregate(
            row.ddl
            for row in file_rows
        )

        mismatches = tuple(
            operation
            for row in file_rows
            for operation in row.mismatches
        )

        notes = tuple(
            note
            for row in file_rows
            for note in row.notes
        )

        errors = tuple(
            section_errors
        )

        return ValidationAssociateResult(
            name=display,
            status=status,
            dml=dml,
            ddl=ddl,
            errors=errors,
            notes=notes,
            mismatches=mismatches,
            blocks_expected=int(
                expected.get(
                    "blocks",
                    0,
                ),
            ),
            blocks_completed=(
                int(
                    section.get(
                        "blocks_ok",
                        0,
                    ),
                )
                if section
                else 0
            ),
            success_markers=(
                int(
                    section.get(
                        "success",
                        0,
                    ),
                )
                if section
                else 0
            ),
            not_run_files=notrun_files,
            files=file_rows,
        )

    # ------------------------------------------------------------------
    # File
    # ------------------------------------------------------------------

    def _reconcile_file(
        self,
        *,
        expected_file: dict[str, Any],
        parsed_file: dict[str, Any] | None,
    ) -> ValidationFileResult:
        path = str(
            expected_file["path"],
        )

        folder, _, filename = path.partition("/")

        total_dml = self._counts(
            expected_file.get(
                "total_dml",
                {},
            ),
        )

        total_ddl = self._counts(
            expected_file.get(
                "total_ddl",
                {},
            ),
        )

        direct_dml = self._counts(
            expected_file.get(
                "direct_dml",
                {},
            ),
        )

        direct_ddl = self._counts(
            expected_file.get(
                "direct_ddl",
                {},
            ),
        )

        block_dml = self._subtract(
            total_dml,
            direct_dml,
        )

        block_ddl = self._subtract(
            total_ddl,
            direct_ddl,
        )

        expected_blocks = int(
            expected_file.get(
                "blocks",
                0,
            ),
        )

        if parsed_file is None:
            return ValidationFileResult(
                folder=folder,
                file=filename,
                jira=str(
                    expected_file.get(
                        "jira",
                        "—",
                    ),
                ),
                schema=str(
                    expected_file.get(
                        "schema",
                        "—",
                    ),
                ),
                dml=self._counts_to_models(
                    total_dml,
                    Counter(),
                ),
                ddl=self._counts_to_models(
                    total_ddl,
                    Counter(),
                ),
                block_operations=tuple(
                    self._block_operation_names(
                        block_dml,
                        block_ddl,
                    ),
                ),
                blocks_expected=expected_blocks,
                status="notrun",
            )

        actual_dml = Counter(
            parsed_file.get(
                "dml",
                {},
            ),
        )

        actual_ddl = Counter(
            parsed_file.get(
                "ddl",
                {},
            ),
        )

        blocks_completed = int(
            parsed_file.get(
                "blocks_ok",
                0,
            ),
        )

        blocks_clean = int(
            parsed_file.get(
                "blocks_clean",
                0,
            ),
        )

        errors = tuple(
            parsed_file.get(
                "errors",
                (),
            ),
        )

        notes = tuple(
            parsed_file.get(
                "notes",
                (),
            ),
        )

        # --------------------------------------------------------------
        # Exact block-credit algorithm from the original implementation.
        # --------------------------------------------------------------

        block_ops: dict[
            tuple[str, str],
            int,
        ] = {}

        for operation, count in block_dml.items():
            if count:
                block_ops[
                    ("dml", operation)
                ] = count

        for operation, count in block_ddl.items():
            if count:
                block_ops[
                    ("ddl", operation)
                ] = count

        if expected_blocks > 0:
            factor = min(
                1.0,
                blocks_clean / expected_blocks,
            )
        elif blocks_clean > 0:
            factor = 1.0
        else:
            factor = 0.0

        credit = {
            key: min(
                count,
                int(
                    round(
                        count * factor,
                    ),
                ),
            )
            for key, count in block_ops.items()
        }

        dml, dml_mismatches = self._combine(
            group="dml",
            total=total_dml,
            block=block_dml,
            actual_direct=actual_dml,
            credit=credit,
        )

        ddl, ddl_mismatches = self._combine(
            group="ddl",
            total=total_ddl,
            block=block_ddl,
            actual_direct=actual_ddl,
            credit=credit,
        )

        mismatches = tuple(
            (
                operation,
                expected,
                actual,
            )
            for operation, expected, actual
            in (
                *dml_mismatches,
                *ddl_mismatches,
            )
        )

        if errors or mismatches:
            status = "fail"
        else:
            status = "pass"

        return ValidationFileResult(
            folder=folder,
            file=filename,
            jira=str(
                expected_file.get(
                    "jira",
                    "—",
                ),
            ),
            schema=str(
                expected_file.get(
                    "schema",
                    "—",
                ),
            ),
            dml=dml,
            ddl=ddl,
            block_operations=tuple(
                self._block_operation_names(
                    block_dml,
                    block_ddl,
                ),
            ),
            blocks_expected=expected_blocks,
            blocks_completed=blocks_completed,
            blocks_clean=blocks_clean,
            success_markers=int(
                parsed_file.get(
                    "success",
                    0,
                ),
            ),
            errors=errors,
            notes=notes,
            status=status,
        )

    # ------------------------------------------------------------------
    # Operation reconciliation
    # ------------------------------------------------------------------

    @staticmethod
    def _combine(
        *,
        group: str,
        total: Counter[str],
        block: Counter[str],
        actual_direct: Counter[str],
        credit: dict[tuple[str, str], int],
    ) -> tuple[
        tuple[OperationCount, ...],
        tuple[tuple[str, int, int], ...],
    ]:
        """
        Combine direct SQLPlus feedback and block credit.

        Only expected > actual is considered a failure.
        """

        operations = sorted(
            set(total)
            | set(actual_direct),
        )

        result: list[
            OperationCount
        ] = []

        mismatches: list[
            tuple[str, int, int]
        ] = []

        for operation in operations:

            expected = int(
                total.get(
                    operation,
                    0,
                ),
            )

            block_count = int(
                block.get(
                    operation,
                    0,
                ),
            )

            actual = (
                int(
                    actual_direct.get(
                        operation,
                        0,
                    ),
                )
                + int(
                    credit.get(
                        (group, operation),
                        0,
                    ),
                )
            )

            if not expected and not actual:
                continue

            result.append(
                OperationCount(
                    operation=operation,
                    expected=expected,
                    actual=actual,
                ),
            )

            if expected > actual:
                mismatches.append(
                    (
                        operation,
                        expected,
                        actual,
                    ),
                )

        return (
            tuple(result),
            tuple(mismatches),
        )

    @staticmethod
    def _aggregate(
        groups: Any,
    ) -> tuple[OperationCount, ...]:
        expected: Counter[str] = Counter()
        actual: Counter[str] = Counter()

        for group in groups:
            for operation in group:
                expected[
                    operation.operation
                ] += operation.expected

                actual[
                    operation.operation
                ] += operation.actual

        return tuple(
            OperationCount(
                operation=operation,
                expected=expected[operation],
                actual=actual[operation],
            )
            for operation in sorted(
                set(expected)
                | set(actual),
            )
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _counts(
        value: Any,
    ) -> Counter[str]:
        if not isinstance(
            value,
            dict,
        ):
            return Counter()

        return Counter(
            {
                str(key): int(count)
                for key, count in value.items()
            },
        )

    @staticmethod
    def _subtract(
        total: Counter[str],
        direct: Counter[str],
    ) -> Counter[str]:
        """
        Calculate block-wrapped operations.

        Negative values are clamped to zero, matching the original tool.
        """

        return Counter(
            {
                operation: max(
                    0,
                    total.get(
                        operation,
                        0,
                    )
                    - direct.get(
                        operation,
                        0,
                    ),
                )
                for operation in total
            },
        )

    @staticmethod
    def _counts_to_models(
        expected: Counter[str],
        actual: Counter[str],
    ) -> tuple[OperationCount, ...]:
        return tuple(
            OperationCount(
                operation=operation,
                expected=expected.get(
                    operation,
                    0,
                ),
                actual=actual.get(
                    operation,
                    0,
                ),
            )
            for operation in sorted(
                set(expected)
                | set(actual),
            )
        )

    @staticmethod
    def _block_operation_names(
        dml: Counter[str],
        ddl: Counter[str],
    ) -> list[str]:
        return [
            *(
                f"DML {operation}"
                for operation, count in dml.items()
                if count
            ),
            *(
                f"DDL {operation}"
                for operation, count in ddl.items()
                if count
            ),
        ]

    @staticmethod
    def _match_per_file(
        section: dict[str, Any],
        expected_path: str,
    ) -> dict[str, Any] | None:
        """
        Match an expected path against the parser's per-file entries.

        Matching is filename/path based and case-insensitive.
        """

        per_file = section.get(
            "per_file",
            {},
        )

        expected = Path(
            expected_path,
        ).as_posix().casefold()

        expected_name = Path(
            expected_path,
        ).name.casefold()

        for parsed_path, data in per_file.items():

            normalized = Path(
                parsed_path,
            ).as_posix().casefold()

            if normalized == expected:
                return data

            if Path(
                parsed_path,
            ).name.casefold() == expected_name:
                return data

        return None

    @staticmethod
    def _load_pre_validation(
        path: Path,
    ) -> dict[str, Any]:
        try:
            with path.open(
                "r",
                encoding="utf-8",
            ) as handle:
                payload = json.load(handle)
        except (
            OSError,
            json.JSONDecodeError,
        ) as exc:
            raise ValueError(
                f"Unable to read pre-validation JSON "
                f"'{path}': {exc}",
            ) from exc

        if not isinstance(
            payload,
            dict,
        ):
            raise ValueError(
                "pre_validation.json must contain a JSON object.",
            )

        if not isinstance(
            payload.get(
                "associates",
            ),
            dict,
        ):
            raise ValueError(
                "pre_validation.json must contain an "
                "'associates' object.",
            )

        return payload
