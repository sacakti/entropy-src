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


class ExtensionCommand(BaseCommand):
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
        # list
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
            "list": self._list,
            "verify": self._verify,
        }[
            args.action
        ](args)

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

        self._extensions.install(
            manifest,
        )

        self._events.info(
            f"Extension '{manifest.name}' installed.",
        )

    # ------------------------------------------------------------------
    # Uninstall
    # ------------------------------------------------------------------

    def _uninstall(
        self,
        args: Namespace,
    ) -> None:

        self._extensions.uninstall(
            args.name,
        )

        self._events.info(
            f"Extension '{args.name}' uninstalled.",
        )
    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def _list(
        self,
        args: Namespace,
    ) -> None:

        extensions = self._extensions.list()
        """
        Sample:
        {
            "sqlparse": {
                "installed_at": "2026-08-03T15:51:28.154060+00:00",
                "installer": "offline",
                "platform_tag": "any",
                "python_tag": "py3",
                "version": "0.5.5",
                "wheel": "sqlparse-0.5.5-py3-none-any.whl"
            }
        }
        """
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
                    extension.installed_at,
                    extension.python_tag,
                    extension.platform_tag,
                    extension.installer,
                    extension.wheel,
                ]
                for extension in extensions
            ],
        )

    # ------------------------------------------------------------------
    # Verify
    # ------------------------------------------------------------------

    def _verify(
        self,
        args: Namespace,
    ) -> None:

        self._extensions.verify(
            args.name,
        )

        self._events.info(
            f"Extension '{args.name}' verified.",
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

        self._extensions.download(
            manifest,
        )

        self._events.info(
            f"Extension '{manifest.name}' downloaded.",
        )
