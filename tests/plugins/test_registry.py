import pytest

from lib.plugins.exceptions import (
    PluginAlreadyRegisteredError,
    PluginNotFoundError,
)
from lib.plugins.registry import PluginRegistry


def test_register(metadata):

    registry = PluginRegistry()

    registry.register(metadata)

    assert registry.has("dummy")


def test_resolve(metadata):

    registry = PluginRegistry()

    registry.register(metadata)

    assert registry.resolve("dummy") is metadata


def test_get(metadata):

    registry = PluginRegistry()

    registry.register(metadata)

    assert registry.get("dummy") is metadata


def test_clear(metadata):

    registry = PluginRegistry()

    registry.register(metadata)

    registry.clear()

    assert len(registry) == 0


def test_duplicate_registration(metadata):

    registry = PluginRegistry()

    registry.register(metadata)

    with pytest.raises(
        PluginAlreadyRegisteredError,
    ):

        registry.register(metadata)


def test_unknown_plugin():

    registry = PluginRegistry()

    with pytest.raises(
        PluginNotFoundError,
    ):

        registry.resolve("unknown")
