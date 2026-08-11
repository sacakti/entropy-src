"""
Workflow codec abstractions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from lib.models.workflow import Workflow


class WorkflowCodec(
    ABC,
):
    """
    Base workflow codec.

    A codec converts between a workflow data mapping
    and the internal Workflow model.
    """

    @property
    @abstractmethod
    def format(
        self,
    ) -> str:
        """
        Return the serialization format name.
        """

    @abstractmethod
    def decode(
        self,
        data: dict[str, Any],
    ) -> Workflow:
        """
        Convert a mapping into a Workflow.
        """

    @abstractmethod
    def encode(
        self,
        workflow: Workflow,
    ) -> dict[str, Any]:
        """
        Convert a Workflow into a mapping.
        """

    @abstractmethod
    def decode_file(
        self,
        path,
    ) -> Workflow:
        """
        Read and decode a workflow file.
        """

    @abstractmethod
    def encode_file(
        self,
        workflow: Workflow,
        path,
    ) -> None:
        """
        Encode and write a workflow file.
        """
