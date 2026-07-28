"""
Password service.
"""

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError


class PasswordService:

    def __init__(self):

        self._hasher = PasswordHasher()

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
    ) -> bool:

        try:

            return self._hasher.verify(
                password_hash,
                password,
            )

        except VerifyMismatchError:

            return False