"""
Authentication exceptions
"""

from core.exceptions import EntropyException


class AuthenticationException(EntropyException):
    """
    Base class for all authentication exception
    """


class AuthenticationRequiredError(AuthenticationException):

    def __init__(self):

        super().__init__("Please authenticate using 'ent auth'.")

class SessionNotFoundError(AuthenticationException):

    def __init__(self, username: str):

        super().__init__(f"No authenticated session exists for '{username}'.")
