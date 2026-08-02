"""
Runtime execution node.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.models.runtime import ExecutionStatus
from core.models.runtime import RuntimeNodeType


@dataclass
class RuntimeNode:
    """
    Represents a node in the runtime execution tree.

    Example

        Workflow
            └── Step
                    └── Stage
                            └── Activity
    """

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    id: str

    name: str

    type: RuntimeNodeType

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------

    status: ExecutionStatus = ExecutionStatus.CREATED

    started_at: datetime | None = None

    finished_at: datetime | None = None

    # ------------------------------------------------------------------
    # Hierarchy
    # ------------------------------------------------------------------

    parent: RuntimeNode | None = None

    children: list["RuntimeNode"] = field(
        default_factory=list,
    )

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    metadata: dict[str, Any] = field(
        default_factory=dict,
    )

    # ------------------------------------------------------------------
    # Tree
    # ------------------------------------------------------------------

    def add_child(
        self,
        node: RuntimeNode,
    ) -> None:
        """
        Attach a child node.
        """

        node.parent = self

        self.children.append(node)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Mark node as running.
        """

        self.status = ExecutionStatus.RUNNING

        if self.started_at is None:

            self.started_at = datetime.utcnow()

    def complete(self) -> None:
        """
        Mark node as completed.
        """

        self.status = ExecutionStatus.COMPLETED

        if self.finished_at is None:

            self.finished_at = datetime.utcnow()

    def fail(self) -> None:
        """
        Mark node as failed.
        """

        self.status = ExecutionStatus.FAILED

        if self.finished_at is None:

            self.finished_at = datetime.utcnow()

    def cancel(self) -> None:
        """
        Mark node as cancelled.
        """

        self.status = ExecutionStatus.CANCELLED

        if self.finished_at is None:

            self.finished_at = datetime.utcnow()

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def put(
        self,
        key: str,
        value: Any,
    ) -> None:

        self.metadata[key] = value

    def get(
        self,
        key: str,
        default: Any = None,
    ) -> Any:

        return self.metadata.get(
            key,
            default,
        )

    def update(
        self,
        **kwargs: Any,
    ) -> None:
        """
        Update multiple metadata values.
        """

        self.metadata.update(kwargs)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def duration_ms(self) -> int | None:
        """
        Execution duration in milliseconds.
        """

        if self.started_at is None:

            return None

        end = self.finished_at or datetime.utcnow()

        return int(
            (end - self.started_at).total_seconds() * 1000
        )

    @property
    def depth(self) -> int:
        """
        Tree depth.

        Workflow = 0
        Step     = 1
        Stage    = 2
        Activity = 3
        """

        depth = 0

        current = self.parent

        while current is not None:

            depth += 1

            current = current.parent

        return depth

    @property
    def root(self) -> RuntimeNode:
        """
        Return the root node.
        """

        current = self

        while current.parent is not None:

            current = current.parent

        return current

    @property
    def path(self) -> list["RuntimeNode"]:
        """
        Return the full hierarchy from root to current node.
        """

        nodes: list[RuntimeNode] = []

        current: RuntimeNode | None = self

        while current is not None:

            nodes.append(current)

            current = current.parent

        nodes.reverse()

        return nodes

    @property
    def is_root(self) -> bool:

        return self.parent is None

    @property
    def is_leaf(self) -> bool:

        return len(self.children) == 0

    @property
    def running(self) -> bool:

        return self.status is ExecutionStatus.RUNNING

    @property
    def completed(self) -> bool:

        return self.status is ExecutionStatus.COMPLETED

    @property
    def succeeded(self) -> bool:

        return self.status is ExecutionStatus.COMPLETED

    @property
    def failed(self) -> bool:

        return self.status is ExecutionStatus.FAILED

    @property
    def cancelled(self) -> bool:

        return self.status is ExecutionStatus.CANCELLED

    @property
    def finished(self) -> bool:

        return self.status in (
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        )

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __str__(self) -> str:

        return f"{self.type.value}: {self.name}"

    def __repr__(self) -> str:

        return (
            "RuntimeNode("
            f"type={self.type.value!r}, "
            f"name={self.name!r}, "
            f"status={self.status.value!r})"
        )
