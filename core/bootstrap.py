"""
Entropy bootstrap.
"""

import os
import sys
from pathlib import Path

# ENTROPY_HOME relocates the Entropy home, e.g. for a node agent.
ENTROPY_HOME = Path(os.environ.get("ENTROPY_HOME") or Path.home() / ".entropy")

PACKAGE_DIRS = (
    ENTROPY_HOME / "site-packages",
    ENTROPY_HOME / "extensions" / "site-packages",
)


def bootstrap() -> None:
    for package_dir in PACKAGE_DIRS:

        path = str(package_dir)

        if path not in sys.path:

            sys.path.insert(0, path)
