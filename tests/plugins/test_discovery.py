from unittest.mock import Mock, patch

from lib.plugins.discovery import PluginDiscovery
from lib.plugins.registry import PluginRegistry


def test_empty_directory(
    entropy_context,
):

    entropy_context.bootstrap.resources.plugins.exists.return_value = False

    registry = PluginRegistry()

    discovery = PluginDiscovery(
        entropy_context,
        registry,
    )

    discovery.discover()

    assert len(registry) == 0


@patch("lib.plugins.discovery.ManifestValidator.validate")
def test_discover(
    validate,
    entropy_context,
    metadata,
):

    root = Mock()

    namespace = Mock()

    namespace.is_dir.return_value = True

    namespace.name = "test"

    plugin = Mock()

    plugin.is_dir.return_value = True

    namespace.iterdir.return_value = [plugin]

    root.exists.return_value = True

    root.iterdir.return_value = [namespace]

    entropy_context.bootstrap.resources.plugins = root

    validate.return_value = metadata

    registry = PluginRegistry()

    discovery = PluginDiscovery(
        entropy_context,
        registry,
    )

    discovery.discover()

    assert registry.has("dummy")
