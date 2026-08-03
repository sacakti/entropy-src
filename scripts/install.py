#!/usr/bin/env python3

"""
Entropy installer.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(PROJECT_ROOT),
)

from lib.install.manager import InstallManager

def main():

    result = InstallManager().install()

    print(result.message)

    if not result.success:
        raise SystemExit(1)


if __name__ == "__main__":

    main()
