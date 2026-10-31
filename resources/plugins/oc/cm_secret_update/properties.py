"""
Properties updater.
"""

from __future__ import annotations

from typing import Any


class PropertiesUpdater:
    """
    Update simple Java-style properties content.
    """

    def update(
        self,
        content: str,
        entries: dict[str, Any],
    ) -> tuple[str, list[dict[str, str]]]:
        """
        Update existing properties and add missing properties.

        Returns the updated content and per-key change information.
        """

        lines = content.splitlines(
            keepends=True,
        )

        updated: set[str] = set()
        result: list[str] = []
        changes: list[dict[str, str]] = []

        for line in lines:

            stripped = line.strip()

            if not stripped or stripped.startswith("#") or stripped.startswith("!"):

                result.append(
                    line,
                )

                continue

            separator = self._separator(
                line,
            )

            if separator is None:

                result.append(
                    line,
                )

                continue

            key, _, _ = line.partition(
                separator,
            )

            key = key.strip()

            if key not in entries:

                result.append(
                    line,
                )

                continue

            newline = "\n"

            if line.endswith(
                "\r\n",
            ):

                newline = "\r\n"

            elif not line.endswith(
                "\n",
            ):

                newline = ""

            result.append(
                f"{key}{separator}" f"{entries[key]}" f"{newline}",
            )

            updated.add(
                key,
            )

            changes.append(
                {
                    "key": key,
                    "status": "updated",
                },
            )

        newline = self._newline(
            lines,
        )

        for key, value in entries.items():

            if key in updated:
                continue

            # The last existing line may lack a line break; without one the
            # appended property would be glued onto it.
            if result and not result[-1].endswith(
                (
                    "\n",
                    "\r",
                ),
            ):

                result[-1] += newline

            result.append(
                f"{key}={value}{newline}",
            )

            changes.append(
                {
                    "key": key,
                    "status": "added",
                },
            )

        return (
            "".join(result),
            changes,
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(
        self,
        content: str,
        keys: list[str],
    ) -> tuple[str, list[dict[str, str]]]:
        """
        Delete properties from content.

        Missing properties are ignored and reported as unchanged.
        """

        requested = set(
            keys,
        )

        deleted: set[str] = set()
        result: list[str] = []
        changes: list[dict[str, str]] = []

        for line in content.splitlines(
            keepends=True,
        ):

            stripped = line.strip()

            if not stripped or stripped.startswith("#") or stripped.startswith("!"):

                result.append(
                    line,
                )

                continue

            separator = self._separator(
                line,
            )

            if separator is None:

                result.append(
                    line,
                )

                continue

            key, _, _ = line.partition(
                separator,
            )

            key = key.strip()

            if key not in requested:

                result.append(
                    line,
                )

                continue

            deleted.add(
                key,
            )

            changes.append(
                {
                    "key": key,
                    "status": "deleted",
                },
            )

        for key in keys:

            if key in deleted:
                continue

            changes.append(
                {
                    "key": key,
                    "status": "unchanged_missing",
                },
            )

        return (
            "".join(result),
            changes,
        )

    # ------------------------------------------------------------------
    # Newline
    # ------------------------------------------------------------------

    @staticmethod
    def _newline(
        lines: list[str],
    ) -> str:

        for line in lines:

            if line.endswith(
                "\r\n",
            ):

                return "\r\n"

            if line.endswith(
                "\n",
            ):

                return "\n"

        return "\n"

    # ------------------------------------------------------------------
    # Separator
    # ------------------------------------------------------------------

    @staticmethod
    def _separator(
        line: str,
    ) -> str | None:

        escaped = False

        for char in line:

            if escaped:

                escaped = False

                continue

            if char == "\\":
                escaped = True

                continue

            if char in {
                "=",
                ":",
            }:

                return char

            if char.isspace():

                return " "

        return None
