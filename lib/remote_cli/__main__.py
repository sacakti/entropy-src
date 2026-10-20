"""python -m lib.remote_cli, or ent.pyz."""

import sys

from .commands import main

if __name__ == "__main__":
    sys.exit(main())
