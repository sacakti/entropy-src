import pytest

from lib.users.exceptions import (
    AuthenticationError,
    InvalidUsernameError,
    SystemUserError,
    UserAlreadyExistsError,
    UserInactiveError,
    UserNotFoundError,
    WeakPasswordError,
)


def test_create_user(manager):

    user = manager.create(
        username="admin",
        password="password123",
    )

    assert user.username == "admin"
    assert manager.exists("admin")


def test_username_is_trimmed(manager):

    user = manager.create(
        username="  admin  ",
        password="password123",
    )

    assert user.username == "admin"


def test_empty_username(manager):

    with pytest.raises(InvalidUsernameError):
        manager.create(
            username="   ",
            password="password123",
        )


def test_duplicate_username(manager):

    manager.create(
        username="admin",
        password="password123",
    )

    with pytest.raises(UserAlreadyExistsError):
        manager.create(
            username="admin",
            password="password123",
        )


def test_weak_password(manager):

    with pytest.raises(WeakPasswordError):
        manager.create(
            username="admin",
            password="123",
        )


def test_authenticate(manager):

    manager.create(
        username="admin",
        password="password123",
    )

    user = manager.authenticate(
        "admin",
        "password123",
    )

    assert user.username == "admin"


def test_authenticate_wrong_password(manager):

    manager.create(
        username="admin",
        password="password123",
    )

    with pytest.raises(AuthenticationError):
        manager.authenticate(
            "admin",
            "wrong",
        )


def test_inactive_user(manager):

    manager.create(
        username="admin",
        password="password123",
    )

    manager.set_active(
        "admin",
        False,
    )

    with pytest.raises(UserInactiveError):
        manager.authenticate(
            "admin",
            "password123",
        )


def test_change_password(manager):

    user = manager.create(
        username="admin",
        password="password123",
    )

    manager.change_password(
        user,
        "newpassword123",
    )

    manager.authenticate(
        "admin",
        "newpassword123",
    )


def test_old_password_invalid_after_change(manager):

    user = manager.create(
        username="admin",
        password="password123",
    )

    manager.change_password(
        user,
        "newpassword123",
    )

    with pytest.raises(AuthenticationError):
        manager.authenticate(
            "admin",
            "password123",
        )


def test_delete_user(manager):

    user = manager.create(
        username="admin",
        password="password123",
    )

    manager.delete(user)

    with pytest.raises(UserNotFoundError):
        manager.get("admin")


def test_delete_system_user(manager):

    user = manager.create(
        username="admin",
        password="password123",
        system=True,
    )

    with pytest.raises(SystemUserError):
        manager.delete(user)


def test_disable_enable_user(manager):

    manager.create(
        username="admin",
        password="password123",
    )

    user = manager.set_active(
        "admin",
        False,
    )

    assert user.is_active is False

    user = manager.set_active(
        "admin",
        True,
    )

    assert user.is_active is True


def test_disable_system_user(manager):

    manager.create(
        username="admin",
        password="password123",
        system=True,
    )

    with pytest.raises(SystemUserError):
        manager.set_active(
            "admin",
            False,
        )


def test_authenticate_unknown_user(manager):

    with pytest.raises(AuthenticationError):
        manager.authenticate(
            "unknown",
            "password123",
        )
