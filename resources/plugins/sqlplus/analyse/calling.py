"""
SQLPlus calling-script analysis.
"""

from __future__ import annotations

from pathlib import Path

from .model import (
    AnalyseFinding,
    AnalysePolicy,
)


class CallingScriptAnalyzer:
    """
    Analyse SQLPlus calling scripts.
    """

    def analyse(
        self,
        script: Path,
        policy: AnalysePolicy,
    ) -> tuple[AnalyseFinding, ...]:
        """
        Analyse a SQLPlus calling script.
        """

        content = script.read_text(
            encoding="utf-8",
        )

        lines = content.splitlines()

        findings: list[AnalyseFinding] = []

        findings.extend(
            self._check_script_calls(
                script,
                lines,
                policy,
            ),
        )

        findings.extend(
            self._check_spool(
                script,
                lines,
                policy,
            ),
        )

        return tuple(findings)

    def _check_script_calls(
        self,
        script: Path,
        lines: list[str],
        policy: AnalysePolicy,
    ) -> list[AnalyseFinding]:
        """
        Validate SQLPlus script references.
        """

        findings: list[AnalyseFinding] = []

        for line_number, line in enumerate(
            lines,
            start=1,
        ):
            stripped = line.strip()

            if not stripped:
                continue

            if stripped.startswith("--"):
                continue

            if not self._looks_like_script_reference(
                stripped,
            ):
                continue

            if not stripped.startswith("@"):
                finding = self._finding(
                    rule="calling_script_at_prefix",
                    message=(
                        "Calling script reference should "
                        "start with '@'."
                    ),
                    script=script,
                    line=line_number,
                    column=(
                        len(line)
                        - len(line.lstrip())
                        + 1
                    ),
                    policy=policy,
                )

                if finding is not None:
                    findings.append(finding)

                continue

            reference = self._extract_reference(
                stripped,
            )

            if not reference:
                continue

            column = (
                len(line)
                - len(line.lstrip())
                + 1
            )

            findings.extend(
                self._validate_reference(
                    script=script,
                    reference=reference,
                    line=line_number,
                    column=column,
                    policy=policy,
                ),
            )

            if not stripped.endswith(";"):
                finding = self._finding(
                    rule="calling_script_semicolon",
                    message=(
                        "Calling script reference should "
                        "end with ';'."
                    ),
                    script=script,
                    line=line_number,
                    column=column,
                    policy=policy,
                )

                if finding is not None:
                    findings.append(finding)

        return findings

    def _validate_reference(
        self,
        script: Path,
        reference: str,
        line: int,
        column: int,
        policy: AnalysePolicy,
    ) -> list[AnalyseFinding]:
        """
        Validate a referenced SQLPlus script.
        """

        reference_path = self._resolve_reference(
            script,
            reference,
        )

        if reference_path is not None:
            return []

        finding = self._finding(
            rule="referenced_script_not_found",
            message=(
                f"Referenced script "
                f"'{reference}' does not exist."
            ),
            script=script,
            line=line,
            column=column,
            policy=policy,
        )

        if finding is None:
            return []

        return [finding]

    @staticmethod
    def _resolve_reference(
        script: Path,
        reference: str,
    ) -> Path | None:
        """
        Resolve a calling-script reference.
        """

        value = reference.strip()

        if value.endswith(";"):
            value = value[:-1].rstrip()

        if not value:
            return None

        reference_path = Path(value)

        if not reference_path.is_absolute():
            reference_path = (
                script.parent / reference_path
            )

        if reference_path.is_file():
            return reference_path

        if reference_path.suffix == "":
            sql_path = reference_path.with_suffix(
                ".sql",
            )

            if sql_path.is_file():
                return sql_path

        return None

    def _check_spool(
        self,
        script: Path,
        lines: list[str],
        policy: AnalysePolicy,
    ) -> list[AnalyseFinding]:
        """
        Validate SQLPlus SPOOL usage.
        """

        findings: list[AnalyseFinding] = []

        spool_active = False

        meaningful_lines = [
            (line_number, line)
            for line_number, line in enumerate(
                lines,
                start=1,
            )
            if line.strip()
            and not line.strip().startswith("--")
        ]

        for index, (line_number, line) in enumerate(
            meaningful_lines,
        ):
            if self._is_spool_off(line):
                if not spool_active:
                    finding = self._finding(
                        rule="spool_off_without_spool",
                        message=(
                            "SPOOL OFF was found without "
                            "an active SPOOL session."
                        ),
                        script=script,
                        line=line_number,
                        column=self._column(line),
                        policy=policy,
                    )

                    if finding is not None:
                        findings.append(finding)

                spool_active = False

                if index != len(meaningful_lines) - 1:
                    finding = self._finding(
                        rule="spool_not_at_end",
                        message=(
                            "SPOOL OFF should be the "
                            "final meaningful command."
                        ),
                        script=script,
                        line=line_number,
                        column=self._column(line),
                        policy=policy,
                    )

                    if finding is not None:
                        findings.append(finding)

                continue

            command = self._sqlplus_command(line)

            if command != "SPOOL":
                continue

            if spool_active:
                finding = self._finding(
                    rule="spool_already_active",
                    message=(
                        "SPOOL was started while "
                        "another SPOOL session is active."
                    ),
                    script=script,
                    line=line_number,
                    column=self._column(line),
                    policy=policy,
                )

                if finding is not None:
                    findings.append(finding)

            spool_active = True

        if spool_active and meaningful_lines:
            line_number, _ = meaningful_lines[-1]

            finding = self._finding(
                rule="spool_not_closed",
                message=(
                    "SPOOL was started but "
                    "SPOOL OFF was not found."
                ),
                script=script,
                line=line_number,
                column=1,
                policy=policy,
            )

            if finding is not None:
                findings.append(finding)

        return findings

    @staticmethod
    def _looks_like_script_reference(
        line: str,
    ) -> bool:
        """
        Determine whether a line appears to reference a script.
        """

        value = line.strip()

        if value.startswith("@"):
            return True

        lower = value.casefold()

        return (
            lower.endswith(".sql")
            or lower.endswith(".prc")
            or lower.endswith(".fnc")
            or lower.endswith(".pck")
            or lower.endswith(".trg")
            or lower.endswith(".vw")
        )

    @staticmethod
    def _extract_reference(
        line: str,
    ) -> str:
        """
        Extract the referenced script from an @ or @@ command.
        """

        value = line.strip()

        if value.startswith("@@"):
            value = value[2:].strip()
        elif value.startswith("@"):
            value = value[1:].strip()
        else:
            return ""

        return value

    @staticmethod
    def _sqlplus_command(
        line: str,
    ) -> str:
        """
        Extract the first SQLPlus command.
        """

        value = line.strip()

        if not value:
            return ""

        parts = value.split(
            maxsplit=1,
        )

        return parts[0].rstrip(";").upper()

    @staticmethod
    def _is_spool_off(
        line: str,
    ) -> bool:
        """
        Determine whether a line is SPOOL OFF.
        """

        normalized = " ".join(
            line.strip().split(),
        )

        normalized = normalized.rstrip(";").upper()

        return normalized == "SPOOL OFF"

    @staticmethod
    def _column(
        line: str,
    ) -> int:
        """
        Return the first meaningful column in a line.
        """

        return (
            len(line)
            - len(line.lstrip())
            + 1
        )

    @staticmethod
    def _finding(
        rule: str,
        message: str,
        script: Path,
        line: int,
        column: int,
        policy: AnalysePolicy,
    ) -> AnalyseFinding | None:
        """
        Create a finding using the configured policy severity.
        """

        severity = CallingScriptAnalyzer._severity(
            rule,
            policy,
        )

        if severity is None:
            return None

        return AnalyseFinding(
            rule=rule,
            severity=severity,
            message=message,
            file=script,
            line=line,
            column=column,
        )

    @staticmethod
    def _severity(
        rule: str,
        policy: AnalysePolicy,
    ) -> str | None:
        """
        Resolve the configured severity for a rule.
        """

        if rule in policy.stop:
            return "stop"

        if rule in policy.error:
            return "error"

        if rule in policy.warning:
            return "warning"

        return None
