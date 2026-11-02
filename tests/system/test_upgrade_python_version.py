"""Release upgrades refuse byte code for another Python unless the package brings it."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from lib.system import upgrade
from lib.system.upgrade import ReleaseUpgrader

RUNNING = f"{sys.version_info[0]}.{sys.version_info[1]}"
OTHER = "3.99"


def _upgrader(tmp_path: Path, python: Path) -> ReleaseUpgrader:
    upgrader = ReleaseUpgrader.__new__(ReleaseUpgrader)
    upgrader.root = tmp_path / "entropy"
    upgrader.record = {"python": str(python)}
    return upgrader


@pytest.fixture(autouse=True)
def installed(tmp_path: Path, monkeypatch) -> None:
    record = tmp_path / "install.json"
    record.write_text("{}")
    monkeypatch.setattr(upgrade.install, "record_path", lambda: record)


def test_same_python_is_fine(tmp_path: Path) -> None:
    upgrader = _upgrader(tmp_path, tmp_path / "entropy" / "python" / "bin" / "python3")
    assert upgrader._python_problems({"bytecode_python": RUNNING, "upgrade_only": True}) == []
    assert upgrader._python_problems({}) == []  # packages from before bytecode_python


def test_full_package_brings_its_python_to_bundled_installs(tmp_path: Path) -> None:
    upgrader = _upgrader(tmp_path, tmp_path / "entropy" / "python" / "bin" / "python3")
    manifest = {"bytecode_python": OTHER, "python": f"{OTHER}.1", "upgrade_only": False}
    assert upgrader._python_problems(manifest) == []


def test_code_only_package_for_another_python_is_refused(tmp_path: Path) -> None:
    upgrader = _upgrader(tmp_path, tmp_path / "entropy" / "python" / "bin" / "python3")
    [problem] = upgrader._python_problems({"bytecode_python": OTHER, "upgrade_only": True})
    assert f"needs Python {OTHER}" in problem and "full release package" in problem


def test_own_python_installs_cannot_take_another_python(tmp_path: Path) -> None:
    upgrader = _upgrader(tmp_path, Path("/usr/bin/python3"))
    manifest = {
        "bytecode_python": OTHER,
        "python": f"{OTHER}.1",
        "upgrade_only": False,
        "version": "2.0",
    }
    [problem] = upgrader._python_problems(manifest)
    assert "its own Python" in problem and "--python" in problem
