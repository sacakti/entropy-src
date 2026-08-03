from __future__ import annotations

from abc import ABC, abstractmethod

from core.context import EntropyContext
from lib.models.extensions import Extension


class BaseInstaller(ABC):
    """
    Base extension installer.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        self._context = context

    @abstractmethod
    def install(
        self,
        name: str,
        version: str | None = None,
    ) -> None:
        """
        Install an extension.
        """

    @abstractmethod
    def uninstall(
        self,
        extension: Extension,
    ) -> None:
        """
        Uninstall an extension.
        """
