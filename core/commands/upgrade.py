"""
Upgrade command.
"""

from __future__ import annotations

import time
from argparse import ArgumentParser, Namespace
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator, Optional

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)

if TYPE_CHECKING:
    from core.context import EntropyContext

# Minutes people with Entropy open are warned (Vision) before it starts, as on the web.
DEFAULT_NOTICE_MINUTES = 5
MAX_NOTICE_MINUTES = 60


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
            "--notice",
            type=int,
            default=DEFAULT_NOTICE_MINUTES,
            metavar="MINUTES",
            help=(
                "Warn everyone with Entropy open this many minutes before it starts, so they "
                f"can save their work (default {DEFAULT_NOTICE_MINUTES}; 0 starts at once). "
                "Ctrl+C during the wait cancels."
            ),
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

        if not 0 <= args.notice <= MAX_NOTICE_MINUTES:
            raise ValueError(f"--notice is 0 to {MAX_NOTICE_MINUTES} minutes.")

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

        with self._notice("upgrade", None, session.username, args.notice) as go:
            if not go:
                return

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

        with self._notice("upgrade", info["version"], username, args.notice) as go:
            if not go:
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

        with self._notice("rollback", last["from"], username, args.notice) as go:
            if not go:
                return

            entry = upgrader.rollback(
                user=username,
            )

            self._restart_web()

        self._ui.success(
            f"Entropy is back at {entry['to']}.",
        )

    # ------------------------------------------------------------------
    # Telling everyone
    # ------------------------------------------------------------------

    def _connection(self) -> Any:
        manager = getattr(self._context, "database_manager", None)
        return manager.connection if manager is not None else None

    @contextmanager
    def _notice(
        self,
        action: str,
        target: Optional[str],
        username: str,
        minutes: int,
    ) -> Iterator[bool]:
        """
        Warn everyone through Vision, wait `minutes` for them to save their work, then
        yield True to go ahead (False when Ctrl+C cancelled the wait). The warning is
        taken down once the block ends, whatever happened in it.
        """

        from lib.system import upgrade_notice, web

        connection = self._connection()
        if connection is None or not web.status()["running"]:
            # No web server: nobody has Entropy open to warn.
            yield True
            return

        starts_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        notice = upgrade_notice.announce(
            connection,
            action,
            target,
            username,
            starts_at if minutes > 0 else None,
            minutes,
        )
        if notice is None:
            self._ui.warning("Could not warn everyone through Vision; going ahead.")
        try:
            if minutes > 0 and not self._wait(action, starts_at):
                done = "upgraded" if action == "upgrade" else "rolled back"
                self._ui.info(f"Cancelled; nothing was {done} and the warning is down.")
                yield False
                return
            yield True
        finally:
            upgrade_notice.end(connection, notice)

    def _wait(self, action: str, starts_at: datetime) -> bool:
        """Count down to `starts_at`; False when Ctrl+C cancelled it."""

        minutes = round((starts_at - datetime.now(timezone.utc)).total_seconds() / 60)
        self._ui.info(
            f"Everyone with Entropy open was warned. The {action} starts in {minutes}"
            f" minute{'' if minutes == 1 else 's'}; press Ctrl+C to cancel."
        )
        said = minutes
        try:
            while True:
                left = (starts_at - datetime.now(timezone.utc)).total_seconds()
                if left <= 0:
                    return True
                # Once a minute: "4 minute(s) to go...".
                whole = int(left // 60)
                if 0 < whole < said:
                    said = whole
                    self._ui.info(f"{whole} minute(s) to go...")
                time.sleep(min(1.0, left))
        except KeyboardInterrupt:
            return False

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
