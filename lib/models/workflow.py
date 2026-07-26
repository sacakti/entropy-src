from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkflowStep:
    order: int
    id: str
    name: str
    plugin: str
    enabled: bool
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowDefinition:
    name: str
    version: str
    steps: list[WorkflowStep] = field(default_factory=list)