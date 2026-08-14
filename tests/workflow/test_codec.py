from lib.workflow.codec.structured import StructuredWorkflowCodec


def test_codec_reads_suppress_result():
    document = {
        "name": "Deploy",
        "version": "1.0",
        "variables": {
            "environment": "uat",
        },
        "steps": [
            {
                "name": "Build",
                "plugin": "custom.build",
                "arguments": {
                    "source": "${release}",
                },
                "enabled": True,
                "tags": ["build"],
                "on_failure": "continue",
                "suppress_result": True,
            },
        ],
    }

    workflow = StructuredWorkflowCodec._from_mapping(document)

    step = workflow.steps[0]

    assert workflow.name == "Deploy"
    assert workflow.variables["environment"] == "uat"
    assert step.arguments["source"] == "${release}"
    assert step.on_failure == "continue"
    assert step.suppress_result is True


def test_codec_defaults_suppress_result_to_false():
    document = {
        "name": "Deploy",
        "version": "1.0",
        "steps": [
            {
                "name": "Build",
                "plugin": "custom.build",
            },
        ],
    }

    workflow = StructuredWorkflowCodec._from_mapping(document)

    assert workflow.steps[0].suppress_result is False


def test_codec_serializes_suppress_result():
    from lib.models.workflow import Workflow, WorkflowStep

    workflow = Workflow(
        name="Deploy",
        version="1.0",
        steps=[
            WorkflowStep(
                name="Build",
                plugin="custom.build",
                suppress_result=True,
            ),
        ],
    )

    document = StructuredWorkflowCodec._to_mapping(workflow)

    assert document["steps"][0]["suppress_result"] is True


def test_codec_rejects_invalid_on_failure():
    import pytest

    from lib.workflow.exceptions import InvalidWorkflowError

    document = {
        "name": "Deploy",
        "version": "1.0",
        "steps": [
            {
                "name": "Build",
                "plugin": "custom.build",
                "on_failure": "retry",
            },
        ],
    }

    with pytest.raises(InvalidWorkflowError):
        StructuredWorkflowCodec._from_mapping(document)


def test_codec_rejects_non_boolean_suppress_result():
    import pytest

    from lib.workflow.exceptions import InvalidWorkflowError

    document = {
        "name": "Deploy",
        "version": "1.0",
        "steps": [
            {
                "name": "Build",
                "plugin": "custom.build",
                "suppress_result": "true",
            },
        ],
    }

    # This test becomes active once the codec validation for the new
    # field is implemented. Until then it documents the required contract.
    with pytest.raises(InvalidWorkflowError):
        StructuredWorkflowCodec._from_mapping(document)
