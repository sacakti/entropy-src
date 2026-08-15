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
        ${variable.path}
        ${variable[key].path}
        ${variable[${other_variable}].path}

    Examples:

        ${environment}
        ${env[sit].api_url}
        ${env[${environment}].api_url}
        ${entv:sitdb}
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

        resolving.add(name)

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

            resolving.remove(name)

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

        if isinstance(value, str):

            return self._resolve_string(
                value,
                variables,
                resolved,
                resolving,
            )

        if isinstance(value, dict):

            return {
                key: self._resolve_value(
                    item,
                    variables,
                    resolved,
                    resolving,
                )
                for key, item in value.items()
            }

        if isinstance(value, list):

            return [
                self._resolve_value(
                    item,
                    variables,
                    resolved,
                    resolving,
                )
                for item in value
            ]

        if isinstance(value, tuple):

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

        reference = self._extract_reference(
            value.strip(),
        )

        if reference is not None:

            if reference.startswith("steps."):

                return value

            return self._resolve_reference(
                reference,
                variables,
                resolved,
                resolving,
            )

        if not self._REFERENCE.search(value):

            return value

        def replace(match):

            reference = match.group(1)

            if reference.startswith("steps."):

                return match.group(0)

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
    # Reference extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_reference(
        value: str,
    ) -> str | None:
        """
        Extract a complete reference while supporting nested
        ${...} expressions inside bracket selectors.
        """

        if not value.startswith("${"):

            return None

        depth = 0

        for index, char in enumerate(value):

            if char == "{":

                depth += 1

            elif char == "}":

                depth -= 1

                if depth == 0:

                    if index == len(value) - 1:

                        return value[2:-1]

                    return None

        return None

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

        if reference.startswith("entv:"):

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
                    f"Entropy Vault entry "
                    f"'{key}' could not be resolved.",
                ) from exc

        path = self._parse_path(
            reference,
            variables,
            resolved,
            resolving,
        )

        if not path:

            raise VariableNotFoundError(
                f"Invalid workflow variable reference "
                f"'{reference}'.",
            )

        current = self._resolve_variable(
            path[0],
            variables,
            resolved,
            resolving,
        )

        for key in path[1:]:

            current = self._lookup(
                current,
                key,
                reference,
            )

        return current

    # ------------------------------------------------------------------
    # Path
    # ------------------------------------------------------------------

    def _parse_path(
        self,
        reference: str,
        variables: Dict[str, Any],
        resolved: Dict[str, Any],
        resolving: Set[str],
    ) -> list[str]:
        """
        Parse a variable path.

        Examples:

            env.sit.api_url

            env[sit].api_url

            env[${environment}].api_url
        """

        parts: list[str] = []
        current: list[str] = []

        index = 0

        while index < len(reference):

            char = reference[index]

            if char == ".":

                if current:

                    parts.append(
                        "".join(current).strip(),
                    )

                    current = []

                index += 1
                continue

            if char == "[":

                if current:

                    parts.append(
                        "".join(current).strip(),
                    )

                    current = []

                end = self._find_bracket(
                    reference,
                    index,
                )

                if end is None:

                    raise VariableNotFoundError(
                        f"Invalid workflow variable "
                        f"reference '{reference}'.",
                    )

                selector = reference[
                    index + 1 : end
                ].strip()

                selector = self._resolve_selector(
                    selector,
                    variables,
                    resolved,
                    resolving,
                )

                parts.append(
                    selector,
                )

                index = end + 1
                continue

            current.append(char)

            index += 1

        if current:

            parts.append(
                "".join(current).strip(),
            )

        return [
            part
            for part in parts
            if part
        ]

    def _resolve_selector(
        self,
        selector: str,
        variables: Dict[str, Any],
        resolved: Dict[str, Any],
        resolving: Set[str],
    ) -> str:
        """
        Resolve a bracket selector.

        Example:

            ${environment}

        becomes:

            sit
        """

        reference = self._extract_reference(
            selector,
        )

        if reference is None:

            return selector

        value = self._resolve_reference(
            reference,
            variables,
            resolved,
            resolving,
        )

        if isinstance(
            value,
            (dict, list, tuple),
        ):

            raise VariableNotFoundError(
                f"Variable selector '{selector}' "
                "must resolve to a scalar value.",
            )

        return str(value)

    @staticmethod
    def _find_bracket(
        value: str,
        start: int,
    ) -> int | None:
        """
        Find the matching closing bracket.
        """

        depth = 0

        for index in range(
            start,
            len(value),
        ):

            char = value[index]

            if char == "[":
                depth += 1

            elif char == "]":

                depth -= 1

                if depth == 0:
                    return index

        return None

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    @staticmethod
    def _lookup(
        value: Any,
        key: str,
        reference: str,
    ) -> Any:
        """
        Resolve one path component.
        """

        if isinstance(value, dict):

            if key in value:

                return value[key]

        elif isinstance(
            value,
            (list, tuple),
        ):

            try:

                return value[int(key)]

            except (
                ValueError,
                IndexError,
            ):

                pass

        raise VariableNotFoundError(
            f"Unable to resolve workflow variable "
            f"reference '{reference}'.",
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

        if isinstance(value, str):
            return value

        if isinstance(value, bool):
            return str(value).lower()

        if isinstance(
            value,
            (int, float),
        ):
            return str(value)

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

        return str(value)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_variables(
        self,
        variables: Dict[str, Any],
    ) -> tuple[Dict[str, Any], list[str]]:
        """
        Validate workflow variables.
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
