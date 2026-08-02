"""
User manager.
"""

from __future__ import annotations

import secrets

from core.context import EntropyContext
from lib.database.repositories.users import UserRepository
from lib.models.users import User
from lib.users.exceptions import (
    InvalidUsernameError,
    SystemUserError,
    UserAlreadyExistsError,
)
from lib.users.password import PasswordService


class UserManager:
    """
    User lifecycle management.

    Responsibilities
    ----------------
    - Create users
    - Delete users
    - Change passwords
    - Enable/disable users
    - Bootstrap administrator
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        assert context.user_repository is not None
        assert context.password_service is not None
        assert context.diagnostics is not None

        self._repository: UserRepository = context.user_repository

        self._password: PasswordService = context.password_service

        self._log = context.diagnostics.logger(
            "user",
        )

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """
        Create the bootstrap administrator when no users exist.
        """

        if self._repository.any():
            return

        password = secrets.token_urlsafe(16)

        self.create(
            username="admin",
            password=password,
            full_name="Administrator",
            system=True,
        )

        self._log.success("Bootstrap administrator created.")

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(
        self,
        username: str,
        password: str,
        full_name: str | None = None,
        email: str | None = None,
        group_id: int | None = None,
        system: bool = False,
    ) -> User:

        username = username.strip()

        if not username:
            raise InvalidUsernameError()

        if self._repository.exists(username):
            raise UserAlreadyExistsError(username)

        self._validate_password(password)

        user = User(
            username=username,
            password_hash=self._password.hash(password),
            full_name=full_name,
            email=email,
            group_id=group_id,
            system=system,
        )

        user = self._repository.create(
            user,
        )

        self._log.success(f"User '{username}' created.")

        return user

    # ------------------------------------------------------------------
    # Change Password
    # ------------------------------------------------------------------

    def change_password(
        self,
        user: User,
        password: str,
    ) -> User:

        self._validate_password(
            password,
        )

        user.password_hash = self._password.hash(
            password,
        )

        self._repository.update(
            user,
        )

        self._log.success(f"Password changed for '{user.username}'.")

        assert user.id is not None

        return self._repository.get(
            user.id,
        )

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get(
        self,
        username: str,
    ) -> User:

        return self._repository.get_by_username(
            username,
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(
        self,
    ) -> list[User]:

        return self._repository.list()

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(
        self,
        user: User,
    ) -> None:

        user = self.get(
            user.username,
        )

        if user.system:

            raise SystemUserError()

        assert user.id is not None

        self._repository.delete(
            user.id,
        )

        self._log.success(f"User '{user.username}' deleted.")

    # ------------------------------------------------------------------
    # Exists
    # ------------------------------------------------------------------

    def exists(
        self,
        username: str,
    ) -> bool:

        return self._repository.exists(
            username,
        )

    # ------------------------------------------------------------------
    # Any
    # ------------------------------------------------------------------

    def any(
        self,
    ) -> bool:

        return self._repository.any()

    # ------------------------------------------------------------------
    # Active
    # ------------------------------------------------------------------

    def set_active(
        self,
        username: str,
        active: bool,
    ) -> User:

        user = self.get(
            username,
        )

        if user.system and not active:

            raise SystemUserError()

        user.is_active = active

        self._repository.update(
            user,
        )

        action = "enabled" if active else "disabled"

        self._log.success(f"User '{username}' {action}.")

        return user

    # ------------------------------------------------------------------
    # Unlock
    # ------------------------------------------------------------------

    def unlock(
        self,
        username: str,
    ) -> User:

        raise NotImplementedError("Account locking is not implemented.")

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_password(
        self,
        password: str,
    ) -> None:

        self._password.validate(
            password,
        )
