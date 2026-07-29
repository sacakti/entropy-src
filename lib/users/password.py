"""
Password service.
"""

from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError


@dataclass(frozen=True)
class PasswordVerification:

    valid: bool

    needs_rehash: bool


class PasswordService:

    def __init__(self):

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

        return self._hasher.hash(password)

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
                needs_rehash=self._hasher.check_needs_rehash(
                    password_hash,
                ),
            )

        except VerificationError:

            return PasswordVerification(
                valid=False,
                needs_rehash=False,
            )