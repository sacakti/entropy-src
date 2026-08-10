"""
Base generator.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from core.context import EntropyContext


@dataclass(frozen=True)
class GeneratorMetadata:
    """
    Generator metadata.
    """

    name: str

    description: str


class BaseGenerator(ABC):
    """
    Base generator.
    """

    metadata: GeneratorMetadata

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        self._context = context

    @abstractmethod
    def generate(
        self,
        args: Any,
        context: EntropyContext | None = None,
    ) -> None:
        """
        Generate an artifact.
        """
