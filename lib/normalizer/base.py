"""
Document normalizer base.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseNormalizer(
    ABC,
):
    """
    Base class for document normalizers.
    """

    @abstractmethod
    def normalize(
        self,
        document: Any,
        structure: dict[str, Any],
    ) -> Any:
        """
        Normalize a parsed document.
        """

        raise NotImplementedError()
