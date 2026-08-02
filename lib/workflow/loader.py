"""
Workflow loader.
"""

from __future__ import annotations

from typing import Any

from lib.models.workflow import (
    FailurePolicy,
    WorkflowPolicy,
    WorkflowDefinition,
    WorkflowStep
)

class WorkflowLoader:
    """
    Maps workflow documents to WorkflowDefinition.
    """

    def load(
        self,
        document: dict[str, Any],
    ) -> WorkflowDefinition:
        """
        Load a workflow definition.
        """

        steps = [
            self._step(step)
            for step in document.get(
                "steps",
                [],
            )
        ]

        return WorkflowDefinition(
            name=document.get(
                "name",
                "",
            ),
            version=document.get(
                "version",
                "1.0",
            ),
            description=document.get(
                "description",
                "",
            ),
            steps=steps,
        )

    # ------------------------------------------------------------------

    def _step(
        self,
        document: dict[str, Any],
    ) -> WorkflowStep:

        policy = WorkflowPolicy(
            enabled=document.get(
                "enabled",
                True,
            ),
            retries=document.get(
                "retry_count",
                0,
            ),
            on_failure=FailurePolicy(
                document.get(
                    "on_failure",
                    FailurePolicy.ABORT.value,
                ),
            ),
            timeout=document.get(
                "timeout",
            ),
        )

        return WorkflowStep(
            id=document["id"],
            order=document["order"],
            name=document["name"],
            plugin=document["plugin"],
            configuration=document.get(
                "config",
                {},
            ),
            policy=policy,
        )
