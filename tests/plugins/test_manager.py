from unittest.mock import patch

from lib.plugins.manager import PluginManager


def test_manager_creation(
    entropy_context,
):

    manager = PluginManager(
        entropy_context,
    )

    assert manager is not None


@patch(
    "lib.plugins.discovery.PluginDiscovery.discover"
)
def test_discover(
    discover,
    entropy_context,
):

    manager = PluginManager(
        entropy_context,
    )

    manager.discover()

    discover.assert_called_once()
