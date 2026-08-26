"""
Entropy application.
"""

from __future__ import annotations

from argparse import Namespace

from core.context import EntropyContext
from core.context_factory import ContextFactory
from core.models.logger import LogLevel
from core.parser import ApplicationParser
from lib.upgrade.transaction import UpgradeTransaction


class Application:
    """
    Entropy application.

    Responsible for bootstrapping the application,
    applying runtime configuration, and executing
    the selected command.
    """

    def __init__(self) -> None:

        self._factory = ContextFactory()

        self._parser = ApplicationParser()

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

        self._recover_upgrade()

    def parse(
        self,
    ) -> tuple[Namespace, list[str]]:
        """
        Parse application arguments.
        """

        return self._parser.parse()

    def initialize(
        self,
        args: Namespace,
    ) -> None:
        """
        Build the application context.
        """

        self._factory.build()

        self._configure_runtime(
            args,
        )

        self._factory.discover()

        self._check_plugin_updates()

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------

    def _configure_runtime(
        self,
        args: Namespace,
    ) -> None:
        """
        Apply runtime configuration overrides.
        """

        assert self.context.console_log_sink is not None

        if args.verbose >= 1:

            self.context.console_log_sink.level = LogLevel.DEBUG

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(
        self,
        argv: list[str],
    ) -> None:

        assert self.context.command_manager is not None

        args = self.context.command_manager.parse(
            argv,
        )

        self.context.command_manager.execute_command(
            args,
        )

    # Recover upgrade
    def _recover_upgrade(self) -> None:
        """
        Recover an interrupted application upgrade.
        """

        assert self.context.bootstrap is not None

        transaction = UpgradeTransaction(
            self.context.bootstrap.application,
        )

        if not transaction.has_pending_transaction():

            return

        print("Recovering interrupted Entropy upgrade...")

        transaction.recover()

        print("Entropy upgrade recovery completed.")

    def _check_plugin_updates(
        self,
    ) -> None:
        """
        Check for available plugin updates.

        Plugin changes are only reported here. No plugin is
        installed, upgraded, or removed automatically.
        """

        assert self.context.plugin_manager is not None
        assert self.context.bootstrap is not None
        assert self.context.ui is not None

        source = (
            self.context.bootstrap.application.directory
            / "resources"
            / "plugins"
        )

        if not source.is_dir():

            return

        changes = self.context.plugin_manager.check_updates(
            source,
        )

        changes = [
            change
            for change in changes
            if change.change_type.value in {
                "new",
                "upgrade",
            }
        ]

        if not changes:

            return

        self.context.ui.info(
            f"{len(changes)} plugin update(s) available. "
            "Run 'ent plugin upgrade' to review and upgrade.",
        )
