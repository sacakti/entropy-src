"""
Plugin workflow argument API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

from lib.plugins.exceptions import PluginValueError


T = TypeVar("T")


class PluginArguments:
    """
    Typed workflow arguments exposed to plugins.

    This class centralizes argument access, type conversion
    and validation for all plugins.
    """

    def __init__(
        self,
        arguments: dict[str, Any],
    ) -> None:

        self._arguments = arguments

    # ------------------------------------------------------------------
    # Generic
    # ------------------------------------------------------------------

    def get(
        self,
        name: str,
        default: T | None = None,
    ) -> Any | T | None:
        """
        Return an argument without type conversion.
        """

        return self._arguments.get(
            name,
            default,
        )

    def required(
        self,
        name: str,
    ) -> Any:
        """
        Return a required argument.

        Raises PluginValueError when the argument is missing or None.
        """

        if name not in self._arguments:

            raise PluginValueError(
                f"Required argument '{name}' "
                "is missing."
            )

        value = self._arguments[name]

        if value is None:

            raise PluginValueError(
                f"Required argument '{name}' "
                "cannot be null."
            )

        return value

    def contains(
        self,
        name: str,
    ) -> bool:
        """
        Return whether an argument exists.
        """

        return name in self._arguments

    # ------------------------------------------------------------------
    # String
    # ------------------------------------------------------------------

    def string(
        self,
        name: str,
        default: str | None = None,
        *,
        required: bool = False,
    ) -> str | None:
        """
        Return a string argument.
        """

        if name not in self._arguments:

            if required:

                raise PluginValueError(
                    f"Required argument '{name}' "
                    "is missing."
                )

            return default

        value = self._arguments[name]

        if value is None:

            if required:

                raise PluginValueError(
                    f"Required argument '{name}' "
                    "cannot be null."
                )

            return default

        if not isinstance(
            value,
            str,
        ):

            raise PluginValueError(
                f"Argument '{name}' must be "
                "a string."
            )

        value = value.strip()

        if not value and required:

            raise PluginValueError(
                f"Required argument '{name}' "
                "cannot be empty."
            )

        return value

    # ------------------------------------------------------------------
    # Boolean
    # ------------------------------------------------------------------

    def boolean(
        self,
        name: str,
        default: bool | None = None,
        *,
        required: bool = False,
    ) -> bool | None:
        """
        Return a boolean argument.

        Accepted string values:

            true
            false
            yes
            no
            1
            0
        """

        if name not in self._arguments:

            if required:

                raise PluginValueError(
                    f"Required argument '{name}' "
                    "is missing."
                )

            return default

        value = self._arguments[name]

        if value is None:

            if required:

                raise PluginValueError(
                    f"Required argument '{name}' "
                    "cannot be null."
                )

            return default

        if isinstance(
            value,
            bool,
        ):

            return value

        if isinstance(
            value,
            str,
        ):

            normalized = (
                value.strip().lower()
            )

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

        raise PluginValueError(
            f"Argument '{name}' must be "
            "a boolean."
        )

    # ------------------------------------------------------------------
    # Integer
    # ------------------------------------------------------------------

    def integer(
        self,
        name: str,
        default: int | None = None,
        *,
        required: bool = False,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> int | None:
        """
        Return an integer argument.
        """

        if name not in self._arguments:

            if required:

                raise PluginValueError(
                    f"Required argument '{name}' "
                    "is missing."
                )

            return default

        value = self._arguments[name]

        if value is None:

            if required:

                raise PluginValueError(
                    f"Required argument '{name}' "
                    "cannot be null."
                )

            return default

        if isinstance(
            value,
            bool,
        ):

            raise PluginValueError(
                f"Argument '{name}' must be "
                "an integer."
            )

        try:

            result = int(
                value,
            )

        except (
            TypeError,
            PluginValueError,
        ) as exc:

            raise PluginValueError(
                f"Argument '{name}' must be "
                "an integer."
            ) from exc

        self._validate_range(
            name,
            result,
            minimum,
            maximum,
        )

        return result

    # ------------------------------------------------------------------
    # Float
    # ------------------------------------------------------------------

    def number(
        self,
        name: str,
        default: float | None = None,
        *,
        required: bool = False,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float | None:
        """
        Return a numeric argument as float.
        """

        if name not in self._arguments:

            if required:

                raise PluginValueError(
                    f"Required argument '{name}' "
                    "is missing."
                )

            return default

        value = self._arguments[name]

        if value is None:

            if required:

                raise PluginValueError(
                    f"Required argument '{name}' "
                    "cannot be null."
                )

            return default

        if isinstance(
            value,
            bool,
        ):

            raise PluginValueError(
                f"Argument '{name}' must be "
                "a number."
            )

        try:

            result = float(
                value,
            )

        except (
            TypeError,
            PluginValueError,
        ) as exc:

            raise PluginValueError(
                f"Argument '{name}' must be "
                "a number."
            ) from exc

        self._validate_range(
            name,
            result,
            minimum,
            maximum,
        )

        return result

    # ------------------------------------------------------------------
    # Path
    # ------------------------------------------------------------------

    def path(
        self,
        name: str,
        default: Path | str | None = None,
        *,
        required: bool = False,
    ) -> Path | None:
        """
        Return a filesystem path argument.

        The path is expanded with '~'.

        The path is intentionally not resolved because
        some plugin arguments represent literal path
        prefixes rather than existing filesystem paths.
        """

        value = self.string(
            name,
            (
                str(default)
                if default is not None
                else None
            ),
            required=required,
        )

        if value is None:

            return None

        return Path(
            value,
        ).expanduser()

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(
        self,
        name: str,
        default: list[Any] | None = None,
        *,
        required: bool = False,
    ) -> list[Any] | None:
        """
        Return a list argument.
        """

        if name not in self._arguments:

            if required:

                raise PluginValueError(
                    f"Required argument '{name}' "
                    "is missing."
                )

            return default

        value = self._arguments[name]

        if value is None:

            if required:

                raise PluginValueError(
                    f"Required argument '{name}' "
                    "cannot be null."
                )

            return default

        if not isinstance(
            value,
            list,
        ):

            raise PluginValueError(
                f"Argument '{name}' must be "
                "a list."
            )

        return value

    # ------------------------------------------------------------------
    # Dictionary
    # ------------------------------------------------------------------

    def dictionary(
        self,
        name: str,
        default: dict[str, Any] | None = None,
        *,
        required: bool = False,
    ) -> dict[str, Any] | None:
        """
        Return a dictionary argument.
        """

        if name not in self._arguments:

            if required:

                raise PluginValueError(
                    f"Required argument '{name}' "
                    "is missing."
                )

            return default

        value = self._arguments[name]

        if value is None:

            if required:

                raise PluginValueError(
                    f"Required argument '{name}' "
                    "cannot be null."
                )

            return default

        if not isinstance(
            value,
            dict,
        ):

            raise PluginValueError(
                f"Argument '{name}' must be "
                "an object."
            )

        return value

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_range(
        name: str,
        value: int | float,
        minimum: int | float | None,
        maximum: int | float | None,
    ) -> None:
        """
        Validate numeric bounds.
        """

        if (
            minimum is not None
            and value < minimum
        ):

            raise PluginValueError(
                f"Argument '{name}' must be "
                f"greater than or equal to "
                f"{minimum}."
            )

        if (
            maximum is not None
            and value > maximum
        ):

            raise PluginValueError(
                f"Argument '{name}' must be "
                f"less than or equal to "
                f"{maximum}."
            )
