"""
User management command.
"""

from __future__ import annotations

import getpass

from argparse import ArgumentParser
from argparse import Namespace

from core.commands.base import BaseCommand
from core.commands.base import CommandMetadata

from lib.users.exceptions import UserError


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

        create.add_argument(
            "--full-name",
        )

        create.add_argument(
            "--email",
        )

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

        password = getpass.getpass(
            "Password: "
        )

        confirm = getpass.getpass(
            "Confirm password: "
        )

        if password != confirm:

            self.context.output.user.error(
                "Passwords do not match."
            )

            return

        try:

            self.context.user_manager.create(
                username=args.username,
                password=password,
                full_name=args.full_name,
                email=args.email,
            )

        except UserError as ex:

            self.context.output.user.error(
                str(ex),
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

        answer = input(
            f"Delete '{user.username}'? [y/N]: "
        )

        if answer.lower() != "y":
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

        password = getpass.getpass(
            "New password: "
        )

        confirm = getpass.getpass(
            "Confirm password: "
        )

        if password != confirm:

            self.context.output.user.error(
                "Passwords do not match."
            )

            return

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

        try:

            self.context.user_manager.set_active(
                args.username,
                True,
            )

        except UserError as ex:

            self.context.output.user.error(str(ex))

    # ------------------------------------------------------------------
    # Disable
    # ------------------------------------------------------------------

    def _disable(
        self,
        args: Namespace,
    ) -> None:

        try:

            self.context.user_manager.set_active(
                args.username,
                False,
            )

        except UserError as ex:

            self.context.output.user.error(str(ex))

    # ------------------------------------------------------------------
    # Unlock
    # ------------------------------------------------------------------

    def _unlock(
        self,
        args: Namespace,
    ) -> None:

        try:

            self.context.user_manager.unlock(
                args.username,
            )

        except UserError as ex:

            self.context.output.user.error(str(ex))