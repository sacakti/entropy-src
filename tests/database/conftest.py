import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from lib.database.connection import DatabaseConnection
from lib.database.manager import DatabaseManager


@pytest.fixture
def database_file(tmp_path: Path) -> Path:
    return tmp_path / "entropy.db"


@pytest.fixture
def connection():

    database = Path(tempfile.gettempdir()) / "entropy_test.db"

    if database.exists():
        database.unlink()

    connection = DatabaseConnection(
        database,
    )

    connection.open()

    yield connection

    connection.close()

    if database.exists():
        database.unlink()


@pytest.fixture
def entropy_context(tmp_path: Path):

    context = Mock()

    context.paths = Mock()
    context.paths.database.file = tmp_path / "entropy.db"

    context.executor = Mock()

    emitter = Mock()

    context.observability = Mock()
    context.observability.emitter.return_value = emitter

    return context


@pytest.fixture
def manager(entropy_context):

    return DatabaseManager(
        entropy_context,
    )
