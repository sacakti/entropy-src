"""
Read and write the comments around the keys of a YAML mapping.

Comments survive round-trip loading on the mapping itself, in a form specific to
the YAML library. These helpers exchange them as plain lines, keyed by the
property each one precedes, so callers do not depend on that form.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.error import CommentMark
from ruamel.yaml.tokens import CommentToken


def read_mapping_comments(
    mapping: Dict[Any, Any],
) -> Tuple[Dict[Any, List[str]], List[str]]:
    """
    Return the comment lines preceding each key, and those after the last key.

    YAML attaches a comment to the key before it, so each one moves forward to
    the key it precedes. An inline comment stays with its own key. Comments
    indented less than the keys belong to whatever follows the mapping and are
    ignored. A mapping that was not round-trip loaded has no comments.
    """

    annotations = getattr(
        mapping,
        "ca",
        None,
    )

    if annotations is None:

        return {}, []

    leading = annotations.comment[1] if annotations.comment else None

    pending = [token.value.strip() for token in leading or []]

    column = mapping.lc.col or 0  # type: ignore[attr-defined]

    comments: Dict[Any, List[str]] = {}

    for key in mapping:

        comments[key] = pending

        pending = []

        token = annotations.items.get(key, [None] * 3)[2]

        if token is None:
            continue

        inline, *following = token.value.split("\n")

        if inline.strip():

            comments[key].append(
                inline.strip(),
            )

        pending = [
            line.strip()
            for line in following
            if line.strip() and len(line) - len(line.lstrip()) >= column
        ]

    return comments, pending


def mapping_with_comments(
    mapping: Dict[Any, Any],
    comments: Dict[Any, List[str]],
    trailing: List[str],
    column: int,
) -> Dict[Any, Any]:
    """
    Return `mapping` carrying comment lines, as `read_mapping_comments` gives them.

    `column` is where the keys are written: `read_mapping_comments` ignores
    comments indented less than the keys. A mapping with no comments is returned
    unchanged.
    """

    keys = list(
        mapping,
    )

    if not any(comments.get(key) for key in keys) and not trailing:

        return mapping

    result = CommentedMap(
        mapping,
    )

    if keys and comments.get(keys[0]):

        result.ca.comment = [
            None,
            [
                CommentToken(
                    f"{line}\n",
                    CommentMark(column),
                    None,
                )
                for line in comments[keys[0]]
            ],
        ]

    indent = " " * column

    for index, key in enumerate(keys):

        following = comments.get(keys[index + 1], []) if index + 1 < len(keys) else trailing

        if following:

            # A leading line break keeps the comment off the line of the value.
            lines = "".join(f"{indent}{line}\n" for line in following)

            result.ca.items[key] = [
                None,
                None,
                CommentToken(
                    f"\n{lines}",
                    CommentMark(column),
                    None,
                ),
                None,
            ]

    return result
