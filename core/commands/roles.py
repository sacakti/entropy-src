"""
Role commands.
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


class RolesCommand(BaseCommand):
    """
    Manage Entropy authorization roles.
    """

    metadata = CommandMetadata(
        name="roles",
        description="Manage authorization roles.",
        aliases=("role",),
    )

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        super().__init__(
            context,
        )

        assert context.role_manager is not None
        assert context.authorization is not None
        assert context.session_manager is not None
        assert context.ui is not None

        self._roles = context.role_manager

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
            help="Create a role.",
        )

        create.add_argument(
            "name",
        )

        create.add_argument(
            "--description",
            help="Role description.",
        )

        #
        # list
        #

        subparsers.add_parser(
            "list",
            help="List roles.",
        )

        #
        # read
        #

        read = subparsers.add_parser(
            "read",
            help="Read a role.",
        )

        read.add_argument(
            "name",
        )

        #
        # modify
        #

        modify = subparsers.add_parser(
            "modify",
            help="Modify a role.",
        )

        modify.add_argument(
            "name",
        )

        modify.add_argument(
            "--new-name",
            dest="new_name",
            help="New role name.",
        )

        modify.add_argument(
            "--description",
            help="Role description.",
        )

        #
        # delete
        #

        delete = subparsers.add_parser(
            "delete",
            help="Delete a role.",
        )

        delete.add_argument(
            "name",
        )

        #
        # permissions
        #

        permissions = subparsers.add_parser(
            "permissions",
            help="Manage role permissions.",
        )

        permissions.add_argument(
            "name",
        )

        permission_subparsers = permissions.add_subparsers(
            dest="permission_action",
        )

        #
        # grant
        #

        grant = permission_subparsers.add_parser(
            "grant",
            help="Grant a permission to a role.",
        )

        grant.add_argument(
            "permission",
        )

        #
        # revoke
        #

        revoke = permission_subparsers.add_parser(
            "revoke",
            help="Revoke a permission from a role.",
        )

        revoke.add_argument(
            "permission",
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
            "permissions": self._permissions,
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
            "roles.create",
        )

        role = self._roles.create(
            name=args.name,
            description=args.description,
        )

        self._ui.success(
            f"Role '{role.name}' created successfully.",
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
            "roles.read",
        )

        roles = self._roles.list()

        if not roles:

            self._ui.info(
                "No roles found.",
            )

            return

        self._ui.table(
            title="Roles",
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
            "roles.read",
        )

        role = self._roles.get(
            args.name,
        )

        self._ui.table(
            title="Role",
            columns=[
                "Property",
                "Value",
            ],
            rows=[
                [
                    "Name",
                    role.name,
                ],
                [
                    "Description",
                    role.description or "",
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
            "roles.modify",
        )

        role = self._roles.get(
            args.name,
        )

        role = self._roles.modify(
            role,
            name=args.new_name,
            description=args.description,
        )

        self._ui.success(
            f"Role '{role.name}' modified successfully.",
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
            "roles.delete",
        )

        role = self._roles.get(
            args.name,
        )

        self._roles.delete(
            role,
        )

        self._ui.success(
            f"Role '{role.name}' deleted successfully.",
        )

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------

    def _permissions(
        self,
        args: Namespace,
    ) -> None:

        session = self._session.require()

        self._authorization.require(
            session,
            "roles.permissions",
        )

        role = self._roles.get(
            args.name,
        )

        if args.permission_action == "grant":

            self._grant_permission(
                role,
                args.permission,
            )

            return

        if args.permission_action == "revoke":

            self._revoke_permission(
                role,
                args.permission,
            )

            return

        permissions = self._roles.permissions(
            role,
        )

        if not permissions:

            self._ui.info(
                f"Role '{role.name}' has no permissions.",
            )

            return

        self._ui.table(
            title=f"Permissions : {role.name}",
            columns=[
                "Permission",
                "Type",
                "Description",
            ],
            rows=[
                [
                    permission.name,
                    permission.permission_type.value,
                    permission.description or "",
                ]
                for permission in permissions
            ],
        )

    # ------------------------------------------------------------------
    # Grant Permission
    # ------------------------------------------------------------------

    def _grant_permission(
        self,
        role,
        permission: str,
    ) -> None:

        self._roles.grant_permission(
            role,
            permission,
        )

        self._ui.success(
            f"Permission '{permission}' " f"granted to role '{role.name}'.",
        )

    # ------------------------------------------------------------------
    # Revoke Permission
    # ------------------------------------------------------------------

    def _revoke_permission(
        self,
        role,
        permission: str,
    ) -> None:

        self._roles.revoke_permission(
            role,
            permission,
        )

        self._ui.success(
            f"Permission '{permission}' " f"revoked from role '{role.name}'.",
        )
