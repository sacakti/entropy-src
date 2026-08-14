"""
Workflow variable resolver.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Set

from .exceptions import (
    VariableCircularReferenceError,
    VariableNotFoundError,
)


class WorkflowVariableResolver:
    """
    Resolves workflow variables and Entropy Vault references.

    Supported references:

        ${entv:key}
        ${variable}

    References can occur inside:

        strings
        dictionaries
        lists
        tuples

    A complete variable reference preserves the original value type.

    Example:

        ${entv:sitdb}

    can resolve to:

        {
            "ip": "127.0.0.1",
            "port": 1521,
            "sid": "SITDB",
        }

    Embedded references are converted to text.

    Example:

        "Connecting to ${host}:${port}"
    """

    _REFERENCE = re.compile(
        r"\$\{([^{}]+)\}",
    )

    def __init__(
        self,
        vault,
    ) -> None:

        self._vault = vault

    # ------------------------------------------------------------------
    # Variables
    # ------------------------------------------------------------------

    def resolve_variables(
        self,
        variables: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Resolve all workflow variables.
        """

        resolved: Dict[str, Any] = {}

        for name in variables:

            resolved[name] = self._resolve_variable(
                name,
                variables,
                resolved,
                set(),
            )

        return resolved

    # ------------------------------------------------------------------
    # Value
    # ------------------------------------------------------------------

    def resolve(
        self,
        value: Any,
        variables: Dict[str, Any],
    ) -> Any:
        """
        Resolve references contained in an arbitrary value.
        """

        return self._resolve_value(
            value,
            variables,
            {},
            set(),
        )

    # ------------------------------------------------------------------
    # Variable
    # ------------------------------------------------------------------

    def _resolve_variable(
        self,
        name: str,
        variables: Dict[str, Any],
        resolved: Dict[str, Any],
        resolving: Set[str],
    ) -> Any:
        """
        Resolve one workflow variable.
        """

        if name in resolved:

            return resolved[name]

        if name in resolving:

            chain = " -> ".join(
                list(resolving) + [name],
            )

            raise VariableCircularReferenceError(
                f"Circular workflow variable reference: {chain}",
            )

        if name not in variables:

            raise VariableNotFoundError(
                f"Workflow variable '{name}' does not exist.",
            )

        resolving.add(
            name,
        )

        try:

            value = self._resolve_value(
                variables[name],
                variables,
                resolved,
                resolving,
            )

            resolved[name] = value

            return value

        finally:

            resolving.remove(
                name,
            )

    # ------------------------------------------------------------------
    # Recursive Value
    # ------------------------------------------------------------------

    def _resolve_value(
        self,
        value: Any,
        variables: Dict[str, Any],
        resolved: Dict[str, Any],
        resolving: Set[str],
    ) -> Any:
        """
        Recursively resolve a value.
        """

        if isinstance(
            value,
            str,
        ):

            return self._resolve_string(
                value,
                variables,
                resolved,
                resolving,
            )

        if isinstance(
            value,
            dict,
        ):

            return {
                key: self._resolve_value(
                    item,
                    variables,
                    resolved,
                    resolving,
                )
                for key, item in value.items()
            }

        if isinstance(
            value,
            list,
        ):

            return [
                self._resolve_value(
                    item,
                    variables,
                    resolved,
                    resolving,
                )
                for item in value
            ]

        if isinstance(
            value,
            tuple,
        ):

            return tuple(
                self._resolve_value(
                    item,
                    variables,
                    resolved,
                    resolving,
                )
                for item in value
            )

        return value

    # ------------------------------------------------------------------
    # String
    # ------------------------------------------------------------------

    def _resolve_string(
        self,
        value: str,
        variables: Dict[str, Any],
        resolved: Dict[str, Any],
        resolving: Set[str],
    ) -> Any:
        """
        Resolve references inside a string.
        """

        match = self._REFERENCE.fullmatch(
            value.strip(),
        )

        if match:

            reference = match.group(
                1,
            )

            return self._resolve_reference(
                reference,
                variables,
                resolved,
                resolving,
            )

        if not self._REFERENCE.search(
            value,
        ):

            return value

        def replace(match) -> str:

            reference = match.group(
                1,
            )

            resolved_value = self._resolve_reference(
                reference,
                variables,
                resolved,
                resolving,
            )

            return self._stringify(
                resolved_value,
            )

        return self._REFERENCE.sub(
            replace,
            value,
        )

    # ------------------------------------------------------------------
    # Reference
    # ------------------------------------------------------------------

    def _resolve_reference(
        self,
        reference: str,
        variables: Dict[str, Any],
        resolved: Dict[str, Any],
        resolving: Set[str],
    ) -> Any:
        """
        Resolve a single reference.
        """

        reference = reference.strip()

        if reference.startswith(
            "entv:",
        ):

            key = reference[5:].strip()

            if not key:

                raise VariableNotFoundError(
                    "Entropy Vault reference cannot be empty.",
                )

            try:

                if key.endswith("*"):

                    return self._vault.get_matching(
                        key,
                    )

                return self._vault.get(
                    key,
                )

            except Exception as exc:

                raise VariableNotFoundError(
                    f"Entropy Vault entry " f"'{key}' could not be resolved.",
                ) from exc

        return self._resolve_variable(
            reference,
            variables,
            resolved,
            resolving,
        )

    # ------------------------------------------------------------------
    # Stringify
    # ------------------------------------------------------------------

    @staticmethod
    def _stringify(
        value: Any,
    ) -> str:
        """
        Convert a resolved value to text for interpolation.
        """

        if isinstance(
            value,
            str,
        ):

            return value

        if isinstance(
            value,
            bool,
        ):

            return str(value).lower()

        if isinstance(
            value,
            (
                int,
                float,
            ),
        ):

            return str(value)

        if isinstance(
            value,
            (
                dict,
                list,
            ),
        ):

            return json.dumps(
                value,
                ensure_ascii=False,
                separators=(
                    ",",
                    ":",
                ),
            )

        return str(value)

    def validate_variables(
        self,
        variables: Dict[str, Any],
    ) -> tuple[Dict[str, Any], list[str]]:
        """
        Validate workflow variables.

        Returns
        -------
        tuple
            Successfully resolved variables and validation errors.
        """

        resolved: Dict[str, Any] = {}
        errors: list[str] = []

        for name in variables:

            try:

                self._resolve_variable(
                    name,
                    variables,
                    resolved,
                    set(),
                )

            except VariableNotFoundError as exc:

                errors.append(
                    str(exc),
                )

            except VariableCircularReferenceError as exc:

                errors.append(
                    str(exc),
                )

        return resolved, errors

    def validate(
        self,
        value: Any,
        variables: Dict[str, Any],
    ) -> list[str]:
        """
        Validate references contained in an arbitrary value.
        """

        errors: list[str] = []

        try:

            self.resolve(
                value,
                variables,
            )

        except VariableNotFoundError as exc:

            errors.append(
                str(exc),
            )

        except VariableCircularReferenceError as exc:

            errors.append(
                str(exc),
            )

        return errors
