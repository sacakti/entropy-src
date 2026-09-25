"""
Tests for Session.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from lib.models.session import Session


def test_to_dict():

    now = datetime.now()

    session = Session(
        user_id=1,
        username="john",
        token="token123",
        created_at=now,
        expires_at=now + timedelta(hours=8),
    )

    data = session.to_dict()

    assert data["user_id"] == 1

    assert data["username"] == "john"

    assert data["token"] == "token123"

    assert data["created_at"] == now.isoformat()

    assert data["expires_at"] == (now + timedelta(hours=8)).isoformat()


def test_from_dict():

    now = datetime.now()

    data = {
        "user_id": 1,
        "username": "john",
        "token": "token123",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=8)).isoformat(),
    }

    session = Session.from_dict(
        data,
    )

    assert session.user_id == 1

    assert session.username == "john"

    assert session.token == "token123"

    assert session.created_at == now

    assert session.expires_at == (now + timedelta(hours=8))


def test_round_trip():

    session = Session(
        user_id=100,
        username="admin",
        token="abcdef",
        created_at=datetime.now(),
        expires_at=datetime.now() + timedelta(hours=8),
    )

    restored = Session.from_dict(
        session.to_dict(),
    )

    assert restored == session


def test_delete_missing_session_file(
    session_manager,
):

    #
    # Ensure the file does not exist.
    #

    session_manager._delete()

    assert session_manager.current() is None
