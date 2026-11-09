"""Which engine Entropy runs on, and switching to it."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from lib.database import engine
from lib.database.connection import DatabaseConnection
from lib.database.exceptions import DatabaseException

VALUES = {
    "engine": "postgresql",
    "host": "db",
    "port": 5432,
    "database": "entropy",
    "schema": "",
    "username": "me",
    "password": "s3cret",
    "ssl": True,
}


@pytest.fixture
def key():
    from lib.vault.cipher import VaultCipher

    candidate = os.urandom(32)
    try:
        VaultCipher(candidate)
    except Exception:  # noqa: BLE001 - a cipher built on Fernet keys
        candidate = Fernet.generate_key()
    return candidate


def test_sqlite_is_the_default_and_needs_no_file(tmp_path) -> None:
    database = tmp_path / "entropy.db"
    assert engine.load(database) is None
    assert engine.engine_name(database) == "sqlite"
    assert engine.public(None) == {"engine": "sqlite"}
    connection = engine.connection_for(SimpleNamespace(), database)
    assert type(connection) is DatabaseConnection


def test_a_saved_engine_reads_back(tmp_path, key) -> None:
    database = tmp_path / "entropy.db"
    engine.save(database, VALUES, key)
    record = engine.load(database)
    assert engine.engine_name(database) == "postgresql"
    assert record["password"] != "s3cret"
    assert engine.reveal(record, key) == VALUES


def test_the_password_is_not_in_the_file_and_only_the_owner_reads_it(tmp_path, key) -> None:
    database = tmp_path / "entropy.db"
    engine.save(database, VALUES, key)
    path = engine.config_path(database)
    assert "s3cret" not in path.read_text()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_public_never_shows_the_password(tmp_path, key) -> None:
    database = tmp_path / "entropy.db"
    engine.save(database, VALUES, key)
    shown = engine.public(engine.load(database))
    assert "password" not in shown
    assert shown["host"] == "db"


def test_removing_goes_back_to_sqlite(tmp_path, key) -> None:
    database = tmp_path / "entropy.db"
    engine.save(database, VALUES, key)
    engine.remove(database)
    assert engine.engine_name(database) == "sqlite"
    engine.remove(database)


@pytest.mark.parametrize("content", ["not json", "[]", "{}"])
def test_a_damaged_record_stops_entropy_instead_of_falling_back_to_sqlite(
    tmp_path, content
) -> None:
    database = tmp_path / "entropy.db"
    engine.config_path(database).write_text(content)
    with pytest.raises(DatabaseException):
        engine.load(database)


def test_an_engine_not_supported_yet_is_refused(tmp_path) -> None:
    database = tmp_path / "entropy.db"
    engine.config_path(database).write_text(json.dumps({"engine": "mssql"}))
    with pytest.raises(DatabaseException, match="mssql"):
        engine.connection_for(SimpleNamespace(), database)


def test_a_saved_oracle_engine_opens_an_oracle_connection(tmp_path, key, monkeypatch) -> None:
    from lib.database.oracle import OracleConnection

    database = tmp_path / "entropy.db"
    engine.save(database, {**VALUES, "engine": "oracle", "port": 1521, "schema": ""}, key)
    monkeypatch.setattr("lib.vault.key.VaultKeyProvider.key", lambda self: key)
    context = SimpleNamespace(
        executor=SimpleNamespace(),
        bootstrap=SimpleNamespace(vault=SimpleNamespace(key=Path("k"))),
    )
    # Created without connecting: the server is reached on first use.
    assert isinstance(engine.connection_for(context, database), OracleConnection)


def test_the_manager_runs_without_file_safety_on_another_engine(tmp_path, key, monkeypatch) -> None:
    from lib.database.manager import DatabaseManager
    from lib.database.postgres import PostgresConnection

    database = tmp_path / "entropy.db"
    engine.save(database, VALUES, key)
    monkeypatch.setattr("lib.vault.key.VaultKeyProvider.key", lambda self: key)
    context = SimpleNamespace(
        paths=SimpleNamespace(database=SimpleNamespace(file=database)),
        executor=SimpleNamespace(),
        bootstrap=SimpleNamespace(vault=SimpleNamespace(key=Path("k"))),
    )
    manager = DatabaseManager(context)
    assert isinstance(manager.connection, PostgresConnection)
    assert manager.safety is None
    assert manager.engine == "postgresql"
