"""
Tests for UserRepository.
"""

from __future__ import annotations

import pytest

from lib.models.users import User
from lib.users.exceptions import UserNotFoundError


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def create_user(
    repository,
    username: str = "john",
) -> User:

    return repository.create(
        User(
            username=username,
            password_hash="hash",
            full_name="John Doe",
            email="john@example.com",
            system=False,
        )
    )


# ------------------------------------------------------------------
# Create
# ------------------------------------------------------------------


def test_create(
    repository,
):

    user = create_user(
        repository,
    )

    assert user.id is not None

    assert user.username == "john"


# ------------------------------------------------------------------
# Get
# ------------------------------------------------------------------


def test_get(
    repository,
):

    created = create_user(
        repository,
    )

    user = repository.get(
        created.id,
    )

    assert user.id == created.id

    assert user.username == created.username


def test_get_unknown(
    repository,
):

    with pytest.raises(
        UserNotFoundError,
    ):

        repository.get(
            999,
        )


# ------------------------------------------------------------------
# Username
# ------------------------------------------------------------------


def test_get_by_username(
    repository,
):

    create_user(
        repository,
    )

    user = repository.get_by_username(
        "john",
    )

    assert user.username == "john"


def test_get_by_username_unknown(
    repository,
):

    with pytest.raises(
        UserNotFoundError,
    ):

        repository.get_by_username(
            "missing",
        )


# ------------------------------------------------------------------
# Exists
# ------------------------------------------------------------------


def test_exists(
    repository,
):

    create_user(
        repository,
    )

    assert repository.exists(
        "john",
    )

    assert not repository.exists(
        "jane",
    )


# ------------------------------------------------------------------
# List
# ------------------------------------------------------------------


def test_list(
    repository,
):

    create_user(
        repository,
        "john",
    )

    create_user(
        repository,
        "jane",
    )

    users = repository.list()

    assert len(
        users,
    ) == 2

    assert users[0].username == "jane"

    assert users[1].username == "john"


# ------------------------------------------------------------------
# Update
# ------------------------------------------------------------------


def test_update(
    repository,
):

    user = create_user(
        repository,
    )

    user.full_name = "Johnny"

    user.email = "johnny@example.com"

    repository.update(
        user,
    )

    updated = repository.get(
        user.id,
    )

    assert updated.full_name == "Johnny"

    assert updated.email == "johnny@example.com"


# ------------------------------------------------------------------
# Delete
# ------------------------------------------------------------------


def test_delete(
    repository,
):

    user = create_user(
        repository,
    )

    repository.delete(
        user.id,
    )

    with pytest.raises(
        UserNotFoundError,
    ):

        repository.get(
            user.id,
        )


# ------------------------------------------------------------------
# Any
# ------------------------------------------------------------------


def test_any(
    repository,
):

    assert not repository.any()

    create_user(
        repository,
    )

    assert repository.any()


# ------------------------------------------------------------------
# Count
# ------------------------------------------------------------------


def test_count(
    repository,
):

    assert repository.count() == 0

    create_user(
        repository,
        "john",
    )

    create_user(
        repository,
        "jane",
    )

    assert repository.count() == 2


# ------------------------------------------------------------------
# System User
# ------------------------------------------------------------------


def test_system_user(
    repository,
):

    repository.create(
        User(
            username="admin",
            password_hash="hash",
            system=True,
        )
    )

    user = repository.system_user()

    assert user.system

    assert user.username == "admin"
