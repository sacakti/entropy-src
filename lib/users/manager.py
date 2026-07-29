"""
User manager.
"""

from core.context import EntropyContext
from lib.models.users import User
from lib.users.exceptions import (
    AuthenticationError,
    InvalidUsernameError,
    SystemUserError,
    UserAlreadyExistsError,
    UserInactiveError,
    UserNotFoundError,
    WeakPasswordError,
)


class UserManager:

    def __init__(
        self,
        context: EntropyContext,
    ):

        self._repository = context.user_repository
        self._password = context.password_service
        self._console = context.output
        self._log = context.output.user

    # ------------------------------------------------------------------
    # Initialize
    # ------------------------------------------------------------------

    def initialize(self) -> None:

        #
        # Create the bootstrap administrator only when the
        # database contains no users.
        #

        if self._repository.any():
            return

        self.create(
            username="admin",
            password="admin123",
            full_name="Administrator",
            email=None,
            group_id=None,
            system=True,
        )

        self._log.success("Default administrator account created.")

        self._console.panel(
            title="Default Administrator",
            lines=[
                "Username : admin",
                "Password : admin123",
                "",
                "Please change the password immediately.",
                "",
                "Command:",
                "    ent user password admin",
            ],
        )

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(
        self,
        username: str,
        password: str,
        full_name: str = None,
        email: str = None,
        group_id: int = None,
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

        user = self._repository.create(user)

        self._log.success(f"User '{username}' created.")

        return user

    # ------------------------------------------------------------------
    # Authenticate
    # ------------------------------------------------------------------

    def authenticate(
        self,
        username: str,
        password: str,
    ) -> User:

        user = self._repository.get_by_username(username)

        if user is None:

            self._log.warning(f"Authentication failed for '{username}'.")

            raise AuthenticationError()

        if not user.is_active:

            self._log.warning(f"Inactive user '{username}' attempted to authenticate.")

            raise UserInactiveError(username)

        verification = self._password.verify(
            password,
            user.password_hash,
        )

        if not verification.valid:

            self._log.warning(f"Authentication failed for '{username}'.")

            raise AuthenticationError()

        self._rehash_password(
            user,
            password,
            verification.needs_rehash,
        )

        self._log.info(f"User '{username}' authenticated.")

        return user

    # ------------------------------------------------------------------
    # Change Password
    # ------------------------------------------------------------------

    def change_password(
        self,
        user: User,
        password: str,
    ) -> User:

        self._validate_password(password)

        user.password_hash = self._password.hash(password)

        self._repository.update(user)

        self._log.success(f"Password changed for '{user.username}'.")

        return self._repository.get(user.id)

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get(
        self,
        username: str,
    ) -> User:

        user = self._repository.get_by_username(username)

        if user is None:
            raise UserNotFoundError(username)

        return user

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(self) -> list[User]:

        return self._repository.list()

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(
        self,
        user: User,
    ) -> None:

        user = self.get(user.username)

        if user.system:
            raise SystemUserError(user.username)

        self._repository.delete(user.id)

        self._log.success(f"User '{user.username}' deleted.")

    # ------------------------------------------------------------------
    # Exists
    # ------------------------------------------------------------------

    def exists(
        self,
        username: str,
    ) -> bool:

        return self._repository.exists(username)

    # ------------------------------------------------------------------
    # Any
    # ------------------------------------------------------------------

    def any(self) -> bool:

        return self._repository.any()

    # ------------------------------------------------------------------
    # Set Active
    # ------------------------------------------------------------------

    def set_active(
        self,
        username: str,
        active: bool,
    ) -> User:

        user = self.get(username)

        if user is None:
            raise UserNotFoundError(username)

        if user.system and not active:
            raise SystemUserError(username)

        user.is_active = active

        self._repository.update(user)

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

        user = self.get(username)

        if user is None:
            raise UserNotFoundError(username)

        #
        # Reserved for future account lock support.
        #

        # user.failed_login_attempts = 0
        # user.locked_until = None

        # self._repository.update(user)

        # self._log.success(
        #     f"User '{username}' unlocked."
        # )

        raise NotImplementedError("Account locking is not implemented.")

        return user

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _validate_password(
        self,
        password: str,
    ) -> None:

        if not password or len(password) < 8:
            raise WeakPasswordError("Password must contain at least 8 characters.")

    def _rehash_password(
        self,
        user: User,
        password: str,
        needs_rehash: bool,
    ) -> None:

        if not needs_rehash:
            return

        user.password_hash = self._password.hash(password)

        self._repository.update(user)

        self._log.info(f"Password hash upgraded for '{user.username}'.")
