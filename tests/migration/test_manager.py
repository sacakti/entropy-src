from unittest.mock import Mock

from lib.migrations.manager import MigrationManager


def test_discover():

    context = Mock()

    context.database_manager.connection = Mock()

    context.observability.emitter.return_value = Mock()

    manager = MigrationManager(
        context,
        package="lib.migration.scripts",
    )

    manager._registry.discover = Mock()

    manager.discover()

    manager._registry.discover.assert_called_once()


def test_migrate():

    context = Mock()

    context.database_manager.connection = Mock()

    context.observability.emitter.return_value = Mock()

    manager = MigrationManager(
        context,
        package="lib.migration.scripts",
    )

    manager.discover = Mock()

    manager._executor.execute = Mock()

    manager.migrate()

    manager.discover.assert_called_once()

    manager._executor.execute.assert_called_once()
