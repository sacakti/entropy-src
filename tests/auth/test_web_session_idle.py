"""Browser sessions: the inactivity limit and the last sign-in."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.web.session_store import WebSessionStore
from lib.database.connection import DatabaseConnection
from lib.database.repositories.user_logins import UserLoginsRepository
from lib.executor import LinuxExecutor
from lib.models.users import User


@pytest.fixture
def connection(tmp_path: Path) -> DatabaseConnection:
    return DatabaseConnection(tmp_path / "entropy.db")


@pytest.fixture
def user() -> User:
    return User(id=1, username="alice", full_name="Alice", is_active=True)


@pytest.fixture
def store(tmp_path: Path, connection: DatabaseConnection, user: User) -> WebSessionStore:
    # Only what WebSessionStore uses; sign-in by password is not under test here.
    context = SimpleNamespace(
        authentication=object(),
        configuration=SimpleNamespace(get=lambda key, default=None: default),
        executor=LinuxExecutor(),
        paths=SimpleNamespace(session=SimpleNamespace(directory=tmp_path / "session")),
        user_repository=SimpleNamespace(get=lambda user_id: user),
        database_manager=SimpleNamespace(connection=connection),
    )
    return WebSessionStore(context)  # type: ignore[arg-type]


def _age(store: WebSessionStore, token: str, minutes: float) -> None:
    """Pretend the last activity was `minutes` ago."""

    path = store._session_path(token)
    data = store._executor.read_json(path)
    data["last_activity"] = (datetime.now() - timedelta(minutes=minutes)).isoformat()
    store._executor.write_json(path, data)


def test_browser_sessions_end_after_15_idle_minutes(store, user) -> None:
    session, _ = store.issue(user)
    assert store.idle_seconds == 15 * 60

    _age(store, session.token, 14)
    assert store.get(session.token) is not None  # reading does not count as activity
    _age(store, session.token, 16)
    assert store.get(session.token) is None
    assert not store._executor.exists(store._session_path(session.token))


def test_keepalive_restarts_the_timer(store, user) -> None:
    session, _ = store.issue(user)
    _age(store, session.token, 14)
    before = store.idle_deadline(session.token)

    after = store.touch(session.token)

    assert after is not None and before is not None and after > before
    assert after - datetime.now() > timedelta(minutes=14, seconds=50)
    _age(store, session.token, 16)
    assert store.touch(session.token) is None  # too late: the session is gone


def test_command_line_tokens_have_no_idle_limit(store, user, connection) -> None:
    # A token made from a signed-in browser (no login_source) is not a sign-in.
    session, _ = store.issue(user, seconds=3600, browser=False)
    _age(store, session.token, 600)

    assert store.get(session.token) is not None
    assert store.idle_deadline(session.token) is None
    assert UserLoginsRepository(connection).get(user.id) is None


def test_command_line_sign_ins_are_remembered(store, user, connection) -> None:
    store.issue(user, seconds=3600, browser=False, address="10.0.0.5", login_source="cli")

    latest = UserLoginsRepository(connection).latest_entry(user.id)
    assert latest is not None and (latest["address"], latest["source"]) == ("10.0.0.5", "cli")


def test_idle_limit_can_be_turned_off(store, user) -> None:
    store.idle_seconds = 0
    session, _ = store.issue(user)
    _age(store, session.token, 600)
    assert store.get(session.token) is not None


def test_sign_ins_remember_the_previous_one(store, user, connection) -> None:
    logins = UserLoginsRepository(connection)

    first, _ = store.issue(user, address="10.0.0.1")
    assert logins.previous(user.id) is None  # first sign-in
    assert store.previous_login(first.token) is None

    store.issue(user, seconds=60, browser=False, address="10.0.0.9", login_source="cli")
    second, _ = store.issue(user, address="10.0.0.2")

    # The session keeps the sign-in before it, even when the command line signed in between.
    before = store.previous_login(second.token)
    assert before is not None and (before["address"], before["source"]) == ("10.0.0.9", "cli")
    assert logins.latest([user.id, 999])[user.id]["address"] == "10.0.0.2"
