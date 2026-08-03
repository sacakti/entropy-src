"""
Authentication service.
"""

from __future__ import annotations

from core.context import EntropyContext
from lib.models.users import User
from lib.users.exceptions import (
    AuthenticationError,
    UserInactiveError,
    UserNotFoundError,
)


class AuthenticationService:
    """
    Authenticates users.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        assert context.user_repository is not None
        assert context.password_service is not None

        self._repository = context.user_repository
        self._password = context.password_service

    # ------------------------------------------------------------------
    # Authenticate
    # ------------------------------------------------------------------

    def authenticate(
        self,
        username: str,
        password: str,
    ) -> User:
        """
        Authenticate a user.
        """

        try:

            user = self._repository.get_by_username(
                username,
            )

        except UserNotFoundError:

            raise AuthenticationError() from None

        if not user.is_active:

            raise UserInactiveError(
                username,
            )

        verification = self._password.verify(
            password,
            user.password_hash,
        )

        if not verification.valid:

            raise AuthenticationError()

        if verification.needs_rehash:

            user.password_hash = self._password.hash(
                password,
            )

            self._repository.update(
                user,
            )

        return user
