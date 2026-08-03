"""
Authentication service.
"""

from __future__ import annotations

from core.context import EntropyContext
from core.observability.null import NullEmitter
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

        if context.observability is not None:

            self._events = context.observability.emitter(
                "entropy",
            )

        else:

            self._events = NullEmitter()

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

            self._events.warning(f"Authentication failed for '{username}'.")

            raise AuthenticationError() from None

        if not user.is_active:

            self._events.warning(f"Inactive user '{username}' attempted authentication.")

            raise UserInactiveError(
                username,
            )

        verification = self._password.verify(
            password,
            user.password_hash,
        )

        if not verification.valid:

            self._events.warning(f"Authentication failed for '{username}'.")

            raise AuthenticationError()

        if verification.needs_rehash:

            user.password_hash = self._password.hash(
                password,
            )

            self._repository.update(
                user,
            )

            self._events.info(f"Password hash upgraded for '{user.username}'.")

        # self._events.info(f"User '{username}' authenticated.")

        return user
