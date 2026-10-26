"""
Keep vault secrets out of run messages.

Values a run reads from the vault are registered with the run; messages
plugins emit have them replaced by a mask. Plain string entries are secret
as a whole; in JSON objects, fields whose names look secret (password,
token, key, ...) are, so hosts and user names stay readable.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, List, Optional, Set

MASK = "••••••"
SECRET_KEY = re.compile(r"pass|secret|token|key|credential|pwd|auth|private", re.IGNORECASE)
# Shorter values would mask ordinary words.
MIN_LENGTH = 4


def secret_values(value: Any, key: Optional[str] = None) -> List[str]:
    """The strings in `value` to mask."""

    if isinstance(value, str):
        secret = key is None or SECRET_KEY.search(key) is not None
        return [value] if secret and len(value) >= MIN_LENGTH else []
    if isinstance(value, dict):
        found: List[str] = []
        for name, item in value.items():
            found.extend(secret_values(item, str(name)))
        return found
    if isinstance(value, (list, tuple)):
        found = []
        for item in value:
            found.extend(secret_values(item, key))
        return found
    return []


def mask(text: str, secrets: Iterable[str]) -> str:
    """`text` with every known secret replaced, longest first."""

    for secret in sorted(set(secrets), key=len, reverse=True):
        if secret and secret in text:
            text = text.replace(secret, MASK)
    return text


def register(secrets: Optional[Set[str]], value: Any) -> None:
    if secrets is not None:
        secrets.update(secret_values(value))
