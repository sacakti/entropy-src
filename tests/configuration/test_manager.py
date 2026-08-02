from unittest.mock import Mock

from core.configuration.configuration import (
    Configuration,
)
from core.configuration.manager import (
    ConfigurationManager,
)

import pytest

from core.configuration.exceptions import (
    ConfigurationNotLoadedError,
)


def test_load(
    entropy_context,
    configuration_dict,
):

    manager = ConfigurationManager(
        entropy_context,
    )

    manager._loader = Mock()

    manager._parser = Mock()

    manager._resolver = Mock()

    manager._validator = Mock()

    manager._loader.load.return_value = "{}"

    manager._parser.read.return_value = (
        configuration_dict
    )

    manager._resolver.resolve.return_value = (
        configuration_dict
    )

    configuration = manager.load()

    assert isinstance(
        configuration,
        Configuration,
    )

    assert manager.loaded


def test_not_loaded(
    entropy_context,
):

    manager = ConfigurationManager(
        entropy_context,
    )

    with pytest.raises(
        ConfigurationNotLoadedError,
    ):

        _ = manager.configuration
