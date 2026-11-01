"""
Command manager.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import pkgutil
import time
import traceback
from argparse import Namespace
from typing import List, Optional

from core.commands import __path__
from core.commands.base import BaseCommand
from core.commands.exceptions import (
    CommandAlreadyExistsError,
    CommandNotFoundError,
)
from core.exceptions import EntropyException
from lib.audit.cli import record_command
from lib.auth.exceptions import AuthenticationException
from lib.authorization.exceptions import AuthorizationRequiredError


class CommandManager:
    """
    Command subsystem.
    """

    def __init__(
        self,
        context,
    ) -> None:

        assert context.observability is not None

        self._context = context

        self._commands: dict[str, BaseCommand] = {}

        self._events = context.observability.emitter(
            "cli",
        )

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(
        self,
    ) -> None:
        """
        Discover commands.
        """

        self._events.log.debug("Discovering commands...")

        for _, module_name, _ in pkgutil.iter_modules(
            __path__,
        ):

            if module_name in (
                "base",
                "exceptions",
                "manager",
            ):
                continue

            module = importlib.import_module(f"core.commands.{module_name}")

            for _, cls in inspect.getmembers(
                module,
                inspect.isclass,
            ):

                if (
                    not issubclass(
                        cls,
                        BaseCommand,
                    )
                    or cls is BaseCommand
                ):
                    continue

                self.register(
                    cls(
                        self._context,
                    )
                )

        self._events.log.debug(
            "Discovered {} command(s).".format(
                len(
                    self.list(),
                ),
            )
        )

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        command: BaseCommand,
    ) -> None:
        """
        Register a command.
        """

        metadata = command.metadata

        if metadata.name in self._commands:

            raise CommandAlreadyExistsError(
                metadata.name,
            )

        self._commands[metadata.name] = command

        for alias in metadata.aliases:

            if alias in self._commands:

                raise CommandAlreadyExistsError(
                    alias,
                )

            self._commands[alias] = command

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(
        self,
        name: str,
    ) -> Optional[BaseCommand]:
        """
        Return a command.
        """

        return self._commands.get(
            name,
        )

    def list(
        self,
    ) -> List[BaseCommand]:
        """
        Return registered commands.
        """

        commands = []
        seen = set()

        for command in self._commands.values():

            identifier = id(
                command,
            )

            if identifier in seen:
                continue

            seen.add(
                identifier,
            )

            commands.append(
                command,
            )

        return sorted(
            commands,
            key=lambda command: command.metadata.name,
        )

    # ------------------------------------------------------------------
    # Parser
    # ------------------------------------------------------------------

    def build_parser(
        self,
    ) -> argparse.ArgumentParser:
        """
        Build the application parser.
        """

        parser = argparse.ArgumentParser(
            prog="entropy",
            add_help=False,
        )

        self._configure_parser(
            parser,
        )

        return parser

    def _configure_parser(
        self,
        parser: argparse.ArgumentParser,
    ) -> None:
        """
        Configure the application parser.
        """

        subparsers = parser.add_subparsers(
            dest="command",
        )

        for command in self.list():

            command_parser = subparsers.add_parser(
                command.metadata.name,
                aliases=list(
                    command.metadata.aliases,
                ),
                help=command.metadata.description,
            )

            command.configure(
                command_parser,
            )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        name: str,
        args: Namespace,
    ) -> None:
        """
        Execute a command.
        """

        command = self.get(
            name,
        )

        if command is None:

            raise CommandNotFoundError(
                name,
            )

        started = time.monotonic()
        outcome, error = "failure", None

        try:

            if command.metadata.authentication_required:

                assert self._context.session_manager is not None

                self._context.session_manager.require()

            command.execute(
                args,
            )

            outcome = "success"

        except (AuthenticationException, AuthorizationRequiredError) as exc:

            outcome, error = "denied", str(exc)

            self._events.log.error(
                str(exc),
            )

            raise SystemExit(1) from exc

        except EntropyException as exc:

            error = str(exc)

            self._events.log.error(
                str(exc),
            )

            raise SystemExit(1) from exc

        except ValueError as exc:

            error = str(exc)

            self._events.log.error(
                str(exc),
            )

            raise SystemExit(1) from exc

        except SystemExit as exc:

            # Commands may end themselves; exit code 0 (or none) is success.
            if exc.code in (0, None):
                outcome = "success"

            raise

        except Exception as exc:

            self._events.log.critical(
                traceback.format_exc(),
            )

            raise SystemExit(2) from exc

        finally:

            # Server-side commands bypass the web API: audit them here.
            record_command(
                self._context,
                command.metadata.name,
                args,
                outcome=outcome,
                duration_ms=int((time.monotonic() - started) * 1000),
                error=error,
            )

    # ------------------------------------------------------------------
    # Parse
    # ------------------------------------------------------------------

    def parse(self, argv: List[str]) -> Namespace:

        parser = self.build_parser()

        return parser.parse_args(
            argv,
        )

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def execute_command(
        self,
        args: Namespace,
    ) -> None:
        """
        Execute the selected command.
        """

        self.execute(
            args.command or "help",
            args,
        )
