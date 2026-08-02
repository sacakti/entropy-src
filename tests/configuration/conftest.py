"""
Configuration test fixtures.
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from core.context import EntropyContext
from core.configuration import ConfigurationManager


@pytest.fixture
def entropy_context(tmp_path: Path):

    context = Mock(spec=EntropyContext)

    #
    # Executor
    #

    executor = Mock()

    context.executor = executor

    #
    # Bootstrap
    #

    bootstrap = Mock()

    bootstrap.configuration.file = (
        tmp_path / "entropy.json"
    )

    context.bootstrap = bootstrap

    return context


@pytest.fixture
def configuration_dict():

    return {
        "application": {
            "name": "Entropy",
            "version": "1.0.0",
        },
        "console": {},
        "logging": {
            "directory": "./logs",
        },
        "database": {
            "path": "./database.db",
        },
        "runtime": {
            "directory": "./runtime",
        },
        "session": {
            "directory": "./session",
        },
        "python": {
            "packages": "./site-packages",
        },
        "workflow": {
            "default": "./workflow/default.json",
        },
        "git": {
            "repository": "./repository",
        },
        "plugins": {
            "directory": "./plugins",
        },
    }
