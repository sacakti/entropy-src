"""
Document normalization manager.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from lib.normalizer.base import BaseNormalizer
from lib.normalizer.loader import StructureLoader
from lib.normalizer.structure import StructureNormalizer

if TYPE_CHECKING:

    from lib.executor import LinuxExecutor


class NormalizerManager:
    """
    Resolve and execute document normalizers.
    """

    def __init__(
        self,
        executor: LinuxExecutor,
    ) -> None:

        self._normalizers: dict[str, BaseNormalizer] = {}

        self._structure_loader = StructureLoader(
            executor,
        )

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
