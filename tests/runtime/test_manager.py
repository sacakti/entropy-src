from core.runtime.manager import ExecutionManager


class Workflow:

    name = "deploy_database"


def test_execution_manager(entropy_context):

    manager = ExecutionManager(entropy_context)

    execution = manager.create(Workflow())

    assert execution.id.startswith("deploy_database")

    assert execution.context.execution is execution
