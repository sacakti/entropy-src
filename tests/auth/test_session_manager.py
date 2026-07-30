from datetime import datetime, timedelta

import pytest

from lib.auth.exceptions import AuthenticationRequiredError
from lib.auth.session import Session


def test_login(session_manager, manager):

    manager.create(
        username="admin",
        password="password123",
    )

    session = session_manager.login(
        "admin",
        "password123",
    )

    assert session.username == "admin"
    assert session.token


def test_current_session(session_manager, manager):

    manager.create(
        username="admin",
        password="password123",
    )

    session_manager.login(
        "admin",
        "password123",
    )

    current = session_manager.current()

    assert current is not None
    assert current.username == "admin"


def test_authenticated(session_manager, manager):

    assert session_manager.authenticated() is False

    manager.create(
        username="admin",
        password="password123",
    )

    session_manager.login(
        "admin",
        "password123",
    )

    assert session_manager.authenticated() is True


def test_logout(session_manager, manager):

    manager.create(
        username="admin",
        password="password123",
    )

    session_manager.login(
        "admin",
        "password123",
    )

    session_manager.logout()

    assert session_manager.current() is None


def test_require(session_manager, manager):

    manager.create(
        username="admin",
        password="password123",
    )

    session_manager.login(
        "admin",
        "password123",
    )

    session = session_manager.require()

    assert session.username == "admin"


def test_require_without_login(session_manager):

    with pytest.raises(AuthenticationRequiredError):
        session_manager.require()


def test_login_replaces_existing_session(session_manager, manager):

    manager.create(
        username="admin",
        password="password123",
    )

    first = session_manager.login(
        "admin",
        "password123",
    )

    second = session_manager.login(
        "admin",
        "password123",
    )

    assert first.token != second.token


def test_expired_session(session_manager):

    session = Session(
        user_id=1,
        username="admin",
        token="abc",
        created_at=datetime.now() - timedelta(hours=10),
        expires_at=datetime.now() - timedelta(hours=1),
    )

    session_manager._save(session)

    assert session_manager.current() is None
    assert session_manager.authenticated() is False
