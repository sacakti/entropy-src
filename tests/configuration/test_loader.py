from pathlib import Path

import pytest

from core.configuration.exceptions import (
    ConfigurationFileNotFoundError,
)
from core.configuration.loader import ConfigurationLoader


def test_loader(entropy_context):

    executor = entropy_context.executor

    executor.read_text.return_value = "{}"

    loader = ConfigurationLoader(
        executor,
    )

    file = Path("entropy.json")

    executor.exists.return_value = True

    assert loader.load(file) == "{}"

    executor.read_text.assert_called_once()


def test_missing_file(entropy_context):

    executor = entropy_context.executor

    executor.exists.return_value = False

    loader = ConfigurationLoader(
        executor,
    )

    with pytest.raises(
        ConfigurationFileNotFoundError,
    ):

        loader.load(
            Path("entropy.json"),
        )
