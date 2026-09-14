"""
Plugin management command.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)
from core.commands.exceptions import CommandError
from lib.models.plugin import PluginResult
from lib.plugins.mode import PluginMode
from lib.workflow.assignments import WorkflowAssignments

if TYPE_CHECKING:
    from core.context import EntropyContext


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
        context: EntropyContext,
    ) -> None:

        super().__init__(
            context,
        )

        assert context.plugin_manager is not None
        assert context.ui is not None
        assert context.authorization is not None
        assert context.session_manager is not None

        self._plugins = context.plugin_manager

        self._ui = context.ui

        self._authorization = context.authorization

        self._session = context.session_manager

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
            nargs="?",
            help="Qualified plugin name.",
        )

        run.add_argument(
            "--local",
            type=Path,
            help="Execute a plugin directly from a local directory.",
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
        # upgrade
        #

        upgrade = subparsers.add_parser(
            "upgrade",
            help="Check and upgrade plugins.",
        )

        upgrade.add_argument(
            "--path",
            type=Path,
            help="Plugin source directory.",
        )

        upgrade.add_argument(
            "--show",
            action="store_true",
            help="Show available plugin changes without upgrading.",
        )

        upgrade.add_argument(
            "--confirm",
            action="store_true",
            help="Upgrade without confirmation.",
        )

        upgrade.add_argument(
            "--force",
            action="store_true",
            help="Allow plugin downgrades.",
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
            "upgrade": self._upgrade,
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

        self._require(
            "plugins.install",
        )

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

        self._require(
            "plugins.uninstall",
        )

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

        self._require(
            "plugins.list",
        )

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

        self._require(
            "plugins.run",
        )

        if args.plugin is None and args.local is None:

            raise CommandError(
                "Either a plugin name or --local path must be specified.",
            )

        if args.plugin is not None and args.local is not None:

            raise CommandError(
                "Plugin name and --local cannot be used together.",
            )

        arguments = self._parse_arguments(
            args.argument,
        )

        context = self._create_plugin_execution_context(
            arguments=arguments,
        )

        if args.local is not None:

            result = self._plugins.execute_local(
                context=context,
                directory=args.local,
                mode=PluginMode.CLI,
            )

        else:

            assert args.plugin is not None

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

        self._require(
            "plugins.list",
        )

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

        self._require(
            "plugins.install",
        )

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

        self._require(
            "plugins.install",
        )

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
    ) -> dict[str, Any]:
        """
        Parse CLI plugin arguments.

        Arguments use KEY=VALUE syntax.

        Values are automatically converted using the same
        assignment rules used by workflows.
        """

        return WorkflowAssignments().parse_typed(
            values,
            value_type="auto",
        )

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

    # ------------------------------------------------------------------
    # Upgrade
    # ------------------------------------------------------------------

    def _upgrade(
        self,
        args: Namespace,
    ) -> None:
        """
        Check and upgrade available plugins.
        """

        self._require(
            "plugins.upgrade",
        )

        if args.show and args.confirm:

            raise CommandError(
                "'--show' cannot be used with '--confirm'.",
            )

        source = (
            args.path.expanduser().resolve()
            if args.path is not None
            else self._default_plugin_source()
        )

        if not source.exists():

            raise CommandError(
                f"Plugin source directory does not exist: {source}",
            )

        if not source.is_dir():

            raise CommandError(
                f"Plugin source is not a directory: {source}",
            )

        self._ui.rule(
            "Plugin Upgrade",
        )

        self._ui.info(
            f"Scanning plugin source: {source}",
        )

        plan = self._plugins.plan_upgrade(
            source,
            force=args.force,
        )

        if not plan.changes:

            self._ui.success(
                "All installed plugins are up to date.",
            )

            return

        self._render_upgrade_plan(
            plan,
        )

        if args.show:

            return

        if not args.confirm:

            if not self._ui.confirm(
                "Proceed with plugin upgrade?",
            ):

                self._ui.info(
                    "Plugin upgrade cancelled.",
                )

                return

        result = self._plugins.upgrade(
            source,
            force=args.force,
        )

        if result.success:

            self._ui.success(
                f"Successfully upgraded {len(result.upgraded)} plugin(s).",
            )

            return

        self._ui.error(
            "Plugin upgrade completed with errors.",
        )

        if result.upgraded:

            self._ui.success(
                f"Successfully upgraded " f"{len(result.upgraded)} plugin(s).",
            )

        if result.failed:

            self._ui.error(
                f"Failed to upgrade " f"{len(result.failed)} plugin(s).",
            )

    def _default_plugin_source(
        self,
    ) -> Path:
        """
        Return the default plugin source directory.
        """

        assert self.context.bootstrap is not None

        return (self.context.bootstrap.application.directory / "resources" / "plugins").resolve()

    def _render_upgrade_plan(
        self,
        plan,
    ) -> None:
        """
        Render available plugin changes.
        """

        rows = []

        for change in plan.changes:

            installed = change.installed.version if change.installed is not None else "-"

            rows.append(
                [
                    change.manifest.qualified_name,
                    installed,
                    change.manifest.version,
                    change.change_type.value,
                ],
            )

        self._ui.table(
            title="Plugin Updates Available",
            columns=[
                "Plugin",
                "Installed",
                "Available",
                "Change",
            ],
            rows=rows,
        )

        self._ui.info(
            f"{len(plan.changes)} plugin change(s) available.",
        )

    def _require(
        self,
        permission: str,
    ) -> None:

        session = self._session.require()

        self._authorization.require(
            session,
            permission,
        )
