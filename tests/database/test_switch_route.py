"""Settings -> Database: switching the engine through the API."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

pytest.importorskip("psycopg")

from core.web.routes import database as routes  # noqa: E402
from core.web.routes import vision as vision_routes  # noqa: E402
from lib.database import engine  # noqa: E402
from lib.database.connection import DatabaseConnection  # noqa: E402
from lib.database.switch import PROGRESS, DatabaseSwitchError, SwitchProgress  # noqa: E402

TARGET = {
    "engine": "postgresql",
    "host": "db",
    "port": 5432,
    "database": "entropy",
    "schema": "",
    "username": "me",
    "password": "s3cret",
    "ssl": False,
}


class FakeTarget:
    def __init__(self, values, database):
        self.closed = False

    def close(self):
        self.closed = True


@pytest.fixture
def setup(tmp_path, monkeypatch):
    database = tmp_path / "entropy.db"
    connection = DatabaseConnection(database)
    connection.execute("CREATE TABLE t (a TEXT)")
    connection.commit()
    manager = SimpleNamespace(
        connection=connection,
        database=database,
        safety=SimpleNamespace(status=lambda: {"size": 1}),
    )
    manager.engine = "sqlite"
    context = SimpleNamespace(
        database_manager=manager,
        executor=SimpleNamespace(),
        bootstrap=SimpleNamespace(vault=SimpleNamespace(key=Path("k"))),
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(entropy_context=context)))

    PROGRESS.reset()
    allowed = []
    # The copy runs here, not on a thread, so each test sees its outcome.
    monkeypatch.setattr(routes, "_start_in_background", lambda work: work())
    monkeypatch.setattr(routes, "require", lambda _req, _user, name: allowed.append(name))
    monkeypatch.setattr(routes, "_refuse_while_running", lambda _context: None)
    monkeypatch.setattr(routes, "_restart_after_switch", lambda: True)
    monkeypatch.setattr(
        "lib.system.settings.settings_for",
        lambda _context: SimpleNamespace(values=lambda _section: dict(TARGET)),
    )
    monkeypatch.setattr("lib.database.postgres.PostgresConnection", FakeTarget)
    monkeypatch.setattr("lib.vault.key.VaultKeyProvider.key", lambda self: b"0" * 32)
    monkeypatch.setattr("lib.database.engine.save", lambda *a: saved.append(a))
    saved = []

    yield SimpleNamespace(
        request=request,
        manager=manager,
        connection=connection,
        database=database,
        allowed=allowed,
        saved=saved,
    )
    connection.close()
    PROGRESS.reset()


def _switch(setup, name):
    return routes.switch_engine(
        routes.EngineRequest(engine=name), setup.request, (None, None, SimpleNamespace())
    )


def _copying(*rows):
    def copy(_source, _target, progress):
        progress.update(tables_total=2, rows_total=5)
        for count in rows:
            progress.add_rows(count)
        return {"t": 3, "u": 2}

    return copy


def test_switching_answers_at_once_then_records_and_restarts(setup, monkeypatch) -> None:
    monkeypatch.setattr("lib.database.switch.copy_database", _copying(3, 2))
    assert _switch(setup, "postgresql") == {
        "engine": "postgresql",
        "switching": True,
        "restarting": False,
    }
    assert len(setup.saved) == 1
    assert setup.allowed == ["system.settings"]
    progress = PROGRESS.snapshot()
    assert progress["state"] == "restarting"
    assert progress["rows_done"] == 5


def test_the_copy_runs_on_a_thread_of_its_own(setup, monkeypatch) -> None:
    started = []
    monkeypatch.setattr(routes, "_start_in_background", started.append)
    assert _switch(setup, "postgresql")["switching"]
    assert len(started) == 1
    assert setup.saved == []


def test_the_server_can_read_while_copying(setup, monkeypatch) -> None:
    """The copy must not hold the server's lock, or Vision and every page would wait."""

    import threading

    answers = []

    def copy(_source, _target, _progress):
        def read():
            answers.append(setup.connection.fetchone("SELECT count(*) FROM t")[0])

        reader = threading.Thread(target=read)
        reader.start()
        reader.join(timeout=5)
        assert not reader.is_alive(), "the server's connection is blocked during the copy"
        return {}

    monkeypatch.setattr("lib.database.switch.copy_database", copy)
    _switch(setup, "postgresql")
    assert PROGRESS.snapshot()["state"] == "restarting"
    assert answers == [0]


def test_sqlite_stays_read_only_after_the_switch(setup, monkeypatch) -> None:
    monkeypatch.setattr("lib.database.switch.copy_database", _copying())
    _switch(setup, "postgresql")
    with pytest.raises(sqlite3.OperationalError):
        setup.connection.execute("INSERT INTO t VALUES ('late')")


def test_the_server_cannot_write_during_the_copy(setup, monkeypatch) -> None:
    seen = []

    def copy(_source, _target, _progress):
        try:
            setup.connection.execute("INSERT INTO t VALUES ('during')")
        except sqlite3.OperationalError as error:
            seen.append(str(error))
        return {}

    monkeypatch.setattr("lib.database.switch.copy_database", copy)
    _switch(setup, "postgresql")
    assert seen


