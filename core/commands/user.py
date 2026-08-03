"""
User management command.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)
from lib.models.users import User
from lib.users.exceptions import CurrentPasswordMismatchError, SystemUserError, UnauthorizedActionError, UserAlreadyActiveError, UserAlreadyExistsError, UserAlreadyInactiveError, WeakPasswordError, PasswordReuseError


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
        assert context.session_manager is not None

        self._session = context.session_manager

        self._users = context.user_manager

        self._ui = context.ui

        assert context.observability is not None

        self._events = context.observability.emitter(
            "user",
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
            help="Manage user passwords.",
        )

        mode = password.add_mutually_exclusive_group(
            required=True,
        )

        mode.add_argument(
            "--change",
            action="store_true",
            help="Change a password.",
        )

        mode.add_argument(
            "--reset",
            action="store_true",
            help="Reset a password.",
        )

        password.add_argument(
            "username",
            nargs="?",
            help="Target user.",
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
        # unlock yet to implement
        #

        # unlock = subparsers.add_parser(
        #     "unlock",
        #     help="Unlock a user.",
        # )

        # unlock.add_argument(
        #     "username",
        # )

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
        }[args.action](args)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def _create(
        self,
        args: Namespace,
    ) -> None:

        if self._users.exists(args.username):
            raise UserAlreadyExistsError(args.username)

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

        self._events.info(
            f"User '{args.username}' created.",
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

        if user.system:
            raise SystemUserError()

        if not self._ui.confirm(
            f"Delete '{user.username}'?",
        ):
            return

        self._users.delete(
            user,
        )

        self._events.info(
            f"User '{user.username}' deleted.",
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

        if args.change:

            self._change_password(
                args,
            )

            return

        self._reset_password(
            args,
        )


    # ------------------------------------------------------------------
    # Change Password
    # ------------------------------------------------------------------

    def _change_password(
        self,
        args: Namespace,
    ) -> None:

        assert self._session is not None

        session = self._session.require()

        #
        # Change own password.
        #
        if args.username is None:

            user = self._users.get(
                session.username,
            )

            current_password = self._ui.prompt(
                "Current Password",
                password=True,
            )

            new_password = self._read_password()

            self._users.change_password(
                user=user,
                current_password=current_password,
                new_password=new_password,
            )

            self._events.info(
                "Password changed successfully.",
            )

            return

        #
        # Change another user's password.
        #
        # TODO:
        # Validate administrator permission.
        #

        user = self._users.get(
            args.username,
        )

        if user.system:
            raise UnauthorizedActionError()

        new_password = self._read_password()

        self._users.admin_change_password(
            user=user,
            password=new_password,
        )

        self._events.info(
            f"Password changed for '{user.username}'.",
        )


    # ------------------------------------------------------------------
    # Reset Password
    # ------------------------------------------------------------------

    def _reset_password(
        self,
        args: Namespace,
    ) -> None:

        if args.username is None:

            raise ValueError(
                "Username is required.",
            )

        #
        # TODO:
        # Validate administrator/reset-password permission.
        #

        user = self._users.get(
            args.username,
        )

        if user.system:
            raise UnauthorizedActionError()

        _, password = self._users.reset_password(
            user,
        )

        self._ui.print()
        self._ui.print("Temporary Password")
        self._ui.print("------------------")
        self._ui.print(password)
        self._ui.print()

        self._events.info(
            f"Password reset for '{user.username}'.",
        )


    # ------------------------------------------------------------------
    # Enable
    # ------------------------------------------------------------------

    def _enable(
        self,
        args: Namespace,
    ) -> None:

        user = self._users.get(
            args.username,
        )

        if user.system:
            raise SystemUserError()

        if user.is_active:
            raise UserAlreadyActiveError()

        self._users.set_active(
            args.username,
            True,
        )

        self._events.info(
            f"User '{args.username}' enabled.",
        )


    # ------------------------------------------------------------------
    # Disable
    # ------------------------------------------------------------------

    def _disable(
        self,
        args: Namespace,
    ) -> None:

        user = self._users.get(
            args.username,
        )

        if user.system:
            raise SystemUserError()

        if not user.is_active:
            raise UserAlreadyInactiveError()

        self._users.set_active(
            args.username,
            False,
        )

        self._events.info(
            f"User '{args.username}' disabled.",
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

        self._events.info(
            f"User '{args.username}' unlocked.",
        )


    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _optional(
        self,
        message: str,
    ) -> str | None:

        value = self._ui.prompt(
            message,
        ).strip()

        return value or None


    def _read_password(
        self,
    ) -> str:

        while True:

            password = self._ui.prompt(
                "Password",
                password=True,
            )

            confirm = self._ui.prompt(
                "Confirm Password",
                password=True,
            )

            if password == confirm:

                return password

            self._events.warning(
                "Passwords do not match.",
            )
