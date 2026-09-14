from core.exceptions import EntropyException


class VaultError(EntropyException):
    """
    Base exception for Vault errors.
    """


class VaultEntryExistsError(VaultError):
    """
    Raised when a Vault key already exists.
    """


class VaultEntryNotFoundError(VaultError):
    """
    Raised when a Vault key does not exist.
    """


class VaultKeyError(VaultError, RuntimeError):
    """
    Raised when the Vault master key cannot be loaded or created.
    """


class VaultValueError(VaultError):
    """
    Raised when a Vault value is invalid.
    """

    def __init__(
        self,
        message: str,
    ) -> None:

        super().__init__(
            message,
        )


class VaultNamespaceExistsError(VaultError):
    """
    Raised when a Vault namespace already exists.
    """

    def __init__(
        self,
        name: str,
    ) -> None:

        super().__init__(
            f"Vault namespace '{name}' already exists.",
        )


class VaultNamespaceNotFoundError(VaultError):
    """
    Raised when a Vault namespace does not exist.
    """

    def __init__(
        self,
        name: str,
    ) -> None:

        super().__init__(
            f"Vault namespace '{name}' not found.",
        )


class VaultNamespaceNameError(VaultError):
    """
    Raised when a Vault namespace name is invalid.
    """

    def __init__(
        self,
        message: str = "Vault namespace name cannot be empty.",
    ) -> None:

        super().__init__(
            message,
        )


class VaultNamespaceAccessError(VaultError):
    """
    Raised when Vault namespace access is invalid.
    """

    def __init__(
        self,
        message: str,
    ) -> None:

        super().__init__(
            message,
        )


class VaultAccessDeniedError(VaultError):
    """
    Raised when a user cannot access a Vault namespace.
    """
