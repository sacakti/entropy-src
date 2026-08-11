"""
Vault value serializer.
"""

from __future__ import annotations

import json
from typing import Any

from ..models.vault import VaultValueType


class VaultSerializationError(
    ValueError,
):
    """
    Raised when a Vault value cannot be serialized or deserialized.
    """


class VaultSerializer:
    """
    Serializes and deserializes typed Vault values.

    The serializer does not perform encryption.
    """

    # ------------------------------------------------------------------
    # Serialize
    # ------------------------------------------------------------------

    def serialize(
        self,
        value: Any,
        value_type: VaultValueType,
    ) -> bytes:
        """
        Serialize a Vault value into UTF-8 JSON bytes.
        """

        self._validate(
            value,
            value_type,
        )

        try:

            payload = json.dumps(
                value,
                ensure_ascii=False,
                separators=(
                    ",",
                    ":",
                ),
            )

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise VaultSerializationError(
                "Unable to serialize Vault value."
            ) from exc

        return payload.encode(
            "utf-8",
        )

    # ------------------------------------------------------------------
    # Deserialize
    # ------------------------------------------------------------------

    def deserialize(
        self,
        value: bytes,
        value_type: VaultValueType,
    ) -> Any:
        """
        Deserialize UTF-8 JSON bytes into a Python value.
        """

        try:

            payload = value.decode(
                "utf-8",
            )

            result = json.loads(
                payload,
            )

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:

            raise VaultSerializationError(
                "Invalid serialized Vault value."
            ) from exc

        self._validate(
            result,
            value_type,
        )

        return result

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate(
        value: Any,
        value_type: VaultValueType,
    ) -> None:
        """
        Validate a value against its declared type.
        """

        if value_type is VaultValueType.STRING:

            if not isinstance(
                value,
                str,
            ):

                raise VaultSerializationError(
                    "Vault string value must be a string."
                )

            return

        if value_type is VaultValueType.NUMBER:

            if isinstance(
                value,
                bool,
            ) or not isinstance(
                value,
                (
                    int,
                    float,
                ),
            ):

                raise VaultSerializationError(
                    "Vault number value must be an integer or float."
                )

            return

        if value_type is VaultValueType.BOOLEAN:

            if not isinstance(
                value,
                bool,
            ):

                raise VaultSerializationError(
                    "Vault boolean value must be a boolean."
                )

            return

        if value_type is VaultValueType.ARRAY:

            if not isinstance(
                value,
                list,
            ):

                raise VaultSerializationError(
                    "Vault array value must be a list."
                )

            return

        if value_type is VaultValueType.OBJECT:

            if not isinstance(
                value,
                dict,
            ):

                raise VaultSerializationError(
                    "Vault object value must be a dictionary."
                )

            return

        if value_type is VaultValueType.JSON:

            try:

                json.dumps(
                    value,
                )

            except (
                TypeError,
                ValueError,
            ) as exc:

                raise VaultSerializationError(
                    "Vault JSON value is not valid JSON."
                ) from exc

            return

        raise VaultSerializationError(
            f"Unsupported Vault value type: {value_type!r}"
        )
