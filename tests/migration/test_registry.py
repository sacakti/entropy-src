from lib.migrations.base import BaseMigration


class Migration001(BaseMigration):

    VERSION = 1
    DESCRIPTION = "Test"

    def upgrade(
        self,
        connection,
    ):
        pass


def test_register(registry):

    migration = Migration001()

    registry.register(
        migration,
    )

    assert registry.has(1)


def test_get(registry):

    migration = Migration001()

    registry.register(
        migration,
    )

    assert registry.get(1) is migration


def test_list(registry):

    registry.register(
        Migration001(),
    )

    assert len(registry.list()) == 1


def test_clear(registry):

    registry.register(
        Migration001(),
    )

    registry.clear()

    assert registry.list() == []
