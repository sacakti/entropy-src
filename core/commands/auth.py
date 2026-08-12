"""
Authentication command.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
import sys

from core.commands.base import BaseCommand, CommandMetadata


class AuthCommand(BaseCommand):
    """
    Authentication commands.
    """

    metadata = CommandMetadata(
        name="auth",
        description="Authentication commands.",
        authentication_required=False,
    )

    def __init__(
        self,
        context,
    ) -> None:

        super().__init__(
            context,
        )

        assert context.session_manager is not None
        assert context.ui is not None

        self._session = context.session_manager
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
        )

        login = subparsers.add_parser(
            "login",
            help="Authenticate.",
        )

        login.add_argument(
            "-u",
            "--user",
            dest="username",
            help="Username.",
        )

        password_group = login.add_mutually_exclusive_group()

        password_group.add_argument(
            "-p",
            "--password",
            dest="password",
            help="Password. Warning: visible in shell history/process arguments.",
        )

        password_group.add_argument(
            "--password-stdin",
            action="store_true",
            help="Read the password from standard input.",
        )
        subparsers.add_parser(
            "logout",
            help="Logout the current session.",
        )

        subparsers.add_parser(
            "status",
            help="Display the current session.",
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        args: Namespace,
    ) -> None:

        {
            None: self._login,
            "login": self._login,
            "logout": self._logout,
            "status": self._status,
        }[args.action](
            args,
        )

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def _login(
        self,
        args: Namespace,
    ) -> None:

        session = self._session.current()

        if session is not None:

            self._ui.info(
                f"Already authenticated as '{session.username}'.",
            )

            return

        username = args.username

        if username is None:

            username = self._ui.prompt(
                "Username",
            )

        if args.password_stdin:

            password = sys.stdin.readline().rstrip(
                "\r\n",
            )

            if not password:

                self._ui.error(
                    "No password was provided through standard input.",
                )

                return

        elif args.password is not None:

            self._ui.warning(
                "Passing a password through the command line is insecure. "
                "The password may be visible in shell history or process "
                "arguments.",
            )

            password = args.password

        else:

            password = self._ui.prompt(
                "Password",
                password=True,
            )

        self._session.login(
            username,
            password,
        )

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    def _logout(
        self,
        args: Namespace,
    ) -> None:

        self._session.logout()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def _status(
        self,
        args: Namespace,
    ) -> None:

        session = self._session.current()

        if session is None:

            self._ui.warning(
                "Not authenticated.",
            )

            return

        self._ui.panel(
            title="Authenticated Session",
            lines=[
                f"Username : {session.username}",
                f"Expires  : {session.expires_at}",
            ],
        )
