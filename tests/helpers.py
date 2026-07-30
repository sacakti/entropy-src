"""
Testing helper functions.
"""

from __future__ import annotations

from pathlib import Path

from lib.models.users import User


def write_file(
    path: Path,
    content: str,
) -> Path:
    """
    Write a file and return its path.
    """

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        content,
        encoding="utf-8",
    )

    return path


def make_user(
    username: str = "admin",
) -> User:
    return User(
        username=username,
        password_hash="hash",
        full_name="Administrator",
        email="admin@test.com",
    )
