"""
Properties updater.
"""

from __future__ import annotations

from typing import Any, Iterator

from lib.executor.yaml_comments import read_mapping_comments


class PropertiesUpdater:
    """
    Update simple Java-style properties content.

    Comments, blank lines, unmanaged properties, indentation, and the
    separator style of updated properties are preserved.

    Comments written around the entries in a YAML source are carried into
    the properties content. Plain mappings have no comments and add none.
    """

    def update(
        self,
        content: str,
        entries: dict[str, Any],
    ) -> tuple[str, list[dict[str, str]]]:
        """
        Update existing properties and add missing properties.

        Comments preceding an entry in the source are written directly above
        its property, unless already there, so repeated runs add nothing.

        Returns the updated content and per-key change information.
        """

        lines = content.splitlines(
            keepends=True,
        )

        existing_comments = {line.strip() for line in lines if self._is_comment(line)}

        comments, trailing = read_mapping_comments(
            entries,
        )

        updated: set[str] = set()
        result: list[str] = []
        changes: list[dict[str, str]] = []

        for statement in self._statements(
            lines,
        ):

            parsed = self._parse(
                statement[0],
            )

            if parsed is None or parsed[0] not in entries:

                result.extend(
                    statement,
                )

                continue

            key, prefix = parsed

            self._insert_comments(
                result,
                comments.pop(key, []),
                prefix[: len(prefix) - len(prefix.lstrip())],
                self._line_ending(statement[-1]) or self._newline(lines),
            )

            result.append(
                f"{prefix}" f"{self._format(entries[key])}" f"{self._line_ending(statement[-1])}",
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

            self._insert_comments(
                result,
                comments.pop(key, []),
                "",
                newline,
            )

            result.append(
                f"{key}={self._format(value)}{newline}",
            )

            changes.append(
                {
                    "key": key,
                    "status": "added",
                },
            )

        # Trailing comments follow no property, so nothing marks their place on
        # a later run: the whole content decides whether they are already there.
        missing = [line for line in trailing if line not in existing_comments]

        if missing:

            if result and not result[-1].endswith(
                (
                    "\n",
                    "\r",
                ),
            ):

                result[-1] += newline

            result.extend(f"{line}{newline}" for line in missing)

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

        for statement in self._statements(
            content.splitlines(
                keepends=True,
            ),
        ):

            parsed = self._parse(
                statement[0],
            )

            if parsed is None or parsed[0] not in requested:

                result.extend(
                    statement,
                )

                continue

            key = parsed[0]

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

    @staticmethod
    def _line_ending(
        line: str,
    ) -> str:

        if line.endswith(
            "\r\n",
        ):

            return "\r\n"

        return "\n" if line.endswith("\n") else ""

    # ------------------------------------------------------------------
    # Source comments
    # ------------------------------------------------------------------

    @classmethod
    def _insert_comments(
        cls,
        result: list[str],
        comments: list[str],
        indent: str,
        newline: str,
    ) -> None:
        """
        Append comment lines missing from the block directly above this point.
        """

        present: set[str] = set()

        for line in reversed(result):

            if not cls._is_comment(line):
                break

            present.add(
                line.strip(),
            )

        result.extend(f"{indent}{line}{newline}" for line in comments if line not in present)

    # ------------------------------------------------------------------
    # Value
    # ------------------------------------------------------------------

    @staticmethod
    def _format(
        value: Any,
    ) -> str:
        """
        Render a YAML/JSON scalar as properties text.

        Python's str() would turn YAML true into "True" and null into "None".
        """

        if isinstance(
            value,
            bool,
        ):

            return "true" if value else "false"

        return "" if value is None else str(value)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _is_comment(
        line: str,
    ) -> bool:

        return line.lstrip().startswith(("#", "!"))

    @staticmethod
    def _is_comment_or_blank(
        line: str,
    ) -> bool:

        stripped = line.strip()

        return not stripped or stripped.startswith(("#", "!"))

    @classmethod
    def _statements(
        cls,
        lines: list[str],
    ) -> Iterator[list[str]]:
        """
        Group physical lines into logical lines.

        A line ending in an odd number of backslashes continues on the next
        line, so continuation text is never mistaken for a property. Comments
        do not continue.
        """

        statement: list[str] = []

        for line in lines:

            statement.append(
                line,
            )

            if len(statement) == 1 and cls._is_comment_or_blank(
                line,
            ):

                yield statement

                statement = []

                continue

            text = line.rstrip(
                "\r\n",
            )

            trailing = len(text) - len(text.rstrip("\\"))

            if trailing % 2 == 0:

                yield statement

                statement = []

        if statement:

            yield statement

    @classmethod
    def _parse(
        cls,
        line: str,
    ) -> tuple[str, str] | None:
        """
        Split a property line into its key and the text before its value.

        The prefix keeps the indentation and separator exactly as written,
        such as "key=", "key = ", "key: " or "key ". Returns None for comments
        and blank lines.
        """

        if cls._is_comment_or_blank(
            line,
        ):

            return None

        text = line.rstrip(
            "\r\n",
        )

        start = len(text) - len(text.lstrip())

        index = start

        escaped = False

        while index < len(text):

            char = text[index]

            if escaped:

                escaped = False

            elif char == "\\":

                escaped = True

            elif char in {"=", ":"} or char.isspace():

                break

            index += 1

        key = text[start:index]

        # Key-only line: the value needs a separator to attach to.
        if index == len(text):

            return (
                key,
                f"{text} ",
            )

        end = index

        while end < len(text) and text[end].isspace():

            end += 1

        if end < len(text) and text[end] in {"=", ":"}:

            end += 1

            while end < len(text) and text[end].isspace():

                end += 1

        return (
            key,
            text[:end],
        )
