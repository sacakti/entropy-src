"""
Tests for SessionManager.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from lib.auth.exceptions import AuthenticationRequiredError


# ------------------------------------------------------------------
# Login
# ------------------------------------------------------------------


def test_login(
    session_manager,
    user_manager,
):

    user_manager.create(
        username="john",
        password="TestUser#2026",
    )

    session = session_manager.login(
        "john",
        "TestUser#2026",
    )

    assert session.username == "john"

    assert session.token

    assert session.created_at < session.expires_at


def test_login_replaces_existing_session(
    session_manager,
    user_manager,
):

    user_manager.create(
        username="john",
        password="TestUser#2026",
    )

    first = session_manager.login(
        "john",
        "TestUser#2026",
    )

    second = session_manager.login(
        "john",
        "TestUser#2026",
    )

    assert first.token != second.token

    current = session_manager.current()

    assert current is not None

    assert current.token == second.token


# ------------------------------------------------------------------
# Current
# ------------------------------------------------------------------


def test_current(
    session_manager,
    user_manager,
):

    user_manager.create(
        username="john",
        password="TestUser#2026",
    )

    session_manager.login(
        "john",
        "TestUser#2026",
    )

    current = session_manager.current()

    assert current is not None

    assert current.username == "john"


def test_current_without_session(
    session_manager,
):

    assert session_manager.current() is None


def test_current_expired_session(
    session_manager,
    user_manager,
    monkeypatch,
):

    user_manager.create(
        username="john",
        password="TestUser#2026",
    )

    session = session_manager.login(
        "john",
        "TestUser#2026",
    )

    #
    # Advance time beyond expiry.
    #

    monkeypatch.setattr(
        session_manager,
        "_now",
        lambda: session.expires_at + timedelta(
            seconds=1,
        ),
    )

    assert session_manager.current() is None


# ------------------------------------------------------------------
# Authenticated
# ------------------------------------------------------------------


def test_authenticated_true(
    session_manager,
    user_manager,
):

    user_manager.create(
        username="john",
        password="TestUser#2026",
    )

    session_manager.login(
        "john",
        "TestUser#2026",
    )

    assert session_manager.authenticated()


def test_authenticated_false(
    session_manager,
):

    assert not session_manager.authenticated()


# ------------------------------------------------------------------
# Require
# ------------------------------------------------------------------


def test_require(
    session_manager,
    user_manager,
):

    user_manager.create(
        username="john",
        password="TestUser#2026",
    )

    session_manager.login(
        "john",
        "TestUser#2026",
    )

    session = session_manager.require()

    assert session.username == "john"


def test_require_without_session(
    session_manager,
):

    with pytest.raises(
        AuthenticationRequiredError,
    ):

        session_manager.require()


# ------------------------------------------------------------------
# Logout
# ------------------------------------------------------------------


def test_logout(
    session_manager,
    user_manager,
):

    user_manager.create(
        username="john",
        password="TestUser#2026",
    )

    session_manager.login(
        "john",
        "TestUser#2026",
    )

    assert session_manager.authenticated()

    session_manager.logout()

    assert not session_manager.authenticated()


def test_logout_without_session(
    session_manager,
):

    #
    # Should not raise.
    #

    session_manager.logout()

    assert session_manager.current() is None


# ------------------------------------------------------------------
# Persistence
# ------------------------------------------------------------------


def test_session_persisted(
    session_manager,
    user_manager,
):

    user_manager.create(
        username="john",
        password="TestUser#2026",
    )

    session_manager.login(
        "john",
        "TestUser#2026",
    )

    assert session_manager._executor.exists(
        session_manager._session_file,
    )


def test_session_removed_after_logout(
    session_manager,
    user_manager,
):

    user_manager.create(
        username="john",
        password="TestUser#2026",
    )

    session_manager.login(
        "john",
        "TestUser#2026",
    )

    session_manager.logout()

    assert not session_manager._executor.exists(
        session_manager._session_file,
    )
