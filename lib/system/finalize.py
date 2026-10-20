"""
Post-upgrade step, run by the upgrader with the *new* application code:
back up the database, apply migrations and reconcile built-in
permissions. Prints one JSON line with the outcome.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


def _backup(database: Path, target: Path) -> None:
    """A consistent copy, even while the web server has the database open."""

    source = sqlite3.connect(str(database))
    try:
        destination = sqlite3.connect(str(target))
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()


def main(argv=None) -> int:
    from core.bootstrap import bootstrap

    bootstrap()

    from core.context_factory import ContextFactory

    tag = (argv or sys.argv[1:] or ["upgrade"])[0]
    database = backup = None
    try:
        factory = ContextFactory(interactive=False)
        factory.bootstrap()
        factory.runtime()
        factory.observability()
        factory.ui()
        factory.infrastructure()
        context = factory.context

        database = Path(context.paths.database.file)
        backup = database.with_name(f"{database.stem}.before-{tag}.db")
        if database.exists():
            _backup(database, backup)
        else:
            backup = None

        context.migration_manager.migrate()

        from lib.authorization.initializer import AuthorizationInitializer

        AuthorizationInitializer(context.database_manager.connection).reconcile()
        context.database_manager.close()
    except Exception as exc:  # noqa: BLE001 - report every failure to the upgrader
        restored = False
        if database is not None and backup is not None and backup.exists():
            # Undo a migration that stopped half way.
            try:
                restore(database, backup)
                restored = True
            except Exception:  # noqa: BLE001 - the upgrader reports the original error
                pass
        print(
            json.dumps(
                {"ok": False, "error": f"{exc.__class__.__name__}: {exc}", "restored": restored}
            )
        )
        return 1

    print(
        json.dumps(
            {"ok": True, "database": str(database), "backup": str(backup) if backup else None}
        )
    )
    return 0


def restore(database: Path, backup: Path) -> None:
    """Put the pre-upgrade database back (used on rollback)."""

    if backup.exists():
        _backup(backup, database)


if __name__ == "__main__":
    sys.exit(main())
