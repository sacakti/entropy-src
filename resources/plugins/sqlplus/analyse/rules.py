"""
Oracle SQL / SQLPlus analysis rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .model import (
    AnalyseFinding,
    AnalysePolicy,
    AnalyseStatement,
    AnalyseToken,
)


@dataclass(frozen=True)
class RuleContext:
    """
    Context required by analysis rules.
    """

    file: Path
    policy: AnalysePolicy


class AnalyseRules:
    """
    Detect configured SQL / SQLPlus policy violations.
    """

    _PLSQL_OBJECTS = {
        "PROCEDURE",
        "FUNCTION",
        "PACKAGE",
        "TRIGGER",
        "TYPE",
    }

    _SQLPLUS_COMMANDS = {
        "ACCEPT",
    }

    def analyse(
        self,
        statement: AnalyseStatement,
        context: RuleContext,
        next_statement: AnalyseStatement | None = None,
    ) -> tuple[AnalyseFinding, ...]:
        """
        Analyse a parsed statement.
        """

        findings: list[AnalyseFinding] = []

        findings.extend(
            self._check_action(
                statement,
                context,
            ),
        )

        findings.extend(
            self._check_hardcoded_schema(
                statement,
                context,
            ),
        )

        findings.extend(
            self._check_accept(
                statement,
                context,
            ),
        )

        findings.extend(
            self._check_plsql_terminator(
                statement,
                context,
                next_statement,
            ),
        )

        return tuple(findings)

    def _check_action(
        self,
        statement: AnalyseStatement,
        context: RuleContext,
    ) -> list[AnalyseFinding]:
        """
        Check INSERT, DELETE, DROP and TRUNCATE statements.
        """

        findings: list[AnalyseFinding] = []

        for token in statement.tokens:

            rule = self._action_rule(
                token,
            )

            if rule is None:
                continue

            severity = self._severity(
                rule,
                context.policy,
            )

            if severity is None:
                continue

            findings.append(
                AnalyseFinding(
                    rule=rule,
                    severity=severity,
                    message=(
                        f"Restricted SQL action "
                        f"'{token.value.upper()}' detected."
                    ),
                    file=context.file,
                    line=token.line,
                    column=token.column,
                ),
            )

        return findings

    @staticmethod
    def _action_rule(
        token: AnalyseToken,
    ) -> str | None:
        """
        Map a SQL action token to its configured rule.
        """

        value = token.value.casefold()

        token_type = token.token_type

        if value == "insert" and "Token.Keyword.DML" in token_type:
            return "insert"

        if value == "delete" and "Token.Keyword.DML" in token_type:
            return "delete"

        if value == "drop" and "Token.Keyword.DDL" in token_type:
            return "drop"

        if value == "truncate" and "Token.Keyword.DDL" in token_type:
            return "truncate"

        return None

    def _check_hardcoded_schema(
        self,
        statement: AnalyseStatement,
        context: RuleContext,
    ) -> list[AnalyseFinding]:
        """
        Detect schema-qualified object names such as APP1.USERS.
        """

        severity = self._severity(
            "hardcoded",
            context.policy,
        )

        if severity is None:
            return []

        tokens = statement.tokens
        findings: list[AnalyseFinding] = []

        for index in range(
            1,
            len(tokens) - 1,
        ):
            previous_token = tokens[index - 1]
            token = tokens[index]
            next_token = tokens[index + 1]

            if (
                token.value == "."
                and self._is_name(previous_token)
                and self._is_name(next_token)
            ):
                findings.append(
                    AnalyseFinding(
                        rule="hardcoded",
                        severity=severity,
                        message=(
                            "Hardcoded schema-qualified "
                            f"object '{previous_token.value}."
                            f"{next_token.value}' detected."
                        ),
                        file=context.file,
                        line=previous_token.line,
                        column=previous_token.column,
                    ),
                )

        return findings

    def _check_accept(
        self,
        statement: AnalyseStatement,
        context: RuleContext,
    ) -> list[AnalyseFinding]:
        """
        Detect SQLPlus ACCEPT commands.
        """

        severity = self._severity(
            "accept",
            context.policy,
        )

        if severity is None:
            return []

        for token in statement.tokens:

            if (
                token.value.casefold()
                == "accept"
            ):
                return [
                    AnalyseFinding(
                        rule="accept",
                        severity=severity,
                        message=(
                            "SQLPlus ACCEPT parameter "
                            "command detected."
                        ),
                        file=context.file,
                        line=token.line,
                        column=token.column,
                    ),
                ]

        return []

    def _check_plsql_terminator(
        self,
        statement: AnalyseStatement,
        context: RuleContext,
        next_statement: AnalyseStatement | None,
    ) -> list[AnalyseFinding]:
        """
        Detect PL/SQL objects that do not end with SQLPlus '/'.
        """

        severity = self._severity(
            "not_endwith_slash",
            context.policy,
        )

        if severity is None:
            return []

        if not self._is_plsql_statement(
            statement,
        ):
            return []

        if next_statement is not None:
            next_tokens = next_statement.tokens

            if any(
                token.value.strip() == "/"
                for token in next_tokens
            ):
                return []

        return [
            AnalyseFinding(
                rule="not_endwith_slash",
                severity=severity,
                message=(
                    "PL/SQL object does not end "
                    "with a SQLPlus '/' terminator."
                ),
                file=context.file,
                line=statement.line,
                column=statement.column,
            ),
        ]

    def _is_plsql_statement(
        self,
        statement: AnalyseStatement,
    ) -> bool:
        """
        Determine whether a statement defines a PL/SQL object.
        """

        tokens = statement.tokens

        for index, token in enumerate(tokens):

            if token.value.casefold() != "create":
                continue

            for following in tokens[index + 1 :]:
                value = following.value.upper()

                if value in self._PLSQL_OBJECTS:
                    return True

                if value in {
                    ";",
                    "/",
                }:
                    break

        return False

    @staticmethod
    def _is_name(
        token: AnalyseToken,
    ) -> bool:
        """
        Determine whether a token represents an identifier.
        """

        return token.token_type.startswith(
            "Token.Name",
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
