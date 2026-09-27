"""
Entropy bootstrap.
"""

import sys
from pathlib import Path

PACKAGE_DIRS = (
    Path.home() / ".entropy" / "site-packages",
    Path.home() / ".entropy" / "extensions" / "site-packages",
)


def bootstrap() -> None:
    for package_dir in PACKAGE_DIRS:

        path = str(package_dir)

        if path not in sys.path:

            sys.path.insert(0, path)
