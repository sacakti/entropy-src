"""
Authorization exceptions.
"""

from __future__ import annotations

from core.exceptions import EntropyException


class AuthorizationException(EntropyException):
    """
    Base class for authorization failures.
    """


class AuthorizationRequiredError(AuthorizationException):
    """
    Raised when the authenticated user lacks a required permission.
    """

    def __init__(
        self,
        permission: str,
    ) -> None:

        super().__init__(
            f"Permission denied: '{permission}'.",
        )

class RoleNotFoundError(AuthorizationException):
    """
    Raised when a role does not exist.
    """

    def __init__(
        self,
        name: str,
    ) -> None:

        super().__init__(
            f"Role '{name}' not found.",
        )


class RoleAlreadyExistsError(AuthorizationException):
    """
    Raised when a role already exists.
    """

    def __init__(
        self,
        name: str,
    ) -> None:

        super().__init__(
            f"Role '{name}' already exists.",
        )


class GroupNotFoundError(AuthorizationException):
    """
    Raised when a group does not exist.
    """

    def __init__(
        self,
        name: str,
    ) -> None:

        super().__init__(
            f"Group '{name}' not found.",
        )


class GroupAlreadyExistsError(AuthorizationException):
    """
    Raised when a group already exists.
    """

    def __init__(
        self,
        name: str,
    ) -> None:

        super().__init__(
            f"Group '{name}' already exists.",
        )


class PermissionNotFoundError(AuthorizationException):
    """
    Raised when a permission does not exist.
    """

    def __init__(
        self,
        name: str,
    ) -> None:

        super().__init__(
            f"Permission '{name}' not found.",
        )

class AuthGenericError(AuthorizationException):
    """
    Raised when a generic authorization error occurs.
    """
