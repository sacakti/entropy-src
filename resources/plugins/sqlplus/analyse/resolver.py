"""
SQL analysis configuration resolver.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .exceptions import AnalysePluginException
from .model import AnalysePolicy


class AnalyseResolver:
    """
    Resolve and validate SQL analysis configuration.
    """

    DEFAULT_EXTENSIONS = (
        ".sql",
    )

    SUPPORTED_RULES = frozenset(
        {
            "insert",
            "drop",
            "truncate",
            "delete",
            "hardcoded",
            "not_endwith_slash",
            "accept",
            "calling_script_at_prefix",
            "calling_script_semicolon",
            "referenced_script_not_found",
            "spool_not_at_end",
            "spool_off_without_spool",
            "spool_already_active",
            "spool_not_closed",
        },
    )

    def resolve_path(
        self,
        value: Any,
    ) -> Path:
        """
        Resolve the analysis path.
        """

        if not isinstance(
            value,
            (str, Path),
        ):
            raise AnalysePluginException(
                "'path' must be a string.",
            )

        path = Path(value)

        if not path.exists():
            raise AnalysePluginException(
                f"Analysis path does not exist: {path}",
            )

        if not path.is_dir():
            raise AnalysePluginException(
                f"Analysis path is not a directory: {path}",
            )

        return path

    def resolve_extensions(
        self,
        value: Any,
    ) -> tuple[str, ...]:
        """
        Resolve file extensions.
        """

        if value is None:
            return self.DEFAULT_EXTENSIONS

        if not isinstance(
            value,
            list,
        ):
            raise AnalysePluginException(
                "'extensions' must be a list of strings.",
            )

        extensions: list[str] = []

        for extension in value:

            if not isinstance(
                extension,
                str,
            ):
                raise AnalysePluginException(
                    "'extensions' must contain only strings.",
                )

            extension = extension.strip().casefold()

            if not extension:
                raise AnalysePluginException(
                    "'extensions' cannot contain empty values.",
                )

            if not extension.startswith("."):
                raise AnalysePluginException(
                    f"Invalid file extension '{extension}'. "
                    "Extensions must start with '.'.",
                )

            if extension not in extensions:
                extensions.append(
                    extension,
                )

        if not extensions:
            raise AnalysePluginException(
                "'extensions' must contain at least one extension.",
            )

        return tuple(extensions)

    def resolve_policy(
        self,
        value: Any,
    ) -> AnalysePolicy:
        """
        Resolve the analysis policy.
        """

        if value is None:
            return AnalysePolicy()

        if not isinstance(
            value,
            dict,
        ):
            raise AnalysePluginException(
                "'policy' must be an object.",
            )

        warning = self._resolve_rules(
            value.get(
                "warning",
                [],
            ),
            "warning",
        )

        error = self._resolve_rules(
            value.get(
                "error",
                [],
            ),
            "error",
        )

        stop = self._resolve_rules(
            value.get(
                "stop",
                [],
            ),
            "stop",
        )

        self._validate_rule_conflicts(
            warning=warning,
            error=error,
            stop=stop,
        )

        return AnalysePolicy(
            warning=warning,
            error=error,
            stop=stop,
        )

    def _resolve_rules(
        self,
        value: Any,
        severity: str,
    ) -> tuple[str, ...]:
        """
        Resolve rules assigned to a severity.
        """

        if not isinstance(
            value,
            list,
        ):
            raise AnalysePluginException(
                f"'policy.{severity}' must be a list of strings.",
            )

        rules: list[str] = []

        for rule in value:

            if not isinstance(
                rule,
                str,
            ):
                raise AnalysePluginException(
                    f"'policy.{severity}' must contain "
                    "only strings.",
                )

            rule = rule.strip().casefold()

            if not rule:
                raise AnalysePluginException(
                    f"'policy.{severity}' cannot contain "
                    "empty values.",
                )

            if rule not in self.SUPPORTED_RULES:
                raise AnalysePluginException(
                    f"Unsupported analysis rule '{rule}'.",
                )

            if rule not in rules:
                rules.append(
                    rule,
                )

        return tuple(rules)

    @staticmethod
    def _validate_rule_conflicts(
        *,
        warning: tuple[str, ...],
        error: tuple[str, ...],
        stop: tuple[str, ...],
    ) -> None:
        """
        Ensure a rule has only one severity.
        """

        assignments: dict[str, str] = {}

        for severity, rules in (
            ("warning", warning),
            ("error", error),
            ("stop", stop),
        ):

            for rule in rules:

                previous = assignments.get(
                    rule,
                )

                if previous is not None:
                    raise AnalysePluginException(
                        f"Analysis rule '{rule}' is configured "
                        f"as both '{previous}' and '{severity}'.",
                    )

                assignments[rule] = severity
