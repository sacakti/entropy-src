"""
Workflow manager.
"""

from .executor import WorkflowExecutor
from .loader import WorkflowLoader
from .validator import WorkflowValidator


class WorkflowManager:

    def __init__(self, context):

        self.context = context

        self.loader = WorkflowLoader(context)
        self.validator = WorkflowValidator()
        self.executor = WorkflowExecutor(context)

        self.data = None

    def load(self, workflow_name: str):

        workflow = self.loader.load(workflow_name)

        self.validator.validate(workflow)

        self.data = workflow

        self.context.workflow = workflow

        return workflow

    def execute(self):

        if self.data is None:
            raise RuntimeError("Workflow not loaded.")

        self.executor.execute(self.data)
