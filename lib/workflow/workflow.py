"""
Workflow loader.
"""

from __future__ import annotations

import json
from pathlib import Path


from lib.models.workflow import WorkflowDefinition, WorkflowStep
from lib.workflow.validator import WorkflowValidator
from core.constants import WORKFLOW_DIR


class Workflow:

    def __init__(self, context):

        self.context = context

        self.data = None

    def load(self, workflow_name: str):

        workflow_file = (
            WORKFLOW_DIR
            / f"{workflow_name}.json"
        )

        task = self.context.output.progress(
            f"Loading workflow '{workflow_name}'"
        )

        if not workflow_file.exists():

            self.context.output.workflow.error(
                f"Workflow '{workflow_name}' not found",
                task=task,
            )

            raise FileNotFoundError(workflow_file)

        with workflow_file.open(
            "r",
            encoding="utf-8",
        ) as fp:

            raw = json.load(fp)

        self.context.output.workflow.success(
            f"Workflow '{workflow_name}' loaded",
            task=task,
        )

        validator = WorkflowValidator(self.context)

        validator.validate(raw)

        workflow = WorkflowDefinition(
            name=raw["name"],
            version=raw["version"],
            steps=[
                WorkflowStep(**step)
                for step in raw["steps"]
            ],
        )

        self.data = workflow

        self.context.workflow = workflow

        return workflow

    def execute(self):

        for step in sorted(
            self.data.steps,
            key=lambda step: step.order,
        ):

            if not step.enabled:
                continue

            self.context.output.step(
                step.order,
                step.name,
            )

            try:
                self.context.plugin_manager.execute(
                    step.plugin,
                    step.config,
                )

            except Exception as exc:

                self.context.output.workflow.error(str(exc))

                if step.stop_on_error:
                    raise