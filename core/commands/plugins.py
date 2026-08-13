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
from lib.models.plugin import PluginResult
from lib.plugins.mode import PluginMode

class PluginCommand(
    BaseCommand,
):
    """
    Manage Entropy plugins.
    """

    metadata = CommandMetadata(
        name="plugin",
        description="Manage Entropy plugins.",
        aliases=(
            "plugins",
            "pl",
        ),
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

        self._plugins = context.plugin_manager

        self._ui = context.ui

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
        # run
        #

        run = subparsers.add_parser(
            "run",
            help="Execute a plugin.",
        )

        run.add_argument(
            "plugin",
            help="Qualified plugin name.",
        )

        run.add_argument(
            "--argument",
            "-a",
            action="append",
            default=[],
            metavar="KEY=VALUE",
            help="Plugin argument. May be specified multiple times.",
        )

        #
        # verify
        #

        verify = subparsers.add_parser(
            "verify",
            help="Verify an installed plugin.",
        )

        verify.add_argument(
            "plugin",
            help="Qualified plugin name.",
        )

        #
        # repair
        #

        repair = subparsers.add_parser(
            "repair",
            help="Repair an installed plugin.",
        )

        repair.add_argument(
            "plugin",
            help="Qualified plugin name.",
        )

        repair.add_argument(
            "--source",
            required=True,
            help="Plugin source directory.",
        )

        #
        # enable / disable
        #

        set_command = subparsers.add_parser(
            "set",
            help="Enable or disable a plugin.",
        )

        state = set_command.add_mutually_exclusive_group(
            required=True,
        )

        state.add_argument(
            "--enable",
            action="store_true",
            help="Enable the plugin.",
        )

        state.add_argument(
            "--disable",
            action="store_true",
            help="Disable the plugin.",
        )

        set_command.add_argument(
            "plugin",
            help="Qualified plugin name.",
        )

        #
        # man
        #

        man = subparsers.add_parser(
            "man",
            help="Read plugin documentation.",
        )

        man.add_argument(
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
            "run": self._run,
            "verify": self._verify,
            "repair": self._repair,
            "set": self._set,
            "man": self._man,
        }[args.action](
            args,
        )

    # ------------------------------------------------------------------
    # Install
    # ------------------------------------------------------------------

    def _install(
        self,
        args: Namespace,
    ) -> None:

        directory = Path(
            args.directory,
        )

        self._ui.rule(
            f"Install Plugin : {directory.name}",
        )

        self._ui.info(
            "Validating plugin...",
        )

        plugin = self._plugins.install(
            directory,
            reinstall=args.reinstall,
        )

        self._ui.table(
            title="Plugin",
            columns=[
                "Property",
                "Value",
            ],
            rows=[
                [
                    "Name",
                    plugin.qualified_name,
                ],
                [
                    "Version",
                    plugin.version,
                ],
                [
                    "Enabled",
                    "Yes" if plugin.enabled else "No",
                ],
                [
                    "Location",
                    str(plugin.path),
                ],
            ],
        )

    # ------------------------------------------------------------------
    # Uninstall
    # ------------------------------------------------------------------

    def _uninstall(
        self,
        args: Namespace,
    ) -> None:

        self._ui.rule(
            f"Uninstall Plugin : {args.plugin}",
        )

        self._ui.info(
            "Validating plugin...",
        )

        self._plugins.uninstall(
            args.plugin,
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def _list(
        self,
        args: Namespace,
    ) -> None:

        plugins = self._plugins.list()

        if not plugins:

            self._ui.info(
                "No plugins installed.",
            )

            return

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
                    plugin.installed_at.isoformat(),
                    str(plugin.path),
                ]
                for plugin in plugins
            ],
        )

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def _run(
        self,
        args: Namespace,
    ) -> None:

        arguments = self._parse_arguments(
            args.argument,
        )

        context = self._create_plugin_execution_context(
            arguments=arguments,
        )

        result = self._plugins.execute(
            context=context,
            qualified_name=args.plugin,
            mode=PluginMode.CLI,
        )

        self._render_result(
            result,
        )

    # ------------------------------------------------------------------
    # Verify
    # ------------------------------------------------------------------

    def _verify(
        self,
        args: Namespace,
    ) -> None:

        self._ui.rule(
            f"Verify Plugin : {args.plugin}",
        )

        self._ui.info(
            "Checking installation...",
        )

        self._plugins.verify(
            args.plugin,
        )

    # ------------------------------------------------------------------
    # Repair
    # ------------------------------------------------------------------

    def _repair(
        self,
        args: Namespace,
    ) -> None:

        self._ui.rule(
            f"Repair Plugin : {args.plugin}",
        )

        self._ui.info(
            "Checking installation...",
        )

        self._plugins.repair(
            args.plugin,
            Path(
                args.source,
            ),
        )

    # ------------------------------------------------------------------
    # Enable / Disable
    # ------------------------------------------------------------------

    def _set(
        self,
        args: Namespace,
    ) -> None:

        if args.enable:

            self._ui.rule(
                f"Enable Plugin : {args.plugin}",
            )

            self._plugins.enable(
                args.plugin,
            )

            return

        self._ui.rule(
            f"Disable Plugin : {args.plugin}",
        )

        self._plugins.disable(
            args.plugin,
        )

    # ------------------------------------------------------------------
    # Man release document
    # ------------------------------------------------------------------
    def _man(
        self,
        args: Namespace,
    ) -> None:

        self._ui.rule(
            f"Manual : {args.plugin}",
        )

        documentation = self._plugins.documentation(
            args.plugin,
        )

        self._ui.markdown(
            documentation,
            pager=True,
        )

    # Helper
    def _parse_arguments(
        self,
        values: list[str],
    ) -> dict[str, str]:
        """
        Parse CLI plugin arguments.

        Arguments use KEY=VALUE syntax.
        """

        arguments: dict[str, str] = {}

        for value in values:

            if "=" not in value:

                raise ValueError(
                    f"Invalid plugin argument '{value}'. "
                    "Expected KEY=VALUE.",
                )

            key, argument_value = value.split(
                "=",
                1,
            )

            key = key.strip()

            if not key:

                raise ValueError(
                    "Plugin argument name cannot be empty.",
                )

            arguments[key] = argument_value

        return arguments

    def _create_plugin_execution_context(
        self,
        *,
        arguments: dict[str, str] | None = None,
    ):
        assert self.context.execution_manager is not None

        return self.context.execution_manager.create_plugin(
            arguments=arguments,
        )

    def _render_result(
        self,
        result: PluginResult,
    ) -> None:
        """
        Render standalone plugin result.
        """

        self._ui.print(
            result.to_dict(),
        )
