"""
Tests for PasswordService.
"""

from lib.users.password import PasswordService


class TestPasswordService:

    def test_hash_returns_non_empty_string(self) -> None:

        service = PasswordService()

        password_hash = service.hash("secret")

        assert isinstance(password_hash, str)
        assert password_hash
        assert password_hash != "secret"

    def test_verify_valid_password(self) -> None:

        service = PasswordService()

        password = "secret"

        password_hash = service.hash(password)

        result = service.verify(
            password,
            password_hash,
        )

        assert result.valid is True
        assert result.needs_rehash is False

    def test_verify_invalid_password(self) -> None:

        service = PasswordService()

        password_hash = service.hash("secret")

        result = service.verify(
            "wrong-password",
            password_hash,
        )

        assert result.valid is False
        assert result.needs_rehash is False

    def test_same_password_produces_different_hashes(self) -> None:

        service = PasswordService()

        hash1 = service.hash("secret")
        hash2 = service.hash("secret")

        assert hash1 != hash2

    def test_unicode_password(self) -> None:

        service = PasswordService()

        password = "Pāsswörd🔐தமிழ்"

        password_hash = service.hash(password)

        result = service.verify(
            password,
            password_hash,
        )

        assert result.valid is True

    def test_empty_password(self) -> None:

        service = PasswordService()

        password_hash = service.hash("")

        result = service.verify(
            "",
            password_hash,
        )

        assert result.valid is True

    def test_hash_is_argon2(self) -> None:

        service = PasswordService()

        password_hash = service.hash("secret")

        assert password_hash.startswith("$argon2")

    def test_modified_hash_fails_verification(self) -> None:

        service = PasswordService()

        password_hash = service.hash("secret")

        modified = password_hash[:-1] + ("A" if password_hash[-1] != "A" else "B")

        result = service.verify(
            "secret",
            modified,
        )

        assert result.valid is False
