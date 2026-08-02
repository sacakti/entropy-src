"""
Runtime execution tree.
"""

from __future__ import annotations

from collections.abc import Generator
from uuid import uuid4

from core.models.runtime import RuntimeNodeType

from .node import RuntimeNode
from .stack import RuntimeStack


class RuntimeTree:
    """
    Represents the runtime execution hierarchy.

        Workflow
            └── Step
                    └── Stage
                            └── Activity
    """

    def __init__(self) -> None:

        self._root: RuntimeNode | None = None

        self._stack = RuntimeStack()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def root(self) -> RuntimeNode | None:

        return self._root

    @property
    def current(self) -> RuntimeNode | None:

        return self._stack.current()

    @property
    def parent(self) -> RuntimeNode | None:

        return self._stack.parent()

    @property
    def depth(self) -> int:

        return self._stack.depth()

    @property
    def empty(self) -> bool:

        return self._stack.empty()

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------

    def enter(
        self,
        *,
        type: RuntimeNodeType,
        name: str,
        metadata: dict | None = None,
    ) -> RuntimeNode:
        """
        Enter a runtime scope.

        Creates the node, attaches it to the hierarchy and
        pushes it onto the execution stack.
        """

        node = RuntimeNode(
            id=uuid4().hex,
            type=type,
            name=name,
            metadata=metadata or {},
        )

        parent = self.current

        if parent is None:

            self._root = node

        else:

            parent.add_child(node)

        self._stack.push(node)

        return node

    def leave(self) -> RuntimeNode:
        """
        Leave the current runtime scope.

        The caller is responsible for updating the node's
        execution status.
        """

        return self._stack.pop()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def find(
        self,
        node_id: str,
    ) -> RuntimeNode | None:

        for node in self.walk():

            if node.id == node_id:

                return node

        return None

    # ------------------------------------------------------------------
    # Traversal
    # ------------------------------------------------------------------

    def walk(
        self,
    ) -> Generator[RuntimeNode, None, None]:

        if self._root is None:

            return

        yield from self._walk(self._root)

    def _walk(
        self,
        node: RuntimeNode,
    ) -> Generator[RuntimeNode, None, None]:

        yield node

        for child in node.children:

            yield from self._walk(child)

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def reset(self) -> None:

        self._root = None

        self._stack.clear()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def __len__(self) -> int:

        return sum(1 for _ in self.walk())

    def __bool__(self) -> bool:

        return self._root is not None
