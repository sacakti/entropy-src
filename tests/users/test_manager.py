"""
Tests for UserManager.
"""

from __future__ import annotations

import pytest

from lib.users.exceptions import (
    InvalidUsernameError,
    SystemUserError,
    UserAlreadyExistsError,
    WeakPasswordError,
)

# ------------------------------------------------------------------
# Initialize
# ------------------------------------------------------------------


def test_initialize_creates_default_admin(
    manager,
):

    assert not manager.any()

    manager.initialize()

    assert manager.any()

    admin = manager.get(
        "admin",
    )

    assert admin.username == "admin"

    assert admin.system


def test_initialize_skips_existing_database(
    manager,
):

    manager.create(
        username="john",
        password="TestUser#2026",
    )

    manager.initialize()

    users = manager.list()

    assert len(users) == 1

    assert users[0].username == "john"


# ------------------------------------------------------------------
# Create
# ------------------------------------------------------------------


def test_create_user(
    manager,
):

    user = manager.create(
        username="john",
        password="TestUser#2026",
        full_name="John Doe",
        email="john@example.com",
    )

    assert user.id is not None

    assert user.username == "john"


def test_create_duplicate_user(
    manager,
):

    manager.create(
        username="john",
        password="TestUser#2026",
    )

    with pytest.raises(
        UserAlreadyExistsError,
    ):

        manager.create(
            username="john",
            password="TestUser#2026",
        )


def test_create_invalid_username(
    manager,
):

    with pytest.raises(
        InvalidUsernameError,
    ):

        manager.create(
            username="",
            password="TestUser#2026",
        )


def test_create_weak_password(
    manager,
):

    with pytest.raises(
        WeakPasswordError,
    ):

        manager.create(
            username="john",
            password="123",
        )


# ------------------------------------------------------------------
# Authenticate
# ------------------------------------------------------------------


# def test_authenticate_success(
#     manager,
# ):

#     manager.create(
#         username="john",
#         password="TestUser#2026",
#     )

#     user = manager.authenticate(
#         "john",
#         "TestUser#2026",
#     )

#     assert user.username == "john"


# def test_authenticate_unknown_user(
#     manager,
# ):

#     with pytest.raises(
#         AuthenticationError,
#     ):

#         manager.authenticate(
#             "john",
#             "TestUser#2026",
#         )


# def test_authenticate_invalid_password(
#     manager,
# ):

#     manager.create(
#         username="john",
#         password="TestUser#2026",
#     )

#     with pytest.raises(
#         AuthenticationError,
#     ):

#         manager.authenticate(
#             "john",
#             "wrong-password",
#         )


# def test_authenticate_inactive_user(
#     manager,
# ):

#     manager.create(
#         username="john",
#         password="TestUser#2026",
#     )

#     manager.set_active(
#         "john",
#         False,
#     )

#     with pytest.raises(
#         UserInactiveError,
#     ):

#         manager.authenticate(
#             "john",
#             "TestUser#2026",
#         )


# ------------------------------------------------------------------
# Password
# ------------------------------------------------------------------


def test_change_password(
    manager,
):

    user = manager.create(
        username="john",
        password="TestUser#2026",
    )

    old_hash = user.password_hash

    manager.change_password(
        user,
        "newTestUser#2026",
    )

    updated = manager.get("john")

    assert updated.password_hash != old_hash


# ------------------------------------------------------------------
# Delete
# ------------------------------------------------------------------


def test_delete_user(
    manager,
):

    user = manager.create(
        username="john",
        password="TestUser#2026",
    )

    manager.delete(
        user,
    )

    assert not manager.exists(
        "john",
    )


def test_delete_system_user(
    manager,
):

    manager.initialize()

    admin = manager.get(
        "admin",
    )

    with pytest.raises(
        SystemUserError,
    ):

        manager.delete(
            admin,
        )


# ------------------------------------------------------------------
# Active
# ------------------------------------------------------------------


def test_disable_user(
    manager,
):

    manager.create(
        username="john",
        password="TestUser#2026",
    )

    user = manager.set_active(
        "john",
        False,
    )

    assert not user.is_active


def test_enable_user(
    manager,
):

    manager.create(
        username="john",
        password="TestUser#2026",
    )

    manager.set_active(
        "john",
        False,
    )

    user = manager.set_active(
        "john",
        True,
    )

    assert user.is_active


def test_disable_system_user(
    manager,
):

    manager.initialize()

    with pytest.raises(
        SystemUserError,
    ):

        manager.set_active(
            "admin",
            False,
        )


# ------------------------------------------------------------------
# Misc
# ------------------------------------------------------------------


def test_exists(
    manager,
):

    assert not manager.exists(
        "john",
    )

    manager.create(
        username="john",
        password="TestUser#2026",
    )

    assert manager.exists(
        "john",
    )


def test_any(
    manager,
):

    assert not manager.any()

    manager.create(
        username="john",
        password="TestUser#2026",
    )

    assert manager.any()


def test_list(
    manager,
):

    manager.create(
        username="john",
        password="TestUser#2026",
    )

    manager.create(
        username="jane",
        password="TestUser#2026",
    )

    users = manager.list()

    assert len(users) == 2

    assert sorted(user.username for user in users) == [
        "jane",
        "john",
    ]


def test_unlock_not_implemented(
    manager,
):

    with pytest.raises(
        NotImplementedError,
    ):

        manager.unlock(
            "john",
        )
