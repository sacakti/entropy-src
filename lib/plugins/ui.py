"""
Plugin user interface.

Provides interactive UI widgets for plugins.

This class intentionally exposes only interactive and rich UI
components. Runtime messages such as info(), warning(), success()
and error() are emitted through the plugin runtime API instead.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from core.ui import UIManager


class PluginUI:
    """
    Public UI exposed to plugins.

    This class provides only interactive widgets and rich rendering.
    Runtime messages are handled separately through the runtime
    message system.
    """

    def __init__(
        self,
        ui: UIManager,
    ) -> None:

        self._ui = ui

    # ------------------------------------------------------------------
    # Rich Widgets
    # ------------------------------------------------------------------

    def panel(
        self,
        title: str,
        lines: Sequence[str],
    ) -> None:
        """
        Display a panel.
        """

        self._ui.panel(
            title,
            list(lines),
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

        self._ui.table(
            title,
            list(columns),
            list(rows),
        )

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def prompt(
        self,
        message: str,
        *,
        password: bool = False,
    ) -> str:
        """
        Prompt for user input.
        """

        return self._ui.prompt(
            message,
            password=password,
        )

    def confirm(
        self,
        message: str,
    ) -> bool:
        """
        Prompt for confirmation.
        """

        return self._ui.confirm(
            message,
        )

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------

    def progress(
        self,
        description: str,
        total: int | None = None,
    ):
        """
        Create a progress indicator.
        """

        return self._ui.progress(
            description,
            total,
        )
