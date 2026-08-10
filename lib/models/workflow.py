from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Workflow:
    """
    Workflow definition.
    """

    name: str

    version: str

    description: str | None = None

    variables: dict[
        str,
        object,
    ] = field(
        default_factory=dict,
    )

    steps: list[WorkflowStep] = field(
        default_factory=list,
    )

    @property
    def step_count(
        self,
    ) -> int:

        return len(
            self.steps,
        )


@dataclass(frozen=True)
class WorkflowStep:
    """
    Workflow step.
    """

    name: str

    plugin: str

    arguments: dict[
        str,
        object,
    ] = field(
        default_factory=dict,
    )

    enabled: bool = True

    continue_on_error: bool = False

    @property
    def qualified_plugin(
        self,
    ) -> str:

        return self.plugin
