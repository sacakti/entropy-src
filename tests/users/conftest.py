"""
Shared fixtures for user tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.context import EntropyContext
from lib.database.connection import DatabaseConnection
from lib.database.installer import DatabaseInstaller
from lib.database.repositories.users import UserRepository
from lib.users.manager import UserManager
from lib.users.password import PasswordService

class DummyEmitter:

    def debug(self, *_):
        pass

    def info(self, *_):
        pass

    def success(self, *_):
        pass

    def warning(self, *_):
        pass

    def error(self, *_):
        pass


class DummyObservability:

    def emitter(
        self,
        source: str,
    ):

        return DummyEmitter()


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

# ------------------------------------------------------------------
# Database
# ------------------------------------------------------------------


@pytest.fixture
def connection(
    tmp_path: Path,
) -> DatabaseConnection:

    connection = DatabaseConnection(
        tmp_path / "users.db",
    )

    connection.open()

    DatabaseInstaller().install(
        connection,
    )

    yield connection

    connection.close()


# ------------------------------------------------------------------
# Context
# ------------------------------------------------------------------


@pytest.fixture
def context(
    connection: DatabaseConnection,
) -> EntropyContext:

    context = EntropyContext()

    # context.diagnostics = DummyObservability()

    context.diagnostics = DummyDiagnostics()

    context.password_service = PasswordService()

    context.user_repository = UserRepository(
        connection,
    )

    context.user_manager = UserManager(
        context,
    )

    return context


# ------------------------------------------------------------------
# Services
# ------------------------------------------------------------------


@pytest.fixture
def repository(
    context: EntropyContext,
) -> UserRepository:

    assert context.user_repository is not None

    return context.user_repository


@pytest.fixture
def manager(
    context: EntropyContext,
) -> UserManager:

    assert context.user_manager is not None

    return context.user_manager


@pytest.fixture
def password_service(
    context: EntropyContext,
) -> PasswordService:

    assert context.password_service is not None

    return context.password_service
