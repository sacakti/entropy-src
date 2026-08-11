"""
Vault management command.
"""

from __future__ import annotations

import json
import questionary

from argparse import ArgumentParser, Namespace
from typing import Any, TYPE_CHECKING

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)
from lib.vault import (
    VaultValueType,
)

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
        assert context.ui is not None
        assert context.session_manager is not None
        assert context.observability is not None

        self._vault = context.vault_manager

        self._ui = context.ui

        self._session = context.session_manager

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

        subparsers.add_parser(
            "list",
            help="List Vault entries.",
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
            choices=[
                value.value
                for value in VaultValueType
            ],
            default=VaultValueType.STRING.value,
            help="Vault value type.",
        )

        add.add_argument(
            "--enc",
            action="store_true",
            help="Encrypt the value before storing it.",
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
            choices=[
                value.value
                for value in VaultValueType
            ],
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

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        args: Namespace,
    ) -> None:

        self._require_authentication()

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

            raise ValueError(
                f"Unsupported Vault action: {args.action}",
            )

        action(
            args,
        )

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _require_authentication(
        self,
    ) -> None:
        """
        Require an authenticated Entropy session.
        """

        self._session.require()

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

        entries = self._vault.list()

        if not entries:

            self._ui.info(
                "No Vault entries found.",
            )

            return

        self._ui.table(
            title="Vault Entries",
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
            key=key,
            value=value,
            value_type=value_type,
            sensitive=args.enc,
        )

        self._events.log.info(
            f"Vault entry '{key}' created.",
        )

        # self._ui.info(
        #     f"Vault entry '{key}' created successfully.",
        # )

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

        entry = self._vault.get_entry(
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
                    entry.key,
                ),
            )

            self._events.log.info(
                f"Inspected sensitive Vault entry "
                f"'{entry.key}' without revealing it.",
            )

            return

        value = self._vault.get(
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
                f"Sensitive Vault entry '{entry.key}' "
                "was explicitly revealed.",
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

        entry = self._vault.get_entry(
            args.key,
        )

        if args.enc and args.plain:

            raise ValueError(
                "Use either --enc or --plain, not both.",
            )

        current = self._vault.get(
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
                entry=entry,
                current=current,
            )

            return

        #
        # Primitive replacement.
        #

        self._update_primitive(
            entry=entry,
            args=args,
        )

    # ------------------------------------------------------------------
    # Primitive Update
    # ------------------------------------------------------------------

    def _update_primitive(
        self,
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

            raise ValueError(
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
                f"Current type for '{field}': "
                f"{value_type.value}",
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
            default=value_type.value
            if value_type.value in choices
            else "string",
        ).ask()

        if selected_type is None:

            raise ValueError(
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
                default=bool(
                    current,
                )
                if isinstance(
                    current,
                    bool,
                )
                else False,
            ).ask()

            if result is None:

                raise ValueError(
                    "Value input cancelled.",
                )

            return result

        if selected_type == "array":

            raw = self._prompt_value(
                f"Array for '{field}' "
                "(JSON array):",
                sensitive=sensitive,
            )

            return self._convert_value(
                raw,
                VaultValueType.ARRAY,
            )

        raise ValueError(
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

            if sensitive:

                display = self._mask_value(
                    value,
                )

            else:

                display = self._format_value(
                    value,
                )

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

        entry = self._vault.get_entry(
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
            entry.key,
        )

        self._events.log.info(
            f"Vault entry '{entry.key}' deleted.",
        )

        # self._ui.info(
        #     f"Vault entry '{entry.key}' deleted successfully.",
        # )

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
            "Note: Enter key(s) to save and exit "
            "with 's'. Enter 'e' to exit without saving.",
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

                    raise ValueError(
                        "At least one JSON key/value pair "
                        "is required.",
                    )

                return title, values

            self._validate_key(
                key,
            )

            if key in values:

                raise ValueError(
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

            raise ValueError(
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

                raise ValueError(
                    f"Invalid JSON array: {exc}",
                ) from exc

            if not isinstance(
                result,
                list,
            ):

                raise ValueError(
                    "JSON value is not an array.",
                )

            if self._contains_object(
                result,
            ):

                raise ValueError(
                    "Nested JSON objects are not allowed "
                    "inside Vault JSON values.",
                )

            return result

        #
        # Quoted JSON string
        #

        if (
            normalized.startswith('"')
            and normalized.endswith('"')
        ):

            try:

                result = json.loads(
                    normalized,
                )

            except json.JSONDecodeError as exc:

                raise ValueError(
                    f"Invalid JSON string: {exc}",
                ) from exc

            if not isinstance(
                result,
                str,
            ):

                raise ValueError(
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

                raise ValueError(
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

            raise ValueError(
                "Boolean value must be true or false.",
            )

        if value_type is VaultValueType.ARRAY:

            try:

                result = json.loads(
                    value,
                )

            except json.JSONDecodeError as exc:

                raise ValueError(
                    "Array value must be valid JSON.",
                ) from exc

            if not isinstance(
                result,
                list,
            ):

                raise ValueError(
                    "Vault array value must be a JSON array.",
                )

            if VaultCommand._contains_object(
                result,
            ):

                raise ValueError(
                    "Nested JSON objects are not allowed "
                    "inside Vault arrays.",
                )

            return result

        if value_type is VaultValueType.OBJECT:

            try:

                result = json.loads(
                    value,
                )

            except json.JSONDecodeError as exc:

                raise ValueError(
                    "Object value must be valid JSON.",
                ) from exc

            if not isinstance(
                result,
                dict,
            ):

                raise ValueError(
                    "Vault object value must be a JSON object.",
                )

            return result

        if value_type is VaultValueType.JSON:

            try:

                return json.loads(
                    value,
                )

            except json.JSONDecodeError as exc:

                raise ValueError(
                    "Value must be valid JSON.",
                ) from exc

        raise ValueError(
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

            raise ValueError(
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

            raise ValueError(
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

            raise ValueError(
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

            raise ValueError(
                "Vault key must be a string.",
            )

        if not key:

            raise ValueError(
                "Vault key cannot be empty.",
            )

        for character in key:

            if not (
                character.isascii()
                and (
                    character.isalnum()
                    or character == "_"
                )
            ):

                raise ValueError(
                    "Vault key may contain only "
                    "letters, numbers, and underscore (_).",
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
