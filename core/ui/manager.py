"""
User interface manager.
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence

from .prompt import PromptManager
from .renderer import Renderer


class UIManager:
    """
    User interface subsystem.
    """

    def __init__(
        self,
        renderer: Renderer,
        prompt: PromptManager,
    ) -> None:

        self._renderer = renderer
        self._prompt = prompt

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def print(
        self,
        *args,
        **kwargs,
    ) -> None:
        """
        Display arbitrary renderable content.
        """

        self._renderer.print(
            *args,
            **kwargs,
        )

    def rule(
        self,
        title: str = "",
    ) -> None:
        """
        Display a rule.
        """

        self._renderer.rule(
            title,
        )

    def banner(
        self,
        application: str,
        version: str,
    ) -> None:
        """
        Display the application banner.
        """

        self._renderer.banner(
            application,
            version,
        )

    def panel(
        self,
        title: str,
        lines: Sequence[str],
    ) -> None:
        """
        Display a panel.
        """

        self._renderer.panel(
            title,
            lines,
        )

    def table(
        self,
        title: str,
        columns: Sequence[str],
        rows: Iterable[Sequence[str]],
    ) -> None:
        """
        Display a table.
        """

        self._renderer.table(
            title,
            columns,
            rows,
        )

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def prompt(
        self,
        message: str,
        password: bool = False,
    ) -> str:
        """
        Prompt for user input.
        """

        return self._prompt.prompt(
            message,
            password,
        )

    def confirm(
        self,
        message: str,
    ) -> bool:
        """
        Prompt for confirmation.
        """

        return self._prompt.confirm(
            message,
        )

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------

    def progress(
        self,
        description: str,
        total: Optional[int] = None,
    ):
        """
        Create a progress indicator.
        """

        return self._renderer.progress(
            description,
            total,
        )

    def info(
        self,
        message: str,
    ) -> None:

        self._renderer.info(
            message,
        )


    def success(
        self,
        message: str,
    ) -> None:

        self._renderer.success(
            message,
        )


    def warning(
        self,
        message: str,
    ) -> None:

        self._renderer.warning(
            message,
        )


    def error(
        self,
        message: str,
    ) -> None:

        self._renderer.error(
            message,
        )
