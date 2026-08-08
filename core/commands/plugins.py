"""
Plugin management command.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)


class PluginCommand(BaseCommand):
    """
    Manage Entropy plugins.
    """

    metadata = CommandMetadata(
        name="plugin",
        description="Manage Entropy plugins.",
    )

    def __init__(
        self,
        context,
    ) -> None:

        super().__init__(
            context,
        )

        assert context.plugin_manager is not None
        assert context.ui is not None
        assert context.observability is not None

        self._plugins = context.plugin_manager

        self._ui = context.ui

        self._events = context.observability.emitter(
            "plugin",
        )

    # ------------------------------------------------------------------
    # Configure
    # ------------------------------------------------------------------

    def configure(
        self,
        parser: ArgumentParser,
    ) -> None:

        subparsers = parser.add_subparsers(
            dest="action",
            required=True,
        )

        #
        # install
        #

        install = subparsers.add_parser(
            "install",
            help="Install a plugin.",
        )

        install.add_argument(
            "--reinstall",
            action="store_true",
            help="Reinstall if already installed.",
        )

        install.add_argument(
            "directory",
            help="Plugin directory.",
        )

        #
        # uninstall
        #

        uninstall = subparsers.add_parser(
            "uninstall",
            help="Uninstall a plugin.",
        )

        uninstall.add_argument(
            "plugin",
            help="Qualified plugin name.",
        )

        #
        # list
        #

        subparsers.add_parser(
            "list",
            help="List installed plugins.",
        )

        #
        # verify
        #

        verify = subparsers.add_parser(
            "verify",
            help="Verify a plugin manifest.",
        )

        verify.add_argument(
            "directory",
            help="Plugin directory.",
        )

        #
        # enable/disable
        #

        set = subparsers.add_parser(
            "set",
            help="Enable or disable a plugin.",
        )

        # Flag to enable/disable the plugin

        set.add_argument(
            "--enable",
            action="store_true",
            help="Enable the plugin.",
        )

        set.add_argument(
            "--disable",
            action="store_true",
            help="Disable the plugin.",
        )

        set.add_argument(
            "plugin",
            help="Qualified plugin name.",
        )
    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        args: Namespace,
    ) -> None:

        {
            "install": self._install,
            "uninstall": self._uninstall,
            "list": self._list,
            "verify": self._verify,
        }[
            args.action
        ](
            args,
        )

    # ------------------------------------------------------------------
    # Install
    # ------------------------------------------------------------------

    def _install(
        self,
        args: Namespace,
    ) -> None:

        plugin = self._plugins.install(
            Path(
                args.directory,
            ),
            reinstall=args.reinstall,
        )

        self._events.log.info(
            f"Plugin '{plugin.qualified_name}' installed.",
        )

    # ------------------------------------------------------------------
    # Uninstall
    # ------------------------------------------------------------------

    def _uninstall(
        self,
        args: Namespace,
    ) -> None:

        self._plugins.uninstall(
            args.plugin,
        )

        self._events.log.info(
            f"Plugin '{args.plugin}' uninstalled.",
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def _list(
        self,
        args: Namespace,
    ) -> None:

        plugins = self._plugins.list()

        self._ui.table(
            title="Installed Plugins",
            columns=[
                "Namespace",
                "Name",
                "Version",
                "Enabled",
                "Installed At",
                "Path",
            ],
            rows=[
                [
                    plugin.namespace,
                    plugin.name,
                    plugin.version,
                    "Yes" if plugin.enabled else "No",
                    plugin.installed_at,
                    str(plugin.path),
                ]
                for plugin in plugins
            ],
        )

    # ------------------------------------------------------------------
    # Verify
    # ------------------------------------------------------------------

    def _verify(
        self,
        args: Namespace,
    ) -> None:

        self._plugins.verify(
            Path(
                args.directory,
            ),
        )

        self._events.log.info(
            "Plugin manifest verified.",
        )
