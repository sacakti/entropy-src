"""
Database safety command: status, backups, checks and restore.
"""

from __future__ import annotations

import getpass
import os
from argparse import ArgumentParser, BooleanOptionalAction, Namespace
from typing import Any, Dict

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)
from lib.database import engine as database_engine
from lib.database.connection import DatabaseConnection
from lib.database.exceptions import DatabaseException
from lib.database.safety import DatabaseLockedError, DatabaseSafety


def _size(value: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return str(value)


def _still_running(run: Dict[str, Any]) -> bool:
    """
    The web server is stopped, and sorts out its runs when it starts. A local run with no
    live process is only a row waiting for that; a run on another node cannot be told.
    """

    if run.get("node") != "local":
        return True
    pid = run.get("pid")
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


class DatabaseCommand(BaseCommand):
    """
    Back up, check and restore Entropy's database (entropy.db), and switch the
    database Entropy runs on.

    Works without signing in: whoever may read and replace the database file
    may already do all of this; restoring must work when signing in cannot.
    """

    metadata = CommandMetadata(
        name="database",
        description="Back up, check, restore and switch Entropy's database.",
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

        self._context = context

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

        switch = subparsers.add_parser(
            "switch",
            help="Choose the database Entropy runs on (stop the web server first).",
        )

        switch.add_argument(
            "engine",
            choices=("sqlite", "postgresql"),
            help="sqlite goes back to its file. postgresql copies SQLite to an empty database.",
        )

        for flag, kwargs in (
            ("--host", {"help": "PostgreSQL host (default: the saved connection)."}),
            ("--port", {"type": int, "help": "PostgreSQL port."}),
            ("--name", {"help": "PostgreSQL database name."}),
            ("--schema", {"help": "PostgreSQL schema (default: the user's default)."}),
            ("--user", {"help": "PostgreSQL user; asks for the password."}),
        ):
            switch.add_argument(flag, **kwargs)

        switch.add_argument(
            "--ssl",
            action=BooleanOptionalAction,
            default=None,
            help="Require TLS.",
        )

        switch.add_argument(
            "--use-existing",
            action="store_true",
            help="Run on Entropy data already in the target; nothing is copied.",
        )

        switch.add_argument(
            "--yes",
            "-y",
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

        if args.action == "switch":
            self._switch(args)
            return

        if args.action == "status" and self._safety is None:
            shown = database_engine.public(database_engine.load(self._manager.database))
            self._ui.table(
                title="Database",
                columns=["Property", "Value"],
                rows=[[name.title(), str(value)] for name, value in shown.items()],
            )
            return

        if self._safety is None:
            raise DatabaseException(
                f"Entropy runs on {self._manager.engine}: its server handles status, "
                "backups and restores, not this command."
            )

        getattr(
            self,
            f"_{args.action}",
        )(
            args,
        )

    # ------------------------------------------------------------------
    # Switch
    # ------------------------------------------------------------------

    def _switch(
        self,
        args: Namespace,
    ) -> None:

        if args.engine == database_engine.SQLITE:
            self._manager.close()
            database_engine.switch_to_sqlite(self._manager.database, assume_yes=args.yes)
            return

        if self._manager.engine != database_engine.SQLITE and not args.use_existing:
            raise SystemExit(
                "Entropy already runs on PostgreSQL. Data is only copied from SQLite: switch "
                "back first, or give --use-existing to run on another database as it is."
            )

        guard = self._safety or DatabaseSafety(self._manager.database)
        try:
            guard.acquire_server_lock()
        except DatabaseLockedError as exc:
            raise SystemExit(f"{exc} (ent web stop)") from None
        try:
            self._switch_to_postgresql(args)
        finally:
            guard.release_server_lock()

    def _target_values(
        self,
        args: Namespace,
        settings: Any,
    ) -> Dict[str, Any]:
        """The saved connection, changed by what the command line gives."""

        values: Dict[str, Any] = dict(settings.values("database_target"))
        if values.get("engine") != database_engine.POSTGRESQL:
            values["port"] = 5432
        values["engine"] = database_engine.POSTGRESQL
        for field, given in (
            ("host", args.host),
            ("port", args.port),
            ("database", args.name),
            ("schema", args.schema),
            ("username", args.user),
            ("ssl", args.ssl),
        ):
            if given is not None:
                values[field] = given

        # Never on the command line, where other users and the shell history can see it.
        password = os.environ.get("ENTROPY_DB_PASSWORD")
        if password is None and (args.user or args.host or not values.get("password")):
            password = getpass.getpass(f"Password for {values.get('username') or 'the user'}: ")
        if password is not None:
            values["password"] = password

        if not values.get("host") or not values.get("database"):
            raise SystemExit("Give the connection: --host and --name (nothing is saved yet).")
        return values

    def _switch_to_postgresql(
        self,
        args: Namespace,
    ) -> None:

        from lib.database.postgres import PostgresConnection
        from lib.database.switch import SwitchProgress, copy_database
        from lib.runs.store import RunStore
        from lib.system.settings import settings_for
        from lib.vault.key import VaultKeyProvider

        current = self._manager.connection
        active = [run for run in RunStore(current).active() if _still_running(run)]
        if active:
            raise SystemExit(f"{len(active)} run(s) are active: switch when they have finished.")

        settings = settings_for(self._context)
        values = self._target_values(args, settings)
        target = PostgresConnection(values, self._manager.database)
        where = f"{values['database']} on {values['host']}:{values['port']}"
        try:
            try:
                target.ensure_schema()
                occupied = target.fetchone("SELECT 1 FROM sqlite_master WHERE type = 'table'")
                has_entropy = target.table_exists("schema_migrations")
            except Exception as exc:  # noqa: BLE001 - every failure means the same here
                raise SystemExit(f"Cannot use {where}: {exc}") from None

            if args.use_existing and not has_entropy:
                raise SystemExit(f"{where} holds no Entropy data, so there is nothing to run on.")
            if not args.use_existing and occupied:
                raise SystemExit(
                    f"{where} already has tables, so nothing was copied. Give an empty database, "
                    "or --use-existing to run on the Entropy data already there."
                )

            action = (
                f"Run on the data already in {where}? Nothing is copied"
                if args.use_existing
                else f"Copy all data to {where} and run on it? SQLite stays as it is"
            )
            if not args.yes:
                answer = input(f"{action}. [y/N] ")
                if answer.strip().lower() not in ("y", "yes"):
                    self._ui.info("Nothing changed.")
                    return

            # Saved first, so the copy carries it and later switches need no options.
            if self._safety is not None:
                settings.update("database_target", {**values, "enabled": True})

            if not args.use_existing:
                self._copy(target, SwitchProgress, copy_database)

            key = VaultKeyProvider(
                self._context.executor,
                self._context.bootstrap.vault.key,
            ).key()
            database_engine.save(self._manager.database, values, key)
        finally:
            target.close()

        self._ui.success(f"Entropy now runs on PostgreSQL ({where}). Start it: ent web start")

    def _copy(
        self,
        target: Any,
        progress_type: Any,
        copy_database: Any,
    ) -> None:
        ui = self._ui

        class Printed(progress_type):
            def update(self, **changes: Any) -> None:
                super().update(**changes)
                if changes.get("table"):
                    ui.info(f"Copying {changes['table']}")

        reader = DatabaseConnection(self._manager.database)
        try:
            # One read transaction: the copy sees one moment, whatever else happens.
            reader.execute("BEGIN")
            counts = copy_database(reader, target, Printed())
        finally:
            reader.close()
        ui.info(f"Copied {sum(counts.values())} rows in {len(counts)} tables.")

    def _status(
        self,
        args: Namespace,
    ) -> None:

        status = self._safety.status()

        self._ui.table(
            title="Database",
            columns=["Property", "Value"],
            rows=[
                ["Engine", "SQLite"],
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
