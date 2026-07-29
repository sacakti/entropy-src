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

        super().__init__(
            "Please authenticate using 'ent auth'."
        )
