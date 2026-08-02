from lib.migrations.base import BaseMigration
from lib.migrations.executor import MigrationExecutor


class Migration001(BaseMigration):

    VERSION = 1

    DESCRIPTION = "Create table"

    def __init__(self):

        self.executed = False

    def upgrade(
        self,
        connection,
    ):

        self.executed = True


def test_execute(
    connection,
    registry,
    history,
    emitter,
):

    migration = Migration001()

    registry.register(
        migration,
    )

    executor = MigrationExecutor(
        connection=connection,
        registry=registry,
        history=history,
        emitter=emitter,
    )

    executor.execute()

    assert migration.executed

    assert history.exists(1)


def test_skip_applied(
    connection,
    registry,
    history,
    emitter,
):

    history.record(
        1,
        "Create table",
    )

    migration = Migration001()

    registry.register(
        migration,
    )

    executor = MigrationExecutor(
        connection,
        registry,
        history,
        emitter,
    )

    executor.execute()

    assert history.applied() == [1]
