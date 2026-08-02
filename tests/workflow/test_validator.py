import pytest

from lib.workflow.exceptions import WorkflowValidationError
from lib.workflow.validator import WorkflowValidator


def test_valid(workflow):

    WorkflowValidator().validate(workflow)


def test_empty_workflow():

    from lib.models.workflow import WorkflowDefinition

    workflow = WorkflowDefinition(
        name="",
        steps=[],
    )

    with pytest.raises(
        WorkflowValidationError,
    ):

        WorkflowValidator().validate(
            workflow,
        )
