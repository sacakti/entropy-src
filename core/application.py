"""
Entropy application.
"""

from __future__ import annotations

from core.context import EntropyContext
from core.context_factory import ContextFactory


class Application:
    """
    Entropy application.

    Responsible only for bootstrapping the application
    and executing the command line.
    """

    def __init__(self) -> None:

        self._factory = ContextFactory()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def context(self) -> EntropyContext:

        return self._factory.context

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def bootstrap(self) -> None:
        """
        Bootstrap the application.
        """

        self._factory.bootstrap()

    def initialize(self) -> None:
        """
        Build the application context.
        """

        self._factory.build()

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Execute the requested command.
        """

        assert self.context.command_manager is not None

        self.context.command_manager.run()
