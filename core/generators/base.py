"""
Base generator.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class GeneratorMetadata:

    name: str

    description: str


class BaseGenerator(ABC):

    metadata: GeneratorMetadata

    def __init__(self, context):

        self.context = context

    @abstractmethod
    def generate(self, args) -> None:
        """
        Generate the requested artifact.
        """
