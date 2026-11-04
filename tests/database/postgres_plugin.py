"""
Run other test suites against PostgreSQL: every DatabaseConnection a test opens
gets a schema of its own on a real server.

    ENTROPY_TEST_POSTGRES_URL=postgresql://user:password@host:5432/database \
        python -m pytest -p tests.database.postgres_plugin tests/<area>

Tests that open SQLite files directly, or check SQLite itself, are expected to fail.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

import lib.database.connection as connection_module
from lib.database.postgres import PostgresConnection

_URL = urlsplit(os.environ["ENTROPY_TEST_POSTGRES_URL"])
_SCHEMAS = set()


class TestServerConnection(PostgresConnection):
    __test__ = False

    def __init__(self, database: Path) -> None:
        schema = "t_" + hashlib.sha256(str(database).encode()).hexdigest()[:24]
        super().__init__(
            {
                "host": _URL.hostname,
                "port": _URL.port or 5432,
                "database": _URL.path.lstrip("/"),
                "schema": schema,
                "username": unquote(_URL.username or ""),
                "password": unquote(_URL.password or ""),
            },
            Path(database),
        )
        _SCHEMAS.add(schema)
        self.ensure_schema()


connection_module.DatabaseConnection = TestServerConnection


def pytest_sessionfinish(session, exitstatus) -> None:
    if not _SCHEMAS:
        return
    cleaner = PostgresConnection(
        {
            "host": _URL.hostname,
            "port": _URL.port or 5432,
            "database": _URL.path.lstrip("/"),
            "username": unquote(_URL.username or ""),
            "password": unquote(_URL.password or ""),
        },
        Path("unused"),
    )
    for schema in _SCHEMAS:
        cleaner.raw_execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    cleaner.close()
