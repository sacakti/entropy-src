from pathlib import Path
from types import SimpleNamespace

import pytest

from lib.auth.manager import SessionManager
from lib.database.connection import DatabaseConnection
from lib.database.executor import MigrationExecutor
from lib.database.registry import MigrationRegistry
from lib.database.repositories.users import UserRepository
from lib.executor.linux import LinuxExecutor
from lib.users.manager import UserManager
from lib.users.password import PasswordService


class DummyLogger:

    def __getattr__(self, _):
        return lambda *args, **kwargs: None


class DummyOutput:

    def __init__(self):
        self.user = DummyLogger()
        self.auth = DummyLogger()
        self.database = DummyLogger()
        self.system = DummyLogger()

    def __getattr__(self, _):
        return lambda *args, **kwargs: None


class DummyContext:

    def __init__(self):
        self.output = DummyOutput()


@pytest.fixture
def database(tmp_path: Path) -> DatabaseConnection:

    db = DatabaseConnection(tmp_path / "entropy.db")

    registry = MigrationRegistry()
    registry.discover()

    executor = MigrationExecutor(
        db,
        registry,
        DummyContext(),
    )

    executor.execute()

    yield db

    db.close()


@pytest.fixture
def repository(database: DatabaseConnection) -> UserRepository:

    return UserRepository(database)


@pytest.fixture
def context(repository):

    output = DummyOutput()

    return SimpleNamespace(
        user_repository=repository,
        password_service=PasswordService(),
        output=output,
    )


@pytest.fixture
def manager(context) -> UserManager:

    return UserManager(context)


@pytest.fixture
def executor():

    return LinuxExecutor()


@pytest.fixture
def session_context(manager, executor):

    output = DummyOutput()

    return SimpleNamespace(
        user_manager=manager,
        executor=executor,
        output=output,
    )


@pytest.fixture
def session_manager(session_context, tmp_path):

    return SessionManager(
        session_context,
        session_file=tmp_path / "session.json",
        session_directory=tmp_path,
    )
