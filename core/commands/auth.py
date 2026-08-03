"""
Authentication command.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace

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

        self._session = context.session_manager

        assert context.ui is not None

        self._ui = context.ui

        assert context.observability is not None

        self._events = context.observability.emitter(
            "auth",
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
        )

        subparsers.add_parser(
            "login",
            help="Authenticate.",
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
        }[
            args.action
        ](args)

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def _login(
        self,
        args: Namespace,
    ) -> None:

        session = self._session.current()

        if session is not None:

            self._events.info(f"Already authenticated as '{session.username}'.")

            return

        username = self._ui.prompt(
            "Username",
        )

        password = self._ui.prompt(
            "Password",
            password=True,
        )

        session = self._session.login(
            username,
            password,
        )

        self._events.info(f"Logged in as {session.username}")

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    def _logout(
        self,
        args: Namespace,
    ) -> None:

        if not self._session.authenticated():

            self._events.warning("No active session.")

            return

        self._session.logout()

        self._events.info(f"Logged out successfully.")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def _status(
        self,
        args: Namespace,
    ) -> None:

        session = self._session.current()

        if session is None:

            self._events.warning("Not authenticated.")

            return

        self._ui.panel(
            title="Authenticated Session",
            lines=[
                f"Username : {session.username}",
                f"Expires  : {session.expires_at}",
            ],
        )
