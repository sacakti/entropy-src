"""
Application parser.

Parses global application arguments.
"""

from __future__ import annotations

import argparse
from argparse import Namespace


class ApplicationParser:
    """
    Parses global application arguments.
    """

    def parse(
        self,
    ) -> Namespace:
        """
        Parse application arguments.
        """

        parser = argparse.ArgumentParser(
            prog="ent",
            add_help=False,
        )

        parser.add_argument(
            "-v",
            "--verbose",
            action="count",
            default=0,
            help="Increase console verbosity.",
        )

        return parser.parse_known_args()
