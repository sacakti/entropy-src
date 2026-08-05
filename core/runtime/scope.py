"""
Base execution scope.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.models.runtime import RuntimeNodeType

from core.models.enums import EventType

from .node import RuntimeNode


class ExecutionScope(ABC):
    """
    Base class for runtime execution scopes.

    Handles

        • Runtime tree
        • Runtime node lifecycle
        • Event emission

    Subclasses define only the node type and
    event types.
    """

    def __init__(
        self,
        *,
        context,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:

        self._context = context

        self._name = name

        self._metadata = metadata or {}

        self._node: RuntimeNode | None = None

    # ---------------------------------------------------------
    # Context Manager
    # ---------------------------------------------------------

    def __enter__(self):

        #
        # Enter runtime tree
        #

        self._node = self._context.enter(
            type=self.node_type,
            name=self._name,
            metadata=self._metadata,
        )

        #
        # Start execution
        #

        self._node.start()

        #
        # Emit event
        #

        self._emit(
            self.started_event,
        )

        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ) -> bool:

        assert self._node is not None

        if exc is None:

            self._node.complete()

            self._emit(
                self.completed_event,
            )

        else:

            self._node.put(
                "exception",
                str(exc),
            )

            self._node.fail()

            self._emit(
                self.failed_event,
            )

        #
        # Leave runtime tree
        #

        self._context.leave()

        #
        # Never swallow exceptions.
        #

        return False

    # ---------------------------------------------------------
    # Events
    # ---------------------------------------------------------

    def _emit(
        self,
        event: EventType,
    ) -> None:
        """
        Emit a runtime event.
        """

        assert self._node is not None

        emitter = self._context.emitter(
            self.source,
        )

        emitter.emit(
            event_type=event,
            execution_id=self._context.execution.id,
            node=self._node,
        )

    # ---------------------------------------------------------
    # Abstract Properties
    # ---------------------------------------------------------

    @property
    @abstractmethod
    def node_type(self) -> RuntimeNodeType: ...

    @property
    @abstractmethod
    def source(self) -> str: ...

    @property
    @abstractmethod
    def started_event(self) -> EventType: ...

    @property
    @abstractmethod
    def completed_event(self) -> EventType: ...

    @property
    @abstractmethod
    def failed_event(self) -> EventType: ...
