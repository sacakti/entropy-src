"""
Entropy node agent command line.

    python -m lib.agent init --workspace DIR
    python -m lib.agent run --config FILE
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="entropy-agent")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Create or upgrade the agent's Entropy home.")
    init.add_argument("--workspace", type=Path, required=True)

    run = commands.add_parser("run", help="Run the agent.")
    run.add_argument("--config", type=Path, required=True)

    commands.add_parser("version", help="Print the agent version.")

    args = parser.parse_args(argv)

    if args.command == "init":
        from .home import initialize

        home = initialize(args.workspace.expanduser().resolve())
        print(f"Agent home ready: {home}")
        return 0

    if args.command == "version":
        from .agent import AGENT_VERSION

        print(AGENT_VERSION)
        return 0

    from .agent import Agent, configure_logging

    configure_logging(args.config.parent)
    return Agent(args.config).run()


if __name__ == "__main__":
    sys.exit(main())
