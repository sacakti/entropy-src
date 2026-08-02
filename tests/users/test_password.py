"""
Tests for PasswordService.
"""

from __future__ import annotations

import pytest

from lib.users.exceptions import WeakPasswordError
from lib.users.password import PasswordVerification


def test_hash_returns_hash(
    password_service,
):

    password_hash = password_service.hash(
        "TestUser#2026",
    )

    assert isinstance(
        password_hash,
        str,
    )

    assert password_hash


def test_hash_is_not_plaintext(
    password_service,
):

    password = "TestUser#2026"

    password_hash = password_service.hash(
        password,
    )

    assert password_hash != password


def test_verify_valid_password(
    password_service,
):

    password = "TestUser#2026"

    password_hash = password_service.hash(
        password,
    )

    verification = password_service.verify(
        password,
        password_hash,
    )

    assert isinstance(
        verification,
        PasswordVerification,
    )

    assert verification.valid

    assert verification.needs_rehash is False


def test_verify_invalid_password(
    password_service,
):

    password_hash = password_service.hash(
        "TestUser#2026",
    )

    verification = password_service.verify(
        "wrong-password",
        password_hash,
    )

    assert verification.valid is False

    assert verification.needs_rehash is False


def test_hashes_are_unique(
    password_service,
):

    password = "TestUser#2026"

    hash1 = password_service.hash(
        password,
    )

    hash2 = password_service.hash(
        password,
    )

    #
    # Argon2 uses a random salt.
    #

    assert hash1 != hash2

    assert password_service.verify(
        password,
        hash1,
    ).valid

    assert password_service.verify(
        password,
        hash2,
    ).valid

def test_validate_empty_password(
    password_service,
):

    with pytest.raises(
        WeakPasswordError,
    ):

        password_service.validate("")


def test_validate_whitespace_password(
    password_service,
):

    with pytest.raises(
        WeakPasswordError,
    ):

        password_service.validate("        ")


def test_validate_common_password(
    password_service,
):

    with pytest.raises(
        WeakPasswordError,
    ):

        password_service.validate(
            "password123",
        )


def test_validate_short_password(
    password_service,
):

    with pytest.raises(
        WeakPasswordError,
    ):

        password_service.validate(
            "short",
        )


def test_validate_valid_password(
    password_service,
):

    password_service.validate(
        "Entropy@2026",
    )
