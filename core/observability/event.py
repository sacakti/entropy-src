"""
Observability events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from core.models.enums import EventType
from core.models.logger import LogLevel

if TYPE_CHECKING:
    from core.models.runtime import ExecutionStatus, RuntimeNodeType
    from core.runtime.node import RuntimeNode
    from core.runtime.execution import WorkflowExecution


class BaseEvent:
    """
    Marker base class for all observability events.
    """

    pass


# ------------------------------------------------------------------
# Runtime Event
# ------------------------------------------------------------------


@dataclass(frozen=True)
class Event(BaseEvent):
    """
    Immutable runtime observation.

    Produced by the runtime.

    Consumed by observability sinks.
    """

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------

    type: EventType

    source: str

    execution: WorkflowExecution

    node: RuntimeNode

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    id: str = field(
        default_factory=lambda: uuid4().hex,
    )

    timestamp: datetime = field(
        default_factory=datetime.utcnow,
    )

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @property
    def execution_id(self) -> str:

        return self.execution.id

    @property
    def workspace(self):

        return self.execution.context.workspace

    @property
    def name(self) -> str:

        return self.node.name

    @property
    def node_type(self) -> RuntimeNodeType:

        return self.node.type

    @property
    def status(self) -> ExecutionStatus:

        return self.node.status

# ------------------------------------------------------------------
# Log Event
# ------------------------------------------------------------------


@dataclass(frozen=True)
class LogEvent(BaseEvent):
    """
    Application log event.
    """

    source: str

    level: LogLevel

    message: str

    id: str = field(
        default_factory=lambda: uuid4().hex,
    )

    timestamp: datetime = field(
        default_factory=datetime.utcnow,
    )
