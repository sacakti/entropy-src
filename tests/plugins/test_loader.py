from types import ModuleType
from unittest.mock import patch

import pytest

from lib.plugins.exceptions import (
    PluginNotFoundError,
)
from lib.plugins.loader import PluginLoader
from lib.plugins.registry import PluginRegistry


def test_load(
    entropy_context,
    metadata,
    plugin,
):

    registry = PluginRegistry()

    registry.register(metadata)

    module = ModuleType("plugin")

    module.PLUGIN_CLASS = "DummyPlugin"

    module.DummyPlugin = plugin.__class__

    with patch(
        "importlib.import_module",
        return_value=module,
    ):

        loader = PluginLoader(
            entropy_context,
            registry,
        )

        instance = loader.load("dummy")

        assert isinstance(
            instance,
            plugin.__class__,
        )


def test_cached_load(
    entropy_context,
    metadata,
    plugin,
):

    registry = PluginRegistry()

    registry.register(metadata)

    module = ModuleType("plugin")

    module.PLUGIN_CLASS = "DummyPlugin"

    module.DummyPlugin = plugin.__class__

    with patch(
        "importlib.import_module",
        return_value=module,
    ):

        loader = PluginLoader(
            entropy_context,
            registry,
        )

        first = loader.load("dummy")

        second = loader.load("dummy")

        assert first is second


def test_missing_module(
    entropy_context,
    metadata,
):

    registry = PluginRegistry()

    registry.register(metadata)

    with patch(
        "importlib.import_module",
        side_effect=ModuleNotFoundError,
    ):

        loader = PluginLoader(
            entropy_context,
            registry,
        )

        with pytest.raises(
            PluginNotFoundError,
        ):

            loader.load("dummy")
