"""
Automatic version bumps for definitions edited in the web UI.
"""

from __future__ import annotations

import re

_LAST_NUMBER = re.compile(r"(\d+)(?!.*\d)")


def bump_version(version: str) -> str:
    """
    Increment the last number of a version: 1.0.0 -> 1.0.1, 2.3 -> 2.4,
    1.0.0-rc1 -> 1.0.0-rc2. A version without digits gets ".1" appended.
    """

    text = (version or "").strip() or "1.0.0"
    match = _LAST_NUMBER.search(text)

    if match is None:
        return text + ".1"

    number = str(int(match.group(1)) + 1).zfill(len(match.group(1)))
    return text[: match.start(1)] + number + text[match.end(1) :]
