"""
Entropy bootstrap.
"""

import sys
from pathlib import Path

PACKAGE_DIR = Path.home() / ".entropy" / "site-packages"


def bootstrap():

    if PACKAGE_DIR.exists():

        path = str(PACKAGE_DIR)

        if path not in sys.path:

            sys.path.insert(0, path)
