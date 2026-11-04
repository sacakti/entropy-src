"""
Which database Entropy runs on.

SQLite is the default and needs no configuration. When an administrator
switches to another engine, its connection is recorded in `database-engine.json`
beside the SQLite file. It cannot live in the database it describes. The password
is encrypted with the vault key, and the file is readable by its owner only.

A record that cannot be read stops Entropy instead of falling back to SQLite:
silently running on the old file would split the data in two.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from lib.database.connection import DatabaseConnection
from lib.database.exceptions import DatabaseException

CONFIG_FILE = "database-engine.json"
SQLITE = "sqlite"
POSTGRESQL = "postgresql"

_FIELDS = ("engine", "host", "port", "database", "schema", "username", "ssl")


def config_path(database: Path) -> Path:
    """The engine record that belongs to this SQLite file."""

    return Path(database).parent / CONFIG_FILE


def load(database: Path) -> Optional[Dict[str, Any]]:
    """The recorded engine, or None when Entropy runs on SQLite."""

    path = config_path(database)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        raise DatabaseException(f"Cannot read the database engine record {path}: {error}") from None
    if not isinstance(record, dict) or not record.get("engine"):
        raise DatabaseException(f"The database engine record {path} is not valid.")
    return record


def engine_name(database: Path) -> str:
    """The engine this installation runs on."""

    record = load(database)
    return str(record["engine"]) if record else SQLITE


def save(database: Path, values: Dict[str, Any], key: bytes) -> None:
    """Record the engine; the file appears complete or not at all."""

    from lib.vault.cipher import VaultCipher

    record = {name: values.get(name) for name in _FIELDS}
    password = str(values.get("password") or "")
    record["password"] = (
        base64.b64encode(VaultCipher(key).encrypt(password.encode("utf-8"))).decode("ascii")
        if password
        else ""
    )
    path = config_path(database)
    partial = path.with_name(path.name + ".partial")
    descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2)
    os.replace(partial, path)


def remove(database: Path) -> None:
    """Go back to SQLite: forget the recorded engine."""

    config_path(database).unlink(missing_ok=True)


def reveal(record: Dict[str, Any], key: bytes) -> Dict[str, Any]:
    """The record with its password decrypted, for connecting."""

    from lib.vault.cipher import VaultCipher

    values = dict(record)
    if values.get("password"):
        values["password"] = (
            VaultCipher(key).decrypt(base64.b64decode(values["password"])).decode("utf-8")
        )
    return values


def public(record: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """What may be shown about the engine in use: never the password."""

    if record is None:
        return {"engine": SQLITE}
    return {name: record.get(name) for name in _FIELDS}


def asks_for_sqlite(argv: Sequence[str]) -> bool:
    """`ent database switch sqlite`: it must work when the current database is unreachable."""

    words = [word for word in argv if not word.startswith("-")]
    return words[:3] in (["database", "switch", SQLITE], ["db", "switch", SQLITE])


def switch_to_sqlite(database: Path, assume_yes: bool = False) -> None:
    """Go back to the SQLite file, without connecting to the engine being left."""

    from lib.database.safety import DatabaseLockedError, DatabaseSafety

    record = load(database)
    if record is None:
        print("Entropy already runs on SQLite.")
        return
    if not Path(database).is_file():
        raise SystemExit(f"There is no SQLite database at {database}: nothing to go back to.")

    guard = DatabaseSafety(database)
    try:
        guard.acquire_server_lock()
    except DatabaseLockedError as error:
        raise SystemExit(f"{error} (ent web stop)") from None
    try:
        if not assume_yes:
            answer = input(
                "Go back to SQLite as it was when you left it? Changes made since then stay in "
                f"{record['engine']} and are not copied. [y/N] "
            )
            if answer.strip().lower() not in ("y", "yes"):
                print("Nothing changed.")
                return
        remove(database)
    finally:
        guard.release_server_lock()
    print("Entropy now runs on SQLite. Start the server: ent web start")


def connection_for(context: Any, database: Path) -> DatabaseConnection:
    """The connection for the engine this installation runs on."""

    record = load(database)
    if record is None:
        return DatabaseConnection(database)

    if record["engine"] != POSTGRESQL:
        raise DatabaseException(f"Entropy cannot run on the '{record['engine']}' engine yet.")

    from lib.database.postgres import PostgresConnection
    from lib.vault.key import VaultKeyProvider

    key = VaultKeyProvider(context.executor, context.bootstrap.vault.key).key()
    return PostgresConnection(reveal(record, key), database)
