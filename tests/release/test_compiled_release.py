"""Releases ship byte code instead of Python sources."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from lib.install.application import _ignore_caches
from lib.nodes.packaging import _files
from scripts.release import compile_application, keeps_source


def _tree(root: Path) -> Path:
    application = root / "application"
    files = {
        "entropy.py": "from core.app import main\nmain()\n",
        "core/__init__.py": "",
        "core/app.py": (
            "from lib.util import answer\n\ndef main():\n    print('answer', answer())\n"
        ),
        "lib/__init__.py": "",
        "lib/util.py": "def answer():\n    return 42\n",
        "lib/install/__init__.py": "",
        "lib/install/cli.py": "print('installer')\n",
        "lib/remote_cli/__init__.py": "",
        "lib/remote_cli/api.py": "CLIENT = True\n",
    }
    for name, text in files.items():
        path = application / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return application


def test_sources_are_replaced_by_byte_code(tmp_path) -> None:
    application = _tree(tmp_path)
    assert compile_application(application, sys.executable) == 5
    remaining = sorted(p.relative_to(application).as_posix() for p in application.rglob("*.py"))
    # Launchers and the user-facing client stay source; the rest is byte code only.
    assert remaining == [
        "entropy.py",
        "lib/install/cli.py",
        "lib/remote_cli/__init__.py",
        "lib/remote_cli/api.py",
    ]
    assert (application / "lib" / "util.pyc").is_file()
    assert not (application / "lib" / "remote_cli" / "api.pyc").exists()
    assert not list(application.rglob("__pycache__"))

    result = subprocess.run(
        [sys.executable, "entropy.py"], cwd=application, capture_output=True, text=True
    )
    # Run as the `ent` launcher runs it: the script's folder leads sys.path.
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "answer 42"


def test_install_and_node_bundles_keep_byte_code_without_source(tmp_path) -> None:
    application = _tree(tmp_path)
    compile_application(application, sys.executable)
    (application / "lib" / "install" / "cli.cpython-39.pyc").write_bytes(b"cache")

    copy = tmp_path / "installed"
    shutil.copytree(application, copy, ignore=_ignore_caches)
    assert (copy / "lib" / "util.pyc").is_file()

    bundled = {path.as_posix() for path in _files(application, ("core", "lib", "entropy.py"))}
    assert "lib/util.pyc" in bundled and "core/app.pyc" in bundled
    assert "lib/install/cli.py" in bundled


def test_keep_source_rules() -> None:
    assert keeps_source("lib/install/cli.py")
    assert keeps_source("lib/remote_cli/commands.py")
    assert not keeps_source("lib/install/installer.py")
    assert not keeps_source("core/web/application.py")
