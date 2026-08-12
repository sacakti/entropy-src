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

    # continue_on_error: bool = False

    tags: list[str] = field(
        default_factory=list,
    )

    on_failure: str = "abort"

    @property
    def qualified_plugin(
        self,
    ) -> str:

        return self.plugin

@dataclass(frozen=True)
class WorkflowEditResult:
    """
    Result of editing a registered workflow.
    """

    workflow: Workflow
    changed: bool

@dataclass(frozen=True)
class WorkflowExecutionOptions:
    """
    Options controlling workflow execution.
    """

    tags: tuple[str, ...] = ()
    from_step: str | None = None
    to_step: str | None = None
    dry_run: bool = False

@dataclass
class WorkflowDryRunResult:
    """
    Result of workflow dry-run validation.
    """

    errors: list[str] = field(
        default_factory=list,
    )

    @property
    def valid(self) -> bool:
        """
        Return whether the dry-run passed validation.
        """

        return not self.errors

    def add_error(
        self,
        message: str,
    ) -> None:
        """
        Add a validation error.
        """

        self.errors.append(
            message,
        )
