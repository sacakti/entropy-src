"""
Password service.
"""

from dataclasses import dataclass
from typing import cast
import secrets
import string
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from lib.users.exceptions import WeakPasswordError


@dataclass(frozen=True)
class PasswordVerification:

    valid: bool

    needs_rehash: bool


class PasswordService:

    def __init__(
        self,
    ) -> None:

        self._hasher = PasswordHasher(
            time_cost=3,
            memory_cost=65536,
            parallelism=4,
        )

    # ------------------------------------------------------------------
    # Hash
    # ------------------------------------------------------------------

    def hash(
        self,
        password: str,
    ) -> str:

        return cast(str, self._hasher.hash(password))

    # ------------------------------------------------------------------
    # Verify
    # ------------------------------------------------------------------

    def verify(
        self,
        password: str,
        password_hash: str,
    ) -> PasswordVerification:

        try:

            self._hasher.verify(
                password_hash,
                password,
            )

            return PasswordVerification(
                valid=True,
                needs_rehash=cast(
                    bool,
                    self._hasher.check_needs_rehash(password_hash),
                ),
            )

        except VerifyMismatchError:

            return PasswordVerification(
                valid=False,
                needs_rehash=False,
            )

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------

    def validate(
        self,
        password: str,
    ) -> None:
        """
        Validate password strength.
        """

        if not password:

            raise WeakPasswordError("Password is required.")

        if len(password) < 8:

            raise WeakPasswordError("Password must contain at least 8 characters.")

        if password.isspace():

            raise WeakPasswordError("Password cannot contain only whitespace.")

        if password.lower() in {
            "password",
            "password123",
            "admin123",
        }:

            raise WeakPasswordError("Password is too common and must contain at least 8 characters.")

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------

    def generate(
        self,
        length: int = 20,
    ) -> str:
        """
        Generate a temporary password that satisfies
        the current password policy.
        """

        alphabet = (
            string.ascii_letters
            + string.digits
            + "!@#$%^&*()-_=+"
        )

        while True:

            password = "".join(
                secrets.choice(alphabet)
                for _ in range(length)
            )

            try:

                self.validate(
                    password,
                )

                return password

            except WeakPasswordError:

                continue
