"""
Workflow loader.
"""

from __future__ import annotations

import json

from core.constants import WORKFLOW_DIR
from lib.models.workflow import (
    FailurePolicy,
    WorkflowDefinition,
    WorkflowStep,
)


class WorkflowLoader:

    def __init__(self, context):

        self.context = context

    def load(self, workflow_name: str):

        workflow_file = WORKFLOW_DIR / f"{workflow_name}.json"

        if not workflow_file.exists():
            raise FileNotFoundError(workflow_file)

        with workflow_file.open(
            "r",
            encoding="utf-8",
        ) as fp:

            raw = json.load(fp)

        workflow = WorkflowDefinition(
            name=raw["name"],
            version=raw["version"],
            steps=[
                WorkflowStep(
                    order=step["order"],
                    id=step["id"],
                    name=step["name"],
                    plugin=step["plugin"],
                    enabled=step.get("enabled", True),
                    config=step.get("config", {}),
                    retry_count=step.get("retry_count", 0),
                    on_failure=FailurePolicy(
                        step.get("on_failure", "abort")
                    ),
                )
                for step in raw["steps"]
            ],
        )

        workflow.steps.sort(key=lambda s: s.order)

        return workflow