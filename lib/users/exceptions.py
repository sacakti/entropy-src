"""
User exceptions.
"""

from core.exceptions import EntropyException


class UserError(EntropyException):
    """Base exception for all user-related errors."""


class InvalidUsernameError(UserError):

    def __init__(self):

        super().__init__("Username cannot be empty.")


class UserAlreadyExistsError(UserError):

    def __init__(
        self,
        username: str,
    ):

        super().__init__(f"User '{username}' already exists.")


class UserNotFoundError(UserError):

    def __init__(
        self,
        username: str,
    ):

        super().__init__(f"User '{username}' does not exist.")


class WeakPasswordError(UserError):

    def __init__(
        self,
        reason: str,
    ):

        super().__init__(reason)


class AuthenticationError(UserError):

    def __init__(self):

        super().__init__("Invalid username or password. Try again.")


class UserInactiveError(UserError):

    def __init__(
        self,
        username: str,
    ):

        super().__init__(f"User '{username}' is inactive.")


class SystemUserError(UserError):

    def __init__(self, *args):
        super().__init__("System user cannot be disabled or deleted.")

class PasswordsNotMatchError(UserError):

    def __init__(self):

        super().__init__(
            "Passwords do not match.",
        )


class CurrentPasswordMismatchError(UserError):

    def __init__(self):

        super().__init__(
            "Current password is incorrect.",
        )


class PasswordReuseError(UserError):

    def __init__(self):

        super().__init__(
            "New password cannot be the same as the current password.",
        )

class PasswordResetError(UserError):

    def __init__(
        self,
        message: str = "Password reset failed.",
    ):

        super().__init__(
            message,
        )

class UserAlreadyActiveError(UserError):

    def __init__(self):

        super().__init__(
            "User is already active.",
        )

class UserAlreadyInactiveError(UserError):

    def __init__(self):

        super().__init__(
            "User is already inactive.",
        )

class UnauthorizedActionError(UserError):

    def __init__(self):

        super().__init__(
            "You are not authorized to perform this action.",
        )
