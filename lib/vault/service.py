"""
Vault service.

Coordinates namespace authorization, typed serialization,
encryption, and persistence of Vault values.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any

from lib.database.repositories.vault import VaultRepository
from lib.models.authorization import (
    VaultAccess,
    VaultNamespace,
)
from lib.models.vault import VaultEntry, VaultValueType
from lib.models.users import User
from lib.vault.cipher import VaultCipher
from lib.vault.exceptions import (
    VaultAccessDeniedError,
    VaultEntryExistsError,
    VaultEntryNotFoundError,
    VaultValueError,
)
from lib.vault.namespace_manager import VaultNamespaceManager
from lib.vault.serializer import (
    VaultSerializationError,
    VaultSerializer,
)
from lib.models.authorization import VaultAccess

class VaultService:
    """
    Provides authorized access to encrypted Vault values.

    All persisted values are encrypted, irrespective of the
    entry's sensitive metadata flag.
    """

    def __init__(
        self,
        entries: VaultRepository,
        namespaces: VaultNamespaceManager,
        cipher: VaultCipher,
        serializer: VaultSerializer,
    ) -> None:
        self._entries = entries
        self._namespaces = namespaces
        self._cipher = cipher
        self._serializer = serializer

    # ------------------------------------------------------------------
    # Namespace operations
    # ------------------------------------------------------------------

    def list_namespaces(
        self,
        user: User,
    ) -> list[VaultNamespace]:
        """
        Return namespaces visible to the user.

        Private namespaces require ownership or an explicit grant.
        Shared namespaces are visible for reading to authenticated
        users; write and administrative operations still require
        the corresponding access level.
        """
        if user.id is None:
            raise VaultAccessDeniedError(
                "An authenticated user is required."
            )

        visible: list[VaultNamespace] = []

        for namespace in self._namespaces.list():
            if namespace.id is None:
                continue

            access = self._namespaces.access_by_user_id(
                namespace,
                user.id,
            )

            if access is not None or namespace.visibility.value == "shared":
                visible.append(namespace)

        return visible

    def create_namespace(
        self,
        name: str,
        user: User,
        visibility,
    ) -> VaultNamespace:
        """Create a namespace owned by the authenticated user."""
        if user.id is None:
            raise VaultAccessDeniedError(
                "An authenticated user is required."
            )

        return self._namespaces.create(
            name=name,
            owner_user_id=user.id,
            visibility=visibility,
        )

    def get_namespace(
        self,
        name: str,
        user: User,
    ) -> VaultNamespace:
        """Get a namespace if the user is allowed to read it."""
        namespace = self._namespaces.get(name)
        self._require_access(namespace, user, VaultAccess.READ)
        return namespace

    def update_namespace(
        self,
        namespace: VaultNamespace,
        user: User,
        *,
        name: str | None = None,
        visibility=None,
    ) -> VaultNamespace:
        """Rename a namespace or change its visibility."""
        self._require_access(namespace, user, VaultAccess.ADMIN)

        return self._namespaces.modify(
            namespace,
            name=name,
            visibility=visibility,
        )

    def delete_namespace(
        self,
        namespace: VaultNamespace,
        user: User,
    ) -> None:
        """Delete a namespace and its dependent records."""
        self._require_access(namespace, user, VaultAccess.ADMIN)
        self._namespaces.delete(namespace)

    # ------------------------------------------------------------------
    # Entry operations
    # ------------------------------------------------------------------

    def create_entry(
        self,
        namespace: VaultNamespace,
        user: User,
        *,
        key: str,
        value: Any,
        value_type: VaultValueType,
        sensitive: bool = True,
    ) -> VaultEntry:
        """Validate, encrypt, and persist a new entry."""
        self._require_access(namespace, user, VaultAccess.WRITE)

        key = self._validate_key(key)
        self._require_namespace_id(namespace)

        if self._entries.exists(namespace.id, key):
            raise VaultEntryExistsError(
                f"Vault key '{key}' already exists."
            )

        encrypted = self._encrypt_value(value, value_type)

        entry = VaultEntry(
            namespace_id=namespace.id,
            key=key,
            value=encrypted,
            type=value_type,
            sensitive=sensitive,
        )

        return self._entries.create(entry)

    def list_entries(
        self,
        namespace: VaultNamespace,
        user: User,
    ) -> list[dict[str, Any]]:
        """
        List entry metadata only.

        The stored ciphertext is never included in the response.
        """
        self._require_access(namespace, user, VaultAccess.READ)
        self._require_namespace_id(namespace)

        return [
            {
                "id": entry.id,
                "key": entry.key,
                "type": entry.type.value,
                "sensitive": entry.sensitive,
                "created_at": (
                    entry.created_at.isoformat()
                    if entry.created_at
                    else None
                ),
                "updated_at": (
                    entry.updated_at.isoformat()
                    if entry.updated_at
                    else None
                ),
            }
            for entry in self._entries.list(namespace.id)
        ]

    def reveal_entry(
        self,
        namespace: VaultNamespace,
        user: User,
        key: str,
    ) -> dict[str, Any]:
        """Decrypt and return one entry after checking read access."""
        self._require_access(namespace, user, VaultAccess.READ)
        self._require_namespace_id(namespace)

        entry = self._get_entry(namespace.id, key)
        value = self._decrypt_value(entry.value, entry.type)

        return {
            "key": entry.key,
            "type": entry.type.value,
            "value": value,
            "sensitive": entry.sensitive,
        }

    def update_entry(
        self,
        namespace: VaultNamespace,
        user: User,
        *,
        key: str,
        value: Any,
        value_type: VaultValueType,
        sensitive: bool = True,
    ) -> None:
        """Encrypt and update an existing entry."""
        self._require_access(namespace, user, VaultAccess.WRITE)
        self._require_namespace_id(namespace)

        entry = self._get_entry(namespace.id, key)
        encrypted = self._encrypt_value(value, value_type)

        entry.value = encrypted
        entry.type = value_type
        entry.sensitive = sensitive

        self._entries.update(entry)

    def delete_entry(
        self,
        namespace: VaultNamespace,
        user: User,
        key: str,
    ) -> None:
        """Delete an entry after checking write access."""
        self._require_access(namespace, user, VaultAccess.WRITE)
        self._require_namespace_id(namespace)

        self._get_entry(namespace.id, key)
        self._entries.delete(namespace.id, key)

    # ------------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------------

    def _require_access(
        self,
        namespace: VaultNamespace,
        user: User,
        required: VaultAccess,
    ) -> None:
        if user.id is None:
            raise VaultAccessDeniedError(
                "An authenticated user is required."
            )

        access = self._namespaces.access_by_user_id(
            namespace,
            user.id,
        )

        if access is None:
            # Shared visibility grants read access only.
            if (
                namespace.visibility.value == "shared"
                and required is VaultAccess.READ
            ):
                return

            raise VaultAccessDeniedError(
                "You do not have access to this Vault namespace."
            )

        levels = {
            VaultAccess.READ: 1,
            VaultAccess.WRITE: 2,
            VaultAccess.ADMIN: 3,
        }

        if levels[access] < levels[required]:
            raise VaultAccessDeniedError(
                "Your Vault namespace access level is insufficient."
            )

    # ------------------------------------------------------------------
    # Serialization and encryption
    # ------------------------------------------------------------------

    def _encrypt_value(
        self,
        value: Any,
        value_type: VaultValueType,
    ) -> str:
        try:
            serialized = self._serializer.serialize(
                value,
                value_type,
            )
            encrypted = self._cipher.encrypt(serialized)

        except VaultSerializationError as exc:
            raise VaultValueError(str(exc)) from exc

        return base64.b64encode(encrypted).decode("ascii")

    def _decrypt_value(
        self,
        stored_value: Any,
        value_type: VaultValueType,
    ) -> Any:
        if not isinstance(stored_value, str):
            raise VaultValueError(
                "Stored Vault ciphertext has an invalid format."
            )

        try:
            encrypted = base64.b64decode(
                stored_value.encode("ascii"),
                validate=True,
            )
        except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
            raise VaultValueError(
                "Stored Vault ciphertext is not valid Base64."
            ) from exc

        try:
            serialized = self._cipher.decrypt(encrypted)
            return self._serializer.deserialize(
                serialized,
                value_type,
            )
        except VaultSerializationError as exc:
            raise VaultValueError(
                "Stored Vault value could not be deserialized."
            ) from exc

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_entry(
        self,
        namespace_id: int,
        key: str,
    ) -> VaultEntry:
        entry = self._entries.get_by_key(
            namespace_id,
            self._validate_key(key),
        )

        if entry is None:
            raise VaultEntryNotFoundError(
                f"Vault key '{key}' was not found."
            )

        return entry

    @staticmethod
    def _validate_key(key: str) -> str:
        if not isinstance(key, str) or not key.strip():
            raise VaultValueError(
                "Vault key cannot be empty."
            )

        return key.strip()

    @staticmethod
    def _require_namespace_id(
        namespace: VaultNamespace,
    ) -> None:
        if namespace.id is None:
            raise VaultValueError(
                "Vault namespace identifier is required."
            )

    def list_access_assignments(
        self,
        namespace: VaultNamespace,
        user: User,
    ) -> list[dict[str, Any]]:
        """List namespace grants. Only namespace admins may view grants."""
        self._require_access(namespace, user, VaultAccess.ADMIN)

        return [
            {
                "id": assignment.id,
                "user_id": assignment.user_id,
                "access": assignment.access.value,
                "created_at": (
                    assignment.created_at.isoformat()
                    if assignment.created_at
                    else None
                ),
            }
            for assignment in self._namespaces.access_assignments(namespace)
        ]


    def grant_namespace_access(
        self,
        namespace: VaultNamespace,
        user: User,
        *,
        username: str,
        access: VaultAccess,
    ) -> None:
        """Grant a user access to a namespace."""
        self._require_access(namespace, user, VaultAccess.ADMIN)

        if access is VaultAccess.ADMIN:
            raise VaultValueError(
                "Granting administrator access requires a separate "
                "explicit administrative operation."
            )

        self._namespaces.grant_access(
            namespace,
            username.strip(),
            access,
        )


    def revoke_namespace_access(
        self,
        namespace: VaultNamespace,
        user: User,
        *,
        username: str,
    ) -> None:
        """Revoke an explicit namespace access grant."""
        self._require_access(namespace, user, VaultAccess.ADMIN)

        if not username.strip():
            raise VaultValueError("Username cannot be empty.")

        self._namespaces.revoke_access(
            namespace,
            username.strip(),
        )
