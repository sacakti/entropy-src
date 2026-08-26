"""
User manager.
"""

from __future__ import annotations

from core.context import EntropyContext
from lib.database.repositories.users import UserRepository
from lib.models.users import SYSTEM_USERNAME, User
from lib.users.exceptions import (
    CurrentPasswordMismatchError,
    InvalidUsernameError,
    PasswordReuseError,
    SystemUserError,
    UserAlreadyExistsError,
    WeakPasswordError,
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

        self._repository: UserRepository = context.user_repository

        self._password: PasswordService = context.password_service

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """
        Initialize the user subsystem.

        Bootstrap administrator creation is handled by
        BootstrapInstaller.
        """

        return

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(
        self,
        username: str,
        password: str,
        full_name: str | None = None,
        email: str | None = None,
    ) -> User:
        """
        Create a user.
        """

        username = username.strip()
        full_name = full_name.strip() if full_name else None
        email = email.strip() if email else None

        if not username:

            raise InvalidUsernameError()

        if self._repository.exists(
            username,
        ):

            raise UserAlreadyExistsError(
                username,
            )

        self._validate_password(
            password,
        )

        user = User(
            username=username,
            password_hash=self._password.hash(
                password,
            ),
            full_name=full_name,
            email=email,
        )

        return self._repository.create(
            user,
        )

    # ------------------------------------------------------------------
    # Password
    # ------------------------------------------------------------------

    def _set_password(
        self,
        user: User,
        password: str,
    ) -> User:
        """
        Set a user's password.

        Internal helper used by password change and reset.
        """

        self._validate_password(
            password,
        )

        verification = self._password.verify(
            password,
            user.password_hash,
        )

        if verification.valid:

            raise PasswordReuseError()

        user.password_hash = self._password.hash(
            password,
        )

        self._repository.update(
            user,
        )

        assert user.id is not None

        return self._repository.get(
            user.id,
        )

    def change_password(
        self,
        user: User,
        current_password: str,
        new_password: str,
    ) -> User:
        """
        Change the user's own password.
        """

        verification = self._password.verify(
            current_password,
            user.password_hash,
        )

        if not verification.valid:

            raise CurrentPasswordMismatchError()

        return self._set_password(
            user,
            new_password,
        )

    def admin_change_password(
        self,
        user: User,
        password: str,
    ) -> User:
        """
        Change another user's password.

        Authorization is handled by the caller.
        """

        return self._set_password(
            user,
            password,
        )

    def reset_password(
        self,
        user: User,
    ) -> tuple[User, str]:
        """
        Generate and assign a temporary password.

        Authorization is handled by the caller.
        """

        while True:

            password = self._password.generate()

            try:

                user = self.admin_change_password(
                    user,
                    password,
                )

                return (
                    user,
                    password,
                )

            except WeakPasswordError:

                continue

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
        """
        Delete a user.

        Authorization is handled by the caller.
        """

        user = self.get(
            user.username,
        )

        self._ensure_not_system_user(
            user,
        )

        assert user.id is not None

        self._repository.delete(
            user.id,
        )

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
        """
        Enable or disable a user.

        Authorization is handled by the caller.
        """

        user = self.get(
            username,
        )

        self._ensure_not_system_user(
            user,
        )

        user.is_active = active

        self._repository.update(
            user,
        )

        return user

    # ------------------------------------------------------------------
    # Unlock
    # ------------------------------------------------------------------

    def unlock(
        self,
        username: str,
    ) -> User:

        raise NotImplementedError(
            "Account locking is not implemented.",
        )

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

    @staticmethod
    def _ensure_not_system_user(
        user: User,
    ) -> None:

        if user.username == SYSTEM_USERNAME:

            raise SystemUserError()
