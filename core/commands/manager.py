"""
Command manager.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import pkgutil

from core.commands import __path__
from core.commands.base import BaseCommand
from core.commands.exceptions import CommandNotFoundError


class CommandManager:

    def __init__(self, context):

        self.context = context

        self._commands: dict[str, BaseCommand] = {}

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    def _build_parser(self) -> argparse.ArgumentParser:

        parser = argparse.ArgumentParser(
            prog="entropy",
            add_help=False,
        )

        subparsers = parser.add_subparsers(
            dest="command",
        )

        self._configure_commands(
            subparsers,
        )

        return parser

    def _configure_commands(
        self,
        subparsers,
    ):

        for command in self.list():

            parser = subparsers.add_parser(
                command.metadata.name,
                aliases=list(command.metadata.aliases),
                help=command.metadata.description,
            )

            command.configure(parser)

    def _resolve_command(self, args):

        return self.get(
            args.command or "help"
        )

    # ---------------------------------------------------------
    # Discovery
    # ---------------------------------------------------------

    def discover(self) -> None:

        self.context.output.cli.debug(
            "Discovering commands..."
        )

        for _, module_name, _ in pkgutil.iter_modules(__path__):

            if module_name in ("base", "manager", "exceptions"):
                continue

            module = importlib.import_module(
                f"core.commands.{module_name}"
            )

            for _, cls in inspect.getmembers(
                module,
                inspect.isclass,
            ):

                if (
                    not issubclass(cls, BaseCommand)
                    or cls is BaseCommand
                ):
                    continue

                self.register(
                    cls(self.context)
                )

        self.context.output.cli.debug(
            f"{len(self.list())} command(s) loaded."
        )

    # ---------------------------------------------------------
    # Register
    # ---------------------------------------------------------

    def register(
        self,
        command: BaseCommand,
    ) -> None:

        metadata = command.metadata

        self._commands[
            metadata.name
        ] = command

        for alias in metadata.aliases:

            self._commands[
                alias
            ] = command

    # ---------------------------------------------------------
    # Access
    # ---------------------------------------------------------

    def get(
        self,
        name: str,
    ) -> BaseCommand | None:

        return self._commands.get(name)

    def list(
        self,
    ) -> list[BaseCommand]:

        #
        # Remove aliases
        #
        commands = {
            id(command): command
            for command in self._commands.values()
        }

        return sorted(
            commands.values(),
            key=lambda c: c.metadata.name,
        )

    # ---------------------------------------------------------
    # Execute
    # ---------------------------------------------------------

    def execute(
        self,
        name: str,
        args,
    ) -> None:

        command = self.get(name)

        if command is None:

            raise CommandNotFoundError(name)

        command.execute(args)

    def run(self):

        parser = self._build_parser()

        args = parser.parse_args()

        self.execute(
            args.command or "help",
            args,
        )