"""
User interface renderer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Sequence


class Renderer(ABC):
    """
    Abstract user interface renderer.
    """

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    @abstractmethod
    def print(
        self,
        message: str = "",
    ) -> None:
        """
        Display text.
        """

    @abstractmethod
    def rule(
        self,
        title: str = "",
    ) -> None:
        """
        Display a horizontal rule.
        """

    @abstractmethod
    def banner(
        self,
        application: str,
        version: str,
    ) -> None:
        """
        Display the application banner.
        """

    @abstractmethod
    def panel(
        self,
        title: str,
        lines: Sequence[str],
    ) -> None:
        """
        Display a panel.
        """

    @abstractmethod
    def table(
        self,
        title: str,
        columns: Sequence[str],
        rows: Iterable[Sequence[str]],
    ) -> None:
        """
        Display a table.
        """

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    @abstractmethod
    def prompt(
        self,
        message: str,
        password: bool = False,
    ) -> str:
        """
        Prompt for user input.
        """

    @abstractmethod
    def confirm(
        self,
        message: str,
    ) -> bool:
        """
        Prompt for confirmation.
        """

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------

    @abstractmethod
    def progress(
        self,
        description: str,
        total: int | None = None,
    ):
        """
        Create a progress indicator.
        """
