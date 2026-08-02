from __future__ import annotations
from enum import Enum
from typing import Any
from dataclasses import dataclass, field


from enum import Enum


class FailurePolicy(str, Enum):
    """
    Action to take when a workflow step fails.
    """

    ABORT = "abort"
    CONTINUE = "continue"
    RETRY = "retry"

# class WorkflowAction(Enum):
#     CONTINUE = "continue"
#     ABORT_WORKFLOW = "abort_workflow"

"""
Workflow execution policy.
"""

@dataclass(frozen=True)
class WorkflowPolicy:

    enabled: bool = True

    retries: int = 0

    on_failure: FailurePolicy = (
        FailurePolicy.ABORT
    )

    timeout: int | None = None

"""
Workflow step.
"""

@dataclass(frozen=True)
class WorkflowStep:
    """
    Immutable workflow step.
    """

    #
    # Identity
    #

    id: str

    order: int

    name: str

    #
    # Plugin
    #

    plugin: str

    #
    # Configuration
    #

    configuration: dict[str, Any] = field(
        default_factory=dict,
    )

    #
    # Execution
    #

    policy: WorkflowPolicy = field(
        default_factory=WorkflowPolicy,
    )


"""
Workflow definition.
"""

@dataclass(frozen=True)
class WorkflowDefinition:
    """
    Immutable workflow definition.
    """

    #
    # Identity
    #

    name: str

    version: str = "1.0"

    description: str = ""

    #
    # Steps
    #

    steps: list[WorkflowStep] = field(
        default_factory=list,
    )

    # ------------------------------------------------------------------

    def __len__(
        self,
    ) -> int:

        return len(
            self.steps,
        )

    def __iter__(
        self,
    ):

        return iter(
            self.steps,
        )

    def __getitem__(
        self,
        index: int,
    ) -> WorkflowStep:

        return self.steps[index]
