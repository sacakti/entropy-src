"""
User management command.
"""

from __future__ import annotations

from argparse import ArgumentParser
from argparse import Namespace

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)
from lib.users.exceptions import PasswordsNotMatchError


class UserCommand(BaseCommand):
    """
    User management.
    """

    metadata = CommandMetadata(
        name="user",
        description="Manage users.",
    )

    def __init__(
        self,
        context,
    ) -> None:

        super().__init__(
            context,
        )

        assert context.user_manager is not None
        assert context.ui is not None

        self._users = context.user_manager
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

        #
        # create
        #

        create = subparsers.add_parser(
            "create",
            help="Create a user.",
        )

        create.add_argument(
            "username",
        )

        #
        # delete
        #

        delete = subparsers.add_parser(
            "delete",
            help="Delete a user.",
        )

        delete.add_argument(
            "username",
        )

        #
        # list
        #

        subparsers.add_parser(
            "list",
            help="List users.",
        )

        #
        # password
        #

        password = subparsers.add_parser(
            "password",
            help="Change user password.",
        )

        password.add_argument(
            "username",
        )

        #
        # enable
        #

        enable = subparsers.add_parser(
            "enable",
            help="Enable a user.",
        )

        enable.add_argument(
            "username",
        )

        #
        # disable
        #

        disable = subparsers.add_parser(
            "disable",
            help="Disable a user.",
        )

        disable.add_argument(
            "username",
        )

        #
        # unlock
        #

        unlock = subparsers.add_parser(
            "unlock",
            help="Unlock a user.",
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

        {
            "create": self._create,
            "delete": self._delete,
            "list": self._list,
            "password": self._password,
            "enable": self._enable,
            "disable": self._disable,
            "unlock": self._unlock,
        }[args.action](args)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def _create(
        self,
        args: Namespace,
    ) -> None:

        self._users.create(
            username=args.username,
            password=self._read_password(),
            full_name=self._optional(
                "Full Name",
            ),
            email=self._optional(
                "Email",
            ),
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def _delete(
        self,
        args: Namespace,
    ) -> None:

        user = self._users.get(
            args.username,
        )

        if not self._ui.confirm(
            "Delete '{0}'?".format(
                user.username,
            )
        ):
            return

        self._users.delete(
            user,
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def _list(
        self,
        args: Namespace,
    ) -> None:

        users = self._users.list()

        self._ui.table(
            title="Users",
            columns=[
                "Username",
                "Active",
                "Full Name",
                "Email",
            ],
            rows=[
                [
                    user.username,
                    "Yes" if user.is_active else "No",
                    user.full_name or "",
                    user.email or "",
                ]
                for user in users
            ],
        )

    # ------------------------------------------------------------------
    # Password
    # ------------------------------------------------------------------

    def _password(
        self,
        args: Namespace,
    ) -> None:

        user = self._users.get(
            args.username,
        )

        self._users.change_password(
            user,
            self._read_password(),
        )

    # ------------------------------------------------------------------
    # Enable
    # ------------------------------------------------------------------

    def _enable(
        self,
        args: Namespace,
    ) -> None:

        self._users.set_active(
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

        self._users.set_active(
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

        self._users.unlock(
            args.username,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _optional(
        self,
        message: str,
    ):

        value = self._ui.prompt(
            message,
        )

        return value or None

    def _read_password(
        self,
    ) -> str:

        password = self._ui.prompt(
            "Password",
            password=True,
        )

        confirm = self._ui.prompt(
            "Confirm Password",
            password=True,
        )

        if password != confirm:

            raise PasswordsNotMatchError()

        return password
