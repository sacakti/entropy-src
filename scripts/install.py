#!/usr/bin/env python3

"""
Entropy installer.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:

    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

    from lib.install.manager import InstallManager

    result = InstallManager().install()

    print(result.message)

    if not result.success:
        raise SystemExit(1)


if __name__ == "__main__":
    raise SystemExit(
        main(),
    )
