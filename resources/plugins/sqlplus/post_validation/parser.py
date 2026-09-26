"""
SQLPlus deployment log parser.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .model import (
    ValidationError,
    ValidationNote,
)


class PostValidationLogParser:
    """
    Parse SQLPlus deployment logs into associate/file sections.
    """

    _START_MARKER = re.compile(
        r"-{2,}\s*(.*?)\s+Script starts here",
        re.IGNORECASE,
    )

    _END_MARKER = re.compile(
        r"-{2,}\s*(.*?)\s+Script ends here",
        re.IGNORECASE,
    )

    _FILE_ECHO = re.compile(
        r"@@\s*(\S+?\.sql)",
        re.IGNORECASE,
    )

    _DML_FEEDBACK = re.compile(
        r"^\s*(\d[\d,]*)\s+rows?\s+"
        r"(created|inserted|updated|deleted|merged)\b",
        re.IGNORECASE,
    )

    _DDL_FEEDBACK = re.compile(
        r"^\s*(?:warning:\s*)?"
        r"(table|view|index|sequence|synonym|trigger|procedure|"
        r"function|package(?:\s+body)?|type|materialized\s+view)\s+"
        r"(created|altered|dropped|truncated)\b",
        re.IGNORECASE,
    )

    _FAILED_OPERATION = re.compile(
        r"Exception occurred on\s+(.+?)\s+statement",
        re.IGNORECASE,
    )

    _PLSQL_OK = re.compile(
        r"PL/SQL procedure successfully completed",
        re.IGNORECASE,
    )

    _SUCCESS_LINE = re.compile(
        r"^\s*SUCCESS\s*:",
        re.IGNORECASE,
    )

    _HARD_ERROR_PATTERNS = (
        re.compile(r"\bORA-\d{4,5}\b"),
        re.compile(r"\bSP2-\d{3,5}\b"),
        re.compile(r"\bPLS-\d{3,5}\b"),
        re.compile(r"^\s*ERROR at line", re.IGNORECASE),
        re.compile(r"COMPILE FAILED", re.IGNORECASE),
        re.compile(r"^\s*Disconnected\b", re.IGNORECASE),
        re.compile(
            r"created with compilation errors",
            re.IGNORECASE,
        ),
        re.compile(
            r"Invalid identifier",
            re.IGNORECASE,
        ),
        re.compile(
            r"Missing or invalid option in the DDL statement",
            re.IGNORECASE,
        ),
        re.compile(
            r"Missing BY keyword in the DDL statement",
            re.IGNORECASE,
        ),
        re.compile(
            r"Cannot drop a user who is currently connected",
            re.IGNORECASE,
        ),
        re.compile(
            r"Invalid tablespace reference",
            re.IGNORECASE,
        ),
        re.compile(
            r"No privileges on the tablespace",
            re.IGNORECASE,
        ),
        re.compile(
            r"Numeric or value error",
            re.IGNORECASE,
        ),
        re.compile(
            r"obeject not found",
            re.IGNORECASE,
        ),
        re.compile(
            r"^\s*ERROR:\s*Unexpected error",
            re.IGNORECASE,
        ),
    )

    _SOFT_NOTE_PATTERNS = (
        re.compile(
            r"Column already exists in table",
            re.IGNORECASE,
        ),
        re.compile(
            r"Object already exists",
            re.IGNORECASE,
        ),
        re.compile(
            r"Unique or primary key already exists",
            re.IGNORECASE,
        ),
        re.compile(
            r"Name already used by an existing constraint",
            re.IGNORECASE,
        ),
        re.compile(
            r"Table can have only one primary key",
            re.IGNORECASE,
        ),
        re.compile(
            r"^\s*Failed\s*:",
            re.IGNORECASE,
        ),
        re.compile(
            r"^\s*ERROR\s*:",
            re.IGNORECASE,
        ),
        re.compile(
            r"^\s*Warning\s*:",
            re.IGNORECASE,
        ),
    )

    _DROP_BENIGN_PATTERNS = (
        re.compile(r"does not exist", re.IGNORECASE),
        re.compile(r"\bORA-0?2289\b"),
        re.compile(r"\bORA-0?0942\b"),
        re.compile(r"\bORA-0?1418\b"),
        re.compile(r"\bORA-0?4043\b"),
        re.compile(r"\bORA-0?1432\b"),
    )

    _DML_VERBS = {
        "created": "INSERT",
        "inserted": "INSERT",
        "updated": "UPDATE",
        "deleted": "DELETE",
        "merged": "MERGE",
    }

    _DDL_VERBS = {
        "created": "CREATE",
        "altered": "ALTER",
        "dropped": "DROP",
        "truncated": "TRUNCATE",
    }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(
        self,
        path: Path,
    ) -> dict[str, Any]:
        """
        Parse a deployment log.

        The returned structure is intentionally close to the source
        tool's intermediate representation. Reconciliation converts
        it into the plugin's immutable models.
        """

        try:
            lines = path.read_text(
                encoding="utf-8",
                errors="replace",
            ).splitlines()
        except OSError as exc:
            raise ValueError(
                f"Unable to read deployment log: {path}: {exc}",
            ) from exc

        sections = self.slice_sections(
            lines,
        )

        sections_map: dict[str, dict[str, Any]] = {}

        for name, start, end in sections:

            parsed = self._analyse_section(
                lines,
                start,
                end,
            )

            key = name.strip().casefold()

            if key in sections_map:
                self._merge_sections(
                    sections_map[key],
                    parsed,
                )
            else:
                sections_map[key] = parsed

        return {
            "sections": sections,
            "sections_map": sections_map,
        }

    # ------------------------------------------------------------------
    # Section discovery
    # ------------------------------------------------------------------

    def slice_sections(
        self,
        lines: list[str],
    ) -> list[tuple[str, int, int]]:
        """
        Slice the log into associate sections.

        Repeated start/end markers caused by SQLPlus echoing are
        treated as duplicate markers.
        """

        sections: list[tuple[str, int, int]] = []

        open_name: str | None = None
        open_normalized: str | None = None
        open_start: int | None = None

        for index, line in enumerate(lines):

            start_match = self._START_MARKER.search(
                line,
            )

            if start_match:

                name = start_match.group(
                    1,
                ).strip()

                normalized = name.casefold()

                if open_normalized is not None:

                    if normalized == open_normalized:
                        continue

                    if open_start is not None:
                        sections.append(
                            (
                                open_name or "",
                                open_start,
                                index,
                            ),
                        )

                open_name = name
                open_normalized = normalized
                open_start = index + 1

                continue

            end_match = self._END_MARKER.search(
                line,
            )

            if end_match and open_normalized is not None:

                if open_start is not None:
                    sections.append(
                        (
                            open_name or "",
                            open_start,
                            index,
                        ),
                    )

                open_name = None
                open_normalized = None
                open_start = None

        if open_normalized is not None and open_start is not None:

            sections.append(
                (
                    open_name or "",
                    open_start,
                    len(lines),
                ),
            )

        return sections

    # ------------------------------------------------------------------
    # Section parsing
    # ------------------------------------------------------------------

    def _analyse_section(
        self,
        lines: list[str],
        start: int,
        end: int,
    ) -> dict[str, Any]:
        """
        Parse one associate section.
        """

        actual_dml: Counter[str] = Counter()
        actual_ddl: Counter[str] = Counter()

        blocks_ok = 0
        blocks_clean = 0
        success = 0

        errors: list[ValidationError] = []
        notes: list[ValidationNote] = []

        per_file: defaultdict[str, dict[str, Any]] = defaultdict(
            self._new_file_bucket,
        )

        current_file = "(section)"
        hard_in_block = False
        pending_operation: str | None = None

        for index in range(
            start,
            end,
        ):
            line = lines[index].rstrip(
                "\n",
            )

            file_match = self._FILE_ECHO.search(
                line,
            )

            if file_match:

                current_file = file_match.group(
                    1,
                )

                self._touch_file(
                    per_file,
                    current_file,
                )

                hard_in_block = False
                pending_operation = None

                continue

            dml_match = self._DML_FEEDBACK.match(
                line,
            )

            if dml_match:

                verb = self._DML_VERBS[
                    dml_match.group(
                        2,
                    ).casefold(),
                ]

                actual_dml[verb] += 1
                per_file[current_file]["dml"][verb] += 1

                continue

            ddl_match = self._DDL_FEEDBACK.match(
                line,
            )

            if ddl_match:

                object_phrase = ddl_match.group(
                    1,
                ).upper()

                object_type = (
                    "VIEW"
                    if object_phrase.startswith(
                        "MATERIALIZED",
                    )
                    else object_phrase.split()[0]
                )

                verb = self._DDL_VERBS[
                    ddl_match.group(
                        2,
                    ).casefold(),
                ]

                key = f"{verb} {object_type}"

                actual_ddl[key] += 1
                per_file[current_file]["ddl"][key] += 1

                continue

            if self._PLSQL_OK.search(line):

                blocks_ok += 1

                per_file[current_file][
                    "blocks_ok"
                ] += 1

                if not hard_in_block:

                    blocks_clean += 1

                    per_file[current_file][
                        "blocks_clean"
                    ] += 1

                hard_in_block = False
                pending_operation = None

                continue

            if self._SUCCESS_LINE.match(line):

                success += 1

                per_file[current_file][
                    "success"
                ] += 1

                continue

            text = line.strip()

            if not text:
                continue

            failed_operation = self._FAILED_OPERATION.search(
                line,
            )

            if failed_operation:

                pending_operation = (
                    failed_operation.group(
                        1,
                    )
                    .strip()
                    .casefold()
                )

            hard = self._is_hard_error(
                line,
            )

            if (
                hard
                and pending_operation
                and "drop" in pending_operation
                and self._is_drop_benign(line)
            ):
                hard = False

            if hard:

                error = ValidationError(
                    file=current_file,
                    line=index + 1,
                    message=text,
                )

                errors.append(
                    error,
                )

                per_file[current_file][
                    "errors"
                ].append(
                    error,
                )

                hard_in_block = True

            elif self._is_soft_note(line) or failed_operation:

                note = ValidationNote(
                    file=current_file,
                    line=index + 1,
                    message=text,
                )

                notes.append(
                    note,
                )

                per_file[current_file][
                    "notes"
                ].append(
                    note,
                )

        return {
            "actual_dml": actual_dml,
            "actual_ddl": actual_ddl,
            "blocks_ok": blocks_ok,
            "blocks_clean": blocks_clean,
            "success": success,
            "errors": errors,
            "notes": notes,
            "per_file": dict(per_file),
        }

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    def _merge_sections(
        self,
        target: dict[str, Any],
        source: dict[str, Any],
    ) -> None:
        """
        Merge two sections belonging to the same associate.
        """

        target["actual_dml"].update(
            source["actual_dml"],
        )

        target["actual_ddl"].update(
            source["actual_ddl"],
        )

        target["blocks_ok"] += source[
            "blocks_ok"
        ]

        target["blocks_clean"] = (
            target.get(
                "blocks_clean",
                0,
            )
            + source.get(
                "blocks_clean",
                0,
            )
        )

        target["success"] += source[
            "success"
        ]

        target["errors"].extend(
            source["errors"],
        )

        target.setdefault(
            "notes",
            [],
        ).extend(
            source.get(
                "notes",
                [],
            ),
        )

        for file_name, file_data in source[
            "per_file"
        ].items():

            if file_name in target["per_file"]:

                existing = target[
                    "per_file"
                ][file_name]

                existing["dml"].update(
                    file_data["dml"],
                )

                existing["ddl"].update(
                    file_data["ddl"],
                )

                existing["errors"].extend(
                    file_data["errors"],
                )

                existing.setdefault(
                    "notes",
                    [],
                ).extend(
                    file_data.get(
                        "notes",
                        [],
                    ),
                )

                existing["blocks_ok"] += (
                    file_data["blocks_ok"]
                )

                existing["blocks_clean"] = (
                    existing.get(
                        "blocks_clean",
                        0,
                    )
                    + file_data.get(
                        "blocks_clean",
                        0,
                    )
                )

                existing["success"] += (
                    file_data["success"]
                )

            else:

                target["per_file"][
                    file_name
                ] = file_data

    # ------------------------------------------------------------------
    # Error classification
    # ------------------------------------------------------------------

    @classmethod
    def _is_hard_error(
        cls,
        line: str,
    ) -> bool:
        """
        Determine whether a log line represents a hard error.
        """

        return any(
            pattern.search(line)
            for pattern in cls._HARD_ERROR_PATTERNS
        )

    @classmethod
    def _is_soft_note(
        cls,
        line: str,
    ) -> bool:
        """
        Determine whether a log line is an advisory note.
        """

        return any(
            pattern.search(line)
            for pattern in cls._SOFT_NOTE_PATTERNS
        )

    @classmethod
    def _is_drop_benign(
        cls,
        line: str,
    ) -> bool:
        """
        Determine whether a DROP-related error is benign.
        """

        return any(
            pattern.search(line)
            for pattern in cls._DROP_BENIGN_PATTERNS
        )

    # ------------------------------------------------------------------
    # File buckets
    # ------------------------------------------------------------------

    @staticmethod
    def _new_file_bucket() -> dict[str, Any]:
        """
        Create an empty per-file parsing bucket.
        """

        return {
            "dml": Counter(),
            "ddl": Counter(),
            "errors": [],
            "notes": [],
            "blocks_ok": 0,
            "blocks_clean": 0,
            "success": 0,
        }

    @classmethod
    def _touch_file(
        cls,
        per_file: defaultdict[str, dict[str, Any]],
        file_name: str,
    ) -> None:
        """
        Ensure a file has a parsing bucket.
        """

        per_file[file_name]
