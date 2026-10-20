"""
Upgrade command.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import TYPE_CHECKING

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)

if TYPE_CHECKING:
    from core.context import EntropyContext


class UpgradeCommand(
    BaseCommand,
):
    """
    Upgrade the Entropy application.
    """

    metadata = CommandMetadata(
        name="upgrade",
        description="Upgrade Entropy.",
        aliases=("up",),
    )

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        super().__init__(
            context,
        )

        assert context.ui is not None
        assert context.authorization is not None
        assert context.session_manager is not None

        self._context = context

        self._ui = context.ui

        self._authorization = context.authorization

        self._session = context.session_manager

    # ------------------------------------------------------------------
    # Configure
    # ------------------------------------------------------------------

    def configure(
        self,
        parser: ArgumentParser,
    ) -> None:

        parser.add_argument(
            "--source",
            type=Path,
            help="Release package (entropy-<version>-<platform>.tar.gz) or legacy .epkg.",
        )

        parser.add_argument(
            "--check",
            action="store_true",
            help="Only inspect the package; change nothing.",
        )

        parser.add_argument(
            "--allow-downgrade",
            action="store_true",
            help="Apply a package that is not newer than the installed version.",
        )

        parser.add_argument(
            "--rollback",
            action="store_true",
            help="Return to the version before the last upgrade (database included).",
        )

        parser.add_argument(
            "-y",
            "--yes",
            action="store_true",
            help="Do not ask for confirmation.",
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        args: Namespace,
    ) -> None:

        session = self._session.require()

        self._authorization.require(
            session,
            "upgrade.entropy",
        )

        if args.rollback:
            self._rollback(args, session.username)
            return

        if args.source is None:
            raise ValueError("Give a package with --source, or use --rollback.")

        if args.source.name.endswith((".tar.gz", ".tgz")):
            self._release(args, session.username)
            return

        #
        # Import lazily so the upgrade subsystem isn't loaded
        # unless the command is actually used.
        #

        from lib.upgrade.manager import UpgradeManager

        self._ui.info(
            f"Upgrade package: {args.source}",
        )

        self._ui.info(
            "Validating upgrade package...",
        )

        UpgradeManager(
            self._context,
        ).upgrade(
            args.source,
        )

        self._ui.success(
            "Entropy upgraded successfully.",
        )

    # ------------------------------------------------------------------
    # Release packages
    # ------------------------------------------------------------------

    def _release(
        self,
        args: Namespace,
        username: str,
    ) -> None:

        from lib.system.upgrade import ReleaseUpgrader

        upgrader = ReleaseUpgrader(
            progress=self._ui.info,
        )

        info = upgrader.inspect(
            args.source.expanduser(),
        )

        self._ui.table(
            "Upgrade package",
            ("Field", "Value"),
            (
                ("Installed", info["current"]),
                ("Package", info["version"]),
                ("Platform", str(info["platform"])),
                ("Python", str(info["python"])),
                ("Built", str(info["built_at"])),
            ),
        )

        for problem in info["problems"]:
            self._ui.error(problem)

        if not info["newer"]:
            self._ui.warning(
                f"{info['version']} is not newer than the installed {info['current']}."
            )

        if args.check or info["problems"]:
            return

        if not info["newer"] and not args.allow_downgrade:
            self._ui.info("Use --allow-downgrade to apply it anyway.")
            return

        if not args.yes and not self._ui.confirm(
            f"Upgrade Entropy {info['current']} to {info['version']}?"
        ):
            self._ui.info("Cancelled.")
            return

        entry = upgrader.apply(
            args.source.expanduser(),
            allow_downgrade=args.allow_downgrade,
            user=username,
        )

        if entry.get("database_backup"):
            self._ui.info(f"Database backup: {entry['database_backup']}")

        self._restart_web()

        self._ui.success(
            f"Entropy upgraded to {entry['to']}.",
        )

    def _rollback(
        self,
        args: Namespace,
        username: str,
    ) -> None:

        from lib.system.upgrade import ReleaseUpgrader

        upgrader = ReleaseUpgrader(
            progress=self._ui.info,
        )

        if not upgrader.can_rollback():
            raise ValueError("There is no previous version to return to.")

        last = upgrader.record["upgrades"][-1]

        if not args.yes and not self._ui.confirm(
            f"Return from {last['to']} to {last['from']}? "
            "The database goes back to its state before that upgrade."
        ):
            self._ui.info("Cancelled.")
            return

        entry = upgrader.rollback(
            user=username,
        )

        self._restart_web()

        self._ui.success(
            f"Entropy is back at {entry['to']}.",
        )

    def _restart_web(self) -> None:
        """A running web server must load the new code."""

        from lib.system import web

        if not web.status()["running"]:
            return

        self._ui.info("Restarting the web server...")

        web.restart()

        state = web.status()

        if state["healthy"]:
            self._ui.success(f"Web server running at {state['url']}.")
        else:
            self._ui.warning(f"The web server did not come back; see {state['log']}.")
