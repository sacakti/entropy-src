"""Linking artifacts to a release: the browser's search, newest-first order and pages."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_finding_artifacts() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed.")
    version = subprocess.run([node, "--version"], capture_output=True, text=True, check=True).stdout
    if int(version.lstrip("v").split(".")[0]) < 23:
        pytest.skip("This Node cannot run TypeScript directly.")
    script = Path(__file__).parent / "release_artifact_search.mts"
    result = subprocess.run([node, "--no-warnings", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
