"""
Shared fixtures for authentication tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.context import EntropyContext
from core.observability import ObservabilityManager
from lib.auth.manager import SessionManager
from lib.auth.service import AuthenticationService
from lib.database.connection import DatabaseConnection
from lib.database.installer import DatabaseInstaller
from lib.database.repositories.users import UserRepository
from lib.executor.linux import LinuxExecutor
from lib.users.manager import UserManager
from lib.users.password import PasswordService

class DummyLogger:

    def debug(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass

    def success(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


class DummyDiagnostics:

    def logger(
        self,
        source: str,
    ):

        return DummyLogger()

class DummyConfiguration:

    def get(
        self,
        key: str,
        default=None,
    ):

        values = {
            "auth.session.timeout": 8,
        }

        return values.get(
            key,
            default,
        )

@pytest.fixture
def connection(
    tmp_path: Path,
) -> DatabaseConnection:

    connection = DatabaseConnection(
        tmp_path / "auth.db",
    )

    connection.open()

    DatabaseInstaller().install(
        connection,
    )

    yield connection

    connection.close()


@pytest.fixture
def context(
    tmp_path: Path,
    connection: DatabaseConnection,
) -> EntropyContext:

    context = EntropyContext()

    #
    # Runtime paths
    #

    session_dir = tmp_path / "session"

    session_dir.mkdir()

    class SessionPaths:

        directory = session_dir

        current = session_dir / "current.json"

    class Paths:

        session = SessionPaths()

    context.paths = Paths()

    #
    # Services
    #
    context.configuration = DummyConfiguration()

    context.executor = LinuxExecutor()

    context.diagnostics = DummyDiagnostics()

    context.password_service = PasswordService()

    context.user_repository = UserRepository(
        connection,
    )

    context.user_manager = UserManager(
        context,
    )

    context.authentication = AuthenticationService(
        context,
    )

    context.session_manager = SessionManager(
        context,
    )

    return context


@pytest.fixture
def authentication(
    context: EntropyContext,
) -> AuthenticationService:

    assert context.authentication is not None

    return context.authentication


@pytest.fixture
def session_manager(
    context: EntropyContext,
) -> SessionManager:

    assert context.session_manager is not None

    return context.session_manager


@pytest.fixture
def user_manager(
    context: EntropyContext,
) -> UserManager:

    assert context.user_manager is not None

    return context.user_manager
