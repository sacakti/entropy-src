"""`ent database switch`: choosing the database from a terminal."""

from __future__ import annotations

import builtins
import os
from argparse import Namespace
from types import SimpleNamespace

import pytest

pytest.importorskip("psycopg")

from core.commands.database import DatabaseCommand  # noqa: E402
from lib.database import engine  # noqa: E402
from lib.database.connection import DatabaseConnection  # noqa: E402
from lib.database.safety import DatabaseSafety  # noqa: E402

SAVED = {
    "engine": "postgresql",
    "host": "db",
    "port": 5432,
    "database": "entropy",
    "schema": "",
    "username": "me",
    "password": "s3cret",
    "ssl": False,
}


def _no_such_process(_pid, _signal):
    raise ProcessLookupError


def _args(**given) -> Namespace:
    values = dict(
        action="switch",
        engine="postgresql",
        host=None,
        port=None,
        name=None,
        schema=None,
        user=None,
        ssl=None,
        use_existing=False,
        yes=True,
    )
    return Namespace(**{**values, **given})


class Target:
    occupied = False
    has_entropy = False

    def __init__(self, values, database):
        self.values = values
        type(self).last = self

    def ensure_schema(self):
        pass

    def fetchone(self, sql, parameters=()):
        return (1,) if self.occupied else None

    def table_exists(self, name):
        return self.has_entropy

    def close(self):
        pass


class Settings:
    def __init__(self):
        self.saved = None

    def values(self, section):
        return dict(SAVED)

    def update(self, section, values):
        self.saved = values


class UI:
    def __init__(self):
        self.lines = []

    def info(self, text):
        self.lines.append(text)

    success = info


@pytest.fixture
def setup(tmp_path, monkeypatch):
    database = tmp_path / "entropy.db"
    connection = DatabaseConnection(database)
    connection.execute("CREATE TABLE t (a TEXT)")
    connection.commit()
    connection.close()

    safety = DatabaseSafety(database)
    manager = SimpleNamespace(
        connection=connection,
        database=database,
        safety=safety,
        engine="sqlite",
        close=connection.close,
    )
    settings = Settings()
    copies = []
    Target.occupied = Target.has_entropy = False
    monkeypatch.setattr("lib.database.postgres.PostgresConnection", Target)
    monkeypatch.setattr("lib.system.settings.settings_for", lambda _context: settings)
    monkeypatch.setattr("lib.runs.store.RunStore", lambda _c: SimpleNamespace(active=lambda: []))
    monkeypatch.setattr(
        "lib.database.switch.copy_database",
        lambda _source, target, _progress: copies.append(target) or {"t": 1},
    )
    monkeypatch.setattr("lib.vault.key.VaultKeyProvider.key", lambda self: b"0" * 32)
    monkeypatch.setattr("lib.database.engine.save", lambda *a: saved.append(a))
    monkeypatch.delenv("ENTROPY_DB_PASSWORD", raising=False)
    saved = []
    ui = UI()
    context = SimpleNamespace(
        ui=ui,
        database_manager=manager,
        executor=SimpleNamespace(),
        bootstrap=SimpleNamespace(vault=SimpleNamespace(key="k")),
    )
    command = DatabaseCommand.__new__(DatabaseCommand)
    command._context, command._ui, command._manager, command._safety = context, ui, manager, safety
    yield SimpleNamespace(
        command=command,
        database=database,
        manager=manager,
        settings=settings,
        saved=saved,
        copies=copies,
        ui=ui,
    )


def test_the_saved_connection_is_copied_to_and_recorded(setup) -> None:
    setup.command._switch(_args())
    assert len(setup.copies) == 1
    assert setup.saved[0][1]["host"] == "db"
    assert setup.saved[0][1]["password"] == "s3cret"


def test_options_change_the_saved_connection_and_are_saved(setup, monkeypatch) -> None:
    monkeypatch.setattr("getpass.getpass", lambda _prompt: "typed")
    setup.command._switch(_args(host="other", port=6000, name="n", user="u", ssl=True))
    values = setup.saved[0][1]
    assert (values["host"], values["port"], values["database"]) == ("other", 6000, "n")
    assert (values["username"], values["password"], values["ssl"]) == ("u", "typed", True)
    assert setup.settings.saved["host"] == "other"
    assert setup.settings.saved["enabled"] is True


def test_the_password_can_come_from_the_environment(setup, monkeypatch) -> None:
    monkeypatch.setenv("ENTROPY_DB_PASSWORD", "from-env")
    setup.command._switch(_args(host="other"))
    assert setup.saved[0][1]["password"] == "from-env"


def test_a_target_with_tables_is_refused_without_use_existing(setup) -> None:
    Target.occupied = True
    with pytest.raises(SystemExit, match="already has tables"):
        setup.command._switch(_args())
    assert setup.copies == []
    assert setup.saved == []


