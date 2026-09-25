"""
SQLPlus spool wrapper generation and detection.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from ..model import SpoolSettings

_ACTIVE_SPOOL_PATTERN = re.compile(
    r"^\s*SPOOL\s+(?!OFF\b)(.+?)\s*;?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_SPOOL_COMMAND_PATTERN = re.compile(
    r"^\s*SPOOL\b.*$",
    re.IGNORECASE | re.MULTILINE,
)


class SpoolScriptBuilder:
    """
    Build SQLPlus spool wrapper scripts and detect
    existing spool commands.
    """

    @staticmethod
    def detect_spool(
        script: Path,
    ) -> Path | None:
        """
        Detect an active SPOOL command and resolve its path.
        """

        content = script.read_text(
            encoding="utf-8",
        )

        match = _ACTIVE_SPOOL_PATTERN.search(
            content,
        )

        if match is None:
            return None

        value = match.group(1).strip()

        if not value:
            return None

        spool_path = Path(value)

        if not spool_path.is_absolute():
            spool_path = script.parent / spool_path

        return spool_path

    @staticmethod
    def is_valid_spool(
        spool_path: Path,
    ) -> bool:
        """
        Determine whether a spool path can be used.
        """

        if spool_path.exists():

            return spool_path.is_file() and os.access(
                spool_path,
                os.W_OK,
            )

        parent = spool_path.parent

        if not parent.exists():
            return False

        if not parent.is_dir():
            return False

        return os.access(
            parent,
            os.W_OK,
        )

    @staticmethod
    def replace_spool(
        script: Path,
        spool_path: Path,
    ) -> Path:
        """
        Replace the active SPOOL target in the original script.
        """

        content = script.read_text(
            encoding="utf-8",
        )

        def replace(
            match: re.Match[str],
        ) -> str:
            return f"SPOOL {spool_path}"

        content = _ACTIVE_SPOOL_PATTERN.sub(
            replace,
            content,
            count=1,
        )

        script.write_text(
            content,
            encoding="utf-8",
        )

        return script

    def build(
        self,
        *,
        script: Path,
        spool_path: Path,
        settings: SpoolSettings,
        destination: Path,
    ) -> Path:
        """
        Create a SQLPlus wrapper script.
        """

        lines: list[str] = []

        lines.extend(
            settings.wrappers_before,
        )

        lines.append(
            f"SPOOL {spool_path}",
        )

        lines.append("")

        lines.append(
            f"@{script}",
        )

        lines.append("")

        lines.extend(
            settings.wrappers_after,
        )

        content = "\n".join(lines) + "\n"

        destination.write_text(
            content,
            encoding="utf-8",
        )

        return destination
