"""
Entropy bootstrap.
"""

import sys

from core.constants import PACKAGE_DIR


def bootstrap():

    if PACKAGE_DIR.exists():

        path = str(PACKAGE_DIR)

        if path not in sys.path:

            sys.path.insert(0, path)
