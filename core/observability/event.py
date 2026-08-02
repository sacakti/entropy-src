"""
Runtime observation event.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from core.models.enums import EventType
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from uuid import uuid4

from core.models.logger import LogLevel



if TYPE_CHECKING:
    from core.models.runtime import RuntimeNodeType
    from core.models.runtime import ExecutionStatus
    from core.runtime.node import RuntimeNode


@dataclass(frozen=True)
class Event:
    """
    Immutable runtime observation.

    Produced by the Runtime.

    Consumed by observability sinks.
    """

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------

    type: EventType

    source: str

    execution_id: str

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
    def name(self) -> str:

        return self.node.name

    @property
    def node_type(self) -> RuntimeNodeType:

        return self.node.type

    @property
    def status(self) -> ExecutionStatus:

        return self.node.status

@dataclass(frozen=True)
class LogEvent:

    level: LogLevel

    source: str

    message: str

    id: str = field(
        default_factory=lambda: uuid4().hex,
    )

    timestamp: datetime = field(
        default_factory=datetime.utcnow,
    )
