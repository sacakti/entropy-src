from pathlib import Path
from unittest.mock import Mock

import pytest

from lib.database.connection import DatabaseConnection
from lib.database.installer import DatabaseInstaller
from lib.migrations.history import MigrationHistory
from lib.migrations.registry import MigrationRegistry


@pytest.fixture
def connection(tmp_path: Path):

    database = DatabaseConnection(
        tmp_path / "migration.db",
    )

    database.open()

    DatabaseInstaller().install(
        database,
    )

    yield database

    database.close()


@pytest.fixture
def history(connection):

    return MigrationHistory(
        connection,
    )


@pytest.fixture
def registry():

    return MigrationRegistry(
        package="lib.migration.scripts",
    )


@pytest.fixture
def emitter():

    return Mock()
