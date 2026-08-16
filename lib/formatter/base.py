"""
Base formatter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseFormatter(ABC):
    """
    Base class for document formatters.
    """

    @property
    @abstractmethod
    def name(
        self,
    ) -> str:
        """
        Canonical formatter name.
        """

        raise NotImplementedError()

    @property
    def aliases(
        self,
    ) -> tuple[str, ...]:
        """
        Alternative names accepted by the formatter.
        """

        return ()

    @abstractmethod
    def format(
        self,
        content: str,
    ) -> str:
        """
        Format document content.
        """

        raise NotImplementedError()

    @abstractmethod
    def serialize(
        self,
        value: Any,
    ) -> str:
        ...
