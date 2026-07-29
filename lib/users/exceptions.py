"""
User exceptions.
"""

from core.exceptions import EntropyException

class UserError(EntropyException):
    """Base exception for all user-related errors."""


class InvalidUsernameError(UserError):

    def __init__(self):

        super().__init__(
            "Username cannot be empty."
        )


class UserAlreadyExistsError(UserError):

    def __init__(
        self,
        username: str,
    ):

        super().__init__(
            f"User '{username}' already exists."
        )


class UserNotFoundError(UserError):

    def __init__(
        self,
        username: str,
    ):

        super().__init__(
            f"User '{username}' does not exist."
        )


class WeakPasswordError(UserError):

    def __init__(
        self,
        reason: str,
    ):

        super().__init__(reason)


class AuthenticationError(UserError):

    def __init__(self):

        super().__init__(
            "Invalid username or password."
        )


class UserInactiveError(UserError):

    def __init__(
        self,
        username: str,
    ):

        super().__init__(
            f"User '{username}' is inactive."
        )

class SystemUserError(UserError):

    def __init__(self, *args):
        super().__init__(
            f"System user cannot be disabled or deleted."
        ) 