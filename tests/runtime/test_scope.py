import pytest
from lib.models.runtime import ExecutionStatus


def test_stage_scope(runtime):

    with runtime.stage(name="Validation"):

        node = runtime.node

        assert node.name == "Validation"

        assert node.status is ExecutionStatus.RUNNING

    assert node.status is ExecutionStatus.COMPLETED


def test_stage_failure(runtime):

    with pytest.raises(RuntimeError), runtime.stage(name="Validation"):

        node = runtime.node

        raise RuntimeError("boom")

    assert node.status is ExecutionStatus.FAILED
