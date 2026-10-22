"""
Database safety command: status, backups, checks and restore.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)


def _size(value: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return str(value)


class DatabaseCommand(BaseCommand):
    """
    Back up, check and restore Entropy's database (entropy.db).

    Works without signing in: whoever may read and replace the database file
    may already do all of this; restoring must work when signing in cannot.
    """

    metadata = CommandMetadata(
        name="database",
        description="Back up, check and restore Entropy's database.",
        aliases=("db",),
        authentication_required=False,
    )

    def __init__(
        self,
        context,
    ) -> None:

        super().__init__(
            context,
        )

        assert context.ui is not None
        assert context.database_manager is not None

        self._ui = context.ui

        self._manager = context.database_manager

        self._safety = context.database_manager.safety

    def configure(
        self,
        parser: ArgumentParser,
    ) -> None:

        subparsers = parser.add_subparsers(
            dest="action",
            required=True,
        )

        subparsers.add_parser(
            "status",
            help="Where the database and its backups are, and their state.",
        )

        subparsers.add_parser(
            "backup",
            help="Make a checked backup now.",
        )

        subparsers.add_parser(
            "backups",
            help="List backups, newest first.",
        )

        subparsers.add_parser(
            "check",
            help="Run a full integrity check.",
        )

        restore = subparsers.add_parser(
            "restore",
            help="Replace the database with a backup (stop the web server first).",
        )

        restore.add_argument(
            "name",
            nargs="?",
            help="Backup file name (default: the newest good one).",
        )

        restore.add_argument(
            "--yes",
            action="store_true",
            help="Do not ask for confirmation.",
        )

        settings = subparsers.add_parser(
            "settings",
            help="Change where backups go, how often, and how many are kept.",
        )

        settings.add_argument(
            "--backup-dir",
            help="Folder for backups (ideally on another disk).",
        )

        settings.add_argument(
            "--interval-hours",
            type=float,
            help="Hours between automatic backups.",
        )

        settings.add_argument(
            "--keep",
            type=int,
            help="How many backups to keep.",
        )

    def execute(
        self,
        args: Namespace,
    ) -> None:

        getattr(
            self,
            f"_{args.action}",
        )(
            args,
        )

    def _status(
        self,
        args: Namespace,
    ) -> None:

        status = self._safety.status()

        self._ui.table(
            title="Database",
            columns=["Property", "Value"],
            rows=[
                ["Database", status["database"]],
                ["Size", _size(status["size"])],
                ["Guard link", "yes" if status["guarded"] else "no"],
                ["Backups in", status["backup_dir"]],
                ["Backups", str(len(status["backups"]))],
                ["Last backup", status["last_backup"] or "never"],
                [
                    "Schedule",
                    "every {} h, keep {}".format(
                        status["settings"]["interval_hours"],
                        status["settings"]["keep"],
                    ),
                ],
            ],
        )

    def _backup(
        self,
        args: Namespace,
    ) -> None:

        connection = self._manager.connection

        with connection._lock:

            entry = self._safety.backup(
                connection.connection,
                reason="manual",
            )

        self._ui.success(
            f"Backup {entry['name']} ({_size(entry['size'])}) made and checked.",
        )

    def _backups(
        self,
        args: Namespace,
    ) -> None:

        backups = self._safety.backups()

        if not backups:

            self._ui.info(
                f"No backups in {self._safety.backup_dir}.",
            )

            return

        self._ui.table(
            title=f"Backups in {self._safety.backup_dir}",
            columns=["Name", "Size", "Made"],
            rows=[[entry["name"], _size(entry["size"]), entry["created_at"]] for entry in backups],
        )

    def _check(
        self,
        args: Namespace,
    ) -> None:

        from lib.database.safety import check_file

        result = check_file(
            self._safety.database,
        )

        if result == "ok":

            self._ui.success(
                "The database passed its integrity check.",
            )

            return

        self._ui.error(
            f"The database is damaged: {result}",
        )

        raise SystemExit(1)

    def _restore(
        self,
        args: Namespace,
    ) -> None:

        from lib.database.safety import DatabaseLockedError

        name = args.name

        if not name:

            latest = self._safety.latest_good_backup()

            if latest is None:

                raise SystemExit("There is no good backup to restore.")

            name = latest.name

        try:

            self._safety.acquire_server_lock()

        except DatabaseLockedError as exc:

            raise SystemExit(f"{exc} (ent web stop)") from None

        try:

            if not args.yes:

                answer = input(
                    f"Replace {self._safety.database} with {name}? "
                    "Changes since then are lost. [y/N] ",
                )

                if answer.strip().lower() not in ("y", "yes"):

                    self._ui.info(
                        "Nothing changed.",
                    )

                    return

            self._manager.close()

            message = self._safety.restore(
                name,
            )

            self._ui.success(
                message,
            )

        finally:

            self._safety.release_server_lock()

    def _settings(
        self,
        args: Namespace,
    ) -> None:

        changes = {
            key: value
            for key, value in (
                ("backup_dir", args.backup_dir),
                ("interval_hours", args.interval_hours),
                ("keep", args.keep),
            )
            if value is not None
        }

        if changes:

            self._safety.save_settings(
                changes,
            )

        self._status(
            args,
        )
