"""Package the remote `ent` client as one runnable file (a Python zipapp)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

PACKAGE = "ent_cli"
SOURCE = Path(__file__).resolve().parent
MODULES = ("__init__.py", "api.py", "commands.py", "config.py", "contract.py", "output.py")

ROOT_MAIN = """import sys

if sys.version_info < (3, 9):
    sys.exit("ent needs Python 3.9 or newer (this is %d.%d)." % sys.version_info[:2])

from ent_cli.commands import main

sys.exit(main())
"""


def build_pyz(version: str) -> bytes:
    """`ent.pyz`: run it with `python3 ent.pyz ...` (or directly on POSIX)."""

    buffer = io.BytesIO()
    buffer.write(b"#!/usr/bin/env python3\n")
    with zipfile.ZipFile(buffer, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("__main__.py", ROOT_MAIN)
        for name in MODULES:
            archive.writestr(f"{PACKAGE}/{name}", (SOURCE / name).read_text(encoding="utf-8"))
        archive.writestr(f"{PACKAGE}/_version.py", f'VERSION = "{version}"\n')
    return buffer.getvalue()


def fingerprint() -> str:
    """Changes when the client's sources change (for caching ent.pyz)."""

    return ":".join(str((SOURCE / name).stat().st_mtime_ns) for name in MODULES)
