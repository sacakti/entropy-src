"""
User management command.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from typing import TYPE_CHECKING

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)
from lib.users.exceptions import (
    SystemUserError,
    UnauthorizedActionError,
    UserAlreadyActiveError,
    UserAlreadyExistsError,
    UserAlreadyInactiveError,
)

if TYPE_CHECKING:
    from core.context import EntropyContext


class UserCommand(BaseCommand):
    """
    User management.
    """

    metadata = CommandMetadata(
        name="user",
        description="Manage users.",
        aliases=("users",),
    )

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        super().__init__(
            context,
        )

        assert context.user_manager is not None
        assert context.ui is not None
        assert context.session_manager is not None
        assert context.observability is not None
        assert context.authorization is not None
        assert context.user_role_manager is not None

        self._users = context.user_manager

        self._user_roles = context.user_role_manager

        self._session = context.session_manager

        self._ui = context.ui

        self._authorization = context.authorization

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
        # roles
        #

        roles = subparsers.add_parser(
            "roles",
            help="Manage user roles.",
        )

        roles.add_argument(
            "username",
        )

        role_subparsers = roles.add_subparsers(
            dest="role_action",
        )

        role_subparsers.add_parser(
            "list",
            help="List user roles.",
        )

        add = role_subparsers.add_parser(
            "grant",
            help="Assign a role to a user.",
        )

        add.add_argument(
            "role",
        )

        revoke = role_subparsers.add_parser(
            "revoke",
            help="Revoke a role from a user.",
        )

        revoke.add_argument(
            "role",
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
            "roles": self._roles,
        }[args.action](
            args,
        )

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def _create(
        self,
        args: Namespace,
    ) -> None:

        self._require(
            "users.create",
        )

        self._ui.rule(
            f"Create User : {args.username}",
        )

        self._events.log.info(
            f"Creating user '{args.username}'.",
        )

        self._ui.info(
            "Validating username...",
        )

        #
        # Let UserManager own the actual validation.
        #

        self._ui.info(
            "Checking user availability...",
        )

        if self._users.exists(
            args.username,
        ):

            raise UserAlreadyExistsError(
                args.username,
            )

        self._ui.info(
            "Collecting user information...",
        )

        full_name = self._optional(
            "Full Name",
        )

        email = self._optional(
            "Email",
        )

        password = self._read_password()

        self._ui.info(
            "Creating user...",
        )

        user = self._users.create(
            username=args.username,
            password=password,
            full_name=full_name,
            email=email,
        )

        self._events.log.success(
            f"User '{user.username}' created successfully.",
        )

        self._ui.table(
            title="User",
            columns=[
                "Property",
                "Value",
            ],
            rows=[
                [
                    "Username",
                    user.username,
                ],
                [
                    "Active",
                    "Yes" if user.is_active else "No",
                ],
                [
                    "Full Name",
                    user.full_name or "",
                ],
                [
                    "Email",
                    user.email or "",
                ],
            ],
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def _delete(
        self,
        args: Namespace,
    ) -> None:

        self._require(
            "users.delete",
        )

        self._ui.rule(
            f"Delete User : {args.username}",
        )

        self._events.log.info(
            f"Preparing to delete user '{args.username}'.",
        )

        self._ui.info(
            "Validating user...",
        )

        user = self._users.get(
            args.username,
        )

        if not self._ui.confirm(
            f"Delete '{user.username}'?",
        ):

            self._events.log.warning(
                f"Deletion of user '{user.username}' cancelled.",
            )

            self._ui.warning(
                "User deletion cancelled.",
            )

            return

        self._ui.info(
            "Removing user...",
        )

        self._users.delete(
            user,
        )

        self._events.log.success(
            f"User '{user.username}' deleted successfully.",
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def _list(
        self,
        args: Namespace,
    ) -> None:

        self._require(
            "users.read",
        )

        users = self._users.list()

        if not users:

            self._ui.info(
                "No users found.",
            )

            return

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

        session = self._session.require()

        #
        # Change own password.
        #

        if args.username is None:

            self._ui.rule(
                "Change Password",
            )

            self._events.log.info(
                f"Changing password for '{session.username}'.",
            )

            self._ui.info(
                "Authenticating current password...",
            )

            user = self._users.get(
                session.username,
            )

            current_password = self._ui.prompt(
                "Current Password",
                password=True,
            )

            new_password = self._read_password()

            self._ui.info(
                "Updating password...",
            )

            self._users.change_password(
                user=user,
                current_password=current_password,
                new_password=new_password,
            )

            self._events.log.success(
                "Password changed successfully.",
            )

            return

        #
        # Change another user's password.
        #

        self._require(
            "users.modify",
        )

        self._ui.rule(
            f"Change Password : {args.username}",
        )

        self._events.log.info(
            f"Changing password for '{args.username}'.",
        )

        user = self._users.get(
            args.username,
        )

        new_password = self._read_password()

        self._ui.info(
            "Updating password...",
        )

        self._users.admin_change_password(
            user=user,
            password=new_password,
        )

        self._events.log.success(
            f"Password changed successfully for '{user.username}'.",
        )

    # ------------------------------------------------------------------
    # Reset Password
    # ------------------------------------------------------------------

    def _reset_password(
        self,
        args: Namespace,
    ) -> None:

        self._require(
            "users.modify",
        )

        if args.username is None:

            self._ui.warning("Username is required.")

            return

        self._ui.rule(
            f"Reset Password : {args.username}",
        )

        self._events.log.info(
            f"Resetting password for '{args.username}'.",
        )

        self._ui.info(
            "Validating user...",
        )

        user = self._users.get(
            args.username,
        )

        self._ui.info(
            "Generating temporary password...",
        )

        _, password = self._users.reset_password(
            user,
        )

        #
        # Never log the generated password.
        #

        self._events.log.success(
            f"Password reset successfully for '{user.username}'.",
        )

        self._ui.panel(
            title="Temporary Password",
            lines=[
                password,
            ],
        )

    # ------------------------------------------------------------------
    # Enable
    # ------------------------------------------------------------------

    def _enable(
        self,
        args: Namespace,
    ) -> None:

        self._require(
            "users.enable",
        )

        self._ui.rule(
            f"Enable User : {args.username}",
        )

        self._events.log.info(
            f"Enabling user '{args.username}'.",
        )

        self._ui.info(
            "Validating user...",
        )

        user = self._users.get(
            args.username,
        )

        if user.is_active:

            raise UserAlreadyActiveError()

        self._ui.info(
            "Enabling account...",
        )

        self._users.set_active(
            args.username,
            True,
        )

        self._events.log.success(
            f"User '{args.username}' enabled successfully.",
        )

    # ------------------------------------------------------------------
    # Disable
    # ------------------------------------------------------------------

    def _disable(
        self,
        args: Namespace,
    ) -> None:

        self._require(
            "users.disable",
        )

        self._ui.rule(
            f"Disable User : {args.username}",
        )

        self._events.log.info(
            f"Disabling user '{args.username}'.",
        )

        self._ui.info(
            "Validating user...",
        )

        user = self._users.get(
            args.username,
        )

        if not user.is_active:

            raise UserAlreadyInactiveError()

        self._ui.info(
            "Disabling account...",
        )

        self._users.set_active(
            args.username,
            False,
        )

        self._events.log.success(
            f"User '{args.username}' disabled successfully.",
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

            self._events.log.warning(
                "Passwords do not match.",
            )

    def _require(
        self,
        permission: str,
    ) -> None:

        session = self._session.require()

        self._authorization.require(
            session,
            permission,
        )

    # ------------------------------------------------------------------
    # Roles
    # ------------------------------------------------------------------

    def _roles(
        self,
        args: Namespace,
    ) -> None:

        session = self._session.require()

        self._authorization.require(
            session,
            "users.roles",
        )

        user = self._users.get(
            args.username,
        )

        if args.role_action == "grant":

            self._user_roles.add_role(
                user,
                args.role,
            )

            self._ui.success(
                f"Role '{args.role}' "
                f"assigned to user '{user.username}'.",
            )

            return

        if args.role_action == "revoke":

            self._user_roles.revoke_role(
                user,
                args.role,
            )

            self._ui.success(
                f"Role '{args.role}' "
                f"revoked from user '{user.username}'.",
            )

            return

        roles = self._user_roles.roles(
            user,
        )

        if not roles:

            self._ui.info(
                f"User '{user.username}' has no roles.",
            )

            return

        self._ui.table(
            title=f"Roles : {user.username}",
            columns=[
                "Name",
                "Description",
            ],
            rows=[
                [
                    role.name,
                    role.description or "",
                ]
                for role in roles
            ],
        )
