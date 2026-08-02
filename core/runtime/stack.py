"""
Runtime execution stack.
"""

from __future__ import annotations

from .node import RuntimeNode


class RuntimeStack:
    """
    Maintains the current runtime execution hierarchy.

    Example

        Workflow
            └── Step
                    └── Stage
                            └── Activity

    The stack always represents the current execution path.
    """

    def __init__(self) -> None:

        self._stack: list[RuntimeNode] = []

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def push(
        self,
        node: RuntimeNode,
    ) -> None:
        """
        Push a node onto the execution stack.
        """

        self._stack.append(node)

    def pop(self) -> RuntimeNode:
        """
        Remove the current node.

        Raises
        ------
        RuntimeError
            If the stack is empty.
        """

        if not self._stack:

            raise RuntimeError("Runtime stack is empty.")

        return self._stack.pop()

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def current(self) -> RuntimeNode | None:
        """
        Return the current runtime node.
        """

        if not self._stack:

            return None

        return self._stack[-1]

    def parent(self) -> RuntimeNode | None:
        """
        Return the parent of the current node.
        """

        if len(self._stack) < 2:

            return None

        return self._stack[-2]

    def root(self) -> RuntimeNode | None:
        """
        Return the root node.
        """

        if not self._stack:

            return None

        return self._stack[0]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def depth(self) -> int:
        """
        Current execution depth.

        Root node depth is zero.
        """

        return max(
            len(self._stack) - 1,
            0,
        )

    def empty(self) -> bool:
        """
        Return True if the stack is empty.
        """

        return not self._stack

    def clear(self) -> None:
        """
        Remove all nodes.
        """

        self._stack.clear()

    # ------------------------------------------------------------------
    # Iteration
    # ------------------------------------------------------------------

    def __iter__(self):

        return iter(self._stack)

    def __len__(self) -> int:

        return len(self._stack)

    def __bool__(self) -> bool:

        return bool(self._stack)

    # ------------------------------------------------------------------
    # Debug
    # ------------------------------------------------------------------

    def __repr__(self) -> str:

        names = " -> ".join(node.name for node in self._stack)

        return f"RuntimeStack({names})"
