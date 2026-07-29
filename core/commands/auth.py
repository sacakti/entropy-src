"""
Authentication command.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace

from core.commands.base import BaseCommand, CommandMetadata


class AuthCommand(BaseCommand):

    metadata = CommandMetadata(
        name="auth",
        description="Authentication commands.",
        authentication_required=False,
    )

    # ------------------------------------------------------------------
    # Configure
    # ------------------------------------------------------------------

    def configure(
        self,
        parser: ArgumentParser,
    ) -> None:

        sub = parser.add_subparsers(
            dest="action",
        )

        #
        # login
        #

        sub.add_parser(
            "login",
            help="Authenticate.",
        )

        #
        # logout
        #

        sub.add_parser(
            "logout",
            help="Logout current session.",
        )

        #
        # status
        #

        sub.add_parser(
            "status",
            help="Show current session.",
        )
    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        args: Namespace,
    ) -> None:

        actions = {
            None: self._login,
            "login": self._login,
            "logout": self._logout,
            "status": self._status,
        }

        actions[args.action](args)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _login(
        self,
        args: Namespace,
    ) -> None:

        session = self.context.session_manager.current()

        if session:

            self.context.output.auth.success(
                f"Already authenticated as '{session.username}'."
            )

            return

        username = self.context.output.prompt(
            "Username"
        )

        password = self.context.output.prompt(
            "Password",
            password=True,
        )

        session = self.context.session_manager.login(
            username,
            password,
        )

        self.context.output.auth.success(
            f"Authenticated as '{session.username}'."
        )

    def _logout(
        self,
        args: Namespace,
    ) -> None:

        if not self.context.session_manager.authenticated():

            self.context.output.auth.info(
                "No active session."
            )

            return

        self.context.session_manager.logout()

        self.context.output.auth.success(
            "Logged out."
        )

    def _status(
        self,
        args: Namespace,
    ) -> None:

        session = self.context.session_manager.current()

        if session is None:

            self.context.output.auth.info(
                "Not authenticated."
            )

            return

        self.context.output.panel(
            lines=[
                f"Username : {session.username}\n",
                f"Expires  : {session.expires_at}"
            ],
            title="Authenticated Session",
        )
