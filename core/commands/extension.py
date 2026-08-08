"""
Extension management command.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)
from lib.extensions.loader import ExtensionLoader


class ExtensionCommand(
    BaseCommand,
):
    """
    Manage Python extensions.
    """

    metadata = CommandMetadata(
        name="extension",
        description="Manage Python extensions.",
    )

    def __init__(
        self,
        context,
    ) -> None:

        super().__init__(
            context,
        )

        assert context.extension_manager is not None
        assert context.ui is not None
        assert context.observability is not None

        self._extensions = context.extension_manager

        self._ui = context.ui

        self._loader = ExtensionLoader()

        self._events = context.observability.emitter(
            "extension",
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
        # list wheels
        #

        wheels = subparsers.add_parser(
            "wheels",
            help="List locally available extension wheels.",
        )

        #
        # install
        #

        install = subparsers.add_parser(
            "install",
            help="Install an extension.",
        )

        install.add_argument(
            "name",
            help="Extension name.",
        )

        install.add_argument(
            "--version",
            help="Extension version.",
        )

        #
        # uninstall
        #

        uninstall = subparsers.add_parser(
            "uninstall",
            help="Uninstall an extension.",
        )

        uninstall.add_argument(
            "name",
            help="Extension name.",
        )

        #
        # repair
        #

        repair = subparsers.add_parser(
            "repair",
            help="Repair an extension."
        )

        repair.add_argument(
            "name",
            help="Extension name.",
        )

        #
        # list installed extensions
        #

        subparsers.add_parser(
            "list",
            help="List installed extensions.",
        )

        #
        # verify
        #

        verify = subparsers.add_parser(
            "verify",
            help="Verify an installed extension.",
        )

        verify.add_argument(
            "name",
            help="Extension name.",
        )

        #
        # download
        #

        download = subparsers.add_parser(
            "download",
            help="Download an extension wheel.",
        )

        download.add_argument(
            "name",
            help="Extension name.",
        )

        download.add_argument(
            "--version",
            help="Extension version.",
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
            "download": self._download,
            "uninstall": self._uninstall,
            "wheels": self._wheels,
            "list": self._list,
            "verify": self._verify,
            "repair": self._repair,
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

        manifest = self._loader.from_name(
            name=args.name,
            version=args.version,
        )

        self._ui.rule(
            f"Install Extension : {manifest.name}",
        )

        self._ui.info(
            "Validating extension...",
        )

        extension = self._extensions.install(
            manifest,
        )

        self._ui.table(
            title="Extension",
            columns=[
                "Property",
                "Value",
            ],
            rows=[
                [
                    "Name",
                    extension.name,
                ],
                [
                    "Version",
                    extension.version,
                ],
                [
                    "Installer",
                    extension.installer,
                ],
                [
                    "Wheel",
                    extension.wheel,
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
            f"Uninstall Extension : {args.name}",
        )

        self._ui.info(
            "Validating extension...",
        )

        self._extensions.uninstall(
            args.name,
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def _list(
        self,
        args: Namespace,
    ) -> None:

        extensions = self._extensions.list()

        if not extensions:

            self._ui.info(
                "No extensions installed.",
            )

            return

        self._ui.table(
            title="Installed Extensions",
            columns=[
                "Name",
                "Version",
                "Installed At",
                "Python Tag",
                "Platform Tag",
                "Installer",
                "Wheel",
            ],
            rows=[
                [
                    extension.name,
                    extension.version,
                    extension.installed_at.isoformat(),
                    extension.python_tag,
                    extension.platform_tag,
                    extension.installer,
                    extension.wheel,
                ]
                for extension in extensions
            ],
        )

    def _wheels(
        self,
        args: Namespace,
    ) -> None:

        self._ui.rule(
            "Available Extension Wheels",
        )

        wheels = self._extensions.wheels()

        if not wheels:

            self._ui.info(
                "No extension wheels available.",
            )

            return

        self._ui.table(
            title="Local Wheels",
            columns=[
                "Wheel",
            ],
            rows=[
                [
                    wheel.name,
                ]
                for wheel in wheels
            ],
        )
    # ------------------------------------------------------------------
    # Verify
    # ------------------------------------------------------------------

    def _verify(
        self,
        args: Namespace,
    ) -> None:

        self._ui.rule(
            f"Verify Extension : {args.name}",
        )

        self._ui.info(
            "Checking installation...",
        )

        self._extensions.verify(
            args.name,
        )

    # ------------------------------------------------------------------
    # Repair
    # ------------------------------------------------------------------

    def _repair(
        self,
        args: Namespace,
    ) -> None:

        self._ui.rule(
            f"Repair Extension : {args.name}",
        )

        self._ui.info(
            "Checking installation...",
        )

        self._extensions.repair(
            args.name,
        )

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def _download(
        self,
        args: Namespace,
    ) -> None:

        manifest = self._loader.from_name(
            name=args.name,
            version=args.version,
        )

        self._ui.rule(
            f"Download Extension : {manifest.name}",
        )

        self._ui.info(
            "Preparing download...",
        )

        self._extensions.download(
            manifest,
        )
