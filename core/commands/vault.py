"""
Vault management command.
"""

from __future__ import annotations

import json
from argparse import ArgumentParser, Namespace
from typing import TYPE_CHECKING, Any

import questionary

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)
from lib.models.authorization import VaultAccess, VaultVisibility
from lib.vault import (
    VaultValueType,
)
from lib.vault.exceptions import VaultValueError

if TYPE_CHECKING:

    from core.context import EntropyContext


class VaultCommand(BaseCommand):
    """
    Manage Entropy Vault entries.
    """

    metadata = CommandMetadata(
        name="vault",
        description="Manage encrypted Vault values.",
        aliases=("entv",),
    )

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        super().__init__(
            context,
        )

        assert context.vault_manager is not None
        assert context.vault_namespace_manager is not None
        assert context.ui is not None
        assert context.session_manager is not None
        assert context.observability is not None

        self._vault = context.vault_manager

        self._namespaces = context.vault_namespace_manager

        self._ui = context.ui

        self._session = context.session_manager

        self._authorization = context.authorization

        self._events = context.observability.emitter(
            "vault",
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
        # list
        #

        list_parser = subparsers.add_parser(
            "list",
            help="List Vault entries.",
        )

        list_parser.add_argument(
            "-n",
            "--namespace",
            required=True,
            help="Vault namespace.",
        )

        #
        # add
        #

        add = subparsers.add_parser(
            "add",
            help="Add a Vault entry.",
        )

        add.add_argument(
            "key",
            nargs="?",
            help="Vault key.",
        )

        add.add_argument(
            "value",
            nargs="?",
            help="Vault value.",
        )

        add.add_argument(
            "--type",
            choices=[value.value for value in VaultValueType],
            default=VaultValueType.STRING.value,
            help="Vault value type.",
        )

        add.add_argument(
            "--enc",
            action="store_true",
            help="Encrypt the value before storing it.",
        )

        add.add_argument(
            "-n",
            "--namespace",
            required=True,
            help="Vault namespace.",
        )

        #
        # inspect
        #

        inspect_parser = subparsers.add_parser(
            "inspect",
            help="Inspect a Vault entry.",
        )

        inspect_parser.add_argument(
            "key",
            help="Vault key.",
        )

        inspect_parser.add_argument(
            "--reveal",
            action="store_true",
            help="Reveal sensitive values.",
        )

        inspect_parser.add_argument(
            "-n",
            "--namespace",
            required=True,
            help="Vault namespace.",
        )

        #
        # update
        #

        update = subparsers.add_parser(
            "update",
            help="Update a Vault entry.",
        )

        update.add_argument(
            "key",
            help="Vault key.",
        )

        update.add_argument(
            "value",
            nargs="?",
            help="Replacement value for primitive entries.",
        )

        update.add_argument(
            "--type",
            choices=[value.value for value in VaultValueType],
            default=None,
            help="Replacement value type.",
        )

        update.add_argument(
            "--enc",
            action="store_true",
            help="Store the replacement value encrypted.",
        )

        update.add_argument(
            "--plain",
            action="store_true",
            help="Store the replacement value without encryption.",
        )

        update.add_argument(
            "-n",
            "--namespace",
            required=True,
            help="Vault namespace.",
        )

        #
        # delete
        #

        delete = subparsers.add_parser(
            "delete",
            help="Delete a Vault entry.",
        )

        delete.add_argument(
            "key",
            help="Vault key.",
        )

        delete.add_argument(
            "-n",
            "--namespace",
            required=True,
            help="Vault namespace.",
        )

        #
        # namespace
        #

        namespace = subparsers.add_parser(
            "namespace",
            help="Manage Vault namespaces.",
        )

        namespace_subparsers = namespace.add_subparsers(
            dest="namespace_action",
            required=True,
        )

        #
        # namespace create
        #

        create_namespace = namespace_subparsers.add_parser(
            "create",
            help="Create a Vault namespace.",
        )

        create_namespace.add_argument(
            "name",
            help="Namespace name.",
        )

        create_namespace.add_argument(
            "--shared",
            action="store_true",
            help="Create a shared namespace.",
        )

        #
        # namespace list
        #

        namespace_subparsers.add_parser(
            "list",
            help="List Vault namespaces.",
        )

        #
        # namespace read
        #

        read_namespace = namespace_subparsers.add_parser(
            "read",
            help="Read a Vault namespace.",
        )

        read_namespace.add_argument(
            "name",
            help="Namespace name.",
        )

        #
        # namespace modify
        #

        modify_namespace = namespace_subparsers.add_parser(
            "modify",
            help="Modify a Vault namespace.",
        )

        modify_namespace.add_argument(
            "name",
            help="Namespace name.",
        )

        modify_namespace.add_argument(
            "--new-name",
            dest="new_name",
            help="New namespace name.",
        )

        visibility = modify_namespace.add_mutually_exclusive_group()

        visibility.add_argument(
            "--shared",
            action="store_true",
            help="Make the namespace shared.",
        )

        visibility.add_argument(
            "--private",
            action="store_true",
            help="Make the namespace private.",
        )

        #
        # namespace delete
        #

        delete_namespace = namespace_subparsers.add_parser(
            "delete",
            help="Delete a Vault namespace.",
        )

        delete_namespace.add_argument(
            "name",
            help="Namespace name.",
        )

        #
        # namespace users
        #

        users_namespace = namespace_subparsers.add_parser(
            "users",
            help="Manage namespace users.",
        )

        users_namespace.add_argument(
            "name",
            help="Namespace name.",
        )

        user_subparsers = users_namespace.add_subparsers(
            dest="user_action",
        )

        grant_user = user_subparsers.add_parser(
            "grant",
            help="Grant namespace access to a user.",
        )

        grant_user.add_argument(
            "username",
            help="Username.",
        )

        grant_user.add_argument(
            "--access",
            choices=[
                "read",
                "write",
                "admin",
            ],
            required=True,
            help="Access level.",
        )

        revoke_user = user_subparsers.add_parser(
            "revoke",
            help="Revoke namespace access from a user.",
        )

        revoke_user.add_argument(
            "username",
            help="Username.",
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        args: Namespace,
    ) -> None:

        #
        # Namespace commands perform their own authorization
        # because each namespace operation requires a different
        # permission.
        #

        if args.action == "namespace":

            self._namespace(
                args,
            )

            return

        permissions = {
            "list": "vault.read",
            "add": "vault.add",
            "inspect": "vault.read",
            "update": "vault.modify",
            "delete": "vault.delete",
        }

        permission = permissions.get(
            args.action,
        )

        if permission is None:

            raise VaultValueError(
                f"Unsupported Vault action: {args.action}",
            )

        self._require_permission(
            permission,
        )

        actions = {
            "list": self._list,
            "add": self._add,
            "inspect": self._inspect,
            "update": self._update,
            "delete": self._delete,
        }

        action = actions.get(
            args.action,
        )

        if action is None:

            raise VaultValueError(
                f"Unsupported Vault action: {args.action}",
            )

        action(
            args,
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def _list(
        self,
        args: Namespace,
    ) -> None:
        """
        List Vault metadata without exposing values.
        """

        namespace_id = self._namespace_id(
            args.namespace,
        )

        entries = self._vault.list(
            namespace_id,
        )

        if not entries:

            self._ui.info(
                "No Vault entries found.",
            )

            return

        self._ui.table(
            title=f"Vault Entries : {args.namespace}",
            columns=[
                "Key",
                "Type",
                "Sensitive",
            ],
            rows=[
                [
                    entry.key,
                    self._type_name(
                        entry.type,
                    ),
                    "Yes" if entry.sensitive else "No",
                ]
                for entry in entries
            ],
        )

        self._events.log.info(
            f"Listed {len(entries)} Vault entry(ies).",
        )

    # ------------------------------------------------------------------
    # Add
    # ------------------------------------------------------------------

    def _add(
        self,
        args: Namespace,
    ) -> None:
        """
        Add a Vault entry.
        """

        namespace_id = self._namespace_id(
            args.namespace,
        )

        value_type = self._value_type(
            args.type,
        )

        key = args.key

        #
        # JSON entries are collected interactively.
        #

        if value_type is VaultValueType.JSON:

            key, value = self._read_json_entry(
                title=key,
                sensitive=args.enc,
            )

        else:

            key = key or self._prompt_required(
                "Key",
            )

            if args.enc:

                value = self._prompt_value(
                    "Value",
                    sensitive=True,
                )

            elif args.value is not None:

                value = args.value

            else:

                value = self._prompt_value(
                    "Value",
                    sensitive=False,
                )

            value = self._convert_value(
                value,
                value_type,
            )

        self._validate_key(
            key,
        )

        self._ui.info(
            f"Creating Vault entry '{key}'...",
        )

        self._vault.add(
            namespace_id=namespace_id,
            key=key,
            value=value,
            value_type=value_type,
            sensitive=args.enc,
        )

        self._events.log.info(
            f"Vault entry '{key}' created.",
        )

    # ------------------------------------------------------------------
    # Inspect
    # ------------------------------------------------------------------

    def _inspect(
        self,
        args: Namespace,
    ) -> None:
        """
        Inspect a Vault entry.

        Sensitive values are masked unless --reveal is supplied.
        """

        namespace_id = self._namespace_id(
            args.namespace,
        )

        entry = self._vault.get_entry(
            namespace_id,
            args.key,
        )

        self._ui.rule(
            f"Vault Entry : {entry.key}",
        )

        self._ui.table(
            title="Metadata",
            columns=[
                "Property",
                "Value",
            ],
            rows=[
                [
                    "Key",
                    entry.key,
                ],
                [
                    "Type",
                    self._type_name(
                        entry.type,
                    ),
                ],
                [
                    "Sensitive",
                    "Yes" if entry.sensitive else "No",
                ],
            ],
        )

        if entry.sensitive and not args.reveal:

            self._display_masked_value(
                self._vault.get(
                    namespace_id,
                    entry.key,
                ),
            )

            self._events.log.info(
                f"Inspected sensitive Vault entry " f"'{entry.key}' without revealing it.",
            )

            return

        value = self._vault.get(
            namespace_id,
            entry.key,
        )

        self._ui.info(
            "Value:",
        )

        self._display_value(
            value,
        )

        if entry.sensitive:

            self._events.log.warning(
                f"Sensitive Vault entry '{entry.key}' " "was explicitly revealed.",
            )

        else:

            self._events.log.info(
                f"Inspected Vault entry '{entry.key}'.",
            )

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def _update(
        self,
        args: Namespace,
    ) -> None:
        """
        Update a Vault entry.

        Object values are edited field-by-field.
        Primitive values are replaced normally.
        """

        namespace_id = self._namespace_id(
            args.namespace,
        )

        entry = self._vault.get_entry(
            namespace_id,
            args.key,
        )

        if args.enc and args.plain:

            raise VaultValueError(
                "Use either --enc or --plain, not both.",
            )

        current = self._vault.get(
            namespace_id,
            entry.key,
        )

        #
        # Object editor.
        #

        if isinstance(
            current,
            dict,
        ):

            self._update_object(
                namespace_id=namespace_id,
                entry=entry,
                current=current,
            )

            return

        #
        # Primitive replacement.
        #

        self._update_primitive(
            namespace_id=namespace_id,
            entry=entry,
            args=args,
        )

    # ------------------------------------------------------------------
    # Primitive Update
    # ------------------------------------------------------------------

    def _update_primitive(
        self,
        namespace_id: int,
        entry,
        args: Namespace,
    ) -> None:
        """
        Replace a primitive Vault value.
        """

        value_type = self._value_type(
            args.type or entry.type,
        )

        #
        # Never accept a sensitive value through the command line.
        #

        if entry.sensitive and args.value is not None:

            raise VaultValueError(
                "Sensitive values must be entered interactively. "
                "Do not provide them on the command line.",
            )

        if args.enc:

            value = self._prompt_value(
                "Value",
                sensitive=True,
            )

        elif args.value is not None:

            value = args.value

        else:

            value = self._prompt_value(
                "Value",
                sensitive=entry.sensitive,
            )

        value = self._convert_value(
            value,
            value_type,
        )

        if args.enc:

            sensitive = True

        elif args.plain:

            sensitive = False

        else:

            sensitive = entry.sensitive

        self._vault.update(
            namespace_id=namespace_id,
            key=entry.key,
            value=value,
            value_type=value_type,
            sensitive=sensitive,
        )

        self._events.log.info(
            f"Vault entry '{entry.key}' updated.",
        )

        # self._ui.info(
        #     f"Vault entry '{entry.key}' updated successfully.",
        # )

    # ------------------------------------------------------------------
    # Object Update
    # ------------------------------------------------------------------

    def _update_object(
        self,
        namespace_id: int,
        entry,
        current: dict[str, Any],
    ) -> None:
        """
        Interactively edit an object Vault entry.

        Changes remain in memory until Save is selected.
        """

        working = dict(
            current,
        )

        original = dict(
            current,
        )

        self._ui.rule(
            f"Vault Entry : {entry.key}",
        )

        self._ui.info(
            f"Type: {self._type_name(entry.type)}",
        )

        self._ui.info(
            f"Sensitive: {'Yes' if entry.sensitive else 'No'}",
        )

        while True:

            operation = questionary.select(
                "Select operation:",
                choices=[
                    "Update field",
                    "Add field",
                    "Remove field",
                    "Show fields",
                    "Review changes",
                    "Save",
                    "Cancel",
                ],
            ).ask()

            if operation is None:

                return

            if operation == "Update field":

                self._object_update_field(
                    working,
                    entry.sensitive,
                )

            elif operation == "Add field":

                self._object_add_field(
                    working,
                    entry.sensitive,
                )

            elif operation == "Remove field":

                self._object_remove_field(
                    working,
                )

            elif operation == "Show fields":

                self._show_object_fields(
                    working,
                    entry.sensitive,
                )

            elif operation == "Review changes":

                self._review_object_changes(
                    original,
                    working,
                    entry.sensitive,
                )

            elif operation == "Save":

                if working == original:

                    self._ui.info(
                        "No changes to save.",
                    )

                    return

                if not questionary.confirm(
                    "Save these changes?",
                    default=True,
                ).ask():

                    continue

                self._vault.update(
                    namespace_id=namespace_id,
                    key=entry.key,
                    value=working,
                    value_type=entry.type,
                    sensitive=entry.sensitive,
                )

                self._events.log.info(
                    f"Vault entry '{entry.key}' updated.",
                )

                # self._ui.info(
                #     f"Vault entry '{entry.key}' updated successfully.",
                # )

                return

            elif operation == "Cancel":

                if working != original:

                    discard = questionary.confirm(
                        "Discard unsaved changes?",
                        default=False,
                    ).ask()

                    if not discard:

                        continue

                self._ui.info(
                    "Update cancelled.",
                )

                return

    # ------------------------------------------------------------------
    # Object Field Update
    # ------------------------------------------------------------------

    def _object_update_field(
        self,
        values: dict[str, Any],
        sensitive: bool,
    ) -> None:
        """
        Update an existing object field.
        """

        if not values:

            self._ui.info(
                "No fields available.",
            )

            return

        field = questionary.select(
            "Select field:",
            choices=list(
                values.keys(),
            ),
        ).ask()

        if field is None:

            return

        new_value = self._prompt_object_value(
            field,
            values[field],
            sensitive,
        )

        values[field] = new_value

    # ------------------------------------------------------------------
    # Object Field Add
    # ------------------------------------------------------------------

    def _object_add_field(
        self,
        values: dict[str, Any],
        sensitive: bool,
    ) -> None:
        """
        Add a new object field.
        """

        field = questionary.text(
            "Field name:",
        ).ask()

        if field is None:

            return

        field = field.strip()

        self._validate_key(
            field,
        )

        if field in values:

            self._ui.info(
                f"Field '{field}' already exists.",
            )

            return

        value = self._prompt_object_value(
            field,
            None,
            sensitive,
        )

        values[field] = value

    # ------------------------------------------------------------------
    # Object Field Remove
    # ------------------------------------------------------------------

    def _object_remove_field(
        self,
        values: dict[str, Any],
    ) -> None:
        """
        Remove an object field.
        """

        if not values:

            self._ui.info(
                "No fields available.",
            )

            return

        if len(values) == 1:

            self._ui.info(
                "An object must contain at least one field.",
            )

            return

        field = questionary.select(
            "Select field to remove:",
            choices=list(
                values.keys(),
            ),
        ).ask()

        if field is None:

            return

        confirmed = questionary.confirm(
            f"Remove '{field}'?",
            default=False,
        ).ask()

        if confirmed:

            del values[field]

    # ------------------------------------------------------------------
    # Object Value Input
    # ------------------------------------------------------------------

    def _prompt_object_value(
        self,
        field: str,
        current: Any,
        sensitive: bool,
    ) -> Any:
        """
        Prompt for an object field value.
        """

        value_type = self._infer_value_type(
            current,
        )

        #
        # Existing value gives us a useful type hint.
        #

        if current is not None:

            self._ui.info(
                f"Current type for '{field}': " f"{value_type.value}",
            )

        choices = [
            "string",
            "number",
            "boolean",
            "array",
        ]

        selected_type = questionary.select(
            f"Value type for '{field}':",
            choices=choices,
            default=value_type.value if value_type.value in choices else "string",
        ).ask()

        if selected_type is None:

            raise VaultValueError(
                "Value input cancelled.",
            )

        if selected_type == "string":

            raw = self._prompt_value(
                f"Value for '{field}':",
                sensitive=sensitive,
            )

            return raw

        if selected_type == "number":

            raw = self._prompt_value(
                f"Value for '{field}':",
                sensitive=sensitive,
            )

            return self._convert_value(
                raw,
                VaultValueType.NUMBER,
            )

        if selected_type == "boolean":

            result = questionary.confirm(
                f"Value for '{field}':",
                default=(
                    bool(
                        current,
                    )
                    if isinstance(
                        current,
                        bool,
                    )
                    else False
                ),
            ).ask()

            if result is None:

                raise VaultValueError(
                    "Value input cancelled.",
                )

            return result

        if selected_type == "array":

            raw = self._prompt_value(
                f"Array for '{field}' " "(JSON array):",
                sensitive=sensitive,
            )

            return self._convert_value(
                raw,
                VaultValueType.ARRAY,
            )

        raise VaultValueError(
            f"Unsupported field type: {selected_type}",
        )

    # ------------------------------------------------------------------
    # Show Object Fields
    # ------------------------------------------------------------------

    def _show_object_fields(
        self,
        values: dict[str, Any],
        sensitive: bool,
    ) -> None:
        """
        Display object fields.

        Sensitive values are masked.
        """

        rows = []

        for key, value in values.items():

            display = self._mask_value(value) if sensitive else self._format_value(value)

            rows.append(
                [
                    key,
                    self._infer_value_type(
                        value,
                    ).value,
                    display,
                ],
            )

        self._ui.table(
            title="Fields",
            columns=[
                "Key",
                "Type",
                "Value",
            ],
            rows=rows,
        )

    # ------------------------------------------------------------------
    # Review Object Changes
    # ------------------------------------------------------------------

    def _review_object_changes(
        self,
        original: dict[str, Any],
        current: dict[str, Any],
        sensitive: bool,
    ) -> None:
        """
        Display pending object changes.
        """

        rows = []

        original_keys = set(
            original,
        )

        current_keys = set(
            current,
        )

        #
        # Removed
        #

        for key in sorted(
            original_keys - current_keys,
        ):

            rows.append(
                [
                    "Removed",
                    key,
                    "",
                ],
            )

        #
        # Added
        #

        for key in sorted(
            current_keys - original_keys,
        ):

            value = (
                self._mask_value(
                    current[key],
                )
                if sensitive
                else self._format_value(
                    current[key],
                )
            )

            rows.append(
                [
                    "Added",
                    key,
                    value,
                ],
            )

        #
        # Modified
        #

        for key in sorted(
            original_keys & current_keys,
        ):

            if original[key] == current[key]:

                continue

            if sensitive:

                old_value = self._mask_value(
                    original[key],
                )

                new_value = self._mask_value(
                    current[key],
                )

            else:

                old_value = self._format_value(
                    original[key],
                )

                new_value = self._format_value(
                    current[key],
                )

            rows.append(
                [
                    "Updated",
                    key,
                    f"{old_value} -> {new_value}",
                ],
            )

        if not rows:

            self._ui.info(
                "No changes.",
            )

            return

        self._ui.table(
            title="Pending Changes",
            columns=[
                "Action",
                "Key",
                "Value",
            ],
            rows=rows,
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def _delete(
        self,
        args: Namespace,
    ) -> None:
        """
        Delete a Vault entry after confirmation.
        """

        namespace_id = self._namespace_id(
            args.namespace,
        )

        entry = self._vault.get_entry(
            namespace_id,
            args.key,
        )

        self._ui.rule(
            f"Delete Vault Entry : {entry.key}",
        )

        self._ui.table(
            title="Entry",
            columns=[
                "Property",
                "Value",
            ],
            rows=[
                [
                    "Key",
                    entry.key,
                ],
                [
                    "Type",
                    self._type_name(
                        entry.type,
                    ),
                ],
                [
                    "Sensitive",
                    "Yes" if entry.sensitive else "No",
                ],
            ],
        )

        if not questionary.confirm(
            f"Delete Vault entry '{entry.key}'?",
            default=False,
        ).ask():

            self._ui.info(
                "Deletion cancelled.",
            )

            return

        self._vault.delete(
            namespace_id,
            entry.key,
        )

        self._events.log.info(
            f"Vault entry '{entry.key}' deleted.",
        )

        # self._ui.info(
        #     f"Vault entry '{entry.key}' deleted successfully.",
        # )

    # ------------------------------------------------------------------
    # Namespace
    # ------------------------------------------------------------------

    def _namespace(
        self,
        args: Namespace,
    ) -> None:
        """
        Manage Vault namespaces.
        """

        actions = {
            "create": self._namespace_create,
            "list": self._namespace_list,
            "read": self._namespace_read,
            "modify": self._namespace_modify,
            "delete": self._namespace_delete,
            "users": self._namespace_users,
        }

        action = actions.get(
            args.namespace_action,
        )

        if action is None:

            raise VaultValueError(
                f"Unsupported namespace action: "
                f"{args.namespace_action}",
            )

        action(
            args,
        )

    def _namespace_create(
        self,
        args: Namespace,
    ) -> None:

        session = self._session.require()

        self._authorization.require(
            session,
            "vault.namespace.create",
        )

        visibility = (
            VaultVisibility.SHARED
            if args.shared
            else VaultVisibility.PRIVATE
        )

        namespace = self._namespaces.create(
            name=args.name,
            owner_user_id=session.user_id,
            visibility=visibility,
        )

        self._ui.success(
            f"Vault namespace '{namespace.name}' "
            "created successfully.",
        )

    def _namespace_list(
        self,
        args: Namespace,
    ) -> None:

        session = self._session.require()

        self._authorization.require(
            session,
            "vault.namespace.read",
        )

        namespaces = self._namespaces.list()

        if not namespaces:

            self._ui.info(
                "No Vault namespaces found.",
            )

            return

        self._ui.table(
            title="Vault Namespaces",
            columns=[
                "Name",
                "Visibility",
                "Owner",
            ],
            rows=[
                [
                    namespace.name,
                    namespace.visibility.value,
                    str(namespace.owner_user_id),
                ]
                for namespace in namespaces
            ],
        )

    def _namespace_read(
        self,
        args: Namespace,
    ) -> None:

        session = self._session.require()

        self._authorization.require(
            session,
            "vault.namespace.read",
        )

        namespace = self._namespaces.get(
            args.name,
        )

        self._ui.table(
            title=f"Vault Namespace : {namespace.name}",
            columns=[
                "Property",
                "Value",
            ],
            rows=[
                [
                    "Name",
                    namespace.name,
                ],
                [
                    "Visibility",
                    namespace.visibility.value,
                ],
                [
                    "Owner",
                    str(namespace.owner_user_id),
                ],
            ],
        )

    def _namespace_modify(
        self,
        args: Namespace,
    ) -> None:

        session = self._session.require()

        self._authorization.require(
            session,
            "vault.namespace.modify",
        )

        namespace = self._namespaces.get(
            args.name,
        )

        visibility = None

        if args.shared:

            visibility = VaultVisibility.SHARED

        elif args.private:

            visibility = VaultVisibility.PRIVATE

        namespace = self._namespaces.modify(
            namespace,
            name=args.new_name,
            visibility=visibility,
        )

        self._ui.success(
            f"Vault namespace '{namespace.name}' "
            "modified successfully.",
        )

    def _namespace_delete(
        self,
        args: Namespace,
    ) -> None:

        session = self._session.require()

        self._authorization.require(
            session,
            "vault.namespace.delete",
        )

        namespace = self._namespaces.get(
            args.name,
        )

        self._ui.rule(
            f"Delete Vault Namespace : {namespace.name}",
        )

        self._ui.table(
            title="Namespace",
            columns=[
                "Property",
                "Value",
            ],
            rows=[
                [
                    "Name",
                    namespace.name,
                ],
                [
                    "Visibility",
                    namespace.visibility.value,
                ],
                [
                    "Owner",
                    str(namespace.owner_user_id),
                ],
            ],
        )

        if not questionary.confirm(
            f"Delete Vault namespace '{namespace.name}'?",
            default=False,
        ).ask():

            self._ui.info(
                "Deletion cancelled.",
            )

            return

        self._namespaces.delete(
            namespace,
        )

        self._ui.success(
            f"Vault namespace '{namespace.name}' "
            "deleted successfully.",
        )

    def _namespace_users(
        self,
        args: Namespace,
    ) -> None:

        session = self._session.require()

        self._authorization.require(
            session,
            "vault.namespace.users",
        )

        namespace = self._namespaces.get(
            args.name,
        )

        if args.user_action == "grant":

            self._namespaces.grant_access(
                namespace=namespace,
                username=args.username,
                access=VaultAccess(
                    args.access,
                ),
            )

            self._ui.success(
                f"User '{args.username}' granted "
                f"{args.access} access to "
                f"namespace '{namespace.name}'.",
            )

            return

        if args.user_action == "revoke":

            self._namespaces.revoke_access(
                namespace=namespace,
                username=args.username,
            )

            self._ui.success(
                f"User '{args.username}' revoked from "
                f"namespace '{namespace.name}'.",
            )

            return

        users = self._namespaces.users(
            namespace,
        )

        if not users:

            self._ui.info(
                f"No users have explicit access to "
                f"namespace '{namespace.name}'.",
            )

            return

        assignments = self._namespaces.access_assignments(
            namespace,
        )

        access_by_user = {
            assignment.user_id: assignment.access.value
            for assignment in assignments
        }

        self._ui.table(
            title=f"Namespace Users : {namespace.name}",
            columns=[
                "Username",
                "Full Name",
                "Access",
            ],
            rows=[
                [
                    user.username,
                    user.full_name or "",
                    access_by_user.get(
                        user.id,
                        "",
                    ),
                ]
                for user in users
            ],
        )

    # ------------------------------------------------------------------
    # JSON Input
    # ------------------------------------------------------------------

    def _read_json_entry(
        self,
        title: str | None,
        sensitive: bool,
    ) -> tuple[str, dict[str, Any]]:
        """
        Collect a JSON object interactively.

        Nested JSON objects are not supported.
        Arrays are supported.
        """

        self._ui.info(
            "Note: Enter key(s) to save and exit " "with 's'. Enter 'e' to exit without saving.",
        )

        self._ui.info(
            "Title/key rules: no spaces. "
            "Use '_' where needed. "
            "Do not use '+', '-', '/', '*', "
            "or other special characters.",
        )

        if title is None:

            title = self._prompt_required(
                "Title",
            )

        self._validate_key(
            title,
        )

        values: dict[str, Any] = {}

        while True:

            key = self._prompt_required(
                "Key",
            )

            if key.lower() == "e":

                self._ui.info(
                    "JSON entry creation cancelled.",
                )

                raise RuntimeError(
                    "Vault JSON entry creation cancelled.",
                )

            if key.lower() == "s":

                if not values:

                    raise VaultValueError(
                        "At least one JSON key/value pair " "is required.",
                    )

                return title, values

            self._validate_key(
                key,
            )

            if key in values:

                raise VaultValueError(
                    f"JSON key '{key}' already exists.",
                )

            raw_value = self._prompt_value(
                "Value",
                sensitive=sensitive,
            )

            values[key] = self._parse_json_member(
                raw_value,
            )

    # ------------------------------------------------------------------
    # JSON Value Parsing
    # ------------------------------------------------------------------

    def _parse_json_member(
        self,
        value: str,
    ) -> Any:
        """
        Convert an interactive JSON member into a JSON-compatible value.

        Nested objects are rejected.

        Arrays are allowed, but arrays may not contain
        nested objects.
        """

        normalized = value.strip()

        if not normalized:

            raise VaultValueError(
                "JSON value cannot be empty.",
            )

        #
        # Boolean
        #

        if normalized.lower() == "true":

            return True

        if normalized.lower() == "false":

            return False

        #
        # Null
        #

        if normalized.lower() == "null":

            return None

        #
        # Number
        #

        try:

            if any(
                character in normalized
                for character in (
                    ".",
                    "e",
                    "E",
                )
            ):

                return float(
                    normalized,
                )

            return int(
                normalized,
            )

        except ValueError:

            pass

        #
        # Array
        #

        if normalized.startswith("["):

            try:

                result = json.loads(
                    normalized,
                )

            except json.JSONDecodeError as exc:

                raise VaultValueError(
                    f"Invalid JSON array: {exc}",
                ) from exc

            if not isinstance(
                result,
                list,
            ):

                raise VaultValueError(
                    "JSON value is not an array.",
                )

            if self._contains_object(
                result,
            ):

                raise VaultValueError(
                    "Nested JSON objects are not allowed " "inside Vault JSON values.",
                )

            return result

        #
        # Quoted JSON string
        #

        if normalized.startswith('"') and normalized.endswith('"'):

            try:

                result = json.loads(
                    normalized,
                )

            except json.JSONDecodeError as exc:

                raise VaultValueError(
                    f"Invalid JSON string: {exc}",
                ) from exc

            if not isinstance(
                result,
                str,
            ):

                raise VaultValueError(
                    "Invalid JSON string value.",
                )

            return result

        #
        # Plain string
        #

        return value

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_value(
        value: str,
        value_type: VaultValueType,
    ) -> Any:
        """
        Convert a CLI string to the requested Vault type.
        """

        if value_type is VaultValueType.STRING:

            return value

        if value_type is VaultValueType.NUMBER:

            normalized = value.strip()

            try:

                if any(
                    character in normalized
                    for character in (
                        ".",
                        "e",
                        "E",
                    )
                ):

                    return float(
                        normalized,
                    )

                return int(
                    normalized,
                )

            except ValueError as exc:

                raise VaultValueError(
                    f"Invalid number value: {value!r}",
                ) from exc

        if value_type is VaultValueType.BOOLEAN:

            normalized = value.strip().lower()

            if normalized in {
                "true",
                "yes",
                "1",
            }:

                return True

            if normalized in {
                "false",
                "no",
                "0",
            }:

                return False

            raise VaultValueError(
                "Boolean value must be true or false.",
            )

        if value_type is VaultValueType.ARRAY:

            try:

                result = json.loads(
                    value,
                )

            except json.JSONDecodeError as exc:

                raise VaultValueError(
                    "Array value must be valid JSON.",
                ) from exc

            if not isinstance(
                result,
                list,
            ):

                raise VaultValueError(
                    "Vault array value must be a JSON array.",
                )

            if VaultCommand._contains_object(
                result,
            ):

                raise VaultValueError(
                    "Nested JSON objects are not allowed " "inside Vault arrays.",
                )

            return result

        if value_type is VaultValueType.OBJECT:

            try:

                result = json.loads(
                    value,
                )

            except json.JSONDecodeError as exc:

                raise VaultValueError(
                    "Object value must be valid JSON.",
                ) from exc

            if not isinstance(
                result,
                dict,
            ):

                raise VaultValueError(
                    "Vault object value must be a JSON object.",
                )

            return result

        if value_type is VaultValueType.JSON:

            try:

                return json.loads(
                    value,
                )

            except json.JSONDecodeError as exc:

                raise VaultValueError(
                    "Value must be valid JSON.",
                ) from exc

        raise VaultValueError(
            f"Unsupported Vault value type: {value_type!r}",
        )

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def _display_value(
        self,
        value: Any,
    ) -> None:
        """
        Display a resolved Vault value.
        """

        if isinstance(
            value,
            (dict, list),
        ):

            self._ui.info(
                json.dumps(
                    value,
                    indent=4,
                    ensure_ascii=False,
                ),
            )

            return

        self._ui.info(
            str(value),
        )

    def _display_masked_value(
        self,
        value: Any,
    ) -> None:
        """
        Display a sensitive value without revealing its contents.
        """

        if isinstance(
            value,
            dict,
        ):

            rows = [
                [
                    key,
                    self._infer_value_type(
                        item,
                    ).value,
                    self._mask_value(
                        item,
                    ),
                ]
                for key, item in value.items()
            ]

            self._ui.table(
                title="Value",
                columns=[
                    "Key",
                    "Type",
                    "Value",
                ],
                rows=rows,
            )

            return

        self._ui.info(
            f"Value: {self._mask_value(value)}",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _namespace_id(
        self,
        name: str,
    ) -> int:
        """
        Resolve a Vault namespace name to its database identifier.
        """

        namespace = self._namespaces.get(
            name,
        )

        if namespace.id is None:

            raise VaultValueError(
                f"Vault namespace '{name}' has no database identifier.",
            )

        return namespace.id

    @staticmethod
    def _value_type(
        value: str,
    ) -> VaultValueType:
        """
        Convert a CLI type string to VaultValueType.
        """

        try:

            return VaultValueType(
                value,
            )

        except ValueError as exc:

            raise VaultValueError(
                f"Unsupported Vault value type: {value!r}",
            ) from exc

    def _prompt_required(
        self,
        message: str,
    ) -> str:
        """
        Prompt for a required value.
        """

        value = questionary.text(
            f"{message}:",
        ).ask()

        if value is None:

            raise RuntimeError(
                "Input cancelled.",
            )

        value = value.strip()

        if not value:

            raise VaultValueError(
                f"{message} is required.",
            )

        return value

    @staticmethod
    def _prompt_value(
        message: str,
        sensitive: bool = False,
    ) -> str:
        """
        Prompt for a value.

        Sensitive values are masked.
        """

        if sensitive:

            value = questionary.password(
                f"{message}:",
            ).ask()

        else:

            value = questionary.text(
                f"{message}:",
            ).ask()

        if value is None:

            raise RuntimeError(
                "Input cancelled.",
            )

        if not value:

            raise VaultValueError(
                f"{message} is required.",
            )

        return value

    @staticmethod
    def _validate_key(
        key: str,
    ) -> None:
        """
        Validate a Vault key.

        Allowed characters:

        - A-Z
        - a-z
        - 0-9
        - _
        """

        if not isinstance(
            key,
            str,
        ):

            raise VaultValueError(
                "Vault key must be a string.",
            )

        if not key:

            raise VaultValueError(
                "Vault key cannot be empty.",
            )

        for character in key:

            if not (character.isascii() and (character.isalnum() or character == "_")):

                raise VaultValueError(
                    "Vault key may contain only " "letters, numbers, and underscore (_).",
                )

    @staticmethod
    def _type_name(
        value_type: Any,
    ) -> str:

        if isinstance(
            value_type,
            VaultValueType,
        ):

            return value_type.value

        return str(
            value_type,
        )

    @staticmethod
    def _format_value(
        value: Any,
    ) -> str:

        if isinstance(
            value,
            (dict, list),
        ):

            return json.dumps(
                value,
                ensure_ascii=False,
                separators=(
                    ",",
                    ":",
                ),
            )

        return str(
            value,
        )

    @staticmethod
    def _mask_value(
        value: Any,
    ) -> str:

        if value is None:

            return "********"

        if isinstance(
            value,
            list,
        ):

            return "********"

        if isinstance(
            value,
            dict,
        ):

            return "********"

        return "********"

    @staticmethod
    def _infer_value_type(
        value: Any,
    ) -> VaultValueType:

        if isinstance(
            value,
            bool,
        ):

            return VaultValueType.BOOLEAN

        if isinstance(
            value,
            (int, float),
        ):

            return VaultValueType.NUMBER

        if isinstance(
            value,
            list,
        ):

            return VaultValueType.ARRAY

        if isinstance(
            value,
            dict,
        ):

            return VaultValueType.OBJECT

        return VaultValueType.STRING

    @staticmethod
    def _contains_object(
        value: Any,
    ) -> bool:
        """
        Return True when a nested dictionary exists.
        """

        if isinstance(
            value,
            dict,
        ):

            return True

        if isinstance(
            value,
            list,
        ):

            return any(
                VaultCommand._contains_object(
                    item,
                )
                for item in value
            )

        return False
