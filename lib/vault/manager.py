"""
Entropy Vault manager.
"""

from __future__ import annotations

from typing import Any

from lib.models.vault import VaultEntry, VaultValueType
from lib.database.repositories.vault import VaultRepository
from lib.vault.cipher import VaultCipher
from lib.vault.exceptions import VaultEntryExistsError, VaultEntryNotFoundError, VaultValueError
from lib.vault.key import VaultKeyProvider
from lib.vault.serializer import VaultSerializer

class VaultManager:
    """
    High-level Vault service.

    Handles:

    - value serialization
    - encryption and decryption
    - Vault persistence

    CLI and workflow concerns are intentionally kept outside
    this class.
    """

    def __init__(
        self,
        repository: VaultRepository,
        serializer: VaultSerializer,
        key_provider: VaultKeyProvider,
    ) -> None:

        self._repository = repository

        self._serializer = serializer

        self._key_provider = key_provider

    # ------------------------------------------------------------------
    # Add
    # ------------------------------------------------------------------

    def add(
        self,
        key: str,
        value: Any,
        value_type: VaultValueType,
        sensitive: bool = False,
    ) -> VaultEntry:
        """
        Add a new Vault entry.
        """

        self._validate_key(
            key,
        )

        if self._repository.exists(
            key,
        ):

            raise VaultEntryExistsError(
                f"Vault entry '{key}' already exists.",
            )

        serialized = self._serializer.serialize(
            value,
            value_type,
        )

        stored_value = self._protect(
            serialized,
            sensitive,
        )

        entry = VaultEntry(
            key=key,
            value=stored_value,
            type=value_type,
            sensitive=sensitive,
        )

        return self._repository.create(
            entry,
        )

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get(
        self,
        key: str,
    ) -> Any:
        """
        Return the resolved logical value.

        Sensitive values are decrypted automatically.
        """

        entry = self.get_entry(
            key,
        )

        payload = self._unprotect(
            entry.value,
            entry.sensitive,
        )

        return self._serializer.deserialize(
            payload,
            entry.type,
        )

    def get_matching(
        self,
        pattern: str,
    ) -> dict[str, Any]:
        """
        Return Vault values matching a prefix pattern.

        Only trailing '*' is supported.

        Example
        -------
        uat_*
            {
                "username": "...",
                "password": "...",
            }
        """

        if not isinstance(
            pattern,
            str,
        ):

            raise VaultValueError(
                "Vault pattern must be a string.",
            )

        pattern = pattern.strip()

        if not pattern:

            raise VaultValueError(
                "Vault pattern cannot be empty.",
            )

        if not pattern.endswith("*"):

            raise VaultValueError(
                "Vault pattern must end with '*'.",
            )

        prefix = pattern[:-1]

        if not prefix:

            raise VaultValueError(
                "Vault wildcard pattern must contain a prefix.",
            )

        entries = self._repository.get_by_prefix(
            prefix,
        )

        if not entries:

            raise VaultEntryNotFoundError(
                f"No Vault entries matched pattern '{pattern}'.",
            )

        matches: dict[str, Any] = {}

        for entry in entries:

            key = entry.key[
                len(prefix):
            ]

            if not key:
                continue

            payload = self._unprotect(
                entry.value,
                entry.sensitive,
            )

            matches[key] = self._serializer.deserialize(
                payload,
                entry.type,
            )

        return matches

    # ------------------------------------------------------------------
    # Get Entry
    # ------------------------------------------------------------------

    def get_entry(
        self,
        key: str,
    ) -> VaultEntry:
        """
        Return a stored Vault entry.

        The value remains in its database representation.
        Sensitive values are not decrypted.
        """

        entry = self._repository.get_by_key(
            key,
        )

        if entry is None:

            raise VaultEntryNotFoundError(
                f"Vault entry '{key}' does not exist.",
            )

        return entry

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(
        self,
    ) -> list[VaultEntry]:
        """
        Return Vault entries without decrypting values.
        """

        return self._repository.list()

    # ------------------------------------------------------------------
    # Exists
    # ------------------------------------------------------------------

    def exists(
        self,
        key: str,
    ) -> bool:
        """
        Return True if a Vault key exists.
        """

        return self._repository.exists(
            key,
        )

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self,
        key: str,
        value: Any,
        value_type: VaultValueType,
        sensitive: bool = False,
    ) -> VaultEntry:
        """
        Replace an existing Vault entry.
        """

        self._validate_key(
            key,
        )

        if not self._repository.exists(
            key,
        ):

            raise VaultEntryNotFoundError(
                f"Vault entry '{key}' does not exist.",
            )

        serialized = self._serializer.serialize(
            value,
            value_type,
        )

        stored_value = self._protect(
            serialized,
            sensitive,
        )

        entry = VaultEntry(
            key=key,
            value=stored_value,
            type=value_type,
            sensitive=sensitive,
        )

        self._repository.update(
            entry,
        )

        return self.get_entry(
            key,
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(
        self,
        key: str,
    ) -> None:
        """
        Delete a Vault entry.
        """

        if not self._repository.exists(
            key,
        ):

            raise VaultEntryNotFoundError(
                f"Vault entry '{key}' does not exist.",
            )

        self._repository.delete(
            key,
        )

    # ------------------------------------------------------------------
    # Encryption
    # ------------------------------------------------------------------

    def _protect(
        self,
        value: bytes,
        sensitive: bool,
    ) -> str:
        """
        Encrypt a serialized value when required.
        """

        if not sensitive:

            return value.decode(
                "utf-8",
            )

        key = self._key_provider.key()

        cipher = VaultCipher(
            key,
        )

        encrypted = cipher.encrypt(
            value,
        )

        return encrypted.hex()

    # ------------------------------------------------------------------
    # Decryption
    # ------------------------------------------------------------------

    def _unprotect(
        self,
        value: str,
        sensitive: bool,
    ) -> bytes:
        """
        Decrypt a stored value when required.
        """

        if not sensitive:

            return value.encode(
                "utf-8",
            )

        key = self._key_provider.key()

        cipher = VaultCipher(
            key,
        )

        encrypted = bytes.fromhex(
            value,
        )

        return cipher.decrypt(
            encrypted,
        )

    # ------------------------------------------------------------------
    # Structured Update
    # ------------------------------------------------------------------

    def update_field(
        self,
        key: str,
        field: str,
        value: Any,
    ) -> VaultEntry:
        """
        Update one field of an object Vault entry.
        """

        entry = self.get_entry(
            key,
        )

        current = self.get(
            key,
        )

        if not isinstance(
            current,
            dict,
        ):
            raise VaultValueError(
                f"Vault entry '{key}' is not an object.",
            )

        if field not in current:
            raise VaultValueError(
                f"Field '{field}' does not exist in "
                f"Vault entry '{key}'.",
            )

        current[field] = value

        return self.update(
            key=key,
            value=current,
            value_type=entry.type,
            sensitive=entry.sensitive,
        )


    def add_field(
        self,
        key: str,
        field: str,
        value: Any,
    ) -> VaultEntry:
        """
        Add one field to an object Vault entry.
        """

        entry = self.get_entry(
            key,
        )

        current = self.get(
            key,
        )

        if not isinstance(
            current,
            dict,
        ):
            raise VaultValueError(
                f"Vault entry '{key}' is not an object.",
            )

        if field in current:
            raise VaultValueError(
                f"Field '{field}' already exists "
                f"in Vault entry '{key}'.",
            )

        self._validate_key(
            field,
        )

        current[field] = value

        return self.update(
            key=key,
            value=current,
            value_type=entry.type,
            sensitive=entry.sensitive,
        )


    def remove_field(
        self,
        key: str,
        field: str,
    ) -> VaultEntry:
        """
        Remove one field from an object Vault entry.
        """

        entry = self.get_entry(
            key,
        )

        current = self.get(
            key,
        )

        if not isinstance(
            current,
            dict,
        ):
            raise VaultValueError(
                f"Vault entry '{key}' is not an object.",
            )

        if field not in current:
            raise VaultValueError(
                f"Field '{field}' does not exist "
                f"in Vault entry '{key}'.",
            )

        del current[field]

        if not current:
            raise VaultValueError(
                "Vault object cannot be empty.",
            )

        return self.update(
            key=key,
            value=current,
            value_type=entry.type,
            sensitive=entry.sensitive,
        )

    # ------------------------------------------------------------------
    # Key validation
    # ------------------------------------------------------------------

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

            if not (
                character.isascii()
                and (
                    character.isalnum()
                    or character == "_"
                )
            ):

                raise VaultValueError(
                    "Vault key may contain only "
                    "letters, numbers, and underscore (_).",
                )
