"""
User management command.
"""

from __future__ import annotations

import getpass

from argparse import ArgumentParser
from argparse import Namespace

from core.commands.base import BaseCommand
from core.commands.base import CommandMetadata

from lib.users.exceptions import PasswordsNotMatchError, SystemUserError, UserError, UserAlreadyExistsError


class UserCommand(BaseCommand):

    metadata = CommandMetadata(
        name="user",
        description="Manage users.",
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
            required=True,
        )

        #
        # create
        #

        create = sub.add_parser(
            "create",
            help="Create a user.",
        )

        create.add_argument(
            "username",
        )

        # create.add_argument(
        #     "--full-name",
        # )

        # create.add_argument(
        #     "--email",
        # )

        #
        # delete
        #

        delete = sub.add_parser(
            "delete",
            help="Delete a user.",
        )

        delete.add_argument(
            "username",
        )

        #
        # list
        #

        sub.add_parser(
            "list",
            help="List users.",
        )

        #
        # password
        #

        password = sub.add_parser(
            "password",
            help="Reset user password.",
        )

        password.add_argument(
            "username",
        )

        #
        # enable
        #

        enable = sub.add_parser(
            "enable",
            help="Enable a user.",
        )

        enable.add_argument(
            "username",
        )

        #
        # disable
        #

        disable = sub.add_parser(
            "disable",
            help="Disable a user.",
        )

        disable.add_argument(
            "username",
        )

        #
        # unlock
        #

        unlock = sub.add_parser(
            "unlock",
            help="Unlock a user account.",
        )

        unlock.add_argument(
            "username",
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        args: Namespace,
    ) -> None:

        actions = {
            "create": self._create,
            "delete": self._delete,
            "list": self._list,
            "password": self._password,
            "enable": self._enable,
            "disable": self._disable,
            "unlock": self._unlock,
        }

        actions[args.action](args)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def _create(
        self,
        args: Namespace,
    ) -> None:

        username = args.username

        # Validate first
        if self.context.user_manager.exists(username):
            raise UserAlreadyExistsError(username)

        full_name = self._prompt("Full Name")
        email = self._prompt("Email")

        password = self._read_password()

        self.context.user_manager.create(
            username=username,
            password=password,
            full_name=full_name,
            email=email,
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def _delete(
        self,
        args: Namespace,
    ) -> None:

        user = self.context.user_manager.get(
            args.username,
        )

        if user is None:

            self.context.output.user.error(
                "User not found."
            )

            return

        if user.system:
            raise SystemUserError()

        if not self._confirm(
            f"Delete '{user.username}'?"
        ):
            return

        self.context.user_manager.delete(
            user,
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def _list(
        self,
        args: Namespace,
    ) -> None:

        users = self.context.user_manager.list()

        rows = []

        for user in users:

            rows.append([
                user.username,
                "Yes" if user.is_active else "No",
                user.full_name or "",
                user.email or "",
            ])

        self.context.output.table(
            title="Users",
            columns=[
                "Username",
                "Active",
                "Full Name",
                "Email",
            ],
            rows=rows,
        )

    # ------------------------------------------------------------------
    # Password
    # ------------------------------------------------------------------

    def _password(
        self,
        args: Namespace,
    ) -> None:

        user = self.context.user_manager.get(
            args.username,
        )

        if user is None:

            self.context.output.user.error(
                "User not found."
            )

            return

        password = self._read_password()

        try:

            self.context.user_manager.change_password(
                user,
                password,
            )

        except UserError as ex:

            self.context.output.user.error(
                str(ex),
            )

    # ------------------------------------------------------------------
    # Enable
    # ------------------------------------------------------------------

    def _enable(
        self,
        args: Namespace,
    ) -> None:

        self.context.user_manager.set_active(
            args.username,
            True,
        )

    # ------------------------------------------------------------------
    # Disable
    # ------------------------------------------------------------------

    def _disable(
        self,
        args: Namespace,
    ) -> None:

        self.context.user_manager.set_active(
            args.username,
            False,
        )

    # ------------------------------------------------------------------
    # Unlock
    # ------------------------------------------------------------------

    def _unlock(
        self,
        args: Namespace,
    ) -> None:


        self.context.user_manager.unlock(
            args.username,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _prompt(
        self,
        message: str,
    ) -> str | None:

        value = self.context.output.prompt(message)

        return value or None

    def _confirm(
        self,
        message: str,
    ) -> bool:

        return self.context.output.confirm(message)

    def _require_user(
        self,
        username: str,
    ):

        return self.context.user_manager.get(
            username,
        )

    def _read_password(self) -> str:

        password = self.context.output.prompt(
            "Password",
            password=True,
        )

        confirm = self.context.output.prompt(
            "Confirm Password",
            password=True,
        )

        if password != confirm:
            raise PasswordsNotMatchError()

        return password