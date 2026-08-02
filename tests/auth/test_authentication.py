"""
Tests for AuthenticationService.
"""

from __future__ import annotations

import pytest

from lib.users.exceptions import (
    AuthenticationError,
    UserInactiveError,
)

# ------------------------------------------------------------------
# Authenticate
# ------------------------------------------------------------------


def test_authenticate_success(
    authentication,
    user_manager,
):

    user_manager.create(
        username="john",
        password="TestUser#2026",
    )

    user = authentication.authenticate(
        "john",
        "TestUser#2026",
    )

    assert user.username == "john"


def test_authenticate_unknown_user(
    authentication,
):

    with pytest.raises(
        AuthenticationError,
    ):

        authentication.authenticate(
            "missing",
            "TestUser#2026",
        )


def test_authenticate_invalid_password(
    authentication,
    user_manager,
):

    user_manager.create(
        username="john",
        password="TestUser#2026",
    )

    with pytest.raises(
        AuthenticationError,
    ):

        authentication.authenticate(
            "john",
            "wrong-password",
        )


def test_authenticate_inactive_user(
    authentication,
    user_manager,
):

    user_manager.create(
        username="john",
        password="TestUser#2026",
    )

    user_manager.set_active(
        "john",
        False,
    )

    with pytest.raises(
        UserInactiveError,
    ):

        authentication.authenticate(
            "john",
            "TestUser#2026",
        )


# ------------------------------------------------------------------
# Password Upgrade
# ------------------------------------------------------------------


def test_authenticate_rehashes_password_when_required(
    authentication,
    user_manager,
    monkeypatch,
):

    user = user_manager.create(
        username="john",
        password="TestUser#2026",
    )

    #
    # Force rehash.
    #

    verification = type(
        "Verification",
        (),
        {
            "valid": True,
            "needs_rehash": True,
        },
    )()

    monkeypatch.setattr(
        authentication._password,
        "verify",
        lambda *_: verification,
    )

    updated_hash = "new-hash"

    monkeypatch.setattr(
        authentication._password,
        "hash",
        lambda *_: updated_hash,
    )

    authenticated = authentication.authenticate(
        "john",
        "TestUser#2026",
    )

    updated = user_manager.get(
        "john",
    )

    assert authenticated.username == "john"

    assert updated.password_hash == updated_hash
