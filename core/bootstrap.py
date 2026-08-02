"""
Entropy bootstrap.
"""

from pathlib import Path
import sys

PACKAGE_DIR = Path.home() / ".entropy" / "site-packages"


def bootstrap():

    if PACKAGE_DIR.exists():

        path = str(PACKAGE_DIR)

        if path not in sys.path:

            sys.path.insert(0, path)
