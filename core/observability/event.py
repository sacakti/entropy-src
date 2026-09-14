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
    from core.runtime.execution import WorkflowExecution
    from core.runtime.node import RuntimeNode


class BaseEvent:
    """
    Marker base class for all observability events.
    """

    pass


# ------------------------------------------------------------------
# Runtime Event
# ------------------------------------------------------------------


class RuntimeEvent(BaseEvent):
    """
    Base class for runtime events.

    Runtime events are associated with a workflow execution and a
    runtime node (workflow, step or activity).
    """

    execution: WorkflowExecution
    node: RuntimeNode

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
# Runtime Lifecycle Event
# ------------------------------------------------------------------


@dataclass(frozen=True)
class LifecycleEvent(RuntimeEvent):
    """
    Runtime lifecycle event.

    Represents workflow, step and activity lifecycle events.
    """

    type: EventType

    source: str

    execution: WorkflowExecution

    node: RuntimeNode

    id: str = field(
        default_factory=lambda: uuid4().hex,
    )

    timestamp: datetime = field(
        default_factory=datetime.utcnow,
    )


# ------------------------------------------------------------------
# Runtime Message Event
# ------------------------------------------------------------------


@dataclass(frozen=True)
class MessageEvent(RuntimeEvent):
    """
    Runtime message produced during workflow execution.
    """

    source: str

    execution: WorkflowExecution

    node: RuntimeNode

    level: LogLevel

    message: str

    id: str = field(
        default_factory=lambda: uuid4().hex,
    )

    timestamp: datetime = field(
        default_factory=datetime.utcnow,
    )


# ------------------------------------------------------------------
# Application Log Event
# ------------------------------------------------------------------


@dataclass(frozen=True)
class LogEvent(BaseEvent):
    """
    Application log event.

    These events are not associated with workflow execution.
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

# ------------------------------------------------------------------
# Plugin Result Event
# ------------------------------------------------------------------


@dataclass(frozen=True)
class PluginResultEvent(RuntimeEvent):
    """
    Result produced by a workflow plugin execution.
    """

    source: str

    execution: WorkflowExecution

    node: RuntimeNode

    result: dict

    id: str = field(
        default_factory=lambda: uuid4().hex,
    )

    timestamp: datetime = field(
        default_factory=datetime.utcnow,
    )
