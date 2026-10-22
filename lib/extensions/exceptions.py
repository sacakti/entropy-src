"""
Extension exceptions.
"""

from core.exceptions import EntropyException


class ExtensionError(EntropyException):
    """
    Base exception for all extension-related errors.
    """


class ExtensionNotFoundError(ExtensionError):

    def __init__(
        self,
        name: str,
    ) -> None:

        super().__init__(
            f"Extension '{name}' is not installed.",
        )


class ExtensionWheelNotFoundError(ExtensionError):

    def __init__(
        self,
        name: str,
    ):

        super().__init__(f"No offline package found for extension '{name}'.")


class ExtensionAlreadyInstalledError(ExtensionError):

    def __init__(
        self,
        name: str,
    ) -> None:

        super().__init__(
            f"Extension '{name}' is already installed.",
        )


class ExtensionInstallationError(ExtensionError):

    def __init__(
        self,
        message: str,
    ) -> None:

        super().__init__(
            message,
        )


class ExtensionValidationError(ExtensionError):

    def __init__(
        self,
        message: str,
    ) -> None:

        super().__init__(
            message,
        )


class ExtensionDownloadError(ExtensionError):

    def __init__(
        self,
        message: str,
    ) -> None:

        super().__init__(
            message,
        )


class ExtensionValueError(ExtensionError):

    def __init__(
        self,
        message: str,
    ) -> None:

        super().__init__(
            message,
        )


class ExtensionExistsError(ExtensionError):
    """The library is already there (as an extension, or as part of Entropy)."""

    def __init__(
        self,
        message: str,
    ) -> None:

        super().__init__(
            message,
        )


class ExtensionInUseError(ExtensionError):
    """Installed plugins still need this version."""

    def __init__(
        self,
        message: str,
    ) -> None:

        super().__init__(
            message,
        )
