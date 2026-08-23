"""
ConfigMap/Secret target adapter.
"""

from __future__ import annotations

import base64
from typing import Any

from .exceptions import DeploymentUpdateTargetError


class ConfigMapSecretTarget:
    """
    Provides logical access to ConfigMap/Secret data.

    ConfigMap values are stored directly.

    Secret values are transparently decoded from and encoded
    back to base64.
    """

    def __init__(
        self,
        document: dict[str, Any],
        kind: str,
    ) -> None:

        self._document = document
        self._kind = kind

        self._validate()

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def keys(self) -> set[str]:
        return set(
            self._data().keys(),
        )

    def contains(
        self,
        key: str,
    ) -> bool:

        return key in self._data()

    def get(
        self,
        key: str,
    ) -> Any:

        data = self._data()

        if key not in data:

            raise KeyError(
                key,
            )

        value = data[key]

        if self._kind == "Secret":

            return self._decode(
                value,
                key,
            )

        return value

    def set(
        self,
        key: str,
        value: Any,
    ) -> None:

        if self._kind == "Secret":

            value = self._encode(
                value,
                key,
            )

        self._data()[key] = value

    def delete(
        self,
        key: str,
    ) -> None:

        del self._data()[key]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(
        self,
    ) -> None:

        if self._kind not in {
            "ConfigMap",
            "Secret",
        }:

            raise DeploymentUpdateTargetError(
                f"Unsupported target kind '{self._kind}'.",
            )

        document_kind = self._document.get(
            "kind",
        )

        if document_kind != self._kind:

            raise DeploymentUpdateTargetError(
                f"Target document kind '{document_kind}' "
                f"does not match expected '{self._kind}'.",
            )

        data = self._document.get(
            "data",
        )

        if data is None:

            self._document["data"] = {}

            return

        if not isinstance(
            data,
            dict,
        ):

            raise DeploymentUpdateTargetError(
                "Target 'data' must be an object.",
            )

    def _data(
        self,
    ) -> dict[str, Any]:

        return self._document["data"]

    # ------------------------------------------------------------------
    # Secret encoding
    # ------------------------------------------------------------------

    @staticmethod
    def _decode(
        value: Any,
        key: str,
    ) -> str:

        if not isinstance(
            value,
            str,
        ):

            raise DeploymentUpdateTargetError(
                f"Secret value for key '{key}' must be " "a base64 string.",
            )

        try:

            return base64.b64decode(
                value,
                validate=True,
            ).decode(
                "utf-8",
            )

        except (
            ValueError,
            UnicodeDecodeError,
        ) as exc:

            raise DeploymentUpdateTargetError(
                f"Secret value for key '{key}' " "contains invalid base64 data.",
            ) from exc

    @staticmethod
    def _encode(
        value: Any,
        key: str,
    ) -> str:

        if not isinstance(
            value,
            str,
        ):

            raise DeploymentUpdateTargetError(
                f"Secret value for key '{key}' must be a string.",
            )

        return base64.b64encode(
            value.encode(
                "utf-8",
            ),
        ).decode(
            "ascii",
        )