def test_the_copy_reads_through_its_own_connection(setup, monkeypatch) -> None:
    seen = []

    def copy(source, _target, _progress):
        seen.append(source)
        return {}

    monkeypatch.setattr("lib.database.switch.copy_database", copy)
    _switch(setup, "postgresql")
    assert seen[0] is not setup.connection


def test_a_failed_copy_keeps_entropy_on_sqlite_and_writable(setup, monkeypatch) -> None:
    def fail(_source, _target, _progress):
        raise DatabaseSwitchError("no room")

    monkeypatch.setattr("lib.database.switch.copy_database", fail)
    assert _switch(setup, "postgresql")["switching"]
    progress = PROGRESS.snapshot()
    assert progress["state"] == "failed"
    assert "no room" in progress["error"]
    assert setup.saved == []
    setup.connection.execute("INSERT INTO t VALUES ('still works')")
    setup.connection.commit()


def test_a_failed_copy_can_be_tried_again(setup, monkeypatch) -> None:
    def fail(_source, _target, _progress):
        raise DatabaseSwitchError("no room")

    monkeypatch.setattr("lib.database.switch.copy_database", fail)
    _switch(setup, "postgresql")
    monkeypatch.setattr("lib.database.switch.copy_database", _copying())
    _switch(setup, "postgresql")
    assert PROGRESS.snapshot()["state"] == "restarting"


def test_a_second_switch_is_refused_while_one_runs(setup, monkeypatch) -> None:
    monkeypatch.setattr(routes, "_start_in_background", lambda work: None)
    _switch(setup, "postgresql")
    with pytest.raises(HTTPException) as caught:
        _switch(setup, "postgresql")
    assert caught.value.status_code == 409


def test_without_an_install_it_asks_for_a_restart(setup, monkeypatch) -> None:
    monkeypatch.setattr(routes, "_restart_after_switch", lambda: False)
    monkeypatch.setattr("lib.database.switch.copy_database", _copying())
    _switch(setup, "postgresql")
    assert PROGRESS.snapshot()["state"] == "restart_required"


def test_vision_tells_everyone_about_a_switch_but_no_error_text(setup) -> None:
    assert vision_routes._database_switch() is None
    PROGRESS.begin("postgresql")
    PROGRESS.update(table="users", tables_done=2, tables_total=9)
    shown = vision_routes._database_switch()
    assert shown["state"] == "copying"
    assert shown["table"] == "users"
    assert "error" not in shown
    PROGRESS.update(state="failed", error="password authentication failed")
    assert vision_routes._database_switch() is None


def test_progress_starts_once() -> None:
    progress = SwitchProgress()
    assert progress.begin("postgresql")
    assert not progress.begin("postgresql")
    progress.update(state="failed")
    assert progress.begin("postgresql")
    assert progress.snapshot()["error"] is None


def test_oracle_is_refused_for_now(setup) -> None:
    with pytest.raises(HTTPException) as caught:
        _switch(setup, "oracle")
    assert caught.value.status_code == 422
    assert setup.saved == []


def test_a_saved_oracle_target_cannot_be_switched_to(setup, monkeypatch) -> None:
    monkeypatch.setattr(
        "lib.system.settings.settings_for",
        lambda _context: SimpleNamespace(values=lambda _section: {**TARGET, "engine": "oracle"}),
    )
    with pytest.raises(HTTPException) as caught:
        _switch(setup, "postgresql")
    assert "Only PostgreSQL" in caught.value.detail


def test_switching_to_the_current_engine_is_refused(setup) -> None:
    with pytest.raises(HTTPException) as caught:
        _switch(setup, "sqlite")
    assert caught.value.status_code == 409


def test_active_runs_block_the_switch(setup, monkeypatch) -> None:
    def busy(_context):
        raise HTTPException(status_code=409, detail="1 run(s) are active.")

    monkeypatch.setattr(routes, "_refuse_while_running", busy)
    with pytest.raises(HTTPException) as caught:
        _switch(setup, "postgresql")
    assert caught.value.status_code == 409
    assert setup.saved == []


def test_going_back_to_sqlite_forgets_the_engine_and_copies_nothing(setup) -> None:
    path = engine.config_path(setup.database)
    path.write_text('{"engine": "postgresql"}')
    setup.manager.engine = "postgresql"
    result = _switch(setup, "sqlite")
    assert result["switching"] is False
    assert not path.exists()


def test_status_says_which_engine_runs_and_never_the_password(setup) -> None:
    response = SimpleNamespace(headers={})
    status = routes.status(setup.request, response, (None, None, SimpleNamespace()))
    assert status == {"size": 1, "engine": {"engine": "sqlite"}}

    engine.config_path(setup.database).write_text(
        '{"engine": "postgresql", "host": "db", "password": "sealed"}'
    )
    setup.manager.safety = None
    status = routes.status(setup.request, response, (None, None, SimpleNamespace()))
    assert status["engine"]["host"] == "db"
    assert "password" not in status["engine"]
