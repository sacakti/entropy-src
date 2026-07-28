#!/usr/bin/env python3

"""
Entropy installer.
"""

from lib.install.manager import InstallManager


def main():

    result = (
        InstallManager()
        .install()
    )

    print(result.message)

    if not result.success:
        raise SystemExit(1)


if __name__ == "__main__":

    main()