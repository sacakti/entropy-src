"""
Workflow execution context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.context import EntropyContext

from lib.models.workflow import (
    Workflow,
    WorkflowStep,
)


@dataclass
class ExecutionContext:
    """
    Runtime workflow execution context.
    """

    #
    # Application
    #

    context: EntropyContext

    #
    # Workflow
    #

    workflow: Workflow

    step: WorkflowStep

    #
    # Runtime
    #

    variables: dict[
        str,
        Any,
    ] = field(
        default_factory=dict,
    )

    arguments: dict[
        str,
        Any,
    ] = field(
        default_factory=dict,
    )
