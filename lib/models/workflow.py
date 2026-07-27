from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FailurePolicy(Enum):
    ABORT = "abort"
    CONTINUE = "continue"
    ROLLBACK = "rollback"
    SKIP_REMAINING = "skip_remaining"


class WorkflowAction(Enum):
    CONTINUE = "continue"
    ABORT_WORKFLOW = "abort_workflow"


@dataclass
class WorkflowStep:
    order: int
    id: str
    name: str
    plugin: str

    enabled: bool = True

    config: dict[str, Any] = field(default_factory=dict)

    retry_count: int = 0

    on_failure: FailurePolicy = FailurePolicy.ABORT


@dataclass
class WorkflowDefinition:
    name: str
    version: str
    steps: list[WorkflowStep] = field(default_factory=list)