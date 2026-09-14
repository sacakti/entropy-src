"""
Group commands.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from typing import TYPE_CHECKING

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)

if TYPE_CHECKING:
    from core.context import EntropyContext


class GroupsCommand(BaseCommand):
    """
    Manage Entropy authorization groups.
    """

    metadata = CommandMetadata(
        name="groups",
        description="Manage authorization groups.",
        aliases=("group",),
    )

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        super().__init__(
            context,
        )

        assert context.group_manager is not None
        assert context.authorization is not None
        assert context.session_manager is not None
        assert context.ui is not None

        self._groups = context.group_manager

        self._authorization = context.authorization

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
            required=True,
        )

        #
        # create
        #

        create = subparsers.add_parser(
            "create",
            help="Create a group.",
        )

        create.add_argument(
            "name",
        )

        create.add_argument(
            "--description",
            help="Group description.",
        )

        #
        # list
        #

        subparsers.add_parser(
            "list",
            help="List groups.",
        )

        #
        # read
        #

        read = subparsers.add_parser(
            "read",
            help="Read a group.",
        )

        read.add_argument(
            "name",
        )

        #
        # modify
        #

        modify = subparsers.add_parser(
            "modify",
            help="Modify a group.",
        )

        modify.add_argument(
            "name",
        )

        modify.add_argument(
            "--new-name",
            dest="new_name",
            help="New group name.",
        )

        modify.add_argument(
            "--description",
            help="Group description.",
        )

        #
        # delete
        #

        delete = subparsers.add_parser(
            "delete",
            help="Delete a group.",
        )

        delete.add_argument(
            "name",
        )

        #
        # users
        #

        users = subparsers.add_parser(
            "users",
            help="Manage group users.",
        )

        users.add_argument(
            "name",
        )

        user_subparsers = users.add_subparsers(
            dest="user_action",
        )

        add = user_subparsers.add_parser(
            "add",
            help="Add a user to a group.",
        )

        add.add_argument(
            "username",
        )

        remove = user_subparsers.add_parser(
            "remove",
            help="Remove a user from a group.",
        )

        remove.add_argument(
            "username",
        )

        #
        # roles
        #

        roles = subparsers.add_parser(
            "roles",
            help="Manage group roles.",
        )

        roles.add_argument(
            "name",
        )

        role_subparsers = roles.add_subparsers(
            dest="role_action",
        )

        grant = role_subparsers.add_parser(
            "grant",
            help="Grant a role to a group.",
        )

        grant.add_argument(
            "role",
        )

        revoke = role_subparsers.add_parser(
            "revoke",
            help="Revoke a role from a group.",
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
            "list": self._list,
            "read": self._read,
            "modify": self._modify,
            "delete": self._delete,
            "users": self._users,
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

        session = self._session.require()

        self._authorization.require(
            session,
            "groups.create",
        )

        group = self._groups.create(
            name=args.name,
            description=args.description,
        )

        self._ui.success(
            f"Group '{group.name}' created successfully.",
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def _list(
        self,
        args: Namespace,
    ) -> None:

        session = self._session.require()

        self._authorization.require(
            session,
            "groups.read",
        )

        groups = self._groups.list()

        if not groups:

            self._ui.info(
                "No groups found.",
            )

            return

        self._ui.table(
            title="Groups",
            columns=[
                "Name",
                "Description",
            ],
            rows=[
                [
                    group.name,
                    group.description or "",
                ]
                for group in groups
            ],
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def _read(
        self,
        args: Namespace,
    ) -> None:

        session = self._session.require()

        self._authorization.require(
            session,
            "groups.read",
        )

        group = self._groups.get(
            args.name,
        )

        self._ui.table(
            title="Group",
            columns=[
                "Property",
                "Value",
            ],
            rows=[
                [
                    "Name",
                    group.name,
                ],
                [
                    "Description",
                    group.description or "",
                ],
            ],
        )

    # ------------------------------------------------------------------
    # Modify
    # ------------------------------------------------------------------

    def _modify(
        self,
        args: Namespace,
    ) -> None:

        session = self._session.require()

        self._authorization.require(
            session,
            "groups.modify",
        )

        group = self._groups.get(
            args.name,
        )

        group = self._groups.modify(
            group,
            name=args.new_name,
            description=args.description,
        )

        self._ui.success(
            f"Group '{group.name}' modified successfully.",
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def _delete(
        self,
        args: Namespace,
    ) -> None:

        session = self._session.require()

        self._authorization.require(
            session,
            "groups.delete",
        )

        group = self._groups.get(
            args.name,
        )

        self._groups.delete(
            group,
        )

        self._ui.success(
            f"Group '{group.name}' deleted successfully.",
        )

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def _users(
        self,
        args: Namespace,
    ) -> None:

        session = self._session.require()

        self._authorization.require(
            session,
            "groups.users",
        )

        group = self._groups.get(
            args.name,
        )

        if args.user_action == "add":

            self._groups.add_user(
                group,
                args.username,
            )

            self._ui.success(
                f"User '{args.username}' " f"added to group '{group.name}'.",
            )

            return

        if args.user_action == "remove":

            self._groups.remove_user(
                group,
                args.username,
            )

            self._ui.success(
                f"User '{args.username}' " f"removed from group '{group.name}'.",
            )

            return

        users = self._groups.users(
            group,
        )

        if not users:

            self._ui.info(
                f"Group '{group.name}' has no users.",
            )

            return

        self._ui.table(
            title=f"Users : {group.name}",
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
    # Roles
    # ------------------------------------------------------------------

    def _roles(
        self,
        args: Namespace,
    ) -> None:

        session = self._session.require()

        self._authorization.require(
            session,
            "groups.roles",
        )

        group = self._groups.get(
            args.name,
        )

        if args.role_action == "grant":

            self._groups.grant_role(
                group,
                args.role,
            )

            self._ui.success(
                f"Role '{args.role}' " f"granted to group '{group.name}'.",
            )

            return

        if args.role_action == "revoke":

            self._groups.revoke_role(
                group,
                args.role,
            )

            self._ui.success(
                f"Role '{args.role}' " f"revoked from group '{group.name}'.",
            )

            return

        roles = self._groups.roles(
            group,
        )

        if not roles:

            self._ui.info(
                f"Group '{group.name}' has no roles.",
            )

            return

        self._ui.table(
            title=f"Roles : {group.name}",
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
