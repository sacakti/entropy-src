"""
SQLPlus spool configuration resolver.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..exceptions import GenericPluginError
from ..model import SpoolSettings


class SpoolSettingsResolver:
    """
    Resolve workflow spool configuration.
    """

    def resolve(
        self,
        value: Any,
    ) -> SpoolSettings:

        if value is None:
            return SpoolSettings()

        enabled = value.get(
            "enabled",
            False,
        )

        create_if_not_exists = value.get(
            "create_if_not_exists",
            True,
        )

        infile_replace = value.get(
            "infile_replace",
            False,
        )

        override = value.get(
            "override",
            False,
        )

        name_placeholder = value.get(
            "name_placeholder",
            "%execution_path/%release_%schema_%date.log",
        )

        wrappers_before = value.get(
            "wrappers_before",
            [],
        )

        wrappers_after = value.get(
            "wrappers_after",
            [],
        )

        if not isinstance(enabled, bool):
            raise GenericPluginError(
                "'spool.enabled' must be a boolean.",
            )

        if not isinstance(
            create_if_not_exists,
            bool,
        ):
            raise GenericPluginError(
                "'spool.create_if_not_exists' " "must be a boolean.",
            )

        if not isinstance(
            infile_replace,
            bool,
        ):
            raise GenericPluginError(
                "'spool.infile_replace' " "must be a boolean.",
            )

        if not isinstance(
            override,
            bool,
        ):
            raise GenericPluginError(
                "'spool.override' " "must be a boolean.",
            )

        if (
            not isinstance(
                name_placeholder,
                str,
            )
            or not name_placeholder.strip()
        ):

            raise GenericPluginError(
                "'spool.name_placeholder' " "must be a non-empty string.",
            )

        if not isinstance(
            wrappers_before,
            list,
        ) or not all(isinstance(item, str) for item in wrappers_before):
            raise GenericPluginError(
                "'spool.wrappers_before' " "must be a list of strings.",
            )

        if not isinstance(
            wrappers_after,
            list,
        ) or not all(isinstance(item, str) for item in wrappers_after):
            raise GenericPluginError(
                "'spool.wrappers_after' " "must be a list of strings.",
            )

        return SpoolSettings(
            enabled=enabled,
            create_if_not_exists=create_if_not_exists,
            name_placeholder=name_placeholder,
            infile_replace=infile_replace,
            override=override,
            wrappers_before=tuple(
                wrappers_before,
            ),
            wrappers_after=tuple(
                wrappers_after,
            ),
        )

    @staticmethod
    def resolve_path(
        pattern: str,
        *,
        execution_path: Path,
        release: str,
        schema: str,
    ) -> Path:

        value = pattern

        replacements = {
            "%execution_path": str(execution_path),
            "%release": release,
            "%schema": schema,
        }

        from datetime import datetime

        replacements["%date"] = datetime.now().strftime(
            "%Y-%m-%d",
        )

        for placeholder, replacement in replacements.items():
            value = value.replace(
                placeholder,
                replacement,
            )

        return Path(value)
