"""
Base execution scope.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.models.enums import EventType
from core.models.runtime import RuntimeNodeType
from lib.workflow.exceptions import WorkflowCancelledError

from .node import RuntimeNode


class ExecutionScope(ABC):
    """
    Base class for runtime execution scopes.

    Handles

        • Runtime tree
        • Runtime node lifecycle
        • Runtime event emission

    Subclasses define only the runtime node type and
    lifecycle event types.
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

    # ------------------------------------------------------------------
    # Context Manager
    # ------------------------------------------------------------------

    def __enter__(self):

        #
        # Enter runtime tree.
        #

        self._node = self._context.enter(
            type=self.node_type,
            name=self._name,
            metadata=self._metadata,
        )

        #
        # Start execution.
        #

        self._node.start()

        #
        # Emit lifecycle event.
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

        elif isinstance(
            exc,
            WorkflowCancelledError,
        ):

            self._node.cancel()

            self._emit(
                self.cancelled_event,
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
        # Leave runtime tree.
        #

        self._context.leave()

        #
        # Never swallow exceptions.
        #

        return False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _emit(
        self,
        event: EventType,
    ) -> None:
        """
        Emit a runtime lifecycle event.
        """

        assert self._node is not None

        self._context.emitter(
            self.source,
        ).lifecycle(
            event_type=event,
            execution=self._context.execution,
            node=self._node,
        )

    # ------------------------------------------------------------------
    # Abstract Properties
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def node_type(self) -> RuntimeNodeType:
        """
        Runtime node type.
        """

    @property
    @abstractmethod
    def source(self) -> str:
        """
        Event source.
        """

    @property
    @abstractmethod
    def started_event(self) -> EventType:
        """
        Lifecycle event emitted when execution starts.
        """

    @property
    @abstractmethod
    def completed_event(self) -> EventType:
        """
        Lifecycle event emitted when execution completes.
        """

    @property
    @abstractmethod
    def failed_event(self) -> EventType:
        """
        Lifecycle event emitted when execution fails.
        """
