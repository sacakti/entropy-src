"""
Extension management command: Python libraries for plugins.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)


def _size(value: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return str(value)


class ExtensionCommand(
    BaseCommand,
):
    """
    Manage Python extensions (libraries for plugins).
    """

    metadata = CommandMetadata(
        name="extension",
        description="Manage Python libraries for plugins (several versions side by side).",
        aliases=("extensions", "ext"),
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
        assert context.authorization is not None
        assert context.session_manager is not None

        self._authorization = context.authorization

        self._session = context.session_manager

        self._extensions = context.extension_manager

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

        subparsers.add_parser(
            "list",
            help="List installed extension versions.",
        )

        subparsers.add_parser(
            "builtin",
            help="List the libraries Entropy itself ships with.",
        )

        install = subparsers.add_parser(
            "install",
            help="Install a library from the package index, or from a file.",
        )

        install.add_argument(
            "name",
            nargs="?",
            help="Library name (from the package index).",
        )

        install.add_argument(
            "--version",
            help="Version or range, e.g. 3.0 or '>=2,<3' (default: newest).",
        )

        install.add_argument(
            "--file",
            type=Path,
            help="A wheel, source archive, .py module or zipped package folder.",
        )

        install.add_argument(
            "--no-deps",
            action="store_true",
            help="Do not install the library's own dependencies.",
        )

        install.add_argument(
            "--index-url",
            help="Package index to use instead of the default.",
        )

        uninstall = subparsers.add_parser(
            "uninstall",
            help="Remove an installed extension version.",
        )

        uninstall.add_argument(
            "name",
        )

        uninstall.add_argument(
            "--version",
            help="Which version (needed when several are installed).",
        )

        for action, text in (
            ("verify", "Check an installed version's files."),
            ("repair", "Reinstall a version from its kept wheels."),
        ):

            command = subparsers.add_parser(
                action,
                help=text,
            )

            command.add_argument(
                "name",
            )

            command.add_argument(
                "version",
            )

        check = subparsers.add_parser(
            "check",
            help="Say whether a requirement is met (by Entropy or an extension).",
        )

        check.add_argument(
            "name",
        )

        check.add_argument(
            "--version",
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        args: Namespace,
    ) -> None:

        {
            "list": self._list,
            "builtin": self._builtin,
            "install": self._install,
            "uninstall": self._uninstall,
            "verify": self._verify,
            "repair": self._repair,
            "check": self._check,
        }[args.action](
            args,
        )

    def _list(
        self,
        args: Namespace,
    ) -> None:

        self._require(
            "extensions.list",
        )

        entries = self._extensions.list()

        if not entries:

            self._ui.info(
                "No extensions installed.",
            )

            return

        self._ui.table(
            title="Installed Extensions",
            columns=["Name", "Version", "Source", "Includes", "Size", "Installed"],
            rows=[
                [
                    entry["name"],
                    entry["version"],
                    entry["origin"] or entry["source"],
                    ", ".join(entry["packages"]),
                    _size(entry["size"]),
                    f"{entry['installed_at'][:16]} by {entry['installed_by'] or '-'}",
                ]
                for entry in entries
            ],
        )

    def _builtin(
        self,
        args: Namespace,
    ) -> None:

        self._require(
            "extensions.list",
        )

        self._ui.table(
            title="Libraries in Entropy",
            columns=["Name", "Version"],
            rows=[[entry["name"], entry["version"]] for entry in self._extensions.builtin()],
        )

    def _install(
        self,
        args: Namespace,
    ) -> None:

        self._require(
            "extensions.install",
        )

        user = self._session.require().username

        if args.file is not None:

            self._ui.info(
                f"Installing {args.file.name}...",
            )

            entry = self._extensions.install_upload(
                args.file.name,
                args.file.read_bytes(),
                name=args.name,
                version=args.version,
                dependencies=not args.no_deps,
                index_url=args.index_url,
                user=user,
            )

        else:

            if not args.name:

                raise SystemExit("Give a library name, or --file.")

            self._ui.info(
                f"Installing {args.name} {args.version or '(newest)'}...",
            )

            entry = self._extensions.install(
                args.name,
                args.version,
                dependencies=not args.no_deps,
                index_url=args.index_url,
                user=user,
            )

        self._ui.success(
            f"{entry['name']} {entry['version']} installed " f"({', '.join(entry['packages'])}).",
        )

        if entry["shared"]:

            self._ui.info(
                f"Uses Entropy's own {', '.join(entry['shared'])}.",
            )

    def _uninstall(
        self,
        args: Namespace,
    ) -> None:

        self._require(
            "extensions.install",
        )

        removed = self._extensions.uninstall(
            args.name,
            args.version,
        )

        self._ui.success(
            f"{args.name} {', '.join(removed)} removed.",
        )

    def _verify(
        self,
        args: Namespace,
    ) -> None:

        self._require(
            "extensions.list",
        )

        problems = self._extensions.verify(
            args.name,
            args.version,
        )

        if problems:

            for problem in problems:

                self._ui.error(
                    problem,
                )

            raise SystemExit(1)

        self._ui.success(
            f"{args.name} {args.version} is complete.",
        )

    def _repair(
        self,
        args: Namespace,
    ) -> None:

        self._require(
            "extensions.install",
        )

        self._extensions.repair(
            args.name,
            args.version,
        )

        self._ui.success(
            f"{args.name} {args.version} reinstalled from its wheels.",
        )

    def _check(
        self,
        args: Namespace,
    ) -> None:

        self._require(
            "extensions.list",
        )

        entry = self._extensions.check(
            [{"name": args.name, "version": args.version}],
        )[0]

        if entry["status"] == "entropy":

            self._ui.success(
                f"{entry['requirement']}: met by Entropy's own {args.name} {entry['version']}.",
            )

        elif entry["status"] == "extension":

            self._ui.success(
                f"{entry['requirement']}: met by extension {args.name} {entry['version']}.",
            )

        else:

            self._ui.warning(
                f"{entry['requirement']}: not installed.",
            )

            raise SystemExit(1)

    def _require(
        self,
        permission: str,
    ) -> None:

        session = self._session.require()

        self._authorization.require(
            session,
            permission,
        )
