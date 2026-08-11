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

class VaultKeyError(
    EntropyException,
    RuntimeError
):
    """
    Raised when the Vault master key cannot be loaded or created.
    """

class VaultValueError(VaultError):
    """
    Raised value error.
    """
    def __init__(
        self,
        message: str,
    ) -> None:

        super().__init__(
            message,
        )
