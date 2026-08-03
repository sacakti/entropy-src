"""
Extension validator.
"""

from __future__ import annotations
from pathlib import Path

from core.context import EntropyContext

from .metadata import ExtensionMetadata


class ExtensionValidator:
    """
    Validates extension availability.
    """

    def __init__(
        self,
        context: EntropyContext,
        metadata: ExtensionMetadata,
    ) -> None:

        assert context.paths is not None

        self._paths = context.paths.extensions

        self._metadata = metadata

    # ------------------------------------------------------------------
    # Installed
    # ------------------------------------------------------------------

    def exists(
        self,
        name: str,
    ) -> bool:
        """
        Return True if an extension is installed.
        """

        return self._metadata.exists(
            name,
        )

    # ------------------------------------------------------------------
    # Version
    # ------------------------------------------------------------------

    def version(
        self,
        name: str,
    ) -> str | None:
        """
        Return the installed version.
        """

        return self._metadata.version(
            name,
        )

    # ------------------------------------------------------------------
    # Wheel
    # ------------------------------------------------------------------

    def wheel(
        self,
        name: str,
    ) -> Path | None:
        """
        Return the latest available wheel for an extension.
        """

        wheels = sorted(
            self._paths.wheels.glob(
                f"{name}-*.whl",
            )
        )

        if not wheels:
            return None

        return wheels[-1]
    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(
        self,
        name: str,
    ) -> None:
        """
        Verify the extension installation.

        Reserved for future integrity checks.
        """

        raise NotImplementedError()
