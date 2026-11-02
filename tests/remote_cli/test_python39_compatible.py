"""The `ent` client runs on users' own Python: it must stay Python 3.9 compatible."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

CLIENT = Path(__file__).resolve().parents[2] / "lib" / "remote_cli"


@pytest.mark.parametrize("path", sorted(CLIENT.rglob("*.py")), ids=lambda path: path.name)
def test_client_parses_as_python_39(path: Path) -> None:
    # feature_version rejects syntax newer than 3.9 (match, except*, parenthesized with, ...).
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 9))
