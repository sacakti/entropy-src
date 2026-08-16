"""
Document normalization manager.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lib.normalizer.base import BaseNormalizer
from lib.normalizer.structure import StructureNormalizer
from lib.normalizer.loader import StructureLoader


class NormalizerManager:
    """
    Resolve and execute document normalizers.
    """

    def __init__(
        self,
    ) -> None:

        self._normalizers: dict[str, BaseNormalizer] = {}

        self._structure_loader = StructureLoader()

        self.register(
            "structure",
            StructureNormalizer(),
        )

    # ------------------------------------------------------------------
    # Structure
    # ------------------------------------------------------------------

    def load_structure(
        self,
        path: Path,
    ) -> dict[str, Any]:
        """
        Load a normalization structure.
        """

        return self._structure_loader.load(
            path,
        )

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        normalizer: BaseNormalizer,
    ) -> None:

        self._normalizers[
            name
        ] = normalizer

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def normalize(
        self,
        document: Any,
        structure: dict[str, Any],
        *,
        normalizer: str = "structure",
    ) -> Any:

        implementation = self._normalizers.get(
            normalizer,
        )

        if implementation is None:

            raise ValueError(
                f"Unknown normalizer '{normalizer}'.",
            )

        return implementation.normalize(
            document,
            structure,
        )