def test_use_existing_records_without_copying(setup) -> None:
    Target.occupied = Target.has_entropy = True
    setup.command._switch(_args(use_existing=True))
    assert setup.copies == []
    assert len(setup.saved) == 1


def test_use_existing_refuses_a_database_without_entropy(setup) -> None:
    with pytest.raises(SystemExit, match="no Entropy data"):
        setup.command._switch(_args(use_existing=True))
    assert setup.saved == []


def test_answering_no_changes_nothing(setup, monkeypatch) -> None:
    monkeypatch.setattr(builtins, "input", lambda _prompt: "n")
    setup.command._switch(_args(yes=False))
    assert setup.copies == []
    assert setup.saved == []
    assert setup.settings.saved is None


def test_a_running_server_blocks_the_switch(setup) -> None:
    server = DatabaseSafety(setup.database)
    server.acquire_server_lock()
    try:
        with pytest.raises(SystemExit, match="ent web stop"):
            setup.command._switch(_args())
    finally:
        server.release_server_lock()
    assert setup.saved == []


def test_active_runs_block_the_switch(setup, monkeypatch) -> None:
    monkeypatch.setattr(
        "lib.runs.store.RunStore",
        lambda _c: SimpleNamespace(active=lambda: [{"id": 1, "node": "local", "pid": os.getpid()}]),
    )
    with pytest.raises(SystemExit, match="active"):
        setup.command._switch(_args())
    assert setup.saved == []


def test_a_leftover_row_of_a_dead_process_does_not_block_the_switch(setup, monkeypatch) -> None:
    dead = {"id": 1, "node": "local", "state": "running", "pid": 2**22 + 12345}
    monkeypatch.setattr(
        "lib.runs.store.RunStore", lambda _c: SimpleNamespace(active=lambda: [dead])
    )
    monkeypatch.setattr("os.kill", _no_such_process)
    setup.command._switch(_args())
    assert len(setup.saved) == 1


def test_a_queued_run_with_no_process_does_not_block_the_switch(setup, monkeypatch) -> None:
    queued = {"id": 1, "node": "local", "state": "queued", "pid": 0}
    monkeypatch.setattr(
        "lib.runs.store.RunStore", lambda _c: SimpleNamespace(active=lambda: [queued])
    )
    setup.command._switch(_args())
    assert len(setup.saved) == 1


def test_a_run_on_another_node_blocks_the_switch(setup, monkeypatch) -> None:
    remote = {"id": 1, "node": "worker-1", "state": "running", "pid": None}
    monkeypatch.setattr(
        "lib.runs.store.RunStore", lambda _c: SimpleNamespace(active=lambda: [remote])
    )
    with pytest.raises(SystemExit, match="active"):
        setup.command._switch(_args())


def test_data_is_only_copied_from_sqlite(setup) -> None:
    setup.manager.engine = "postgresql"
    setup.command._safety = None
    with pytest.raises(SystemExit, match="only copied from SQLite"):
        setup.command._switch(_args())


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["database", "switch", "sqlite"], True),
        (["db", "switch", "sqlite", "--yes"], True),
        (["database", "switch", "postgresql"], False),
        (["database", "status"], False),
        ([], False),
    ],
)
def test_going_back_to_sqlite_is_recognised_before_connecting(argv, expected) -> None:
    assert engine.asks_for_sqlite(argv) is expected


def test_going_back_needs_no_connection(tmp_path, capsys) -> None:
    database = tmp_path / "entropy.db"
    database.write_bytes(b"")
    engine.config_path(database).write_text('{"engine": "postgresql", "host": "unreachable"}')
    engine.switch_to_sqlite(database, assume_yes=True)
    assert not engine.config_path(database).exists()
    assert "now runs on SQLite" in capsys.readouterr().out


def test_going_back_refuses_while_a_server_runs(tmp_path) -> None:
    database = tmp_path / "entropy.db"
    database.write_bytes(b"")
    engine.config_path(database).write_text('{"engine": "postgresql"}')
    server = DatabaseSafety(database)
    server.acquire_server_lock()
    try:
        with pytest.raises(SystemExit, match="ent web stop"):
            engine.switch_to_sqlite(database, assume_yes=True)
    finally:
        server.release_server_lock()
    assert engine.config_path(database).exists()


def test_going_back_without_the_file_is_refused(tmp_path) -> None:
    database = tmp_path / "entropy.db"
    engine.config_path(database).write_text('{"engine": "postgresql"}')
    with pytest.raises(SystemExit, match="no SQLite database"):
        engine.switch_to_sqlite(database, assume_yes=True)
    assert engine.config_path(database).exists()
